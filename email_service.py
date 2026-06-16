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

def _decode_b64url(data: str) -> str:
    """Decode Gmail's URL-safe base64 body data to text."""
    if not data:
        return ''
    try:
        padded = data + '=' * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8', errors='replace')
    except Exception:
        return ''


def _extract_message_bodies(payload: dict) -> Tuple[str, str]:
    """
    Walk a Gmail message payload (recursively through multipart) and return
    (text_plain, text_html). Either may be empty.
    """
    text_plain, text_html = '', ''

    def walk(part):
        nonlocal text_plain, text_html
        if not part:
            return
        mime = part.get('mimeType', '')
        body = part.get('body', {}) or {}
        data = body.get('data')
        if mime == 'text/plain' and data and not text_plain:
            text_plain = _decode_b64url(data)
        elif mime == 'text/html' and data and not text_html:
            text_html = _decode_b64url(data)
        for sub in part.get('parts', []) or []:
            walk(sub)

    walk(payload)
    return text_plain, text_html


# Quote-stripping: trim the replied-to history so the inbox shows just the new text
_QUOTE_MARKERS = (
    'On ', '-----Original Message-----', '________________________________',
    'wrote:', 'From:', 'Sent from my',
)


def _strip_quoted_text(text: str) -> str:
    """Best-effort removal of quoted reply history from a plain-text body."""
    if not text:
        return ''
    lines = text.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        # Gmail-style "On <date>, <person> wrote:" boundary
        if stripped.startswith('On ') and stripped.endswith('wrote:'):
            break
        if stripped.startswith('>'):
            break
        if stripped in ('-----Original Message-----', '________________________________'):
            break
        out.append(line)
    result = '\n'.join(out).strip()
    return result or text.strip()


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
                # Skip if we already recorded this message
                existing = session.query(EmailReply).filter(EmailReply.gmail_message_id == gmail_id).first()
                if existing:
                    continue

                # Fetch the full message so we capture the actual body, not just metadata
                m_resp = requests.get(
                    f'{GMAIL_API_BASE}/messages/{gmail_id}?format=full',
                    headers=headers, timeout=20,
                )
                if not m_resp.ok:
                    continue
                m_data = m_resp.json()
                payload = m_data.get('payload') or {}
                headers_list = payload.get('headers') or []
                hdr = {h['name'].lower(): h['value'] for h in headers_list}
                from_raw = hdr.get('from', '')
                from_name, from_email = parseaddr(from_raw)
                from_email = (from_email or '').lower()
                subject = hdr.get('subject')
                snippet = m_data.get('snippet')
                thread_id = m_data.get('threadId')

                if not from_email or from_email == account.email.lower():
                    continue  # skip our own outbound messages

                body_text, body_html = _extract_message_bodies(payload)
                clean_text = _strip_quoted_text(body_text) if body_text else ''

                now = datetime.utcnow()

                # Match enrollment by thread first, then by sender
                enrollment = None
                if thread_id:
                    enrollment = session.query(EmailEnrollment).filter(
                        EmailEnrollment.gmail_thread_id == thread_id
                    ).first()
                if not enrollment:
                    enrollment = session.query(EmailEnrollment).filter(
                        EmailEnrollment.email == from_email
                    ).order_by(EmailEnrollment.last_sent_at.desc()).first()

                # Classify auto-reply vs bounce vs real reply
                subj_lower = (subject or '').lower()
                is_bounce = any(k in subj_lower for k in [
                    'undeliverable', 'delivery status notification', 'mail delivery failed',
                    'returned mail', 'failure notice', 'delivery has failed',
                ])
                is_auto = is_bounce or any(k in subj_lower for k in [
                    'out of office', 'auto-reply', 'auto reply', 'autoreply',
                    'automatic reply', 'vacation',
                ])

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
                    body_text=clean_text or body_text,
                    body_html=body_html or None,
                    is_auto_reply=is_auto,
                )
                session.add(reply)
                new_count += 1

                if not enrollment:
                    continue

                # Find the most recent send to this enrollment so we can attribute
                # the reply/bounce at the message level (powers per-step + A/B stats)
                last_send = session.query(EmailSend).filter(
                    EmailSend.enrollment_id == enrollment.id,
                    EmailSend.status == 'sent',
                ).order_by(EmailSend.sent_at.desc()).first()

                if is_bounce:
                    if not enrollment.bounced_at:
                        enrollment.bounced_at = now
                        enrollment.status = 'bounced'
                    if last_send and not last_send.bounced_at:
                        last_send.bounced_at = now
                        last_send.status = 'bounced'
                    account.bounce_count_7d = (account.bounce_count_7d or 0) + 1
                    session.add(EmailEvent(
                        send_id=last_send.id if last_send else None,
                        enrollment_id=enrollment.id,
                        campaign_id=enrollment.campaign_id,
                        event_type='bounce',
                    ))
                    _apply_bounce_guardrail(account, session)

                elif not is_auto:
                    # Real human reply — stop the sequence and attribute to the send
                    if not enrollment.first_reply_at:
                        enrollment.first_reply_at = now
                        enrollment.status = EnrollmentStatus.ENGAGED.value
                    if last_send and not last_send.replied_at:
                        last_send.replied_at = now
                    session.add(EmailEvent(
                        send_id=last_send.id if last_send else None,
                        enrollment_id=enrollment.id,
                        campaign_id=enrollment.campaign_id,
                        event_type='reply',
                    ))

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


def _apply_bounce_guardrail(account: EmailAccount, session) -> None:
    """
    If the account's trailing-7-day bounce rate exceeds its configured threshold
    (with a minimum sample size), auto-pause it so we stop torching the domain.
    """
    threshold = account.bounce_pause_threshold or 8
    window_start = datetime.utcnow() - timedelta(days=7)

    sent_7d = session.query(EmailSend).filter(
        EmailSend.account_id == account.id,
        EmailSend.sent_at >= window_start,
    ).count()

    # Need a meaningful sample before acting
    if sent_7d < 20:
        return

    bounced_7d = session.query(EmailSend).filter(
        EmailSend.account_id == account.id,
        EmailSend.sent_at >= window_start,
        EmailSend.bounced_at.isnot(None),
    ).count()

    rate = (bounced_7d / sent_7d * 100) if sent_7d else 0
    if rate >= threshold and account.status == EmailAccountStatus.ACTIVE.value:
        account.status = EmailAccountStatus.PAUSED.value
        account.auto_paused = True
        account.last_error = (
            f"Auto-paused: bounce rate {rate:.1f}% over last 7d "
            f"({bounced_7d}/{sent_7d}) exceeded {threshold}% threshold"
        )
        logger.warning(f"Auto-paused {account.email} — bounce rate {rate:.1f}%")


def fetch_thread(account_id: int, thread_id: str) -> dict:
    """
    Fetch a full Gmail thread (all messages) for the unified-inbox thread view.
    Returns {success, messages: [{from, to, date, subject, body_html, body_text, is_outbound}], error}.
    """
    session = get_session()
    try:
        account = session.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account:
            return {'success': False, 'error': 'account not found'}
        access_token = ensure_access_token(account, session)
        own_email = account.email.lower()
    finally:
        session.close()

    try:
        resp = requests.get(
            f'{GMAIL_API_BASE}/threads/{thread_id}?format=full',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=25,
        )
        if not resp.ok:
            return {'success': False, 'error': f'{resp.status_code}: {resp.text[:300]}'}
        data = resp.json()
        messages = []
        for m in data.get('messages', []):
            payload = m.get('payload') or {}
            hdrs = {h['name'].lower(): h['value'] for h in (payload.get('headers') or [])}
            from_raw = hdrs.get('from', '')
            from_name, from_email = parseaddr(from_raw)
            body_text, body_html = _extract_message_bodies(payload)
            is_outbound = (from_email or '').lower() == own_email
            messages.append({
                'from_name': from_name,
                'from_email': from_email,
                'to': hdrs.get('to', ''),
                'date': hdrs.get('date', ''),
                'subject': hdrs.get('subject', ''),
                'snippet': m.get('snippet', ''),
                'body_text': body_text,
                'body_html': body_html,
                'is_outbound': is_outbound,
            })
        return {'success': True, 'messages': messages, 'thread_id': thread_id}
    except Exception as e:
        logger.exception("fetch_thread error")
        return {'success': False, 'error': str(e)}


def send_reply(account_id: int, *, to_email: str, subject: str, body_text: str,
               thread_id: str = None, in_reply_to: str = None) -> dict:
    """
    Send a human-written reply in-thread from the connected mailbox.
    Used by the in-app inbox composer. Marks the EmailReply as replied_to.
    """
    session = get_session()
    try:
        account = session.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account:
            return {'success': False, 'error': 'account not found'}

        # Build an HTML body from the plain text the operator typed
        safe_html = (body_text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html_body = '<div style="font-family:Arial,sans-serif;white-space:pre-wrap">' + safe_html + '</div>'

        reply_subject = subject or ''
        if reply_subject and not reply_subject.lower().startswith('re:'):
            reply_subject = 'Re: ' + reply_subject

        result = send_email_via_gmail(
            account=account,
            to_email=to_email,
            subject=reply_subject,
            html_body=html_body,
            text_body=body_text,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=in_reply_to,
            session=session,
        )
        if result.get('success'):
            # Mark any matching inbound replies in this thread as answered
            if thread_id:
                session.query(EmailReply).filter(
                    EmailReply.gmail_thread_id == thread_id
                ).update({EmailReply.replied_to: True})
            session.commit()
        return result
    except Exception as e:
        logger.exception("send_reply error")
        session.rollback()
        return {'success': False, 'error': str(e)}
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
# NAME CLEANING (uses python `nameparser`, same library typically used in
# scraper / Apify pipelines for handling weird name formats)
# =============================================================================

_BUSINESS_MARKERS = (
    ' LLC', ' L.L.C', ' INC', ' INC.', ' CORP', ' CORPORATION', ' CO.', ' CO,',
    ' LTD', ' L.P.', ' LP', ' LLP', ' COMPANY', ' HOLDINGS', ' GROUP',
    ' ASSOCIATES', ' ASSOC', ' PARTNERS', ' ENTERPRISES', ' SOLUTIONS',
    ' SERVICES', ' CONSTRUCTION', ' BUILDERS', ' DEVELOPERS', ' MANAGEMENT',
    ' REALTY', ' PROPERTIES', ' CONTRACTORS', ' CONTRACTING',
)


def _looks_like_business(raw: str) -> bool:
    if not raw:
        return False
    up = ' ' + raw.upper().strip()
    return any(m in up for m in _BUSINESS_MARKERS)


def clean_name(raw: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse a raw name string into structured parts. Handles:
      - "JOHN SMITH" (all caps) -> "John Smith"
      - "Smith, John P." (comma-separated)
      - "Mr. John Q. Smith Jr." (titles + suffixes)
      - "ABC CONSTRUCTION LLC" -> recognized as business, kept as-is
      - "John & Jane Smith" -> primary contact

    Returns dict with: full_name, first_name, last_name, is_business
    All fields can be None.
    """
    if not raw or not str(raw).strip():
        return {'full_name': None, 'first_name': None, 'last_name': None, 'is_business': False}

    raw_s = str(raw).strip()
    is_biz = _looks_like_business(raw_s)

    if is_biz:
        # Preserve canonical business suffix casing (LLC, INC, LP, ...)
        # Title-case everything else, then patch suffixes back to upper-case.
        cased = raw_s.title()
        for suf in ('Llc', 'L.L.C', 'Inc', 'Inc.', 'Corp', 'Co.', 'Co,', 'Ltd',
                    'L.P.', 'Lp', 'Llp', 'P.C.', 'Pc'):
            cased = cased.replace(' ' + suf, ' ' + suf.upper())
        # Also fix any "Llc" at end of string after a comma
        if cased.endswith(' Llc'):
            cased = cased[:-4] + ' LLC'
        return {
            'full_name': cased,
            'first_name': None,
            'last_name': None,
            'is_business': True,
        }

    # Person name — normalize to Title Case regardless of input casing
    cased = raw_s.title() if (raw_s.isupper() or raw_s.islower()) else raw_s

    try:
        from nameparser import HumanName
        # nameparser handles "Smith, John" / titles / suffixes / Jr-III
        n = HumanName(cased)
        first = (n.first or '').strip() or None
        last = (n.last or '').strip() or None
        middle = (n.middle or '').strip()
        title = (n.title or '').strip()
        suffix = (n.suffix or '').strip()

        # Drop "&" splits — take the first person if it's a multi-owner name
        if first and '&' in first:
            first = first.split('&')[0].strip()
        if last and '&' in last:
            last = last.split('&')[0].strip()

        # Reassemble cleanly
        parts = [title, first, middle, last, suffix]
        full = ' '.join(p for p in parts if p).strip() or cased

        return {
            'full_name': full,
            'first_name': first,
            'last_name': last,
            'is_business': False,
        }
    except Exception as e:
        logger.debug(f"nameparser failed on {raw_s!r}: {e}")
        # Fallback: best-effort first token as first name
        tokens = cased.split()
        return {
            'full_name': cased,
            'first_name': tokens[0] if tokens else None,
            'last_name': tokens[-1] if len(tokens) > 1 else None,
            'is_business': False,
        }


# =============================================================================
# CONTACT ENRICHMENT (from leads DB)
# =============================================================================

def enrich_contact_from_leads(email: str, current_data: dict) -> dict:
    """
    Given an email + whatever data the user supplied, look up the leads DB
    (owner_contacts + permits) and merge in anything we know:
      - owner_name -> name (if user didn't provide one)
      - phone
      - most recent permit address, borough, permit_no, job_type, work_type
      - permit_count (how many permits this owner has)
      - owner_business_name -> company

    Never overwrites user-provided data. Always cleans names via clean_name().
    Safe to call in a loop — fails gracefully if the leads DB is unavailable.
    """
    enriched = dict(current_data or {})

    if not email or '@' not in email:
        return enriched

    try:
        # Lazy import to avoid circular dep at module load
        from leads_service import get_leads_engine
        from sqlalchemy import text as _text

        engine = get_leads_engine()
        with engine.connect() as conn:
            # 1. Look up owner_contacts by email (case-insensitive)
            oc_row = conn.execute(_text("""
                SELECT owner_name, phone, phone_type, source, confidence
                FROM owner_contacts
                WHERE LOWER(email) = LOWER(:email)
                ORDER BY confidence DESC NULLS LAST, created_at DESC
                LIMIT 1
            """), {'email': email}).fetchone()

            owner_name_raw = None
            if oc_row:
                oc = dict(oc_row._mapping)
                owner_name_raw = oc.get('owner_name')

                if not enriched.get('phone') and oc.get('phone'):
                    enriched['phone'] = oc['phone']
                if oc.get('source'):
                    enriched.setdefault('lead_source', oc['source'])

            # 2. Clean the name if we have one (from either source)
            best_name = enriched.get('name') or owner_name_raw
            if best_name:
                parsed = clean_name(best_name)
                if parsed['is_business']:
                    # If the "name" looks like a business, promote it
                    if not enriched.get('company'):
                        enriched['company'] = parsed['full_name']
                    # Don't store a business as the person's name
                    if enriched.get('name') and _looks_like_business(enriched['name']):
                        enriched['name'] = None
                else:
                    enriched['name'] = parsed['full_name']
                    if parsed['first_name']:
                        enriched['first_name'] = parsed['first_name']
                    if parsed['last_name']:
                        enriched['last_name'] = parsed['last_name']

            # 3. Fuzzy-match permits to grab project context
            #    Use the owner_name (raw, since permits use the same source) for matching
            permit_query_name = owner_name_raw or enriched.get('name') or enriched.get('company')
            if permit_query_name and len(permit_query_name) > 3:
                try:
                    permits = conn.execute(_text("""
                        SELECT permit_no, address, borough, nta_name,
                               job_type, work_type, permit_type, permit_status,
                               bldg_type, residential,
                               owner_business_name, issuance_date
                        FROM permits
                        WHERE owner_business_name ILIKE :pattern
                          AND owner_business_name IS NOT NULL
                        ORDER BY issuance_date DESC NULLS LAST
                        LIMIT 5
                    """), {'pattern': f'%{permit_query_name}%'}).fetchall()

                    if permits:
                        permit_dicts = [dict(p._mapping) for p in permits]
                        most_recent = permit_dicts[0]

                        if not enriched.get('company') and most_recent.get('owner_business_name'):
                            enriched['company'] = most_recent['owner_business_name']

                        enriched['recent_permit_no'] = most_recent.get('permit_no')
                        enriched['recent_address'] = most_recent.get('address')
                        enriched['recent_borough'] = most_recent.get('borough')
                        enriched['recent_neighborhood'] = most_recent.get('nta_name')
                        enriched['recent_job_type'] = most_recent.get('job_type')
                        enriched['recent_work_type'] = most_recent.get('work_type')
                        enriched['recent_permit_status'] = most_recent.get('permit_status')
                        if most_recent.get('issuance_date'):
                            enriched['recent_permit_date'] = str(most_recent['issuance_date'])
                        enriched['permit_count'] = len(permit_dicts)

                        # If multiple boroughs, note that
                        boroughs = list({p.get('borough') for p in permit_dicts if p.get('borough')})
                        if len(boroughs) > 1:
                            enriched['active_boroughs'] = ', '.join(boroughs)
                except Exception as perm_e:
                    logger.debug(f"Permit lookup failed for {permit_query_name!r}: {perm_e}")

    except Exception as e:
        logger.debug(f"Enrichment failed for {email!r}: {e}")

    return enriched


# =============================================================================
# AI PERSONALIZATION
# =============================================================================

# Job type / work type human readouts so AI gets context it can riff on
_JOB_TYPE_LABELS = {
    'A1': 'major alteration', 'A2': 'minor alteration', 'A3': 'cosmetic alteration',
    'NB': 'new building', 'DM': 'demolition', 'SG': 'sign permit',
}
_WORK_TYPE_LABELS = {
    'OT': 'general work', 'PL': 'plumbing', 'EQ': 'equipment', 'MH': 'HVAC',
    'SP': 'sprinkler', 'FP': 'fire protection', 'BL': 'boiler', 'SD': 'standpipe',
}


def _humanize_context(data: dict) -> str:
    """Turn the enrichment dict into a brief, AI-friendly context block."""
    lines = []
    name = data.get('first_name') or data.get('name')
    if name and not _looks_like_business(name):
        lines.append(f"- recipient: {name}")
    if data.get('company'):
        lines.append(f"- company: {data['company']}")
    if data.get('recent_borough') or data.get('recent_neighborhood'):
        loc = data.get('recent_neighborhood') or data.get('recent_borough')
        if data.get('recent_borough') and data.get('recent_neighborhood'):
            loc = f"{data['recent_neighborhood']} ({data['recent_borough']})"
        lines.append(f"- most recent project location: {loc}")
    if data.get('recent_address'):
        lines.append(f"- most recent project address: {data['recent_address']}")
    if data.get('recent_job_type'):
        jt = _JOB_TYPE_LABELS.get(data['recent_job_type'], data['recent_job_type'])
        lines.append(f"- most recent project type: {jt}")
    if data.get('recent_work_type'):
        wt = _WORK_TYPE_LABELS.get(data['recent_work_type'], data['recent_work_type'])
        lines.append(f"- work category: {wt}")
    if data.get('recent_permit_date'):
        lines.append(f"- most recent permit date: {data['recent_permit_date']}")
    if data.get('permit_count') and data['permit_count'] > 1:
        lines.append(f"- total permits on file: {data['permit_count']}")
    if data.get('active_boroughs'):
        lines.append(f"- active across: {data['active_boroughs']}")
    # Anything else the CSV provided (skip already-rendered keys)
    skip = {'email', 'name', 'first_name', 'last_name', 'company', 'phone',
            'recent_borough', 'recent_neighborhood', 'recent_address',
            'recent_job_type', 'recent_work_type', 'recent_permit_date',
            'permit_count', 'active_boroughs', 'recent_permit_no',
            'recent_permit_status', 'lead_source'}
    for k, v in data.items():
        if k in skip or not v:
            continue
        lines.append(f"- {k}: {v}")
    return '\n'.join(lines) if lines else '- (no additional context)'


# Default opener prompt used when the user leaves the prompt field blank
DEFAULT_AI_PROMPT = (
    "Write a one-line, lowercase, observational opener for a NYC construction-services "
    "cold email. Reference the recipient's most recent permit / project when possible. "
    "Keep it concrete and human — never sycophantic."
)


def generate_ai_first_line(prompt_template: str, enrollment_data: dict) -> Optional[str]:
    """
    Use Anthropic to generate a personalized one-liner opener.
    Returns plain text, or empty string on SKIP, or None on hard failure.
    Output is validated — meta-responses ("I don't have access...", "could you provide...")
    are detected and rejected.
    """
    if not Config.ANTHROPIC_API_KEY:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

        context_block = _humanize_context(enrollment_data)

        system = (
            "You write one-line opening hooks for B2B cold emails. Your output replaces "
            "the {ai_first_line} token inside a templated email.\n\n"
            "ABSOLUTE RULES:\n"
            "- Output exactly ONE short sentence (under 22 words). Plain text only — no quotes, "
            "no greeting, no signoff, no preamble, no markdown.\n"
            "- Use whatever recipient context is provided. If it is sparse, riff on whatever "
            "IS there (name, email domain, company) — DO NOT ask for more information.\n"
            "- NEVER mention what you don't know. NEVER apologize. NEVER explain your reasoning. "
            "NEVER say 'I don't have', 'could you provide', 'I'd need', or 'I cannot'.\n"
            "- If after all that you genuinely cannot write anything natural, output the single "
            "literal word: SKIP\n"
            "- Tone: a real person who did 30 seconds of research. Observational. Specific. "
            "Lowercase okay. Conversational. Never sycophantic. Never use the word 'hope'.\n\n"
            "GOOD examples:\n"
            "  noticed your team pulled a permit on east 86th last month\n"
            "  saw the tribeca alteration job — looked like a tricky one\n"
            "  your group has been busy in the bronx this year\n"
            "  came across [company] while looking at NB filings\n\n"
            "BAD examples (never output these):\n"
            "  I don't have specific permit data for this contact\n"
            "  Could you provide more details so I can craft a specific opener?\n"
            "  Hope this finds you well\n"
            "  I'd need company name and recent projects to write something accurate"
        )

        user_prompt = (
            (prompt_template or DEFAULT_AI_PROMPT).strip()
            + "\n\nRecipient context:\n"
            + context_block
        )

        resp = client.messages.create(
            model=Config.ANTHROPIC_MODEL,
            max_tokens=120,
            system=system,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        text = ''.join(b.text for b in resp.content if hasattr(b, 'text')).strip()

        # Validate output — reject meta-responses
        if _is_meta_response(text):
            logger.info(f"AI produced meta-response, returning empty: {text[:120]!r}")
            return ''
        if text.upper().strip() == 'SKIP':
            return ''

        # Clean up: strip quotes, leading conjunctions
        text = text.strip('"“”\'').strip()
        # Strip trailing periods that double up with template punctuation
        return text
    except Exception as e:
        logger.warning(f"AI personalization failed: {e}")
        return None


def _is_meta_response(text: str) -> bool:
    """Detect when the AI confessed instead of writing an opener."""
    if not text:
        return True
    t = text.lower()
    bad_phrases = [
        "i don't have", "i do not have", "i'd need", "i would need",
        "could you provide", "could you share", "please provide",
        "i cannot", "i can't write", "i'm unable", "i am unable",
        "without more", "to craft", "to write an accurate",
        "more details", "more information", "more context",
        "based on the limited", "with the limited",
    ]
    if any(p in t for p in bad_phrases):
        return True
    # Multi-sentence responses with question marks are usually clarifying questions
    if t.count('?') >= 1 and len(text) > 60:
        return True
    # Bullet lists or multi-line prose
    if text.count('\n') > 0 and ('-' in text or '•' in text):
        return True
    return False
