"""
Campaign Service - Business logic for SMS campaigns
Handles campaign creation, enrollment, scheduling, and tracking.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
import random
import logging
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload

from database import (
    get_db_session, get_session,
    Campaign, CampaignMessage, CampaignABTest, 
    CampaignEnrollment, CampaignSend,
    CampaignStatus, EnrollmentStatus
)
from leads_service import get_all_contacts, normalize_phone, get_contacts_by_phones

logger = logging.getLogger(__name__)

# Opt-out keywords to detect
OPT_OUT_KEYWORDS = ['stop', 'unsubscribe', 'cancel', 'quit', 'end']


class CampaignService:
    """Service class for campaign operations"""
    
    # =========================================================================
    # CAMPAIGN CRUD
    # =========================================================================
    
    def create_campaign(
        self, 
        name: str, 
        description: str = None,
        enrollment_type: str = 'snapshot',
        filter_criteria: dict = None,
        default_send_time: str = '11:00',
        created_by: int = None
    ) -> Campaign:
        """Create a new campaign in draft status"""
        with get_db_session() as session:
            campaign = Campaign(
                name=name,
                description=description,
                status=CampaignStatus.DRAFT.value,
                enrollment_type=enrollment_type,
                filter_criteria=json.dumps(filter_criteria) if filter_criteria else None,
                default_send_time=default_send_time,
                created_by=created_by
            )
            session.add(campaign)
            session.flush()
            
            result = campaign.to_dict()
            return result
    
    def get_campaign(self, campaign_id: int, include_stats: bool = True) -> Optional[dict]:
        """Get a campaign by ID with optional stats"""
        session = get_session()
        try:
            campaign = session.query(Campaign).options(
                joinedload(Campaign.messages),
                joinedload(Campaign.enrollments)
            ).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                return None
            
            result = campaign.to_dict(include_stats=include_stats)
            
            # Add message details with stats
            result['messages'] = [
                msg.to_dict(include_stats=include_stats) 
                for msg in sorted(campaign.messages, key=lambda m: m.sequence_order)
            ]
            
            return result
        finally:
            session.close()
    
    def list_campaigns(self, status: str = None, include_stats: bool = True) -> List[dict]:
        """List all campaigns, optionally filtered by status"""
        session = get_session()
        try:
            query = session.query(Campaign).options(
                joinedload(Campaign.messages),
                joinedload(Campaign.enrollments)
            )
            
            if status:
                query = query.filter(Campaign.status == status)
            
            campaigns = query.order_by(Campaign.created_at.desc()).all()
            
            return [c.to_dict(include_stats=include_stats) for c in campaigns]
        finally:
            session.close()
    
    def update_campaign(self, campaign_id: int, **kwargs) -> Optional[dict]:
        """Update campaign properties (can edit even when active)"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return None
            
            # Updateable fields
            allowed_fields = ['name', 'description', 'enrollment_type', 'filter_criteria', 'default_send_time']
            
            for field in allowed_fields:
                if field in kwargs:
                    value = kwargs[field]
                    if field == 'filter_criteria' and isinstance(value, dict):
                        value = json.dumps(value)
                    setattr(campaign, field, value)
            
            campaign.updated_at = datetime.utcnow()
            session.flush()
            
            return campaign.to_dict()
    
    def delete_campaign(self, campaign_id: int) -> bool:
        """Delete a campaign and all related data (only if draft)"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return False
            
            if campaign.status != CampaignStatus.DRAFT.value:
                raise ValueError("Can only delete campaigns in draft status")
            
            # Delete related data
            session.query(CampaignSend).filter(CampaignSend.campaign_id == campaign_id).delete()
            session.query(CampaignEnrollment).filter(CampaignEnrollment.campaign_id == campaign_id).delete()
            session.query(CampaignABTest).filter(CampaignABTest.campaign_id == campaign_id).delete()
            session.query(CampaignMessage).filter(CampaignMessage.campaign_id == campaign_id).delete()
            session.delete(campaign)
            
            return True
    
    # =========================================================================
    # CAMPAIGN MESSAGES
    # =========================================================================
    
    def add_message(
        self,
        campaign_id: int,
        message_body: str,
        days_after_previous: int = 0,
        send_time: str = None,
        enable_followup: bool = False,
        followup_days: int = 3,
        followup_body: str = None,
        sequence_order: int = None
    ) -> Optional[dict]:
        """Add a message to a campaign sequence"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return None
            
            # Auto-calculate sequence order if not provided
            if sequence_order is None:
                max_order = session.query(func.max(CampaignMessage.sequence_order)).filter(
                    CampaignMessage.campaign_id == campaign_id
                ).scalar() or 0
                sequence_order = max_order + 1
            
            message = CampaignMessage(
                campaign_id=campaign_id,
                sequence_order=sequence_order,
                message_body=message_body,
                days_after_previous=days_after_previous,
                send_time=send_time,
                enable_followup=enable_followup,
                followup_days=followup_days,
                followup_body=followup_body or "Just following up on my last message. Let me know if you have any questions!"
            )
            session.add(message)
            session.flush()
            
            return message.to_dict()
    
    def update_message(self, message_id: int, **kwargs) -> Optional[dict]:
        """Update a campaign message (can edit even when campaign is active)"""
        with get_db_session() as session:
            message = session.query(CampaignMessage).filter(CampaignMessage.id == message_id).first()
            if not message:
                return None
            
            allowed_fields = [
                'message_body', 'days_after_previous', 'send_time',
                'enable_followup', 'followup_days', 'followup_body', 'sequence_order'
            ]
            
            for field in allowed_fields:
                if field in kwargs:
                    setattr(message, field, kwargs[field])
            
            message.updated_at = datetime.utcnow()
            session.flush()
            
            return message.to_dict()
    
    def delete_message(self, message_id: int) -> bool:
        """Delete a campaign message"""
        with get_db_session() as session:
            message = session.query(CampaignMessage).filter(CampaignMessage.id == message_id).first()
            if not message:
                return False
            
            # Don't allow deleting if sends already exist for this message
            send_count = session.query(CampaignSend).filter(
                CampaignSend.campaign_message_id == message_id
            ).count()
            
            if send_count > 0:
                raise ValueError("Cannot delete message that has already been sent")
            
            # Delete A/B test if exists
            session.query(CampaignABTest).filter(
                CampaignABTest.campaign_message_id == message_id
            ).delete()
            
            session.delete(message)
            
            # Reorder remaining messages
            campaign_id = message.campaign_id
            remaining = session.query(CampaignMessage).filter(
                CampaignMessage.campaign_id == campaign_id
            ).order_by(CampaignMessage.sequence_order).all()
            
            for i, msg in enumerate(remaining, 1):
                msg.sequence_order = i
            
            return True
    
    def reorder_messages(self, campaign_id: int, message_order: List[int]) -> bool:
        """Reorder campaign messages by providing list of message IDs in new order"""
        with get_db_session() as session:
            for i, msg_id in enumerate(message_order, 1):
                message = session.query(CampaignMessage).filter(
                    CampaignMessage.id == msg_id,
                    CampaignMessage.campaign_id == campaign_id
                ).first()
                if message:
                    message.sequence_order = i
            
            return True
    
    # =========================================================================
    # A/B TESTING
    # =========================================================================
    
    def setup_ab_test(self, message_id: int, variant_b_body: str) -> Optional[dict]:
        """Set up A/B test for a message (variant A = original message_body)"""
        with get_db_session() as session:
            message = session.query(CampaignMessage).filter(CampaignMessage.id == message_id).first()
            if not message:
                return None
            
            # Check if A/B test already exists
            existing = session.query(CampaignABTest).filter(
                CampaignABTest.campaign_message_id == message_id
            ).first()
            
            if existing:
                existing.variant_b_body = variant_b_body
                session.flush()
                return existing.to_dict()
            
            ab_test = CampaignABTest(
                campaign_id=message.campaign_id,
                campaign_message_id=message_id,
                variant_b_body=variant_b_body
            )
            session.add(ab_test)
            
            message.has_ab_test = True
            session.flush()
            
            return ab_test.to_dict()
    
    def remove_ab_test(self, message_id: int) -> bool:
        """Remove A/B test from a message"""
        with get_db_session() as session:
            ab_test = session.query(CampaignABTest).filter(
                CampaignABTest.campaign_message_id == message_id
            ).first()
            
            if not ab_test:
                return False
            
            message = session.query(CampaignMessage).filter(
                CampaignMessage.id == message_id
            ).first()
            if message:
                message.has_ab_test = False
            
            session.delete(ab_test)
            return True
    
    # =========================================================================
    # ENROLLMENT
    # =========================================================================
    
    def preview_enrollment(self, filter_criteria: dict, limit: int = 50, offset: int = 0) -> Tuple[int, List[dict]]:
        """Preview contacts that would be enrolled based on filter criteria"""
        # Get total count first
        all_contacts = get_all_contacts(
            mobile_only=True,
            limit=10000,  # Max for counting
            **filter_criteria
        )
        
        total_count = len(all_contacts)
        
        # Get slice for display
        sample = all_contacts[offset:offset + limit]
        
        return total_count, sample
    
    def check_overlap(self, phone_numbers: List[str]) -> Dict[str, List[str]]:
        """Check if any phone numbers are already enrolled in active campaigns"""
        session = get_session()
        try:
            overlaps = {}
            
            active_enrollments = session.query(CampaignEnrollment, Campaign).join(
                Campaign, CampaignEnrollment.campaign_id == Campaign.id
            ).filter(
                CampaignEnrollment.phone_number.in_(phone_numbers),
                Campaign.status.in_([CampaignStatus.ACTIVE.value, CampaignStatus.PAUSED.value]),
                CampaignEnrollment.status.in_([EnrollmentStatus.ACTIVE.value, EnrollmentStatus.ENGAGED.value])
            ).all()
            
            for enrollment, campaign in active_enrollments:
                if campaign.name not in overlaps:
                    overlaps[campaign.name] = []
                overlaps[campaign.name].append(enrollment.phone_number)
            
            return overlaps
        finally:
            session.close()
    
    def enroll_contacts(
        self, 
        campaign_id: int, 
        contacts: List[dict] = None,
        use_filters: bool = False,
        exclude_phones: List[str] = None,
        manual_contacts: List[dict] = None
    ) -> int:
        """
        Enroll contacts in a campaign.
        
        For snapshot: Pass contacts list directly
        For dynamic: Set use_filters=True to use campaign's filter_criteria
        manual_contacts: Additional contacts to add regardless of filters
        """
        session = get_session()
        try:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                raise ValueError("Campaign not found")
            
            # Get contacts to enroll
            all_contacts = []
            
            if use_filters and campaign.filter_criteria:
                filter_criteria = json.loads(campaign.filter_criteria)
                filtered = get_all_contacts(mobile_only=True, **filter_criteria)
                if filtered:
                    all_contacts.extend(filtered)
            elif contacts:
                all_contacts.extend(contacts)
            
            # Add manual contacts
            if manual_contacts:
                all_contacts.extend(manual_contacts)
            
            if not all_contacts:
                return 0
            
            exclude_phones = set(exclude_phones or [])
            
            # Check if campaign has A/B tests to assign variants
            has_ab_test = session.query(CampaignMessage).filter(
                CampaignMessage.campaign_id == campaign_id,
                CampaignMessage.has_ab_test == True
            ).count() > 0
            
            enrolled_count = 0
            enrolled_phones = set()  # Track to avoid duplicates from filters + manual
            
            for contact in all_contacts:
                phone = normalize_phone(contact.get('phone') or contact.get('phone_number') or contact.get('phone_normalized'))
                
                if not phone or phone in exclude_phones or phone in enrolled_phones:
                    continue
                
                # Check if already enrolled
                existing = session.query(CampaignEnrollment).filter(
                    CampaignEnrollment.campaign_id == campaign_id,
                    CampaignEnrollment.phone_number == phone
                ).first()
                
                if existing:
                    continue
                
                # Assign A/B variant randomly if campaign has A/B tests
                ab_variant = random.choice(['A', 'B']) if has_ab_test else None
                
                enrollment = CampaignEnrollment(
                    campaign_id=campaign_id,
                    phone_number=phone,
                    contact_name=contact.get('name'),
                    contact_company=contact.get('company'),
                    ab_variant=ab_variant,
                    status=EnrollmentStatus.ACTIVE.value
                )
                session.add(enrollment)
                enrolled_phones.add(phone)
                enrolled_count += 1
            
            session.commit()
            return enrolled_count
        finally:
            session.close()
    
    def get_enrollments(
        self, 
        campaign_id: int, 
        status: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[dict], int]:
        """Get campaign enrollments with optional status filter"""
        session = get_session()
        try:
            query = session.query(CampaignEnrollment).filter(
                CampaignEnrollment.campaign_id == campaign_id
            )
            
            if status:
                query = query.filter(CampaignEnrollment.status == status)
            
            total = query.count()
            enrollments = query.order_by(
                CampaignEnrollment.enrolled_at.desc()
            ).offset(offset).limit(limit).all()
            
            return [e.to_dict() for e in enrollments], total
        finally:
            session.close()
    
    # =========================================================================
    # CAMPAIGN LIFECYCLE
    # =========================================================================
    
    def start_campaign(self, campaign_id: int) -> dict:
        """Start a campaign - schedules first message for all enrollments"""
        with get_db_session() as session:
            campaign = session.query(Campaign).options(
                joinedload(Campaign.messages),
                joinedload(Campaign.enrollments)
            ).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                raise ValueError("Campaign not found")
            
            if campaign.status not in [CampaignStatus.DRAFT.value, CampaignStatus.PAUSED.value]:
                raise ValueError(f"Cannot start campaign in {campaign.status} status")
            
            if not campaign.messages:
                raise ValueError("Campaign has no messages")
            
            if not campaign.enrollments:
                raise ValueError("Campaign has no enrolled contacts")
            
            campaign.status = CampaignStatus.ACTIVE.value
            campaign.started_at = datetime.utcnow()
            campaign.paused_at = None
            
            session.flush()
            
            return campaign.to_dict()
    
    def pause_campaign(self, campaign_id: int) -> dict:
        """Pause an active campaign"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                raise ValueError("Campaign not found")
            
            if campaign.status != CampaignStatus.ACTIVE.value:
                raise ValueError("Can only pause active campaigns")
            
            campaign.status = CampaignStatus.PAUSED.value
            campaign.paused_at = datetime.utcnow()
            
            session.flush()
            
            return campaign.to_dict()
    
    def resume_campaign(self, campaign_id: int) -> dict:
        """Resume a paused campaign"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                raise ValueError("Campaign not found")
            
            if campaign.status != CampaignStatus.PAUSED.value:
                raise ValueError("Can only resume paused campaigns")
            
            campaign.status = CampaignStatus.ACTIVE.value
            campaign.paused_at = None
            
            session.flush()
            
            return campaign.to_dict()
    
    def complete_campaign(self, campaign_id: int) -> dict:
        """Mark a campaign as completed"""
        with get_db_session() as session:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                raise ValueError("Campaign not found")
            
            campaign.status = CampaignStatus.COMPLETED.value
            campaign.completed_at = datetime.utcnow()
            
            # Set response tracking window (30 days from now)
            campaign.response_tracking_ends_at = datetime.utcnow() + timedelta(days=30)
            
            # Mark all active enrollments as completed
            session.query(CampaignEnrollment).filter(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.status == EnrollmentStatus.ACTIVE.value
            ).update({
                CampaignEnrollment.status: EnrollmentStatus.COMPLETED.value
            })
            
            session.flush()
            
            return campaign.to_dict()
    
    # =========================================================================
    # RESPONSE TRACKING
    # =========================================================================
    
    def record_response(self, phone_number: str, message_body: str) -> List[dict]:
        """
        Record a response from a phone number.
        Updates all active campaign enrollments for this phone.
        Returns list of affected campaigns.
        """
        session = get_session()
        try:
            phone = normalize_phone(phone_number)
            now = datetime.utcnow()
            affected_campaigns = []
            
            # Check for opt-out keywords
            is_opt_out = any(
                keyword in message_body.lower() 
                for keyword in OPT_OUT_KEYWORDS
            )
            
            # Find all active/engaged enrollments for this phone
            enrollments = session.query(CampaignEnrollment).join(
                Campaign, CampaignEnrollment.campaign_id == Campaign.id
            ).filter(
                CampaignEnrollment.phone_number == phone,
                CampaignEnrollment.status.in_([EnrollmentStatus.ACTIVE.value, EnrollmentStatus.ENGAGED.value]),
                or_(
                    Campaign.status.in_([CampaignStatus.ACTIVE.value, CampaignStatus.PAUSED.value]),
                    and_(
                        Campaign.status == CampaignStatus.COMPLETED.value,
                        Campaign.response_tracking_ends_at > now
                    )
                )
            ).all()
            
            for enrollment in enrollments:
                if is_opt_out:
                    enrollment.status = EnrollmentStatus.OPTED_OUT.value
                    enrollment.opted_out_at = now
                    enrollment.opted_out_keyword = message_body[:50]  # Store what they said
                else:
                    # Mark as engaged if first response
                    if not enrollment.first_response_at:
                        enrollment.first_response_at = now
                        enrollment.first_response_message_id = enrollment.last_message_id
                    
                    enrollment.status = EnrollmentStatus.ENGAGED.value
                    enrollment.response_count = (enrollment.response_count or 0) + 1
                
                # Update campaign sends to mark response received
                if enrollment.last_message_id:
                    last_send = session.query(CampaignSend).filter(
                        CampaignSend.enrollment_id == enrollment.id,
                        CampaignSend.campaign_message_id == enrollment.last_message_id,
                        CampaignSend.response_received == False
                    ).order_by(CampaignSend.sent_at.desc()).first()
                    
                    if last_send:
                        last_send.response_received = True
                        last_send.response_at = now
                
                affected_campaigns.append({
                    'campaign_id': enrollment.campaign_id,
                    'enrollment_id': enrollment.id,
                    'is_opt_out': is_opt_out
                })
            
            session.commit()
            return affected_campaigns
        finally:
            session.close()
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_campaign_stats(self, campaign_id: int) -> dict:
        """Get detailed statistics for a campaign"""
        session = get_session()
        try:
            campaign = session.query(Campaign).options(
                joinedload(Campaign.messages).joinedload(CampaignMessage.sends),
                joinedload(Campaign.enrollments)
            ).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                return None
            
            stats = campaign.get_stats()
            
            # Per-message stats
            message_stats = []
            for msg in sorted(campaign.messages, key=lambda m: m.sequence_order):
                msg_stat = msg.get_stats()
                msg_stat['sequence_order'] = msg.sequence_order
                msg_stat['message_id'] = msg.id
                
                # A/B test stats if applicable
                if msg.has_ab_test and msg.ab_test:
                    msg_stat['ab_test'] = msg.ab_test.to_dict()
                
                message_stats.append(msg_stat)
            
            stats['messages'] = message_stats
            
            # Get engaged contacts details
            engaged = session.query(CampaignEnrollment).filter(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.first_response_at.isnot(None)
            ).order_by(CampaignEnrollment.first_response_at.desc()).limit(50).all()
            
            stats['engaged_contacts'] = [e.to_dict() for e in engaged]
            
            # Get opted out contacts
            opted_out = session.query(CampaignEnrollment).filter(
                CampaignEnrollment.campaign_id == campaign_id,
                CampaignEnrollment.status == EnrollmentStatus.OPTED_OUT.value
            ).order_by(CampaignEnrollment.opted_out_at.desc()).all()
            
            stats['opted_out_contacts'] = [e.to_dict() for e in opted_out]
            
            return stats
        finally:
            session.close()


# Singleton instance
campaign_service = CampaignService()
