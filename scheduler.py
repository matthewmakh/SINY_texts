from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

from database import get_session, ScheduledBulkMessage
from leads_service import get_all_contacts
from twilio_service import twilio_service

logger = logging.getLogger(__name__)


class MessageScheduler:
    """
    Handles scheduling of bulk SMS messages.
    
    Uses a polling approach (checks DB every 30 seconds) which is more reliable
    for production deployments with multiple workers (gunicorn, etc.)
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        # Check for due messages every 30 seconds
        self.scheduler.add_job(
            func=self._check_and_send_due_messages,
            trigger=IntervalTrigger(seconds=30),
            id='check_scheduled_messages',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Message scheduler started - checking for due messages every 30 seconds")
    
    def _check_and_send_due_messages(self):
        """Check database for messages that are due and send them"""
        session = get_session()
        try:
            # Find messages that are due (scheduled_at <= now) and still pending
            due_messages = session.query(ScheduledBulkMessage).filter(
                ScheduledBulkMessage.status == 'pending',
                ScheduledBulkMessage.scheduled_at <= datetime.utcnow()
            ).all()
            
            for bulk_msg in due_messages:
                logger.info(f"Processing scheduled message: {bulk_msg.name} (ID: {bulk_msg.id})")
                self._execute_bulk_send(bulk_msg.id)
                
        except Exception as e:
            logger.error(f"Error checking scheduled messages: {e}")
        finally:
            session.close()
    
    def _execute_bulk_send(self, bulk_message_id: int):
        """Execute a scheduled bulk send"""
        session = get_session()
        try:
            bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
            
            if not bulk_msg or bulk_msg.status != 'pending':
                return
            
            bulk_msg.status = 'in_progress'
            session.commit()
            
            # Get all contacts from leads database (mobile only for SMS)
            contacts = get_all_contacts(mobile_only=True)
            bulk_msg.total_recipients = len(contacts)
            session.commit()
            
            logger.info(f"Sending to {len(contacts)} contacts...")
            
            # Send to all contacts
            for contact in contacts:
                result = twilio_service.send_sms(
                    contact['phone'], 
                    bulk_msg.body
                )
                if result['success']:
                    bulk_msg.sent_count += 1
                else:
                    bulk_msg.failed_count += 1
                session.commit()
            
            bulk_msg.status = 'completed'
            session.commit()
            logger.info(f"Completed: sent={bulk_msg.sent_count}, failed={bulk_msg.failed_count}")
            
        except Exception as e:
            logger.error(f"Error executing bulk send {bulk_message_id}: {e}")
            if bulk_msg:
                bulk_msg.status = 'failed'
                session.commit()
        finally:
            session.close()
    
    def schedule_bulk_message(self, name: str, body: str, scheduled_at: datetime, contact_ids: list = None) -> dict:
        """Schedule a bulk message for future delivery"""
        session = get_session()
        
        bulk_msg = ScheduledBulkMessage(
            name=name,
            body=body,
            scheduled_at=scheduled_at,
            status='pending'
        )
        
        session.add(bulk_msg)
        session.commit()
        
        logger.info(f"Scheduled message '{name}' for {scheduled_at}")
        
        result = bulk_msg.to_dict()
        session.close()
        return result
    
    def cancel_scheduled_message(self, bulk_message_id: int) -> bool:
        """Cancel a scheduled bulk message"""
        session = get_session()
        bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
        
        if not bulk_msg or bulk_msg.status != 'pending':
            session.close()
            return False
        
        bulk_msg.status = 'cancelled'
        session.commit()
        session.close()
        logger.info(f"Cancelled scheduled message ID: {bulk_message_id}")
        return True
    
    def get_scheduled_messages(self) -> list:
        """Get all scheduled bulk messages"""
        session = get_session()
        messages = session.query(ScheduledBulkMessage).order_by(
            ScheduledBulkMessage.scheduled_at.desc()
        ).all()
        result = [m.to_dict() for m in messages]
        session.close()
        return result
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()


# Singleton instance
message_scheduler = MessageScheduler()
