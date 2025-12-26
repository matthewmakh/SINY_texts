from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, MO, TU, WE, TH, FR, SA, SU
import logging
import json

from database import get_session, ScheduledBulkMessage
from twilio_service import twilio_service

logger = logging.getLogger(__name__)

# SAFETY: Maximum recipients allowed in a single scheduled message
MAX_RECIPIENTS_PER_SCHEDULE = 50

# Day mapping for recurrence
DAY_MAP = {
    'mon': MO, 'tue': TU, 'wed': WE, 'thu': TH,
    'fri': FR, 'sat': SA, 'sun': SU
}


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
    
    def _calculate_next_occurrence(self, bulk_msg):
        """
        Calculate the next occurrence for a recurring message.
        Returns None if the recurrence has ended or is invalid.
        """
        if not bulk_msg.is_recurring or not bulk_msg.recurrence_type:
            return None
        
        # Base time is the current scheduled_at time (preserves the time of day)
        base_time = bulk_msg.scheduled_at
        now = datetime.utcnow()
        
        # Check if we've passed the end date
        if bulk_msg.recurrence_end_date and now >= bulk_msg.recurrence_end_date:
            logger.info(f"Recurrence ended for message {bulk_msg.id}")
            return None
        
        try:
            if bulk_msg.recurrence_type == 'daily':
                rule = rrule(DAILY, dtstart=base_time)
            
            elif bulk_msg.recurrence_type == 'weekly':
                # Parse the days string (e.g., "mon,wed,fri")
                days_str = bulk_msg.recurrence_days or ''
                days = [DAY_MAP[d.strip().lower()] for d in days_str.split(',') if d.strip().lower() in DAY_MAP]
                
                if not days:
                    # Default to same day as original if no days specified
                    days = [list(DAY_MAP.values())[base_time.weekday()]]
                
                rule = rrule(WEEKLY, byweekday=days, dtstart=base_time)
            
            elif bulk_msg.recurrence_type == 'monthly':
                # Same day of month
                rule = rrule(MONTHLY, bymonthday=base_time.day, dtstart=base_time)
            
            else:
                logger.error(f"Unknown recurrence type: {bulk_msg.recurrence_type}")
                return None
            
            # Get the next occurrence after now
            next_time = rule.after(now)
            
            # Check if next_time is past the end date
            if bulk_msg.recurrence_end_date and next_time and next_time > bulk_msg.recurrence_end_date:
                return None
            
            return next_time
            
        except Exception as e:
            logger.error(f"Error calculating next occurrence: {e}")
            return None
    
    def _fill_template_variables(self, template: str, contact: dict) -> str:
        """Fill template variables with contact data"""
        import re
        result = template
        
        # Contact-based variables
        result = result.replace('{name}', contact.get('name') or '')
        result = result.replace('{company}', contact.get('company') or '')
        result = result.replace('{role}', contact.get('role') or '')
        result = result.replace('{phone}', contact.get('phone_normalized') or contact.get('phone') or '')
        
        # Date/time variables
        result = result.replace('{date}', datetime.now().strftime('%m/%d/%Y'))
        result = result.replace('{time}', datetime.now().strftime('%I:%M %p'))
        
        # Clean up any empty variable results (double spaces)
        result = re.sub(r' +', ' ', result).strip()
        
        return result
    
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
            
            # Reset counts for this send (for recurring messages)
            bulk_msg.sent_count = 0
            bulk_msg.failed_count = 0
            
            # Check if message has template variables
            has_variables = '{' in bulk_msg.body and '}' in bulk_msg.body
            
            contacts_map = {}
            if has_variables:
                # Get contact info for variable replacement (import at top level)
                from leads_service import get_contacts_by_phones
                from twilio_service import normalize_phone
                contacts_list = get_contacts_by_phones(phone_numbers)
                contacts_map = {c.get('phone_normalized') or c.get('phone'): c for c in contacts_list}
            
            # Send ONLY to the specified phone numbers
            for phone in phone_numbers:
                # Fill template variables if needed
                message_body = bulk_msg.body
                if has_variables:
                    # Normalize phone to match contacts_map keys
                    normalized = normalize_phone(phone)
                    contact = contacts_map.get(normalized, contacts_map.get(phone, {}))
                    message_body = self._fill_template_variables(message_body, contact)
                
                result = twilio_service.send_sms(phone, message_body)
                if result['success']:
                    bulk_msg.sent_count += 1
                else:
                    bulk_msg.failed_count += 1
                session.commit()
            
            # Handle recurring messages
            if bulk_msg.is_recurring:
                next_occurrence = self._calculate_next_occurrence(bulk_msg)
                if next_occurrence:
                    # Schedule next occurrence
                    bulk_msg.scheduled_at = next_occurrence
                    bulk_msg.status = 'pending'  # Reset to pending for next run
                    bulk_msg.last_sent_at = datetime.utcnow()
                    bulk_msg.send_count = (bulk_msg.send_count or 0) + 1
                    logger.info(f"Recurring message {bulk_msg.id} rescheduled for {next_occurrence}")
                else:
                    # Recurrence ended
                    bulk_msg.status = 'completed'
                    bulk_msg.last_sent_at = datetime.utcnow()
                    bulk_msg.send_count = (bulk_msg.send_count or 0) + 1
                    logger.info(f"Recurring message {bulk_msg.id} completed (no more occurrences)")
            else:
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
    
    def schedule_bulk_message(self, name: str, body: str, scheduled_at: datetime, phone_numbers: list,
                                is_recurring: bool = False, recurrence_type: str = None,
                                recurrence_days: str = None, recurrence_end_date: datetime = None) -> dict:
        """
        Schedule a bulk message for future delivery.
        
        SAFETY: phone_numbers MUST be provided - we NEVER send to "all contacts"
        
        Args:
            name: Name/label for the scheduled message
            body: Message content
            scheduled_at: When to send (first occurrence for recurring)
            phone_numbers: List of phone numbers to send to
            is_recurring: Whether this is a recurring schedule
            recurrence_type: 'daily', 'weekly', or 'monthly'
            recurrence_days: For weekly - comma-separated days like 'mon,wed,fri'
            recurrence_end_date: Optional end date for recurrence
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
        
        # Validate recurring parameters
        if is_recurring:
            if recurrence_type not in ['daily', 'weekly', 'monthly']:
                raise ValueError(f"Invalid recurrence_type: {recurrence_type}. Must be 'daily', 'weekly', or 'monthly'")
            
            if recurrence_type == 'weekly' and recurrence_days:
                valid_days = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}
                days = [d.strip().lower() for d in recurrence_days.split(',')]
                invalid = [d for d in days if d not in valid_days]
                if invalid:
                    raise ValueError(f"Invalid days: {invalid}. Valid days: {valid_days}")
        
        session = get_session()
        
        bulk_msg = ScheduledBulkMessage(
            name=name,
            body=body,
            recipient_phones=json.dumps(phone_numbers),  # Store EXACT recipients
            scheduled_at=scheduled_at,
            total_recipients=len(phone_numbers),
            status='pending',
            is_recurring=is_recurring,
            recurrence_type=recurrence_type if is_recurring else None,
            recurrence_days=recurrence_days if is_recurring and recurrence_type == 'weekly' else None,
            recurrence_end_date=recurrence_end_date if is_recurring else None
        )
        
        session.add(bulk_msg)
        session.commit()
        
        recur_info = f" (recurring: {recurrence_type})" if is_recurring else ""
        logger.info(f"Scheduled message '{name}' for {scheduled_at} to EXACTLY {len(phone_numbers)} recipients{recur_info}")
        
        result = bulk_msg.to_dict()
        session.close()
        return result
    
    def cancel_scheduled_message(self, bulk_message_id: int) -> bool:
        """Cancel a scheduled bulk message"""
        session = get_session()
        bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
        
        if not bulk_msg or bulk_msg.status not in ['pending', 'paused']:
            session.close()
            return False
        
        bulk_msg.status = 'cancelled'
        session.commit()
        session.close()
        logger.info(f"Cancelled scheduled message ID: {bulk_message_id}")
        return True
    
    def pause_scheduled_message(self, bulk_message_id: int) -> bool:
        """Pause a recurring scheduled message"""
        session = get_session()
        bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
        
        if not bulk_msg or bulk_msg.status != 'pending':
            session.close()
            return False
        
        bulk_msg.status = 'paused'
        session.commit()
        session.close()
        logger.info(f"Paused scheduled message ID: {bulk_message_id}")
        return True
    
    def resume_scheduled_message(self, bulk_message_id: int) -> bool:
        """Resume a paused scheduled message"""
        session = get_session()
        bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
        
        if not bulk_msg or bulk_msg.status != 'paused':
            session.close()
            return False
        
        # For recurring messages, recalculate next occurrence
        if bulk_msg.is_recurring:
            next_occurrence = self._calculate_next_occurrence(bulk_msg)
            if next_occurrence:
                bulk_msg.scheduled_at = next_occurrence
            else:
                # No more occurrences
                bulk_msg.status = 'completed'
                session.commit()
                session.close()
                return False
        
        bulk_msg.status = 'pending'
        session.commit()
        session.close()
        logger.info(f"Resumed scheduled message ID: {bulk_message_id}")
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
