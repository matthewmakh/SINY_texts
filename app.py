from datetime import datetime
import signal
import sys
import logging
import csv
import io
import re
from flask import Flask, render_template, request, jsonify, make_response
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

from config import Config
from database import init_db, get_session, Message, MessageTemplate, ManualContact, ContactNote
from twilio_service import twilio_service
from scheduler import message_scheduler
from leads_service import (
    get_leads_stats, 
    get_all_contacts, 
    get_total_contact_count,
    normalize_phone,
    get_contacts_by_phones
)
from auth import (
    init_auth_tables,
    create_admin_if_needed,
    authenticate_user,
    validate_session,
    logout_user,
    get_current_user,
    change_password,
    list_users,
    create_user,
    update_user,
    delete_user,
    get_roles,
    login_required,
    role_required
)
from campaign_service import campaign_service

logger = logging.getLogger(__name__)


# ============ Template Variable Processing ============

def fill_template_variables(template: str, contact: dict) -> str:
    """Fill template variables with contact data"""
    from zoneinfo import ZoneInfo
    
    result = template
    
    # Contact-based variables
    result = result.replace('{name}', contact.get('name') or '')
    result = result.replace('{company}', contact.get('company') or '')
    result = result.replace('{role}', contact.get('role') or '')
    result = result.replace('{phone}', contact.get('phone_normalized') or contact.get('phone') or '')
    
    # Date/time variables (Eastern Time)
    eastern = ZoneInfo('America/New_York')
    now_eastern = datetime.now(eastern)
    result = result.replace('{date}', now_eastern.strftime('%m/%d/%Y'))
    result = result.replace('{time}', now_eastern.strftime('%I:%M %p'))
    
    # Clean up any empty variable results (double spaces)
    result = re.sub(r' +', ' ', result).strip()
    
    return result


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

# Initialize auth tables and create admin if needed
try:
    init_auth_tables()
    create_admin_if_needed()
except Exception as e:
    logger.warning(f"Auth initialization warning: {e}")


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


# ============ Authentication Routes ============

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authenticate user and return session token"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    
    result = authenticate_user(email, password, dashboard='sms')
    
    if result['success']:
        response = make_response(jsonify(result))
        response.set_cookie(
            'auth_token',
            result['token'],
            httponly=True,
            secure=True,
            samesite='Lax',
            max_age=7*24*60*60  # 7 days
        )
        return response
    
    return jsonify(result), 401


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user and invalidate session"""
    token = request.cookies.get('auth_token')
    if token:
        logout_user(token)
    
    response = make_response(jsonify({'success': True}))
    response.delete_cookie('auth_token')
    return response


@app.route('/api/auth/me', methods=['GET'])
def get_me():
    """Get current user info"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'user': user})


@app.route('/api/auth/change-password', methods=['POST'])
def change_user_password():
    """Change current user's password"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    data = request.json
    old_password = data.get('old_password') or data.get('current_password')
    new_password = data.get('new_password')
    
    if not old_password or not new_password:
        return jsonify({'success': False, 'error': 'Both passwords required'}), 400
    
    if len(new_password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
    
    result = change_password(user['id'], old_password, new_password)
    return jsonify(result)


# ============ User Management Routes (Admin only) ============

@app.route('/api/users', methods=['GET'])
@login_required
@role_required('admin')
def get_users():
    """Get all users (admin only)"""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    users = list_users(include_inactive)
    return jsonify({'success': True, 'users': users})


@app.route('/api/users', methods=['POST'])
@login_required
@role_required('admin')
def create_new_user():
    """Create a new user (admin only)"""
    from flask import g
    data = request.json
    
    required = ['email', 'password', 'name']
    if not all(data.get(f) for f in required):
        return jsonify({'success': False, 'error': 'Email, password, and name required'}), 400
    
    result = create_user(
        email=data['email'],
        password=data['password'],
        name=data['name'],
        role=data.get('role', 'viewer'),
        created_by=g.current_user['id']
    )
    
    return jsonify(result)


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@role_required('admin')
def update_existing_user(user_id):
    """Update a user (admin only)"""
    data = request.json
    result = update_user(user_id, **data)
    return jsonify(result)


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_existing_user(user_id):
    """Delete a user (admin only)"""
    from flask import g
    if user_id == g.current_user['id']:
        return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
    result = delete_user(user_id)
    return jsonify(result)


@app.route('/api/roles', methods=['GET'])
@login_required
def get_available_roles():
    """Get available roles"""
    roles = get_roles()
    return jsonify({'success': True, 'roles': roles})


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
    """Send a single SMS message with template variable support"""
    data = request.json
    to_number = data.get('to')
    body = data.get('body')
    
    if not to_number or not body:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # Check if body contains template variables
    if '{' in body and '}' in body:
        # Get contact info for variable replacement
        normalized = normalize_phone_number(to_number)
        contacts_list = get_contacts_by_phones([to_number])
        contact = {}
        if contacts_list:
            contact = contacts_list[0]
        
        # Fill template variables
        body = fill_template_variables(body, contact)
    
    result = twilio_service.send_sms(to_number, body)
    return jsonify(result)


@app.route('/api/messages/bulk', methods=['POST'])
def send_bulk_messages():
    """Send bulk SMS to multiple recipients (by phone numbers) with template variable support"""
    data = request.json
    body = data.get('body')
    phone_numbers = data.get('phone_numbers', [])
    
    if not body:
        return jsonify({'success': False, 'error': 'Message body is required'}), 400
    
    if not phone_numbers:
        return jsonify({'success': False, 'error': 'No recipients specified'}), 400
    
    # Check if body contains template variables
    has_variables = '{' in body and '}' in body
    
    if has_variables:
        # Get contact info for variable replacement
        contacts_list = get_contacts_by_phones(phone_numbers)
        contacts_map = {c.get('phone_normalized') or c.get('phone'): c for c in contacts_list}
        
        results = {'sent': 0, 'failed': 0, 'messages': []}
        
        for phone in phone_numbers:
            normalized = normalize_phone_number(phone)
            # Try normalized first, then raw phone as fallback
            contact = contacts_map.get(normalized, contacts_map.get(phone, {}))
            
            # Fill template variables
            personalized_body = fill_template_variables(body, contact)
            
            result = twilio_service.send_sms(phone, personalized_body)
            if result['success']:
                results['sent'] += 1
            else:
                results['failed'] += 1
            results['messages'].append(result)
        
        return jsonify({'success': True, **results})
    else:
        # No variables, use simple bulk send
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
    Get contacts from leads database AND manual contacts.
    """
    search = request.args.get('search', '')
    mobile_only = request.args.get('mobile_only', 'true').lower() == 'true'
    source = request.args.get('source', 'all')  # 'permit', 'owner', or 'all'
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    borough = request.args.get('borough', '')  # MANHATTAN, BROOKLYN, etc.
    role = request.args.get('role', '')  # Owner, Permittee
    
    # Advanced filters
    neighborhood = request.args.get('neighborhood', '')
    zip_code = request.args.get('zip_code', '')
    job_type = request.args.get('job_type', '')
    work_type = request.args.get('work_type', '')
    permit_type = request.args.get('permit_type', '')
    permit_status = request.args.get('permit_status', '')
    bldg_type = request.args.get('bldg_type', '')
    residential = request.args.get('residential', '')
    
    try:
        # Get leads database contacts
        contacts = get_all_contacts(
            search=search if search else None,
            mobile_only=mobile_only,
            source=source,
            limit=limit,
            offset=offset,
            borough=borough if borough else None,
            role=role if role else None,
            neighborhood=neighborhood if neighborhood else None,
            zip_code=zip_code if zip_code else None,
            job_type=job_type if job_type else None,
            work_type=work_type if work_type else None,
            permit_type=permit_type if permit_type else None,
            permit_status=permit_status if permit_status else None,
            bldg_type=bldg_type if bldg_type else None,
            residential=residential if residential else None
        )
        
        # Format leads contacts for frontend
        result = []
        seen_phones = set()
        
        for c in contacts:
            phone = c.get('phone_normalized')
            if phone:
                seen_phones.add(phone)
            result.append({
                'id': c.get('id'),
                'phone_number': phone,
                'name': c.get('name'),
                'company': c.get('company'),
                'permit_number': c.get('permit_no'),
                'address': c.get('address'),
                'role': c.get('role'),
                'source': c.get('source', c.get('contact_source')),
                'is_mobile': c.get('is_mobile', True),
                'borough': c.get('borough'),
                'neighborhood': c.get('neighborhood'),
                'zip_code': c.get('zip_code'),
                'job_type': c.get('job_type'),
                'work_type': c.get('work_type'),
                'permit_type': c.get('permit_type'),
                'permit_status': c.get('permit_status'),
                'bldg_type': c.get('bldg_type'),
                'residential': c.get('residential')
            })
        
        # Also include manual contacts (filter by search if provided)
        session = get_session()
        try:
            manual_query = session.query(ManualContact)
            if search:
                search_term = f'%{search}%'
                manual_query = manual_query.filter(
                    (ManualContact.name.ilike(search_term)) |
                    (ManualContact.phone_number.ilike(search_term)) |
                    (ManualContact.company.ilike(search_term))
                )
            if role:
                manual_query = manual_query.filter(ManualContact.role == role)
            
            manual_contacts = manual_query.all()
            
            for mc in manual_contacts:
                # Skip if already in leads results (dedupe by phone)
                if mc.phone_number in seen_phones:
                    continue
                seen_phones.add(mc.phone_number)
                result.append({
                    'id': f'manual_{mc.id}',
                    'phone_number': mc.phone_number,
                    'name': mc.name,
                    'company': mc.company,
                    'permit_number': None,
                    'address': None,
                    'role': mc.role,
                    'source': 'manual',
                    'is_mobile': True,  # Assume manual contacts are mobile
                    'borough': None
                })
        finally:
            session.close()
        
        total = get_total_contact_count(
            mobile_only=mobile_only, 
            source=source,
            borough=borough if borough else None,
            role=role if role else None
        )
        # Add manual contacts to total
        total += len([r for r in result if r.get('source') == 'manual'])
        
        return jsonify({
            'success': True, 
            'contacts': result,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/filter-options', methods=['GET'])
def get_contact_filter_options():
    """Get available filter options for contacts (neighborhoods, zip codes)"""
    try:
        from leads_service import get_leads_engine
        engine = get_leads_engine()
        
        with engine.connect() as conn:
            # Get top neighborhoods by count
            neighborhoods_result = conn.execute(text("""
                SELECT nta_name as value, COUNT(*) as cnt 
                FROM permits 
                WHERE nta_name IS NOT NULL AND nta_name != ''
                GROUP BY nta_name 
                ORDER BY cnt DESC 
                LIMIT 50
            """))
            neighborhoods = [{'value': r.value, 'label': f"{r.value} ({r.cnt:,})"} for r in neighborhoods_result]
            
            # Get top zip codes by count
            zips_result = conn.execute(text("""
                SELECT zip_code as value, COUNT(*) as cnt 
                FROM permits 
                WHERE zip_code IS NOT NULL AND zip_code != ''
                GROUP BY zip_code 
                ORDER BY cnt DESC 
                LIMIT 50
            """))
            zip_codes = [{'value': r.value, 'label': f"{r.value} ({r.cnt:,})"} for r in zips_result]
        
        return jsonify({
            'success': True,
            'neighborhoods': neighborhoods,
            'zip_codes': zip_codes
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


# ============ API Routes - Manual Contacts ============

def normalize_phone_number(phone):
    """Normalize phone number to E.164 format"""
    if not phone:
        return None
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    # Handle US numbers
    if len(digits) == 10:
        return f'+1{digits}'
    elif len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    elif len(digits) > 10:
        return f'+{digits}'
    return None


@app.route('/api/contacts/manual', methods=['GET'])
def get_manual_contacts():
    """Get all manually added contacts"""
    session = get_session()
    try:
        contacts = session.query(ManualContact).order_by(ManualContact.name).all()
        return jsonify({
            'success': True,
            'contacts': [c.to_dict() for c in contacts],
            'total': len(contacts)
        })
    finally:
        session.close()


@app.route('/api/contacts/manual', methods=['POST'])
def add_manual_contact():
    """Add a single manual contact"""
    data = request.json
    phone = data.get('phone') or data.get('phone_number')
    name = data.get('name')
    company = data.get('company')
    role = data.get('role')
    notes = data.get('notes')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number is required'}), 400
    
    normalized = normalize_phone_number(phone)
    if not normalized:
        return jsonify({'success': False, 'error': 'Invalid phone number format'}), 400
    
    session = get_session()
    try:
        # Check if already exists
        existing = session.query(ManualContact).filter_by(phone_number=normalized).first()
        if existing:
            return jsonify({'success': False, 'error': 'Contact with this phone number already exists'}), 400
        
        contact = ManualContact(
            phone_number=normalized,
            name=name,
            company=company,
            role=role,
            notes=notes
        )
        session.add(contact)
        session.commit()
        
        return jsonify({'success': True, 'contact': contact.to_dict()})
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/contacts/manual/<int:contact_id>', methods=['PUT'])
def update_manual_contact(contact_id):
    """Update a manual contact"""
    data = request.json
    session = get_session()
    try:
        contact = session.query(ManualContact).get(contact_id)
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        
        if 'name' in data:
            contact.name = data['name']
        if 'company' in data:
            contact.company = data['company']
        if 'role' in data:
            contact.role = data['role']
        if 'notes' in data:
            contact.notes = data['notes']
        if 'phone' in data or 'phone_number' in data:
            phone = data.get('phone') or data.get('phone_number')
            normalized = normalize_phone_number(phone)
            if normalized:
                contact.phone_number = normalized
        
        session.commit()
        return jsonify({'success': True, 'contact': contact.to_dict()})
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/contacts/manual/<int:contact_id>', methods=['DELETE'])
def delete_manual_contact(contact_id):
    """Delete a manual contact"""
    session = get_session()
    try:
        contact = session.query(ManualContact).get(contact_id)
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        
        session.delete(contact)
        session.commit()
        return jsonify({'success': True})
    finally:
        session.close()


@app.route('/api/contacts/manual/upload', methods=['POST'])
def upload_contacts_csv():
    """
    Bulk upload contacts via CSV.
    Expected columns: phone (required), name, company, role, notes
    """
    if 'file' not in request.files:
        # Check if CSV data was sent as text
        csv_data = request.form.get('csv_data') or request.json.get('csv_data') if request.is_json else None
        if not csv_data:
            return jsonify({'success': False, 'error': 'No file or CSV data provided'}), 400
        file_content = csv_data
    else:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        file_content = file.read().decode('utf-8')
    
    session = get_session()
    try:
        reader = csv.DictReader(io.StringIO(file_content))
        
        added = 0
        skipped = 0
        errors = []
        
        for i, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            # Find phone column (flexible naming)
            phone = row.get('phone') or row.get('Phone') or row.get('phone_number') or row.get('Phone Number') or row.get('mobile') or row.get('Mobile')
            
            if not phone:
                errors.append(f'Row {i}: Missing phone number')
                skipped += 1
                continue
            
            normalized = normalize_phone_number(phone)
            if not normalized:
                errors.append(f'Row {i}: Invalid phone number "{phone}"')
                skipped += 1
                continue
            
            # Check for duplicate
            existing = session.query(ManualContact).filter_by(phone_number=normalized).first()
            if existing:
                skipped += 1
                continue
            
            # Get other fields (flexible naming)
            name = row.get('name') or row.get('Name') or row.get('contact_name') or row.get('Contact Name')
            company = row.get('company') or row.get('Company') or row.get('business') or row.get('Business')
            role = row.get('role') or row.get('Role') or row.get('title') or row.get('Title')
            notes = row.get('notes') or row.get('Notes') or row.get('comments') or row.get('Comments')
            
            contact = ManualContact(
                phone_number=normalized,
                name=name,
                company=company,
                role=role,
                notes=notes
            )
            session.add(contact)
            added += 1
        
        session.commit()
        
        return jsonify({
            'success': True,
            'added': added,
            'skipped': skipped,
            'errors': errors[:10] if errors else []  # Return first 10 errors max
        })
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': f'CSV parsing error: {str(e)}'}), 400
    finally:
        session.close()


# ============ API Routes - Contact Notes (for Leads DB) ============

@app.route('/api/contacts/notes/<phone>', methods=['GET'])
def get_contact_note(phone):
    """Get notes for a leads DB contact"""
    normalized = normalize_phone_number(phone)
    if not normalized:
        return jsonify({'success': False, 'error': 'Invalid phone number'}), 400
    
    session = get_session()
    try:
        note = session.query(ContactNote).filter_by(phone_number=normalized).first()
        if note:
            return jsonify({'success': True, 'note': note.to_dict()})
        else:
            return jsonify({'success': True, 'note': {'phone_number': normalized, 'notes': None}})
    finally:
        session.close()


@app.route('/api/contacts/notes', methods=['POST'])
def save_contact_note():
    """Add or update notes for a leads DB contact"""
    data = request.json
    phone = data.get('phone') or data.get('phone_number')
    notes = data.get('notes', '')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number is required'}), 400
    
    normalized = normalize_phone_number(phone)
    if not normalized:
        return jsonify({'success': False, 'error': 'Invalid phone number'}), 400
    
    session = get_session()
    try:
        note = session.query(ContactNote).filter_by(phone_number=normalized).first()
        if note:
            note.notes = notes
        else:
            note = ContactNote(phone_number=normalized, notes=notes)
            session.add(note)
        
        session.commit()
        return jsonify({'success': True, 'note': note.to_dict()})
    except Exception as e:
        session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        session.close()


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
    
    # Recurring options
    is_recurring = data.get('is_recurring', False)
    recurrence_type = data.get('recurrence_type')  # daily, weekly, monthly
    recurrence_days = data.get('recurrence_days')  # For weekly: "mon,wed,fri"
    recurrence_end_date = data.get('recurrence_end_date')  # Optional end date
    
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
    
    # Parse recurrence end date if provided
    recurrence_end_dt = None
    if is_recurring and recurrence_end_date:
        try:
            recurrence_end_dt = datetime.fromisoformat(recurrence_end_date.replace('Z', '+00:00'))
        except:
            return jsonify({'success': False, 'error': 'Invalid recurrence end date format'}), 400
    
    try:
        result = message_scheduler.schedule_bulk_message(
            name=name,
            body=body,
            scheduled_at=scheduled_dt,
            phone_numbers=phone_numbers,
            is_recurring=is_recurring,
            recurrence_type=recurrence_type,
            recurrence_days=recurrence_days,
            recurrence_end_date=recurrence_end_dt
        )
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


@app.route('/api/scheduled/<int:message_id>/pause', methods=['POST'])
def pause_scheduled(message_id):
    """Pause a recurring scheduled message"""
    success = message_scheduler.pause_scheduled_message(message_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Could not pause message'}), 400


@app.route('/api/scheduled/<int:message_id>/resume', methods=['POST'])
def resume_scheduled(message_id):
    """Resume a paused scheduled message"""
    success = message_scheduler.resume_scheduled_message(message_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Could not resume message'}), 400


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
    
    # Track response in campaigns
    try:
        campaign_service.record_response(from_number, body)
    except Exception as e:
        logger.error(f"Error recording campaign response: {e}")
    
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


# ============ Campaign API Endpoints ============

@app.route('/api/campaigns', methods=['GET'])
@login_required
def list_campaigns():
    """List all campaigns"""
    status = request.args.get('status')
    campaigns = campaign_service.list_campaigns(status=status, include_stats=True)
    return jsonify({'success': True, 'campaigns': campaigns})


@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    """Create a new campaign"""
    data = request.get_json()
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Campaign name is required'}), 400
    
    user = get_current_user()
    
    campaign = campaign_service.create_campaign(
        name=data['name'],
        description=data.get('description'),
        enrollment_type=data.get('enrollment_type', 'snapshot'),
        filter_criteria=data.get('filter_criteria'),
        default_send_time=data.get('default_send_time', '11:00'),
        created_by=user.get('id') if user else None
    )
    
    return jsonify({'success': True, 'campaign': campaign})


@app.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
@login_required
def get_campaign(campaign_id):
    """Get campaign details"""
    campaign = campaign_service.get_campaign(campaign_id, include_stats=True)
    
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404
    
    return jsonify({'success': True, 'campaign': campaign})


@app.route('/api/campaigns/<int:campaign_id>', methods=['PUT'])
@login_required
def update_campaign(campaign_id):
    """Update campaign properties"""
    data = request.get_json()
    
    campaign = campaign_service.update_campaign(campaign_id, **data)
    
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404
    
    return jsonify({'success': True, 'campaign': campaign})


@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    """Delete a campaign (only if draft)"""
    try:
        success = campaign_service.delete_campaign(campaign_id)
        if not success:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/stats', methods=['GET'])
@login_required
def get_campaign_stats(campaign_id):
    """Get detailed campaign statistics"""
    stats = campaign_service.get_campaign_stats(campaign_id)
    
    if not stats:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404
    
    return jsonify({'success': True, 'stats': stats})


# ============ Campaign Messages API ============

@app.route('/api/campaigns/<int:campaign_id>/messages', methods=['POST'])
@login_required
def add_campaign_message(campaign_id):
    """Add a message to a campaign sequence"""
    data = request.get_json()
    
    if not data.get('message_body'):
        return jsonify({'success': False, 'error': 'Message body is required'}), 400
    
    message = campaign_service.add_message(
        campaign_id=campaign_id,
        message_body=data['message_body'],
        days_after_previous=data.get('days_after_previous', 0),
        send_time=data.get('send_time'),
        enable_followup=data.get('enable_followup', False),
        followup_days=data.get('followup_days', 3),
        followup_body=data.get('followup_body'),
        sequence_order=data.get('sequence_order')
    )
    
    if not message:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404
    
    return jsonify({'success': True, 'message': message})


@app.route('/api/campaigns/messages/<int:message_id>', methods=['PUT'])
@login_required
def update_campaign_message(message_id):
    """Update a campaign message"""
    data = request.get_json()
    
    message = campaign_service.update_message(message_id, **data)
    
    if not message:
        return jsonify({'success': False, 'error': 'Message not found'}), 404
    
    return jsonify({'success': True, 'message': message})


@app.route('/api/campaigns/messages/<int:message_id>', methods=['DELETE'])
@login_required
def delete_campaign_message(message_id):
    """Delete a campaign message"""
    try:
        success = campaign_service.delete_message(message_id)
        if not success:
            return jsonify({'success': False, 'error': 'Message not found'}), 404
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/messages/reorder', methods=['POST'])
@login_required
def reorder_campaign_messages(campaign_id):
    """Reorder campaign messages"""
    data = request.get_json()
    
    if not data.get('message_order'):
        return jsonify({'success': False, 'error': 'message_order array is required'}), 400
    
    success = campaign_service.reorder_messages(campaign_id, data['message_order'])
    
    return jsonify({'success': success})


# ============ Campaign A/B Testing API ============

@app.route('/api/campaigns/messages/<int:message_id>/ab-test', methods=['POST'])
@login_required
def setup_ab_test(message_id):
    """Set up A/B test for a message"""
    data = request.get_json()
    
    if not data.get('variant_b_body'):
        return jsonify({'success': False, 'error': 'variant_b_body is required'}), 400
    
    ab_test = campaign_service.setup_ab_test(message_id, data['variant_b_body'])
    
    if not ab_test:
        return jsonify({'success': False, 'error': 'Message not found'}), 404
    
    return jsonify({'success': True, 'ab_test': ab_test})


@app.route('/api/campaigns/messages/<int:message_id>/ab-test', methods=['DELETE'])
@login_required
def remove_ab_test(message_id):
    """Remove A/B test from a message"""
    success = campaign_service.remove_ab_test(message_id)
    
    if not success:
        return jsonify({'success': False, 'error': 'A/B test not found'}), 404
    
    return jsonify({'success': True})


# ============ Campaign Enrollment API ============

@app.route('/api/campaigns/preview-enrollment', methods=['POST'])
@login_required
def preview_enrollment():
    """Preview contacts that would be enrolled based on filters"""
    data = request.get_json()
    filter_criteria = data.get('filter_criteria', {})
    limit = data.get('limit', 50)
    offset = data.get('offset', 0)
    
    count, sample = campaign_service.preview_enrollment(filter_criteria, limit=limit, offset=offset)
    
    return jsonify({
        'success': True,
        'count': count,
        'sample': sample
    })


@app.route('/api/campaigns/check-overlap', methods=['POST'])
@login_required
def check_campaign_overlap():
    """Check if contacts are already in active campaigns"""
    data = request.get_json()
    phone_numbers = data.get('phone_numbers', [])
    
    if not phone_numbers:
        return jsonify({'success': True, 'overlaps': {}})
    
    overlaps = campaign_service.check_overlap(phone_numbers)
    
    return jsonify({
        'success': True,
        'overlaps': overlaps,
        'has_overlaps': len(overlaps) > 0
    })


@app.route('/api/campaigns/<int:campaign_id>/enroll', methods=['POST'])
@login_required
def enroll_contacts(campaign_id):
    """Enroll contacts in a campaign"""
    data = request.get_json()
    
    try:
        count = campaign_service.enroll_contacts(
            campaign_id=campaign_id,
            contacts=data.get('contacts'),
            use_filters=data.get('use_filters', False),
            exclude_phones=data.get('exclude_phones'),
            manual_contacts=data.get('manual_contacts')
        )
        
        return jsonify({'success': True, 'enrolled_count': count})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/enrollments', methods=['GET'])
@login_required
def get_campaign_enrollments(campaign_id):
    """Get campaign enrollments"""
    status = request.args.get('status')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    enrollments, total = campaign_service.get_enrollments(
        campaign_id=campaign_id,
        status=status,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        'success': True,
        'enrollments': enrollments,
        'total': total,
        'limit': limit,
        'offset': offset
    })


# ============ Campaign Lifecycle API ============

@app.route('/api/campaigns/<int:campaign_id>/start', methods=['POST'])
@login_required
def start_campaign(campaign_id):
    """Start a campaign"""
    try:
        campaign = campaign_service.start_campaign(campaign_id)
        return jsonify({'success': True, 'campaign': campaign})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/pause', methods=['POST'])
@login_required
def pause_campaign(campaign_id):
    """Pause a campaign"""
    try:
        campaign = campaign_service.pause_campaign(campaign_id)
        return jsonify({'success': True, 'campaign': campaign})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/resume', methods=['POST'])
@login_required
def resume_campaign(campaign_id):
    """Resume a paused campaign"""
    try:
        campaign = campaign_service.resume_campaign(campaign_id)
        return jsonify({'success': True, 'campaign': campaign})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/campaigns/<int:campaign_id>/complete', methods=['POST'])
@login_required
def complete_campaign(campaign_id):
    """Mark a campaign as completed"""
    try:
        campaign = campaign_service.complete_campaign(campaign_id)
        return jsonify({'success': True, 'campaign': campaign})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


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
