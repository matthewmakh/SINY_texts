from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum

from config import Config

engine = create_engine(Config.DATABASE_URL, echo=False)
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
    """Bulk message scheduling"""
    __tablename__ = 'scheduled_bulk_messages'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='pending')  # pending, in_progress, completed, cancelled
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'body': self.body,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'status': self.status,
            'total_recipients': self.total_recipients,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
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


def init_db():
    """Initialize the database tables"""
    Base.metadata.create_all(engine)


def get_session():
    """Get a new database session"""
    return Session()


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
