"""
Email Service — Instantly-style cold email engine.

Responsibilities:
  - Google OAuth flow for connecting Gmail / Workspace mailboxes
  - Sending email via the Gmail API (with proper Message-ID, In-Reply-To, References, List-Unsubscribe)
  - Inbox rotation across multiple connected accounts with per-inbox daily caps + jitter
  - Reply polling via the Gmail History API (no Pub/Sub required)
  - Tracking pixel + link rewriting for open/click telemetry
  - Global unsubscribe enforcement

Token storage: refresh_token persists; access_token is minted on demand and cached
on the EmailAccount row until token_expires_at.
"""
from __future__ import annotations

import base64
import json
import logging
import random
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, or_

from config import Config
from database import (
    get_db_session, get_session,
    EmailAccount, EmailAccountStatus,
    EmailCampaign, EmailCampaignMessage, EmailEnrollment, EmailSend,
    EmailEvent, EmailUnsubscribe, EmailReply,
    CampaignStatus, EnrollmentStatus,
)

logger = logging.getLogger(__name__)


GOOGLE_OAUTH_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_OAUTH_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GMAIL_API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'
GMAIL_SCOPES = [
    'openid',
    'email',
    'profile',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',     # to read replies, label, etc.
    'https://www.googleapis.com/auth/gmail.readonly',   # for history poll
]


# =============================================================================
# OAUTH
# =============================================================================

def build_oauth_url(state: str) -> str:
    """Build the Google OAuth consent URL."""
    if not Config.GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID not configured")
    params = {
        'client_id': Config.GOOGLE_CLIENT_ID,
        'redirect_uri': Config.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(GMAIL_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',       # forces refresh_token issuance every time
        'state': state,
        'include_granted_scopes': 'true',
    }
    return f"{GOOGLE_OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict:
    """Trade an OAuth authorization code for an access + refresh token."""
    resp = requests.post(GOOGLE_OAUTH_TOKEN_URL, data={
        'code': code,
        'client_id': Config.GOOGLE_CLIENT_ID,
        'client_secret': Config.GOOGLE_CLIENT_SECRET,
        'redirect_uri': Config.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Mint a new access token from a refresh token."""
    resp = requests.post(GOOGLE_OAUTH_TOKEN_URL, data={
        'refresh_token': refresh_token,
        'client_id': Config.GOOGLE_CLIENT_ID,
        'client_secret': Config.GOOGLE_CLIENT_SECRET,
        'grant_type': 'refresh_token',
    }, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text}")
    return resp.json()


def get_user_email(access_token: str) -> Tuple[str, str]:
    """Look up the authenticated Google user's email + display name."""
    resp = requests.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(f"userinfo failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return data.get('email'), data.get('name')


def connect_account_from_code(code: str) -> dict:
    """OAuth callback handler — persists/updates the connected mailbox."""
    tokens = exchange_code_for_tokens(code)
    access_token = tokens['access_token']
    refresh_token = tokens.get('refresh_token')
    expires_in = tokens.get('expires_in', 3500)

    email, name = get_user_email(access_token)
    if not email:
        raise RuntimeError("Could not determine connected account email")

    with get_db_session() as session:
        account = session.query(EmailAccount).filter(EmailAccount.email == email).first()
        if not account:
            account = EmailAccount(email=email, provider='gmail')
            session.add(account)

        account.display_name = name or account.display_name or email.split('@')[0]
        account.access_token = access_token
        if refresh_token:
            account.refresh_token = refresh_token
        account.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in) - 60)
        account.scopes = ' '.join(GMAIL_SCOPES)
        account.status = EmailAccountStatus.ACTIVE.value
        account.last_error = None
        session.flush()
        return account.to_dict()


def ensure_access_token(account: EmailAccount, session) -> str:
    """Return a valid access token for this account, refreshing if needed."""
    now = datetime.utcnow()
    if account.access_token and account.token_expires_at and account.token_expires_at > now + timedelta(seconds=30):
        return account.access_token

    if not account.refresh_token:
        raise RuntimeError(f"Account {account.email} has no refresh token — reconnect required")

    tokens = refresh_access_token(account.refresh_token)
    account.access_token = tokens['access_token']
    expires_in = tokens.get('expires_in', 3500)
    account.token_expires_at = now + timedelta(seconds=int(expires_in) - 60)
    session.flush()
    return account.access_token


# =============================================================================
# SEND PIPELINE
# =============================================================================

def is_unsubscribed(email: str) -> bool:
    """Check the global suppression list."""
    session = get_session()
    try:
        return session.query(EmailUnsubscribe).filter(EmailUnsubscribe.email == email.lower()).first() is not None
    finally:
        session.close()


def add_unsubscribe(email: str, reason: str = 'manual', campaign_id: Optional[int] = None):
    """Add to global suppression list (idempotent)."""
    with get_db_session() as session:
        existing = session.query(EmailUnsubscribe).filter(EmailUnsubscribe.email == email.lower()).first()
        if existing:
            return existing
        unsub = EmailUnsubscribe(email=email.lower(), reason=reason, source_campaign_id=campaign_id)
        session.add(unsub)
        session.flush()
        return unsub


def _reset_daily_counter_if_needed(account: EmailAccount):
    today = datetime.utcnow().strftime('%Y-%m-%d')
    if account.sends_today_date != today:
        account.sends_today = 0
        account.sends_today_date = today


def pick_sending_account(campaign: EmailCampaign, session) -> Optional[EmailAccount]:
    """
    Pick the next sending mailbox for this campaign based on rotation strategy.
    Respects per-inbox daily caps; returns None if all are tapped out.
    """
    if not campaign.sending_account_ids:
        # Fall back to any active account
        accounts = session.query(EmailAccount).filter(
            EmailAccount.status == EmailAccountStatus.ACTIVE.value
        ).all()
    else:
        ids = json.loads(campaign.sending_account_ids)
        accounts = session.query(EmailAccount).filter(
            EmailAccount.id.in_(ids),
            EmailAccount.status == EmailAccountStatus.ACTIVE.value
        ).all()

    if not accounts:
        return None

    # Reset counters & filter by remaining capacity
    eligible = []
    for a in accounts:
        _reset_daily_counter_if_needed(a)
        if a.sends_today < a.daily_cap:
            eligible.append(a)

    if not eligible:
        return None

    if campaign.rotation_strategy == 'least_used':
        return min(eligible, key=lambda a: a.sends_today)

    # Round-robin: pick the one that sent the longest ago
    eligible.sort(key=lambda a: a.last_send_at or datetime(1970, 1, 1))
    return eligible[0]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _add_tracking_to_html(html: str, send_token: str, track_opens: bool, track_clicks: bool, unsubscribe_url: str) -> str:
    """Add open pixel, rewrite links for click tracking, and inject unsubscribe footer."""
    base = Config.PUBLIC_BASE_URL.rstrip('/')

    if track_clicks:
        # Rewrite href="..." to go through our redirect — only http/https links, skip mailto/tel
        import re
        def rewrite(match):
            url = match.group(2)
            if url.startswith(('mailto:', 'tel:', '#', 'javascript:')):
                return match.group(0)
            wrapped = f"{base}/api/email/track/click/{send_token}?u={urllib.parse.quote(url, safe='')}"
            return f'{match.group(1)}{wrapped}{match.group(3)}'
        html = re.sub(r'(href=["\'])([^"\']+)(["\'])', rewrite, html, flags=re.IGNORECASE)

    # Unsubscribe footer — always include (Gmail/Yahoo require easy opt-out)
    footer = (
        f'<div style="margin-top:24px;padding-top:12px;border-top:1px solid #eee;'
        f'font-size:11px;color:#888;font-family:Arial,sans-serif">'
        f'<a href="{unsubscribe_url}" style="color:#888">Unsubscribe</a>'
        f'</div>'
    )
    if '</body>' in html.lower():
        import re
        html = re.sub(r'</body>', f'{footer}</body>', html, count=1, flags=re.IGNORECASE)
    else:
        html = f'{html}{footer}'

    if track_opens:
        pixel = f'<img src="{base}/api/email/track/open/{send_token}.gif" width="1" height="1" border="0" style="display:block" alt="" />'
        html = f'{html}{pixel}'

    return html


def _html_to_text(html: str) -> str:
    """Cheap HTML -> plain text fallback."""
    import re
    text = re.sub(r'<style.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def render_personalization(template: str, enrollment: EmailEnrollment) -> str:
    """
    Replace {variables} in subject or body. Supports:
      {name}, {first_name}, {company}, {email},
      {ai_first_line}, plus anything in enrollment.extra_data (JSON).
    """
    if not template:
        return ''
    result = template
    extra = {}
    if enrollment.extra_data:
        try:
            extra = json.loads(enrollment.extra_data)
        except Exception:
            extra = {}

    full_name = enrollment.name or ''
    first = full_name.split(' ', 1)[0] if full_name else ''

    variables = {
        'name': full_name,
        'first_name': first,
        'company': enrollment.company or '',
        'email': enrollment.email or '',
        'ai_first_line': enrollment.ai_first_line or '',
        **{k: ('' if v is None else str(v)) for k, v in extra.items()},
    }

    import re
    def replace(m):
        key = m.group(1).strip().lower()
        return variables.get(key, m.group(0))
    result = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', replace, result)

    # Spintax: {spin:a|b|c}
    def spin(m):
        return random.choice(m.group(1).split('|'))
    result = re.sub(r'\{spin:([^{}]+)\}', spin, result)

    # Collapse runs of whitespace introduced by empty vars
    result = re.sub(r' +', ' ', result).strip()
    return result


def send_email_via_gmail(
    *,
    account: EmailAccount,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    list_unsubscribe_url: Optional[str] = None,
    list_unsubscribe_mailto: Optional[str] = None,
    session=None,
) -> dict:
    """
    Send a raw email via the Gmail API.
    Returns dict: {success, gmail_message_id, gmail_thread_id, message_id_header, error}
    """
    own_session = session is None
    if own_session:
        session = get_session()
    try:
        access_token = ensure_access_token(account, session)

        msg = EmailMessage()
        msg['From'] = f'{account.display_name} <{account.email}>' if account.display_name else account.email
        msg['To'] = to_email
        msg['Subject'] = subject

        message_id_header = make_msgid(domain=account.email.split('@')[-1])
        msg['Message-ID'] = message_id_header

        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
        if references:
            msg['References'] = references
        if list_unsubscribe_url or list_unsubscribe_mailto:
            parts = []
            if list_unsubscribe_mailto:
                parts.append(f'<mailto:{list_unsubscribe_mailto}>')
            if list_unsubscribe_url:
                parts.append(f'<{list_unsubscribe_url}>')
            msg['List-Unsubscribe'] = ', '.join(parts)
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

        msg.set_content(text_body or _html_to_text(html_body))
        msg.add_alternative(html_body, subtype='html')

        raw = _b64url(msg.as_bytes())
        payload = {'raw': raw}
        if thread_id:
            payload['threadId'] = thread_id

        resp = requests.post(
            f'{GMAIL_API_BASE}/messages/send',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            json=payload,
            timeout=30,
        )

        if not resp.ok:
            error = f"{resp.status_code}: {resp.text[:500]}"
            logger.error(f"Gmail send failed for {account.email} -> {to_email}: {error}")
            account.last_error = error
            if resp.status_code in (401, 403):
                account.status = EmailAccountStatus.ERROR.value
            session.flush()
            if own_session:
                session.commit()
            return {'success': False, 'error': error}

        data = resp.json()
        # Bump counters
        _reset_daily_counter_if_needed(account)
        account.sends_today = (account.sends_today or 0) + 1
        account.last_send_at = datetime.utcnow()
        account.last_error = None
        session.flush()
        if own_session:
            session.commit()

        return {
            'success': True,
            'gmail_message_id': data.get('id'),
            'gmail_thread_id': data.get('threadId'),
            'message_id_header': message_id_header,
        }
    except Exception as e:
        logger.error(f"send_email_via_gmail exception: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        if own_session:
            session.close()


def build_unsubscribe_url(enrollment: EmailEnrollment) -> str:
    if not enrollment.unsubscribe_token:
        enrollment.unsubscribe_token = secrets.token_urlsafe(32)
    base = Config.PUBLIC_BASE_URL.rstrip('/')
    return f'{base}/api/email/unsubscribe/{enrollment.unsubscribe_token}'


def send_campaign_step(send_id: int) -> dict:
    """
    Send a single queued EmailSend row. Called by the scheduler.
    Assumes the EmailSend was already created with status='pending'.
    """
    session = get_session()
    try:
        send = session.query(EmailSend).filter(EmailSend.id == send_id).first()
        if not send or send.status != 'pending':
            return {'success': False, 'error': 'send not found or not pending'}

        enrollment = session.query(EmailEnrollment).filter(EmailEnrollment.id == send.enrollment_id).first()
        campaign = session.query(EmailCampaign).filter(EmailCampaign.id == send.campaign_id).first()
        message = session.query(EmailCampaignMessage).filter(EmailCampaignMessage.id == send.message_id).first()

        if not enrollment or not campaign or not message:
            send.status = 'failed'
            send.error_message = 'missing related records'
            session.commit()
            return {'success': False, 'error': 'missing related records'}

        if is_unsubscribed(enrollment.email):
            send.status = 'failed'
            send.error_message = 'recipient unsubscribed'
            enrollment.status = 'unsubscribed'
            enrollment.unsubscribed_at = datetime.utcnow()
            session.commit()
            return {'success': False, 'error': 'unsubscribed'}

        # Pick account
        account_id = send.account_id
        if account_id:
            account = session.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        else:
            account = pick_sending_account(campaign, session)

        if not account:
            # All caps used — leave pending for next run
            return {'success': False, 'error': 'no sending account available (daily cap?)'}

        # Refresh send row with chosen account
        send.account_id = account.id
        send.from_email = account.email

        # Threading for follow-ups
        thread_id = enrollment.gmail_thread_id if message.same_thread and message.sequence_order > 1 else None
        in_reply_to = enrollment.gmail_message_id_header if message.same_thread and message.sequence_order > 1 else None
        references = enrollment.gmail_message_id_header if message.same_thread and message.sequence_order > 1 else None

        unsub_url = build_unsubscribe_url(enrollment)
        session.flush()

        # Final body with tracking
        tracked_html = _add_tracking_to_html(
            send.body_html,
            send_token=str(send.id),
            track_opens=campaign.track_opens,
            track_clicks=campaign.track_clicks,
            unsubscribe_url=unsub_url,
        )

        result = send_email_via_gmail(
            account=account,
            to_email=send.to_email,
            subject=send.subject,
            html_body=tracked_html,
            text_body=send.body_text,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            list_unsubscribe_url=unsub_url,
            list_unsubscribe_mailto=account.email,
            session=session,
        )

        if result.get('success'):
            send.status = 'sent'
            send.sent_at = datetime.utcnow()
            send.gmail_message_id = result.get('gmail_message_id')
            send.gmail_thread_id = result.get('gmail_thread_id')
            send.message_id_header = result.get('message_id_header')

            # Track threading on enrollment so follow-ups stay in-thread
            if not enrollment.gmail_thread_id:
                enrollment.gmail_thread_id = result.get('gmail_thread_id')
                enrollment.gmail_message_id_header = result.get('message_id_header')

            enrollment.current_step = message.sequence_order
            enrollment.last_sent_at = datetime.utcnow()
            session.commit()
            return {'success': True}
        else:
            send.status = 'failed'
            send.error_message = result.get('error')
            session.commit()
            return result
    except Exception as e:
        logger.exception("send_campaign_step error")
        session.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        session.close()


# =============================================================================
# REPLY DETECTION (Gmail History API polling)
# =============================================================================

def poll_replies_for_account(account_id: int) -> int:
    """
    Fetch new inbound messages for one account since its stored history_id.
    Matches them to active enrollments by sender email + thread; records EmailReply
    and stops the sequence (sets enrollment.first_reply_at).
    Returns count of new replies recorded.
    """
    session = get_session()
    new_count = 0
    try:
        account = session.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account or account.status != EmailAccountStatus.ACTIVE.value:
            return 0

        access_token = ensure_access_token(account, session)
        headers = {'Authorization': f'Bearer {access_token}'}

        # Bootstrap history_id if missing
        if not account.history_id:
            profile = requests.get(f'{GMAIL_API_BASE}/profile', headers=headers, timeout=15)
            if profile.ok:
                account.history_id = str(profile.json().get('historyId'))
                account.last_polled_at = datetime.utcnow()
                session.commit()
            return 0

        # Get new history entries
        url = f'{GMAIL_API_BASE}/history?startHistoryId={account.history_id}&historyTypes=messageAdded'
        resp = requests.get(url, headers=headers, timeout=20)
        if not resp.ok:
            if resp.status_code == 404:
                # History expired (>7 days old) — reset
                profile = requests.get(f'{GMAIL_API_BASE}/profile', headers=headers, timeout=15)
                if profile.ok:
                    account.history_id = str(profile.json().get('historyId'))
                    session.commit()
            return 0

        history_data = resp.json()
        latest_history_id = history_data.get('historyId') or account.history_id

        new_message_ids = []
        for record in history_data.get('history', []):
            for ma in record.get('messagesAdded', []):
                m = ma.get('message') or {}
                if 'INBOX' in (m.get('labelIds') or []):
                    new_message_ids.append(m['id'])

        for gmail_id in new_message_ids:
            try:
                m_resp = requests.get(
                    f'{GMAIL_API_BASE}/messages/{gmail_id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=In-Reply-To&metadataHeaders=References',
                    headers=headers, timeout=15,
                )
                if not m_resp.ok:
                    continue
                m_data = m_resp.json()
                headers_list = (m_data.get('payload') or {}).get('headers') or []
                hdr = {h['name'].lower(): h['value'] for h in headers_list}
                from_raw = hdr.get('from', '')
                from_name, from_email = parseaddr(from_raw)
                from_email = (from_email or '').lower()
                subject = hdr.get('subject')
                snippet = m_data.get('snippet')
                thread_id = m_data.get('threadId')

                if not from_email or from_email == account.email.lower():
                    continue  # skip own messages

                # Match enrollment by thread or by sender
                enrollment = None
                if thread_id:
                    enrollment = session.query(EmailEnrollment).filter(
                        EmailEnrollment.gmail_thread_id == thread_id
                    ).first()
                if not enrollment:
                    enrollment = session.query(EmailEnrollment).filter(
                        EmailEnrollment.email == from_email
                    ).order_by(EmailEnrollment.last_sent_at.desc()).first()

                # Detect auto-replies
                is_auto = False
                subj_lower = (subject or '').lower()
                if any(k in subj_lower for k in ['out of office', 'auto-reply', 'auto reply', 'autoreply', 'vacation', 'delivery status notification', 'undeliverable', 'mail delivery failed']):
                    is_auto = True

                # Save reply
                existing = session.query(EmailReply).filter(EmailReply.gmail_message_id == gmail_id).first()
                if not existing:
                    reply = EmailReply(
                        account_id=account.id,
                        enrollment_id=enrollment.id if enrollment else None,
                        campaign_id=enrollment.campaign_id if enrollment else None,
                        gmail_message_id=gmail_id,
                        gmail_thread_id=thread_id,
                        from_email=from_email,
                        from_name=from_name,
                        subject=subject,
                        snippet=snippet,
                        is_auto_reply=is_auto,
                    )
                    session.add(reply)
                    new_count += 1

                # Stop sequence on real reply
                if enrollment and not is_auto and not enrollment.first_reply_at:
                    enrollment.first_reply_at = datetime.utcnow()
                    enrollment.status = EnrollmentStatus.ENGAGED.value

                # Detect bounce / delivery failure on enrollment
                if enrollment and is_auto and any(k in subj_lower for k in ['undeliverable', 'delivery status', 'mail delivery failed']):
                    enrollment.bounced_at = datetime.utcnow()
                    enrollment.status = 'bounced'
                    account.bounce_count_7d = (account.bounce_count_7d or 0) + 1

            except Exception as inner_e:
                logger.warning(f"Failed to process reply {gmail_id}: {inner_e}")
                continue

        account.history_id = str(latest_history_id)
        account.last_polled_at = datetime.utcnow()
        session.commit()
        return new_count
    except Exception as e:
        logger.exception(f"poll_replies_for_account({account_id}) error")
        session.rollback()
        return 0
    finally:
        session.close()


def poll_replies_all_accounts() -> int:
    """Poll all active accounts for replies. Returns total new replies."""
    session = get_session()
    try:
        accounts = session.query(EmailAccount).filter(
            EmailAccount.status == EmailAccountStatus.ACTIVE.value
        ).all()
        account_ids = [a.id for a in accounts]
    finally:
        session.close()

    total = 0
    for aid in account_ids:
        try:
            total += poll_replies_for_account(aid)
        except Exception as e:
            logger.warning(f"poll failed for account {aid}: {e}")
    return total


# =============================================================================
# AI PERSONALIZATION
# =============================================================================

def generate_ai_first_line(prompt_template: str, enrollment_data: dict) -> Optional[str]:
    """
    Use Anthropic to generate a personalized one-liner opener.
    Returns plain text or None on failure.
    """
    if not Config.ANTHROPIC_API_KEY:
        return None
    try:
        # Lazy import — anthropic is optional
        import anthropic
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

        # Render any {variables} in the prompt template
        context_lines = []
        for k, v in enrollment_data.items():
            if v:
                context_lines.append(f"- {k}: {v}")
        context_block = '\n'.join(context_lines)

        system = (
            "You write personalized cold-email opening lines for B2B outreach in NYC construction/permits. "
            "Output ONLY the one-line opener — no greeting, no quotes, no preamble, no follow-up sentence. "
            "Keep it under 20 words, specific, observational, and human. Never use the word 'hope'."
        )
        user_prompt = (
            (prompt_template or "Write a one-line personalized opener based on this contact.")
            + f"\n\nContact data:\n{context_block}"
        )

        resp = client.messages.create(
            model=Config.ANTHROPIC_MODEL,
            max_tokens=120,
            system=system,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        text = ''.join(b.text for b in resp.content if hasattr(b, 'text')).strip()
        # Strip stray quotes if model added them
        return text.strip('"“”\'').strip()
    except Exception as e:
        logger.warning(f"AI personalization failed: {e}")
        return None
