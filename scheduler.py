from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import json

from database import get_session, ScheduledBulkMessage
from twilio_service import twilio_service

logger = logging.getLogger(__name__)

# SAFETY: Maximum recipients allowed in a single scheduled message
MAX_RECIPIENTS_PER_SCHEDULE = 50


class MessageScheduler:
    """
    Handles scheduling of bulk SMS messages.
    
    SAFETY RULES:
    1. NEVER sends to "all contacts" - only to explicitly specified phone numbers
    2. Phone numbers must be provided at schedule time and stored in DB
    3. Maximum recipients per scheduled message is capped at 50
    4. Uses polling approach for reliability
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
        logger.info(f"SAFETY: Max recipients per scheduled message: {MAX_RECIPIENTS_PER_SCHEDULE}")
    
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
        """Execute a scheduled bulk send - ONLY to pre-specified recipients"""
        session = get_session()
        bulk_msg = None
        try:
            bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
            
            if not bulk_msg or bulk_msg.status != 'pending':
                logger.warning(f"Message {bulk_message_id} not found or not pending")
                return
            
            # SAFETY: Get phone numbers from the stored list ONLY
            try:
                phone_numbers = json.loads(bulk_msg.recipient_phones) if bulk_msg.recipient_phones else []
            except (json.JSONDecodeError, TypeError):
                logger.error(f"SAFETY BLOCK: Invalid recipient_phones for message {bulk_message_id}")
                bulk_msg.status = 'failed'
                session.commit()
                return
            
            # SAFETY: Validate we have recipients
            if not phone_numbers or len(phone_numbers) == 0:
                logger.error(f"SAFETY BLOCK: No recipients stored for message {bulk_message_id}")
                bulk_msg.status = 'failed'
                session.commit()
                return
            
            # SAFETY: Cap the number of recipients
            if len(phone_numbers) > MAX_RECIPIENTS_PER_SCHEDULE:
                logger.error(f"SAFETY BLOCK: Too many recipients ({len(phone_numbers)}) for message {bulk_message_id}, max is {MAX_RECIPIENTS_PER_SCHEDULE}")
                bulk_msg.status = 'failed'
                session.commit()
                return
            
            bulk_msg.status = 'in_progress'
            bulk_msg.total_recipients = len(phone_numbers)
            session.commit()
            
            logger.info(f"Sending to {len(phone_numbers)} SPECIFIED contacts (NOT all contacts)")
            
            # Send ONLY to the specified phone numbers
            for phone in phone_numbers:
                result = twilio_service.send_sms(phone, bulk_msg.body)
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
    
    def schedule_bulk_message(self, name: str, body: str, scheduled_at: datetime, phone_numbers: list) -> dict:
        """
        Schedule a bulk message for future delivery.
        
        SAFETY: phone_numbers MUST be provided - we NEVER send to "all contacts"
        """
        # SAFETY: Require explicit phone numbers
        if not phone_numbers or len(phone_numbers) == 0:
            raise ValueError("SAFETY: phone_numbers is REQUIRED - cannot schedule without explicit recipients")
        
        # SAFETY: Cap recipients
        if len(phone_numbers) > MAX_RECIPIENTS_PER_SCHEDULE:
            raise ValueError(f"SAFETY: Too many recipients ({len(phone_numbers)}). Maximum allowed: {MAX_RECIPIENTS_PER_SCHEDULE}")
        
        # SAFETY: Validate phone numbers look like phone numbers
        for phone in phone_numbers:
            if not phone or not isinstance(phone, str) or len(phone) < 10:
                raise ValueError(f"SAFETY: Invalid phone number: {phone}")
        
        session = get_session()
        
        bulk_msg = ScheduledBulkMessage(
            name=name,
            body=body,
            recipient_phones=json.dumps(phone_numbers),  # Store EXACT recipients
            scheduled_at=scheduled_at,
            total_recipients=len(phone_numbers),
            status='pending'
        )
        
        session.add(bulk_msg)
        session.commit()
        
        logger.info(f"Scheduled message '{name}' for {scheduled_at} to EXACTLY {len(phone_numbers)} recipients")
        
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
