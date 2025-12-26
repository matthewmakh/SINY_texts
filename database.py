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
        # Add contact_notes table columns if needed
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
