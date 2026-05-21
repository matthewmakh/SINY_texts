"""
Email Campaign Service — business logic for email sequences.
Mirrors campaign_service.py but for the email rail.
"""
from __future__ import annotations

import json
import logging
import random
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload

from database import (
    get_db_session, get_session,
    EmailCampaign, EmailCampaignMessage, EmailEnrollment, EmailSend,
    EmailAccount, EmailUnsubscribe,
    CampaignStatus, EnrollmentStatus,
)

logger = logging.getLogger(__name__)


def _now_eastern() -> datetime:
    return datetime.now(ZoneInfo('America/New_York'))


class EmailCampaignService:

    # ---------------------- CAMPAIGNS ----------------------

    def create_campaign(self, *, name: str, description: str = None,
                        enrollment_type: str = 'snapshot',
                        filter_criteria: dict = None,
                        send_window_start: str = '09:00',
                        send_window_end: str = '17:00',
                        send_days: str = 'mon,tue,wed,thu,fri',
                        sending_account_ids: list = None,
                        rotation_strategy: str = 'round_robin',
                        ai_personalization: bool = False,
                        ai_prompt: str = None,
                        track_opens: bool = True,
                        track_clicks: bool = True,
                        created_by: int = None) -> dict:
        with get_db_session() as session:
            c = EmailCampaign(
                name=name,
                description=description,
                status=CampaignStatus.DRAFT.value,
                enrollment_type=enrollment_type,
                filter_criteria=json.dumps(filter_criteria) if filter_criteria else None,
                send_window_start=send_window_start,
                send_window_end=send_window_end,
                send_days=send_days,
                sending_account_ids=json.dumps(sending_account_ids) if sending_account_ids else None,
                rotation_strategy=rotation_strategy,
                ai_personalization=ai_personalization,
                ai_prompt=ai_prompt,
                track_opens=track_opens,
                track_clicks=track_clicks,
                created_by=created_by,
            )
            session.add(c)
            session.flush()
            return c.to_dict()

    def list_campaigns(self, status: str = None, include_stats: bool = True) -> List[dict]:
        session = get_session()
        try:
            q = session.query(EmailCampaign).options(
                joinedload(EmailCampaign.messages),
                joinedload(EmailCampaign.enrollments),
            )
            if status:
                q = q.filter(EmailCampaign.status == status)
            campaigns = q.order_by(EmailCampaign.created_at.desc()).all()
            return [c.to_dict(include_stats=include_stats) for c in campaigns]
        finally:
            session.close()

    def get_campaign(self, campaign_id: int, include_stats: bool = True) -> Optional[dict]:
        session = get_session()
        try:
            c = session.query(EmailCampaign).options(
                joinedload(EmailCampaign.messages),
                joinedload(EmailCampaign.enrollments),
            ).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                return None
            result = c.to_dict(include_stats=include_stats)
            result['messages'] = [m.to_dict(include_stats=include_stats)
                                  for m in sorted(c.messages, key=lambda m: m.sequence_order)]
            return result
        finally:
            session.close()

    def update_campaign(self, campaign_id: int, **kwargs) -> Optional[dict]:
        with get_db_session() as session:
            c = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                return None
            allowed = ['name', 'description', 'enrollment_type', 'filter_criteria',
                       'send_window_start', 'send_window_end', 'send_days',
                       'sending_account_ids', 'rotation_strategy',
                       'ai_personalization', 'ai_prompt',
                       'track_opens', 'track_clicks']
            for f in allowed:
                if f in kwargs:
                    val = kwargs[f]
                    if f in ('filter_criteria', 'sending_account_ids') and not isinstance(val, str):
                        val = json.dumps(val) if val is not None else None
                    setattr(c, f, val)
            c.updated_at = datetime.utcnow()
            session.flush()
            return c.to_dict()

    def delete_campaign(self, campaign_id: int) -> bool:
        with get_db_session() as session:
            c = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                return False
            session.delete(c)
            return True

    # ---------------------- MESSAGES ----------------------

    def add_message(self, *, campaign_id: int, subject: str, body_html: str,
                    preheader: str = None, body_text: str = None,
                    days_after_previous: int = 0, same_thread: bool = True,
                    sequence_order: int = None,
                    subject_variant_b: str = None) -> Optional[dict]:
        with get_db_session() as session:
            campaign = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not campaign:
                return None
            if sequence_order is None:
                max_order = session.query(func.max(EmailCampaignMessage.sequence_order)).filter(
                    EmailCampaignMessage.campaign_id == campaign_id).scalar() or 0
                sequence_order = max_order + 1
            m = EmailCampaignMessage(
                campaign_id=campaign_id,
                sequence_order=sequence_order,
                subject=subject,
                preheader=preheader,
                body_html=body_html,
                body_text=body_text,
                days_after_previous=days_after_previous,
                same_thread=same_thread,
                has_ab_test=bool(subject_variant_b),
                subject_variant_b=subject_variant_b,
            )
            session.add(m)
            session.flush()
            return m.to_dict()

    def update_message(self, message_id: int, **kwargs) -> Optional[dict]:
        with get_db_session() as session:
            m = session.query(EmailCampaignMessage).filter(EmailCampaignMessage.id == message_id).first()
            if not m:
                return None
            allowed = ['subject', 'preheader', 'body_html', 'body_text',
                       'days_after_previous', 'same_thread', 'sequence_order',
                       'subject_variant_b']
            for f in allowed:
                if f in kwargs:
                    setattr(m, f, kwargs[f])
            m.has_ab_test = bool(m.subject_variant_b)
            session.flush()
            return m.to_dict()

    def delete_message(self, message_id: int) -> bool:
        with get_db_session() as session:
            m = session.query(EmailCampaignMessage).filter(EmailCampaignMessage.id == message_id).first()
            if not m:
                return False
            sent_count = session.query(EmailSend).filter(EmailSend.message_id == message_id).count()
            if sent_count > 0:
                raise ValueError("Cannot delete message that has already been sent")
            campaign_id = m.campaign_id
            session.delete(m)
            session.flush()
            remaining = session.query(EmailCampaignMessage).filter(
                EmailCampaignMessage.campaign_id == campaign_id
            ).order_by(EmailCampaignMessage.sequence_order).all()
            for i, msg in enumerate(remaining, 1):
                msg.sequence_order = i
            return True

    # ---------------------- ENROLLMENT ----------------------

    def enroll_contacts(self, campaign_id: int, contacts: List[dict],
                        exclude_emails: List[str] = None,
                        enrich: bool = True) -> dict:
        """
        Enroll a list of contacts. Each dict needs at least 'email'.
        If enrich=True (default), each contact is run through clean_name() and
        cross-referenced against the leads DB (owner_contacts + permits) so
        the AI personalization has real context to work with.

        Returns {enrolled, skipped_invalid, skipped_duplicate, skipped_unsubscribed,
                 enriched_count} so the UI can show meaningful feedback.
        """
        # Lazy import to avoid circular dep
        from email_service import enrich_contact_from_leads, clean_name

        session = get_session()
        stats = {
            'enrolled': 0,
            'skipped_invalid': 0,
            'skipped_duplicate': 0,
            'skipped_unsubscribed': 0,
            'enriched_count': 0,
        }
        try:
            campaign = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not campaign:
                raise ValueError("Campaign not found")

            has_ab = session.query(EmailCampaignMessage).filter(
                EmailCampaignMessage.campaign_id == campaign_id,
                EmailCampaignMessage.has_ab_test == True
            ).count() > 0

            exclude = set((e or '').lower() for e in (exclude_emails or []))

            # Global suppression list
            unsubs = {u.email for u in session.query(EmailUnsubscribe).all()}

            seen = set()
            for c in contacts:
                email = (c.get('email') or '').strip().lower()
                if not email or '@' not in email:
                    stats['skipped_invalid'] += 1
                    continue
                if email in exclude or email in seen:
                    stats['skipped_duplicate'] += 1
                    continue
                if email in unsubs:
                    stats['skipped_unsubscribed'] += 1
                    continue
                existing = session.query(EmailEnrollment).filter(
                    EmailEnrollment.campaign_id == campaign_id,
                    EmailEnrollment.email == email
                ).first()
                if existing:
                    stats['skipped_duplicate'] += 1
                    continue

                # Clean the supplied name even if we don't enrich
                if c.get('name'):
                    parsed = clean_name(c['name'])
                    if parsed['is_business']:
                        if not c.get('company'):
                            c['company'] = parsed['full_name']
                        c['name'] = None  # don't use a business name as person name
                    else:
                        c['name'] = parsed['full_name']
                        if parsed['first_name']:
                            c['first_name'] = parsed['first_name']
                        if parsed['last_name']:
                            c['last_name'] = parsed['last_name']

                # Enrich from leads DB (looks up owner_contacts by email,
                # fuzzy-matches permits by owner name)
                if enrich:
                    enriched = enrich_contact_from_leads(email, c)
                    had_new_keys = any(
                        k not in c and enriched.get(k)
                        for k in ('recent_address', 'recent_borough', 'permit_count', 'company')
                    )
                    if had_new_keys:
                        stats['enriched_count'] += 1
                    c = enriched

                extra = {k: v for k, v in c.items()
                         if k not in ('email', 'name', 'company') and v is not None}
                ab = random.choice(['A', 'B']) if has_ab else None

                enrollment = EmailEnrollment(
                    campaign_id=campaign_id,
                    email=email,
                    name=c.get('name'),
                    company=c.get('company'),
                    extra_data=json.dumps(extra) if extra else None,
                    ab_variant=ab,
                    status=EnrollmentStatus.ACTIVE.value,
                    unsubscribe_token=secrets.token_urlsafe(32),
                )
                session.add(enrollment)
                seen.add(email)
                stats['enrolled'] += 1

            session.commit()
            return stats
        finally:
            session.close()

    def get_enrollments(self, campaign_id: int, status: str = None,
                        limit: int = 100, offset: int = 0) -> Tuple[List[dict], int]:
        session = get_session()
        try:
            q = session.query(EmailEnrollment).filter(EmailEnrollment.campaign_id == campaign_id)
            if status:
                q = q.filter(EmailEnrollment.status == status)
            total = q.count()
            rows = q.order_by(EmailEnrollment.enrolled_at.desc()).offset(offset).limit(limit).all()
            return [r.to_dict() for r in rows], total
        finally:
            session.close()

    # ---------------------- LIFECYCLE ----------------------

    def start_campaign(self, campaign_id: int) -> dict:
        with get_db_session() as session:
            c = session.query(EmailCampaign).options(
                joinedload(EmailCampaign.messages),
                joinedload(EmailCampaign.enrollments),
            ).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                raise ValueError("Campaign not found")
            if c.status not in (CampaignStatus.DRAFT.value, CampaignStatus.PAUSED.value):
                raise ValueError(f"Cannot start campaign in {c.status} status")
            if not c.messages:
                raise ValueError("Campaign has no messages")
            if not c.enrollments:
                raise ValueError("Campaign has no enrolled contacts")
            if not c.sending_account_ids or not json.loads(c.sending_account_ids):
                raise ValueError("Campaign has no sending accounts assigned")

            c.status = CampaignStatus.ACTIVE.value
            c.started_at = datetime.utcnow()
            c.paused_at = None
            session.flush()
            return c.to_dict()

    def pause_campaign(self, campaign_id: int) -> dict:
        with get_db_session() as session:
            c = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                raise ValueError("Campaign not found")
            c.status = CampaignStatus.PAUSED.value
            c.paused_at = datetime.utcnow()
            session.flush()
            return c.to_dict()

    def resume_campaign(self, campaign_id: int) -> dict:
        with get_db_session() as session:
            c = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                raise ValueError("Campaign not found")
            if c.status != CampaignStatus.PAUSED.value:
                raise ValueError("Can only resume paused campaigns")
            c.status = CampaignStatus.ACTIVE.value
            c.paused_at = None
            session.flush()
            return c.to_dict()

    def complete_campaign(self, campaign_id: int) -> dict:
        with get_db_session() as session:
            c = session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
            if not c:
                raise ValueError("Campaign not found")
            c.status = CampaignStatus.COMPLETED.value
            c.completed_at = datetime.utcnow()
            session.flush()
            return c.to_dict()


email_campaign_service = EmailCampaignService()
