from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import enum
import logging

from config import Config

logger = logging.getLogger(__name__)

# Create engine with connection pooling for PostgreSQL reliability
engine_args = {
    'echo': False,
    'pool_pre_ping': True,  # Test connections before using them
}

# Add connection pool settings for PostgreSQL
if Config.DATABASE_URL and Config.DATABASE_URL.startswith('postgresql'):
    engine_args.update({
        'poolclass': QueuePool,
        'pool_size': 5,
        'max_overflow': 10,
        'pool_recycle': 300,  # Recycle connections every 5 minutes
    })

engine = create_engine(Config.DATABASE_URL, **engine_args)
Session = sessionmaker(bind=engine)
Base = declarative_base()


class MessageStatus(enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"


class MessageDirection(enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


# NOTE: Contacts are NOT stored locally - they are queried live from the leads database.
# This keeps data in sync and avoids duplication. See leads_service.py for contact queries.


class Message(Base):
    """
    SMS message record.
    Links to contacts via phone_number (contacts live in leads database).
    """
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    twilio_sid = Column(String(50), unique=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)  # Links to leads DB by phone
    body = Column(Text, nullable=False)
    direction = Column(String(20), default=MessageDirection.OUTBOUND.value)
    status = Column(String(20), default=MessageStatus.PENDING.value)
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    
    def to_dict(self, contact=None):
        """Convert to dict. Contact info is fetched separately from leads DB."""
        return {
            'id': self.id,
            'twilio_sid': self.twilio_sid,
            'phone_number': self.phone_number,
            'body': self.body,
            'direction': self.direction,
            'status': self.status,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'error_message': self.error_message,
            'contact': contact
        }


class ScheduledBulkMessage(Base):
    """Bulk message scheduling - ONLY sends to explicitly specified recipients"""
    __tablename__ = 'scheduled_bulk_messages'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    # Store the exact phone numbers to send to (JSON array)
    # This is CRITICAL for safety - we NEVER send to "all contacts"
    recipient_phones = Column(Text, nullable=False)  # JSON array of phone numbers
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='pending')  # pending, in_progress, completed, cancelled, failed, paused
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Recurring schedule fields
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(String(20), nullable=True)  # daily, weekly, monthly
    recurrence_days = Column(String(50), nullable=True)  # For weekly: "mon,wed,fri" etc.
    recurrence_end_date = Column(DateTime, nullable=True)  # Optional end date (null = forever)
    last_sent_at = Column(DateTime, nullable=True)  # Track last successful send
    send_count = Column(Integer, default=0)  # Total times this schedule has sent
    
    def to_dict(self):
        import json
        phones = []
        try:
            phones = json.loads(self.recipient_phones) if self.recipient_phones else []
        except:
            pass
        return {
            'id': self.id,
            'name': self.name,
            'body': self.body,
            'recipient_count': len(phones),
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'status': self.status,
            'total_recipients': self.total_recipients,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_recurring': self.is_recurring,
            'recurrence_type': self.recurrence_type,
            'recurrence_days': self.recurrence_days,
            'recurrence_end_date': self.recurrence_end_date.isoformat() if self.recurrence_end_date else None,
            'last_sent_at': self.last_sent_at.isoformat() if self.last_sent_at else None,
            'send_count': self.send_count
        }


class MessageTemplate(Base):
    """Reusable message templates"""
    __tablename__ = 'message_templates'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'body': self.body,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ManualContact(Base):
    """Manually added contacts (separate from scraped leads)"""
    __tablename__ = 'manual_contacts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)
    company = Column(String(255), nullable=True)
    role = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone_number,
            'phone_number': self.phone_number,
            'phone_normalized': self.phone_number,  # Already normalized in E.164 format
            'company': self.company,
            'role': self.role,
            'notes': self.notes,
            'source': 'manual',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ContactNote(Base):
    """Notes for leads DB contacts (since we can't edit the leads DB directly)"""
    __tablename__ = 'contact_notes'
    
    id = Column(Integer, primary_key=True)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)  # Links to leads contact
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'phone_number': self.phone_number,
            'notes': self.notes,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# =============================================================================
# CAMPAIGN TABLES
# =============================================================================

class CampaignStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class EnrollmentStatus(enum.Enum):
    ACTIVE = "active"
    ENGAGED = "engaged"  # Has responded at least once
    COMPLETED = "completed"  # Received all messages
    OPTED_OUT = "opted_out"  # Said STOP or similar


class Campaign(Base):
    """
    A campaign is a sequence of scheduled messages sent to a group of contacts.
    Supports both snapshot (fixed list) and dynamic (re-filter each time) enrollment.
    """
    __tablename__ = 'campaigns'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CampaignStatus.DRAFT.value)
    
    # Enrollment type: 'snapshot' locks contacts at start, 'dynamic' re-filters before each message
    enrollment_type = Column(String(20), default='snapshot')
    
    # JSON storing filter criteria used to select contacts
    # e.g., {"borough": "BROOKLYN", "role": "Owner", "job_type": "NB"}
    filter_criteria = Column(Text, nullable=True)
    
    # Default time of day to send messages (EST)
    default_send_time = Column(String(10), default='11:00')  # HH:MM format
    
    # Tracking
    created_by = Column(Integer, nullable=True)  # User ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Response tracking window (30 days after completion)
    response_tracking_ends_at = Column(DateTime, nullable=True)
    
    # Relationships
    messages = relationship("CampaignMessage", back_populates="campaign", order_by="CampaignMessage.sequence_order")
    enrollments = relationship("CampaignEnrollment", back_populates="campaign")
    
    def to_dict(self, include_stats=False):
        import json
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'enrollment_type': self.enrollment_type,
            'filter_criteria': json.loads(self.filter_criteria) if self.filter_criteria else {},
            'default_send_time': self.default_send_time,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'paused_at': self.paused_at.isoformat() if self.paused_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'message_count': len(self.messages) if self.messages else 0
        }
        if include_stats:
            result['stats'] = self.get_stats()
        return result
    
    def get_stats(self):
        """Calculate campaign statistics"""
        total_enrolled = len(self.enrollments) if self.enrollments else 0
        engaged = sum(1 for e in self.enrollments if e.status == EnrollmentStatus.ENGAGED.value or e.first_response_at) if self.enrollments else 0
        opted_out = sum(1 for e in self.enrollments if e.status == EnrollmentStatus.OPTED_OUT.value) if self.enrollments else 0
        completed = sum(1 for e in self.enrollments if e.status == EnrollmentStatus.COMPLETED.value) if self.enrollments else 0
        
        return {
            'total_enrolled': total_enrolled,
            'engaged': engaged,
            'engaged_rate': round((engaged / total_enrolled * 100), 1) if total_enrolled > 0 else 0,
            'opted_out': opted_out,
            'completed': completed
        }


class CampaignMessage(Base):
    """
    A single message in a campaign sequence.
    Each message can have its own timing, follow-up settings, and A/B test variants.
    """
    __tablename__ = 'campaign_messages'
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    
    # Position in the sequence (1, 2, 3, ...)
    sequence_order = Column(Integer, nullable=False)
    
    # Message content (supports template variables: {name}, {company}, {address}, etc.)
    message_body = Column(Text, nullable=False)
    
    # Timing: days to wait after previous message (0 for first message = send immediately on start)
    days_after_previous = Column(Integer, default=0)
    
    # Optional: override campaign's default send time for this message
    send_time = Column(String(10), nullable=True)  # HH:MM format, NULL = use campaign default
    
    # Follow-up settings
    enable_followup = Column(Boolean, default=False)
    followup_days = Column(Integer, default=3)  # Days to wait before follow-up
    followup_body = Column(Text, default="Just following up on my last message. Let me know if you have any questions!")
    
    # A/B Testing
    has_ab_test = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    campaign = relationship("Campaign", back_populates="messages")
    ab_test = relationship("CampaignABTest", back_populates="campaign_message", uselist=False)
    sends = relationship("CampaignSend", back_populates="campaign_message")
    
    def to_dict(self, include_stats=False):
        result = {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'sequence_order': self.sequence_order,
            'message_body': self.message_body,
            'days_after_previous': self.days_after_previous,
            'send_time': self.send_time,
            'enable_followup': self.enable_followup,
            'followup_days': self.followup_days,
            'followup_body': self.followup_body,
            'has_ab_test': self.has_ab_test,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if self.ab_test:
            result['ab_test'] = self.ab_test.to_dict()
        if include_stats:
            result['stats'] = self.get_stats()
        return result
    
    def get_stats(self):
        """Calculate message-level statistics"""
        if not self.sends:
            return {'sent': 0, 'delivered': 0, 'responses': 0, 'followups_sent': 0}
        
        scheduled_sends = [s for s in self.sends if s.message_type == 'scheduled']
        followup_sends = [s for s in self.sends if s.message_type == 'followup']
        
        return {
            'sent': len(scheduled_sends),
            'delivered': sum(1 for s in scheduled_sends if s.status in ['delivered', 'sent']),
            'responses': sum(1 for s in scheduled_sends if s.response_received),
            'followups_sent': len(followup_sends),
            'followup_responses': sum(1 for s in followup_sends if s.response_received)
        }


class CampaignABTest(Base):
    """
    A/B test configuration for a campaign message.
    Contacts are randomly split 50/50 between variant A and B.
    """
    __tablename__ = 'campaign_ab_tests'
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    campaign_message_id = Column(Integer, ForeignKey('campaign_messages.id'), nullable=False, unique=True)
    
    # Variant A is the original message_body from campaign_message
    # Variant B is stored here
    variant_b_body = Column(Text, nullable=False)
    
    # Tracking (auto-calculated from sends, but cached for performance)
    variant_a_sent = Column(Integer, default=0)
    variant_b_sent = Column(Integer, default=0)
    variant_a_responses = Column(Integer, default=0)
    variant_b_responses = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    campaign_message = relationship("CampaignMessage", back_populates="ab_test")
    
    def to_dict(self):
        a_rate = round((self.variant_a_responses / self.variant_a_sent * 100), 1) if self.variant_a_sent > 0 else 0
        b_rate = round((self.variant_b_responses / self.variant_b_sent * 100), 1) if self.variant_b_sent > 0 else 0
        
        return {
            'id': self.id,
            'campaign_message_id': self.campaign_message_id,
            'variant_b_body': self.variant_b_body,
            'variant_a_sent': self.variant_a_sent,
            'variant_b_sent': self.variant_b_sent,
            'variant_a_responses': self.variant_a_responses,
            'variant_b_responses': self.variant_b_responses,
            'variant_a_response_rate': a_rate,
            'variant_b_response_rate': b_rate,
            'winner': 'A' if a_rate > b_rate else ('B' if b_rate > a_rate else 'tie')
        }


class CampaignEnrollment(Base):
    """
    Tracks each contact's enrollment and progress through a campaign.
    """
    __tablename__ = 'campaign_enrollments'
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    
    # Contact info (snapshot at enrollment time)
    phone_number = Column(String(20), nullable=False, index=True)
    contact_name = Column(String(255), nullable=True)
    contact_company = Column(String(255), nullable=True)
    
    # A/B test assignment (if campaign has A/B tests)
    ab_variant = Column(String(1), nullable=True)  # 'A' or 'B'
    
    # Progress tracking
    current_step = Column(Integer, default=0)  # Which message they're on (0 = not started yet)
    status = Column(String(20), default=EnrollmentStatus.ACTIVE.value)
    
    # Timestamps
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)
    last_message_id = Column(Integer, nullable=True)  # campaign_message_id
    
    # Response tracking
    first_response_at = Column(DateTime, nullable=True)
    first_response_message_id = Column(Integer, nullable=True)  # Which message they first responded to
    response_count = Column(Integer, default=0)
    
    # Opt-out tracking (for display purposes - Twilio handles actual blocking)
    opted_out_at = Column(DateTime, nullable=True)
    opted_out_keyword = Column(String(50), nullable=True)  # What they said: "STOP", "stop", etc.
    
    # Unique constraint: one enrollment per phone per campaign
    __table_args__ = (
        # UniqueConstraint('campaign_id', 'phone_number', name='unique_campaign_enrollment'),
    )
    
    # Relationships
    campaign = relationship("Campaign", back_populates="enrollments")
    sends = relationship("CampaignSend", back_populates="enrollment")
    
    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'phone_number': self.phone_number,
            'contact_name': self.contact_name,
            'contact_company': self.contact_company,
            'ab_variant': self.ab_variant,
            'current_step': self.current_step,
            'status': self.status,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'last_message_id': self.last_message_id,
            'first_response_at': self.first_response_at.isoformat() if self.first_response_at else None,
            'first_response_message_id': self.first_response_message_id,
            'response_count': self.response_count,
            'opted_out_at': self.opted_out_at.isoformat() if self.opted_out_at else None,
            'opted_out_keyword': self.opted_out_keyword
        }


class CampaignSend(Base):
    """
    Log of every message sent as part of a campaign.
    Provides audit trail and enables detailed analytics.
    """
    __tablename__ = 'campaign_sends'
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False, index=True)
    campaign_message_id = Column(Integer, ForeignKey('campaign_messages.id'), nullable=False)
    enrollment_id = Column(Integer, ForeignKey('campaign_enrollments.id'), nullable=False)
    
    phone_number = Column(String(20), nullable=False, index=True)
    
    # Type: 'scheduled' for main message, 'followup' for follow-up
    message_type = Column(String(20), nullable=False)
    
    # Actual message sent (after variable substitution)
    message_body = Column(Text, nullable=False)
    
    # A/B variant used (if applicable)
    ab_variant = Column(String(1), nullable=True)
    
    # Twilio tracking
    twilio_sid = Column(String(50), nullable=True, index=True)
    status = Column(String(20), default='pending')  # pending, queued, sent, delivered, failed
    error_message = Column(Text, nullable=True)
    
    # Timing
    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    
    # Response tracking
    response_received = Column(Boolean, default=False)
    response_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    campaign_message = relationship("CampaignMessage", back_populates="sends")
    enrollment = relationship("CampaignEnrollment", back_populates="sends")
    
    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'campaign_message_id': self.campaign_message_id,
            'enrollment_id': self.enrollment_id,
            'phone_number': self.phone_number,
            'message_type': self.message_type,
            'message_body': self.message_body,
            'ab_variant': self.ab_variant,
            'twilio_sid': self.twilio_sid,
            'status': self.status,
            'error_message': self.error_message,
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'response_received': self.response_received,
            'response_at': self.response_at.isoformat() if self.response_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# =============================================================================
# EMAIL TABLES (Instantly-style cold email)
# =============================================================================

class EmailAccountStatus(enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    WARMING = "warming"


class EmailAccount(Base):
    """
    A connected sending mailbox (Gmail / Workspace) used for rotation.
    Stores OAuth refresh token; access tokens are minted on demand.
    """
    __tablename__ = 'email_accounts'

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)   # "From" name on outbound
    provider = Column(String(20), default='gmail')      # gmail | google_workspace

    # OAuth tokens
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    scopes = Column(Text, nullable=True)

    # Sending policy
    daily_cap = Column(Integer, default=50)             # Max sends/day for this inbox
    min_delay_seconds = Column(Integer, default=45)     # Jitter floor between sends
    max_delay_seconds = Column(Integer, default=180)    # Jitter ceiling
    sends_today = Column(Integer, default=0)            # Rolling counter, reset daily
    sends_today_date = Column(String(10), nullable=True) # YYYY-MM-DD of the counter

    # Health
    status = Column(String(20), default=EmailAccountStatus.ACTIVE.value)
    bounce_count_7d = Column(Integer, default=0)        # For deliverability scoring
    complaint_count_7d = Column(Integer, default=0)
    last_send_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    # Auto-pause guardrail: if bounce rate over the trailing window exceeds this
    # percent (with a minimum sample), the inbox is paused automatically.
    bounce_pause_threshold = Column(Integer, default=8)  # percent
    auto_paused = Column(Boolean, default=False)         # True if paused by the guardrail

    # Reply polling (Gmail History API cursor)
    history_id = Column(String(50), nullable=True)
    last_polled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'display_name': self.display_name,
            'provider': self.provider,
            'daily_cap': self.daily_cap,
            'min_delay_seconds': self.min_delay_seconds,
            'max_delay_seconds': self.max_delay_seconds,
            'sends_today': self.sends_today if self.sends_today_date == datetime.utcnow().strftime('%Y-%m-%d') else 0,
            'status': self.status,
            'bounce_count_7d': self.bounce_count_7d,
            'complaint_count_7d': self.complaint_count_7d,
            'last_send_at': self.last_send_at.isoformat() if self.last_send_at else None,
            'last_error': self.last_error,
            'bounce_pause_threshold': self.bounce_pause_threshold,
            'auto_paused': bool(self.auto_paused),
            'has_refresh_token': bool(self.refresh_token),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EmailCampaign(Base):
    """
    An email campaign (sequence of emails) — mirror of Campaign but email-side.
    Kept separate from the SMS Campaign table to avoid schema bloat and let
    each channel evolve independently.
    """
    __tablename__ = 'email_campaigns'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CampaignStatus.DRAFT.value)

    # Recipient source
    enrollment_type = Column(String(20), default='snapshot')  # snapshot | dynamic
    filter_criteria = Column(Text, nullable=True)             # JSON, applied to owner_contacts

    # Send policy
    send_window_start = Column(String(10), default='09:00')   # Eastern, HH:MM
    send_window_end = Column(String(10), default='17:00')
    send_days = Column(String(50), default='mon,tue,wed,thu,fri')  # CSV weekdays
    timezone = Column(String(50), default='America/New_York')

    # Inbox rotation
    sending_account_ids = Column(Text, nullable=True)         # JSON array of EmailAccount ids
    rotation_strategy = Column(String(20), default='round_robin')  # round_robin | least_used

    # AI personalization toggle
    ai_personalization = Column(Boolean, default=False)
    ai_prompt = Column(Text, nullable=True)                   # Used to build per-contact opener

    # Tracking
    track_opens = Column(Boolean, default=True)
    track_clicks = Column(Boolean, default=True)

    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    messages = relationship("EmailCampaignMessage", back_populates="campaign", order_by="EmailCampaignMessage.sequence_order", cascade="all, delete-orphan")
    enrollments = relationship("EmailEnrollment", back_populates="campaign", cascade="all, delete-orphan")

    def to_dict(self, include_stats=False):
        import json
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'enrollment_type': self.enrollment_type,
            'filter_criteria': json.loads(self.filter_criteria) if self.filter_criteria else {},
            'send_window_start': self.send_window_start,
            'send_window_end': self.send_window_end,
            'send_days': self.send_days,
            'timezone': self.timezone,
            'sending_account_ids': json.loads(self.sending_account_ids) if self.sending_account_ids else [],
            'rotation_strategy': self.rotation_strategy,
            'ai_personalization': self.ai_personalization,
            'ai_prompt': self.ai_prompt,
            'track_opens': self.track_opens,
            'track_clicks': self.track_clicks,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'paused_at': self.paused_at.isoformat() if self.paused_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'message_count': len(self.messages) if self.messages else 0,
        }
        if include_stats:
            result['stats'] = self.get_stats()
        return result

    def get_stats(self):
        if not self.enrollments:
            return {
                'total_enrolled': 0, 'sent': 0, 'opens': 0, 'clicks': 0,
                'replies': 0, 'bounces': 0, 'unsubscribed': 0,
                'open_rate': 0, 'reply_rate': 0, 'bounce_rate': 0,
            }
        total = len(self.enrollments)
        replied = sum(1 for e in self.enrollments if e.first_reply_at)
        bounced = sum(1 for e in self.enrollments if e.status == 'bounced')
        unsubscribed = sum(1 for e in self.enrollments if e.status == 'unsubscribed')
        opens = sum(1 for e in self.enrollments if e.open_count > 0)
        clicks = sum(1 for e in self.enrollments if e.click_count > 0)
        sent = sum(1 for e in self.enrollments if e.current_step > 0)
        return {
            'total_enrolled': total,
            'sent': sent,
            'opens': opens,
            'clicks': clicks,
            'replies': replied,
            'bounces': bounced,
            'unsubscribed': unsubscribed,
            'open_rate': round((opens / sent * 100), 1) if sent else 0,
            'reply_rate': round((replied / sent * 100), 1) if sent else 0,
            'bounce_rate': round((bounced / sent * 100), 1) if sent else 0,
            'click_rate': round((clicks / sent * 100), 1) if sent else 0,
        }


class EmailCampaignMessage(Base):
    """A single step in an email sequence."""
    __tablename__ = 'email_campaign_messages'

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('email_campaigns.id'), nullable=False)
    sequence_order = Column(Integer, nullable=False)

    subject = Column(Text, nullable=False)
    preheader = Column(Text, nullable=True)               # Hidden preview text
    body_html = Column(Text, nullable=False)              # Sanitized HTML
    body_text = Column(Text, nullable=True)               # Plain fallback (auto-derived if null)

    days_after_previous = Column(Integer, default=0)      # 0 for first step
    same_thread = Column(Boolean, default=True)           # Reply to prev for follow-ups

    # A/B test on subject line (lowest-friction)
    has_ab_test = Column(Boolean, default=False)
    subject_variant_b = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("EmailCampaign", back_populates="messages")
    sends = relationship("EmailSend", back_populates="message", cascade="all, delete-orphan")

    def to_dict(self, include_stats=False):
        result = {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'sequence_order': self.sequence_order,
            'subject': self.subject,
            'preheader': self.preheader,
            'body_html': self.body_html,
            'body_text': self.body_text,
            'days_after_previous': self.days_after_previous,
            'same_thread': self.same_thread,
            'has_ab_test': self.has_ab_test,
            'subject_variant_b': self.subject_variant_b,
        }
        if include_stats and self.sends:
            sent = len(self.sends)
            opens = sum(1 for s in self.sends if s.opened_at)
            clicks = sum(1 for s in self.sends if s.clicked_at)
            replies = sum(1 for s in self.sends if s.replied_at)
            result['stats'] = {
                'sent': sent,
                'opens': opens,
                'clicks': clicks,
                'replies': replies,
                'open_rate': round((opens / sent * 100), 1) if sent else 0,
                'reply_rate': round((replies / sent * 100), 1) if sent else 0,
            }
        return result


class EmailEnrollment(Base):
    """A recipient's progress through an email campaign."""
    __tablename__ = 'email_enrollments'

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('email_campaigns.id'), nullable=False)

    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    extra_data = Column(Text, nullable=True)                # JSON: owner_name, permit_no, address, etc.

    # AI personalization output, generated once at enrollment (or first send)
    ai_first_line = Column(Text, nullable=True)
    ai_generated_at = Column(DateTime, nullable=True)

    # A/B assignment
    ab_variant = Column(String(1), nullable=True)

    # Progress
    current_step = Column(Integer, default=0)
    status = Column(String(20), default=EnrollmentStatus.ACTIVE.value)

    # Gmail threading — preserve thread across follow-ups
    gmail_thread_id = Column(String(100), nullable=True)
    gmail_message_id_header = Column(String(255), nullable=True)  # Original Message-ID for In-Reply-To

    enrolled_at = Column(DateTime, default=datetime.utcnow)
    last_sent_at = Column(DateTime, nullable=True)
    next_send_at = Column(DateTime, nullable=True)

    # Engagement tracking
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    first_open_at = Column(DateTime, nullable=True)
    first_click_at = Column(DateTime, nullable=True)
    first_reply_at = Column(DateTime, nullable=True)

    # Termination
    bounced_at = Column(DateTime, nullable=True)
    unsubscribed_at = Column(DateTime, nullable=True)
    unsubscribe_token = Column(String(64), nullable=True, unique=True, index=True)

    campaign = relationship("EmailCampaign", back_populates="enrollments")
    sends = relationship("EmailSend", back_populates="enrollment", cascade="all, delete-orphan")

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'email': self.email,
            'name': self.name,
            'company': self.company,
            'extra_data': json.loads(self.extra_data) if self.extra_data else {},
            'ai_first_line': self.ai_first_line,
            'ab_variant': self.ab_variant,
            'current_step': self.current_step,
            'status': self.status,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None,
            'last_sent_at': self.last_sent_at.isoformat() if self.last_sent_at else None,
            'next_send_at': self.next_send_at.isoformat() if self.next_send_at else None,
            'open_count': self.open_count,
            'click_count': self.click_count,
            'first_open_at': self.first_open_at.isoformat() if self.first_open_at else None,
            'first_reply_at': self.first_reply_at.isoformat() if self.first_reply_at else None,
            'bounced_at': self.bounced_at.isoformat() if self.bounced_at else None,
            'unsubscribed_at': self.unsubscribed_at.isoformat() if self.unsubscribed_at else None,
        }


class EmailSend(Base):
    """One outbound email — audit trail."""
    __tablename__ = 'email_sends'

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('email_campaigns.id'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('email_campaign_messages.id'), nullable=False)
    enrollment_id = Column(Integer, ForeignKey('email_enrollments.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('email_accounts.id'), nullable=True)  # Which inbox sent it

    to_email = Column(String(255), nullable=False, index=True)
    from_email = Column(String(255), nullable=False)
    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)                # Final rendered content
    body_text = Column(Text, nullable=True)
    ab_variant = Column(String(1), nullable=True)

    # Provider tracking
    gmail_message_id = Column(String(100), nullable=True, index=True)
    gmail_thread_id = Column(String(100), nullable=True, index=True)
    message_id_header = Column(String(255), nullable=True)  # RFC Message-ID

    status = Column(String(20), default='pending')          # pending|sent|failed|bounced
    error_message = Column(Text, nullable=True)

    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    # Engagement (latest)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    bounced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("EmailCampaignMessage", back_populates="sends")
    enrollment = relationship("EmailEnrollment", back_populates="sends")

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'message_id': self.message_id,
            'enrollment_id': self.enrollment_id,
            'account_id': self.account_id,
            'to_email': self.to_email,
            'from_email': self.from_email,
            'subject': self.subject,
            'ab_variant': self.ab_variant,
            'gmail_message_id': self.gmail_message_id,
            'gmail_thread_id': self.gmail_thread_id,
            'status': self.status,
            'error_message': self.error_message,
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'replied_at': self.replied_at.isoformat() if self.replied_at else None,
            'bounced_at': self.bounced_at.isoformat() if self.bounced_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EmailEvent(Base):
    """Event log: open, click, reply, bounce, unsubscribe. Useful for timelines."""
    __tablename__ = 'email_events'

    id = Column(Integer, primary_key=True)
    send_id = Column(Integer, ForeignKey('email_sends.id'), nullable=True, index=True)
    enrollment_id = Column(Integer, ForeignKey('email_enrollments.id'), nullable=True, index=True)
    campaign_id = Column(Integer, nullable=True, index=True)

    event_type = Column(String(20), nullable=False)         # open|click|reply|bounce|unsubscribe|complaint
    url = Column(Text, nullable=True)                       # for click events
    metadata_json = Column(Text, nullable=True)             # JSON: user agent, ip, referrer
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)


class EmailUnsubscribe(Base):
    """Global suppression list — once unsubscribed, never email again."""
    __tablename__ = 'email_unsubscribes'

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    reason = Column(String(100), nullable=True)             # one_click|reply|manual|complaint|bounce
    source_campaign_id = Column(Integer, nullable=True)
    unsubscribed_at = Column(DateTime, default=datetime.utcnow)


class EmailReply(Base):
    """Captured inbound reply (parsed from Gmail). Powers the unified inbox view."""
    __tablename__ = 'email_replies'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('email_accounts.id'), nullable=False, index=True)
    enrollment_id = Column(Integer, ForeignKey('email_enrollments.id'), nullable=True, index=True)
    campaign_id = Column(Integer, nullable=True, index=True)

    gmail_message_id = Column(String(100), nullable=True, unique=True, index=True)
    gmail_thread_id = Column(String(100), nullable=True, index=True)

    from_email = Column(String(255), nullable=False)
    from_name = Column(String(255), nullable=True)
    subject = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)                 # Full HTML body when available

    received_at = Column(DateTime, default=datetime.utcnow)
    is_auto_reply = Column(Boolean, default=False)          # Out-of-office, bounce, etc.
    read = Column(Boolean, default=False)
    replied_to = Column(Boolean, default=False)             # Operator answered from the app

    def to_dict(self, include_body=False):
        d = {
            'id': self.id,
            'account_id': self.account_id,
            'enrollment_id': self.enrollment_id,
            'campaign_id': self.campaign_id,
            'gmail_thread_id': self.gmail_thread_id,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'subject': self.subject,
            'snippet': self.snippet,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'is_auto_reply': self.is_auto_reply,
            'read': self.read,
            'replied_to': bool(self.replied_to),
        }
        if include_body:
            d['body_text'] = self.body_text
            d['body_html'] = self.body_html
        return d


def init_db():
    """Initialize the database tables"""
    try:
        Base.metadata.create_all(engine)
        logger.info("✓ Database tables initialized successfully")

        # Run migrations for new columns
        _run_migrations()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def _run_migrations():
    """Add new columns to existing tables if they don't exist"""
    from sqlalchemy import text

    migrations = [
        # Add recurring schedule columns to scheduled_bulk_messages
        ("scheduled_bulk_messages", "is_recurring", "BOOLEAN DEFAULT FALSE"),
        ("scheduled_bulk_messages", "recurrence_type", "VARCHAR(20)"),
        ("scheduled_bulk_messages", "recurrence_days", "VARCHAR(50)"),
        ("scheduled_bulk_messages", "recurrence_end_date", "TIMESTAMP"),
        ("scheduled_bulk_messages", "last_sent_at", "TIMESTAMP"),
        ("scheduled_bulk_messages", "send_count", "INTEGER DEFAULT 0"),
        # Campaign table columns (in case table exists but missing columns)
        ("campaigns", "response_tracking_ends_at", "TIMESTAMP"),
        ("campaign_enrollments", "response_count", "INTEGER DEFAULT 0"),
        ("campaign_enrollments", "opted_out_keyword", "VARCHAR(50)"),
        # Email table columns added after initial email-module release
        ("email_accounts", "bounce_pause_threshold", "INTEGER DEFAULT 8"),
        ("email_accounts", "auto_paused", "BOOLEAN DEFAULT FALSE"),
        ("email_replies", "body_html", "TEXT"),
        ("email_replies", "replied_to", "BOOLEAN DEFAULT FALSE"),
    ]
    
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                # Check if column exists
                result = conn.execute(text(f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = '{table}' AND column_name = '{column}'
                """))
                if result.fetchone() is None:
                    # Column doesn't exist, add it
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    conn.commit()
                    logger.info(f"✓ Added column {column} to {table}")
            except Exception as e:
                logger.warning(f"Migration for {table}.{column}: {e}")


def get_session():
    """Get a new database session"""
    return Session()


@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    Automatically handles commit/rollback and closing.
    
    Usage:
        with get_db_session() as session:
            session.query(...)
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
