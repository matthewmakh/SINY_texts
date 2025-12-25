from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from database import get_session, ScheduledBulkMessage
from leads_service import get_all_contacts
from twilio_service import twilio_service


class MessageScheduler:
    """Handles scheduling of bulk SMS messages"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._restore_scheduled_jobs()
    
    def _restore_scheduled_jobs(self):
        """Restore pending scheduled jobs from database on startup"""
        session = get_session()
        pending = session.query(ScheduledBulkMessage).filter(
            ScheduledBulkMessage.status == 'pending',
            ScheduledBulkMessage.scheduled_at > datetime.utcnow()
        ).all()
        
        for job in pending:
            self._add_job(job.id, job.scheduled_at)
        
        session.close()
    
    def _add_job(self, bulk_message_id: int, run_at: datetime):
        """Add a job to the scheduler"""
        self.scheduler.add_job(
            func=self._execute_bulk_send,
            trigger=DateTrigger(run_date=run_at),
            args=[bulk_message_id],
            id=f"bulk_message_{bulk_message_id}",
            replace_existing=True
        )
    
    def _execute_bulk_send(self, bulk_message_id: int):
        """Execute a scheduled bulk send"""
        session = get_session()
        bulk_msg = session.query(ScheduledBulkMessage).get(bulk_message_id)
        
        if not bulk_msg or bulk_msg.status != 'pending':
            session.close()
            return
        
        bulk_msg.status = 'in_progress'
        session.commit()
        
        # Get all contacts from leads database (mobile only for SMS)
        contacts = get_all_contacts(mobile_only=True)
        bulk_msg.total_recipients = len(contacts)
        session.commit()
        
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
        
        # Add to scheduler
        self._add_job(bulk_msg.id, scheduled_at)
        
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
        
        # Remove from scheduler
        job_id = f"bulk_message_{bulk_message_id}"
        try:
            self.scheduler.remove_job(job_id)
        except:
            pass
        
        bulk_msg.status = 'cancelled'
        session.commit()
        session.close()
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
