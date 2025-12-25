from datetime import datetime
import os
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from config import Config
from database import get_session, Message, MessageStatus, MessageDirection
from leads_service import get_contact_by_phone, get_contacts_by_phones

logger = logging.getLogger(__name__)


class TwilioService:
    """Service layer for Twilio SMS operations"""
    
    def __init__(self):
        self.client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        self.from_number = Config.TWILIO_PHONE_NUMBER
        # Only use status callback if we have a real URL (not localhost)
        webhook_url = Config.WEBHOOK_BASE_URL
        if webhook_url and 'localhost' not in webhook_url and '127.0.0.1' not in webhook_url:
            # Ensure URL has https:// prefix
            if not webhook_url.startswith('http://') and not webhook_url.startswith('https://'):
                webhook_url = f"https://{webhook_url}"
            # Remove trailing slash if present
            webhook_url = webhook_url.rstrip('/')
            self.status_callback_url = f"{webhook_url}/api/webhook/status"
            logger.info(f"Status callbacks enabled: {self.status_callback_url}")
        else:
            self.status_callback_url = None
            logger.info("Status callbacks disabled (no production webhook URL configured)")
    
    def send_sms(self, to_number: str, body: str) -> dict:
        """Send a single SMS message"""
        session = get_session()
        
        # Create message record
        message = Message(
            phone_number=to_number,
            body=body,
            direction=MessageDirection.OUTBOUND.value,
            status=MessageStatus.PENDING.value
        )
        session.add(message)
        session.commit()
        
        try:
            # Build message params
            message_params = {
                'body': body,
                'from_': self.from_number,
                'to': to_number,
            }
            
            # Only add status callback if we have a valid URL
            if self.status_callback_url:
                message_params['status_callback'] = self.status_callback_url
            
            # Send via Twilio
            twilio_message = self.client.messages.create(**message_params)
            
            # Update message record
            message.twilio_sid = twilio_message.sid
            message.status = MessageStatus.SENT.value
            message.sent_at = datetime.utcnow()
            session.commit()
            
            # Get contact info from leads DB
            contact = get_contact_by_phone(to_number)
            result = message.to_dict(contact=contact)
            session.close()
            return {'success': True, 'message': result}
            
        except TwilioRestException as e:
            message.status = MessageStatus.FAILED.value
            message.error_message = str(e)
            session.commit()
            result = message.to_dict()
            session.close()
            return {'success': False, 'error': str(e), 'message': result}
    
    def send_bulk_sms(self, phone_numbers: list, body: str) -> dict:
        """Send SMS to multiple recipients"""
        results = {'sent': 0, 'failed': 0, 'messages': []}
        
        for phone in phone_numbers:
            result = self.send_sms(phone, body)
            if result['success']:
                results['sent'] += 1
            else:
                results['failed'] += 1
            results['messages'].append(result)
        
        return results
    
    def get_message_history(self, phone_number: str = None, limit: int = 100) -> list:
        """Get message history, optionally filtered by phone number"""
        session = get_session()
        query = session.query(Message).order_by(Message.created_at.desc())
        
        if phone_number:
            query = query.filter(Message.phone_number == phone_number)
        
        messages = query.limit(limit).all()
        
        # Get contact info for all phone numbers in one query
        phones = list(set(m.phone_number for m in messages))
        contacts_list = get_contacts_by_phones(phones)
        contacts_map = {c['phone_normalized']: c for c in contacts_list}
        
        result = []
        for m in messages:
            contact = contacts_map.get(m.phone_number)
            result.append(m.to_dict(contact=contact))
        
        session.close()
        return result
    
    def get_conversations(self) -> list:
        """Get list of unique conversations grouped by phone number"""
        session = get_session()
        
        from sqlalchemy import func, desc
        
        subquery = session.query(
            Message.phone_number,
            func.max(Message.created_at).label('last_message_at')
        ).group_by(Message.phone_number).subquery()
        
        conversations = session.query(Message).join(
            subquery,
            (Message.phone_number == subquery.c.phone_number) &
            (Message.created_at == subquery.c.last_message_at)
        ).order_by(desc(Message.created_at)).all()
        
        # Get contact info for all phones
        phones = [msg.phone_number for msg in conversations]
        contacts_list = get_contacts_by_phones(phones)
        contacts_map = {c['phone_normalized']: c for c in contacts_list}
        
        result = []
        for msg in conversations:
            msg_count = session.query(Message).filter(
                Message.phone_number == msg.phone_number
            ).count()
            
            contact = contacts_map.get(msg.phone_number)
            
            conv_data = {
                'phone_number': msg.phone_number,
                'last_message': msg.to_dict(contact=contact),
                'message_count': msg_count,
                'contact': contact
            }
            result.append(conv_data)
        
        session.close()
        return result
    
    def get_conversation_messages(self, phone_number: str) -> list:
        """Get all messages for a specific conversation"""
        session = get_session()
        messages = session.query(Message).filter(
            Message.phone_number == phone_number
        ).order_by(Message.created_at.asc()).all()
        
        # Get contact info once
        contact = get_contact_by_phone(phone_number)
        
        result = [m.to_dict(contact=contact) for m in messages]
        session.close()
        return result
    
    def process_incoming_message(self, from_number: str, body: str, twilio_sid: str) -> dict:
        """Process and store an incoming SMS message"""
        session = get_session()
        
        message = Message(
            twilio_sid=twilio_sid,
            phone_number=from_number,
            body=body,
            direction=MessageDirection.INBOUND.value,
            status=MessageStatus.RECEIVED.value,
            sent_at=datetime.utcnow()
        )
        
        session.add(message)
        session.commit()
        
        # Get contact info from leads DB
        contact = get_contact_by_phone(from_number)
        result = message.to_dict(contact=contact)
        session.close()
        return result
    
    def update_message_status(self, twilio_sid: str, status: str) -> bool:
        """Update message status from Twilio callback"""
        session = get_session()
        message = session.query(Message).filter(
            Message.twilio_sid == twilio_sid
        ).first()
        
        if message:
            status_map = {
                'queued': MessageStatus.PENDING.value,
                'sent': MessageStatus.SENT.value,
                'delivered': MessageStatus.DELIVERED.value,
                'failed': MessageStatus.FAILED.value,
                'undelivered': MessageStatus.FAILED.value
            }
            message.status = status_map.get(status, status)
            session.commit()
            session.close()
            return True
        
        session.close()
        return False


# Singleton instance
twilio_service = TwilioService()
