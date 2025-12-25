from datetime import datetime
import signal
import sys
import logging
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

from config import Config
from database import init_db, get_session, Message, MessageTemplate
from twilio_service import twilio_service
from scheduler import message_scheduler
from leads_service import (
    get_leads_stats, 
    get_all_contacts, 
    get_total_contact_count,
    normalize_phone
)

logger = logging.getLogger(__name__)

# Validate configuration on startup
if not Config.validate():
    logger.error("Configuration validation failed. Check your environment variables.")
    # Don't exit - let Railway see the error in logs

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize database
init_db()


# ============ Graceful Shutdown ============

def graceful_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM"""
    logger.info("Received shutdown signal, cleaning up...")
    try:
        message_scheduler.shutdown()
        logger.info("Scheduler shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)


# ============ Health Check ============

@app.route('/health')
def health_check():
    """Health check endpoint for Railway/monitoring"""
    try:
        # Check database connection
        session = get_session()
        session.execute("SELECT 1")
        session.close()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'sms-dashboard'
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


# ============ Frontend Routes ============

@app.route('/')
def dashboard():
    """Serve the main dashboard"""
    return render_template('index.html')


# ============ API Routes - Messages ============

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Get message history"""
    phone = request.args.get('phone')
    limit = request.args.get('limit', 100, type=int)
    messages = twilio_service.get_message_history(phone, limit)
    return jsonify({'success': True, 'messages': messages})


@app.route('/api/messages/send', methods=['POST'])
def send_message():
    """Send a single SMS message"""
    data = request.json
    to_number = data.get('to')
    body = data.get('body')
    
    if not to_number or not body:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    result = twilio_service.send_sms(to_number, body)
    return jsonify(result)


@app.route('/api/messages/bulk', methods=['POST'])
def send_bulk_messages():
    """Send bulk SMS to multiple recipients (by phone numbers)"""
    data = request.json
    body = data.get('body')
    phone_numbers = data.get('phone_numbers', [])
    
    if not body:
        return jsonify({'success': False, 'error': 'Message body is required'}), 400
    
    if not phone_numbers:
        return jsonify({'success': False, 'error': 'No recipients specified'}), 400
    
    result = twilio_service.send_bulk_sms(phone_numbers, body)
    return jsonify({'success': True, **result})


# ============ API Routes - Conversations ============

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """Get all conversations"""
    conversations = twilio_service.get_conversations()
    return jsonify({'success': True, 'conversations': conversations})


@app.route('/api/conversations/<phone>', methods=['GET'])
def get_conversation(phone):
    """Get messages for a specific conversation"""
    messages = twilio_service.get_conversation_messages(phone)
    return jsonify({'success': True, 'messages': messages})


# ============ API Routes - Contacts (Live from Leads DB) ============

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """
    Get contacts directly from the leads database (live query).
    No local storage - always fresh data from the source.
    """
    search = request.args.get('search', '')
    mobile_only = request.args.get('mobile_only', 'true').lower() == 'true'
    source = request.args.get('source', 'all')  # 'permit', 'owner', or 'all'
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        contacts = get_all_contacts(
            search=search if search else None,
            mobile_only=mobile_only,
            source=source,
            limit=limit,
            offset=offset
        )
        
        # Format for frontend
        result = []
        for c in contacts:
            result.append({
                'id': c.get('id'),
                'phone_number': c.get('phone_normalized'),
                'name': c.get('name'),
                'company': c.get('company'),
                'permit_number': c.get('permit_no'),
                'address': c.get('address'),
                'role': c.get('role'),
                'source': c.get('source', c.get('contact_source')),
                'is_mobile': c.get('is_mobile', True)
            })
        
        total = get_total_contact_count(mobile_only=mobile_only, source=source)
        
        return jsonify({
            'success': True, 
            'contacts': result,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/stats', methods=['GET'])
def get_contacts_stats():
    """Get stats about available contacts in the leads database"""
    try:
        stats = get_leads_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ API Routes - Scheduling ============

@app.route('/api/scheduled', methods=['GET'])
def get_scheduled():
    """Get all scheduled messages"""
    messages = message_scheduler.get_scheduled_messages()
    return jsonify({'success': True, 'scheduled': messages})


@app.route('/api/scheduled', methods=['POST'])
def schedule_message():
    """Schedule a new bulk message - REQUIRES explicit phone numbers"""
    data = request.json
    name = data.get('name')
    body = data.get('body')
    scheduled_at = data.get('scheduled_at')
    phone_numbers = data.get('phone_numbers', [])  # MUST be provided
    
    # SAFETY: Require all fields including phone_numbers
    if not all([name, body, scheduled_at]):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # SAFETY: REQUIRE phone_numbers - never allow empty
    if not phone_numbers or len(phone_numbers) == 0:
        return jsonify({'success': False, 'error': 'SAFETY: You must select specific recipients. Cannot schedule without phone_numbers.'}), 400
    
    # SAFETY: Cap at 50 recipients
    if len(phone_numbers) > 50:
        return jsonify({'success': False, 'error': f'SAFETY: Too many recipients ({len(phone_numbers)}). Maximum is 50 per scheduled message.'}), 400
    
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
    except:
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400
    
    try:
        result = message_scheduler.schedule_bulk_message(name, body, scheduled_dt, phone_numbers)
        return jsonify({'success': True, 'scheduled': result})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/scheduled/<int:message_id>', methods=['DELETE'])
def cancel_scheduled(message_id):
    """Cancel a scheduled message"""
    success = message_scheduler.cancel_scheduled_message(message_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Could not cancel message'}), 400


# ============ API Routes - Templates ============

@app.route('/api/templates', methods=['GET'])
def get_templates():
    """Get all message templates"""
    session = get_session()
    templates = session.query(MessageTemplate).order_by(MessageTemplate.name).all()
    result = [t.to_dict() for t in templates]
    session.close()
    return jsonify({'success': True, 'templates': result})


@app.route('/api/templates', methods=['POST'])
def create_template():
    """Create a new template"""
    data = request.json
    session = get_session()
    
    template = MessageTemplate(
        name=data.get('name'),
        body=data.get('body')
    )
    
    session.add(template)
    session.commit()
    result = template.to_dict()
    session.close()
    return jsonify({'success': True, 'template': result})


@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a template"""
    session = get_session()
    template = session.query(MessageTemplate).get(template_id)
    
    if not template:
        session.close()
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    session.delete(template)
    session.commit()
    session.close()
    return jsonify({'success': True})


# ============ Twilio Webhooks ============

@app.route('/api/webhook/incoming', methods=['POST'])
def incoming_message():
    """Handle incoming SMS from Twilio"""
    from_number = request.form.get('From')
    body = request.form.get('Body')
    twilio_sid = request.form.get('MessageSid')
    
    # Store the incoming message
    twilio_service.process_incoming_message(from_number, body, twilio_sid)
    
    # Return empty TwiML response (no auto-reply)
    response = MessagingResponse()
    return str(response)


@app.route('/api/webhook/status', methods=['POST'])
def message_status():
    """Handle message status callbacks from Twilio"""
    twilio_sid = request.form.get('MessageSid')
    status = request.form.get('MessageStatus')
    
    twilio_service.update_message_status(twilio_sid, status)
    return '', 200


# ============ Stats ============

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get dashboard statistics"""
    session = get_session()
    
    # Get contact count from leads DB
    try:
        leads_stats = get_leads_stats()
        total_contacts = leads_stats['mobile_contacts']  # Mobile contacts
    except:
        total_contacts = 0
    
    # Get message counts from local DB
    total_messages = session.query(Message).count()
    sent_messages = session.query(Message).filter(
        Message.direction == 'outbound'
    ).count()
    received_messages = session.query(Message).filter(
        Message.direction == 'inbound'
    ).count()
    
    session.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_contacts': total_contacts,
            'total_messages': total_messages,
            'sent_messages': sent_messages,
            'received_messages': received_messages
        }
    })


# ============ Error Handlers ============

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404


if __name__ == '__main__':
    logger.info("Starting SMS Dashboard in development mode...")
    app.run(debug=Config.DEBUG, port=5000)
