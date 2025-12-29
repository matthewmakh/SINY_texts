"""
Shared Authentication Module for SINY Dashboards

This module provides role-based authentication that can be used across:
- SMS Dashboard (this project)
- DOB Permit Dashboard (NYC-DOB-permit-search-and-parse)

Users and roles are stored in the shared PostgreSQL database (LEADS_DATABASE_URL)
so authentication state is consistent across all dashboards.

Roles and Permissions:
- admin: Full access to all features across all dashboards
- manager: Can view all data, send messages, manage contacts
- agent: Can view assigned data, send messages
- viewer: Read-only access
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, g
import psycopg2
from psycopg2.extras import RealDictCursor


# Permission definitions for each dashboard feature
PERMISSIONS = {
    # SMS Dashboard permissions
    'sms.send': ['admin', 'manager', 'agent'],
    'sms.bulk_send': ['admin', 'manager'],
    'sms.view_all': ['admin', 'manager'],
    'sms.view_assigned': ['admin', 'manager', 'agent'],
    'sms.templates.create': ['admin', 'manager'],
    'sms.templates.edit': ['admin', 'manager'],
    'sms.templates.delete': ['admin'],
    'sms.schedule': ['admin', 'manager'],
    
    # Contact permissions
    'contacts.view': ['admin', 'manager', 'agent', 'viewer'],
    'contacts.create': ['admin', 'manager'],
    'contacts.edit': ['admin', 'manager'],
    'contacts.delete': ['admin'],
    'contacts.export': ['admin', 'manager'],
    
    # DOB Permit Dashboard permissions (shared across dashboards)
    'permits.view': ['admin', 'manager', 'agent', 'viewer'],
    'permits.export': ['admin', 'manager'],
    'buildings.view': ['admin', 'manager', 'agent', 'viewer'],
    'leads.view': ['admin', 'manager', 'agent', 'viewer'],
    'leads.assign': ['admin', 'manager'],
    'analytics.view': ['admin', 'manager', 'viewer'],
    
    # Admin permissions
    'users.view': ['admin'],
    'users.create': ['admin'],
    'users.edit': ['admin'],
    'users.delete': ['admin'],
    'settings.view': ['admin', 'manager'],
    'settings.edit': ['admin'],
}


def get_auth_db_connection():
    """Get connection to the shared leads database for auth tables"""
    from config import Config
    
    db_url = Config.LEADS_DATABASE_URL
    if not db_url:
        raise ValueError("LEADS_DATABASE_URL not configured")
    
    # Parse the URL if it's in postgresql:// format
    if db_url.startswith('postgresql://') or db_url.startswith('postgres://'):
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    else:
        return psycopg2.connect(
            host=os.getenv('LEADS_DB_HOST'),
            port=os.getenv('LEADS_DB_PORT', 5432),
            database=os.getenv('LEADS_DB_NAME'),
            user=os.getenv('LEADS_DB_USER'),
            password=os.getenv('LEADS_DB_PASSWORD'),
            cursor_factory=RealDictCursor
        )


def init_auth_tables():
    """
    Initialize authentication tables in the shared database.
    These tables will be used by all dashboards.
    """
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'viewer',
                is_active BOOLEAN DEFAULT TRUE,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER REFERENCES auth_users(id),
                
                -- Profile/settings
                phone VARCHAR(20),
                avatar_url VARCHAR(500),
                preferences JSONB DEFAULT '{}',
                
                -- For tracking which dashboards they can access
                allowed_dashboards TEXT[] DEFAULT ARRAY['sms', 'permits']
            );
            
            CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_users(email);
            CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role);
        """)
        
        # Sessions table (for token-based auth)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES auth_users(id) ON DELETE CASCADE,
                token VARCHAR(255) UNIQUE NOT NULL,
                ip_address VARCHAR(45),
                user_agent TEXT,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Which dashboard this session is for
                dashboard VARCHAR(50) DEFAULT 'sms'
            );
            
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);
        """)
        
        # Roles table (for custom roles in the future)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                description TEXT,
                permissions TEXT[] DEFAULT ARRAY[]::TEXT[],
                is_system BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Insert default roles if they don't exist
            INSERT INTO auth_roles (name, display_name, description, permissions, is_system)
            VALUES 
                ('admin', 'Administrator', 'Full access to all features', ARRAY['*'], TRUE),
                ('manager', 'Manager', 'Can manage team and view all data', ARRAY[
                    'sms.send', 'sms.bulk_send', 'sms.view_all', 'sms.templates.create', 
                    'sms.templates.edit', 'sms.schedule', 'contacts.view', 'contacts.create',
                    'contacts.edit', 'contacts.export', 'permits.view', 'permits.export',
                    'buildings.view', 'leads.view', 'leads.assign', 'analytics.view',
                    'settings.view'
                ], TRUE),
                ('agent', 'Agent', 'Can send messages and view assigned data', ARRAY[
                    'sms.send', 'sms.view_assigned', 'contacts.view', 'permits.view',
                    'buildings.view', 'leads.view'
                ], TRUE),
                ('viewer', 'Viewer', 'Read-only access', ARRAY[
                    'contacts.view', 'permits.view', 'buildings.view', 'leads.view',
                    'analytics.view'
                ], TRUE)
            ON CONFLICT (name) DO NOTHING;
        """)
        
        # Activity log table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_activity_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES auth_users(id),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(100),
                resource_id VARCHAR(100),
                details JSONB,
                ip_address VARCHAR(45),
                dashboard VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_auth_activity_user ON auth_activity_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_activity_action ON auth_activity_log(action);
            CREATE INDEX IF NOT EXISTS idx_auth_activity_date ON auth_activity_log(created_at);
        """)
        
        conn.commit()
        print("Auth tables initialized successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error initializing auth tables: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def hash_password(password, salt=None):
    """Hash a password with salt using SHA-256"""
    if salt is None:
        salt = secrets.token_hex(32)
    
    # Use PBKDF2-like iteration
    combined = f"{salt}{password}".encode('utf-8')
    for _ in range(10000):
        combined = hashlib.sha256(combined).digest()
    
    password_hash = combined.hex()
    return password_hash, salt


def verify_password(password, password_hash, salt):
    """Verify a password against its hash"""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


def generate_session_token():
    """Generate a secure session token"""
    return secrets.token_urlsafe(64)


# ============ User Management Functions ============

def create_user(email, password, name, role='viewer', created_by=None, allowed_dashboards=None):
    """Create a new user"""
    if allowed_dashboards is None:
        allowed_dashboards = ['sms', 'permits']
    
    password_hash, salt = hash_password(password)
    
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO auth_users (email, password_hash, salt, name, role, created_by, allowed_dashboards)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, name, role, is_active, created_at, allowed_dashboards;
        """, (email.lower(), password_hash, salt, name, role, created_by, allowed_dashboards))
        
        user = cur.fetchone()
        conn.commit()
        return {'success': True, 'user': dict(user)}
        
    except psycopg2.IntegrityError:
        conn.rollback()
        return {'success': False, 'error': 'Email already exists'}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def authenticate_user(email, password, dashboard='sms'):
    """Authenticate a user and create a session"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, email, password_hash, salt, name, role, is_active, allowed_dashboards
            FROM auth_users
            WHERE email = %s;
        """, (email.lower(),))
        
        user = cur.fetchone()
        
        if not user:
            return {'success': False, 'error': 'Invalid credentials'}
        
        if not user['is_active']:
            return {'success': False, 'error': 'Account is deactivated'}
        
        if not verify_password(password, user['password_hash'], user['salt']):
            return {'success': False, 'error': 'Invalid credentials'}
        
        # Check if user can access this dashboard
        if dashboard not in user['allowed_dashboards']:
            return {'success': False, 'error': f'No access to {dashboard} dashboard'}
        
        # Create session token
        token = generate_session_token()
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:500] if request else None
        
        cur.execute("""
            INSERT INTO auth_sessions (user_id, token, ip_address, user_agent, expires_at, dashboard)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (user['id'], token, ip_address, user_agent, expires_at, dashboard))
        
        # Update last login
        cur.execute("""
            UPDATE auth_users SET last_login = CURRENT_TIMESTAMP WHERE id = %s;
        """, (user['id'],))
        
        conn.commit()
        
        return {
            'success': True,
            'token': token,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'name': user['name'],
                'role': user['role'],
                'allowed_dashboards': user['allowed_dashboards']
            },
            'expires_at': expires_at.isoformat()
        }
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def validate_session(token, dashboard='sms'):
    """Validate a session token and return user info"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT s.id as session_id, s.expires_at, s.dashboard,
                   u.id, u.email, u.name, u.role, u.is_active, u.allowed_dashboards
            FROM auth_sessions s
            JOIN auth_users u ON s.user_id = u.id
            WHERE s.token = %s AND s.expires_at > CURRENT_TIMESTAMP;
        """, (token,))
        
        result = cur.fetchone()
        
        if not result:
            return None
        
        if not result['is_active']:
            return None
        
        # Update last activity
        cur.execute("""
            UPDATE auth_sessions SET last_activity = CURRENT_TIMESTAMP WHERE id = %s;
        """, (result['session_id'],))
        conn.commit()
        
        return {
            'id': result['id'],
            'email': result['email'],
            'name': result['name'],
            'role': result['role'],
            'allowed_dashboards': result['allowed_dashboards']
        }
        
    except Exception as e:
        print(f"Session validation error: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def logout_user(token):
    """Invalidate a session token"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM auth_sessions WHERE token = %s;", (token,))
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def get_user_by_id(user_id):
    """Get user details by ID"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, email, name, role, is_active, last_login, created_at, 
                   phone, avatar_url, preferences, allowed_dashboards
            FROM auth_users WHERE id = %s;
        """, (user_id,))
        
        user = cur.fetchone()
        return dict(user) if user else None
        
    finally:
        cur.close()
        conn.close()


def update_user(user_id, **kwargs):
    """Update user details"""
    allowed_fields = ['name', 'role', 'is_active', 'phone', 'avatar_url', 'preferences', 'allowed_dashboards']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return {'success': False, 'error': 'No valid fields to update'}
    
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        set_clause = ', '.join([f"{k} = %s" for k in updates.keys()])
        values = list(updates.values()) + [user_id]
        
        cur.execute(f"""
            UPDATE auth_users 
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, email, name, role, is_active, allowed_dashboards;
        """, values)
        
        user = cur.fetchone()
        conn.commit()
        
        return {'success': True, 'user': dict(user)} if user else {'success': False, 'error': 'User not found'}
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def delete_user(user_id):
    """Delete a user and all their sessions"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        # First delete user's sessions
        cur.execute("DELETE FROM auth_sessions WHERE user_id = %s;", (user_id,))
        
        # Then delete the user
        cur.execute("DELETE FROM auth_users WHERE id = %s RETURNING id;", (user_id,))
        deleted = cur.fetchone()
        
        conn.commit()
        
        if deleted:
            return {'success': True}
        else:
            return {'success': False, 'error': 'User not found'}
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def change_password(user_id, old_password, new_password):
    """Change user's password"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT password_hash, salt FROM auth_users WHERE id = %s;", (user_id,))
        user = cur.fetchone()
        
        if not user:
            return {'success': False, 'error': 'User not found'}
        
        if not verify_password(old_password, user['password_hash'], user['salt']):
            return {'success': False, 'error': 'Current password is incorrect'}
        
        new_hash, new_salt = hash_password(new_password)
        
        cur.execute("""
            UPDATE auth_users 
            SET password_hash = %s, salt = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (new_hash, new_salt, user_id))
        
        conn.commit()
        return {'success': True}
        
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cur.close()
        conn.close()


def list_users(include_inactive=False):
    """List all users"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        query = """
            SELECT id, email, name, role, is_active, last_login, created_at, allowed_dashboards
            FROM auth_users
        """
        if not include_inactive:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY created_at DESC;"
        
        cur.execute(query)
        users = cur.fetchall()
        return [dict(u) for u in users]
        
    finally:
        cur.close()
        conn.close()


def get_roles():
    """Get all available roles"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT name, display_name, description, permissions
            FROM auth_roles ORDER BY id;
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


# ============ Permission Checking ============

def has_permission(user, permission):
    """Check if a user has a specific permission"""
    if not user:
        return False
    
    role = user.get('role', 'viewer')
    
    # Admin has all permissions
    if role == 'admin':
        return True
    
    # Check against permission definitions
    allowed_roles = PERMISSIONS.get(permission, [])
    return role in allowed_roles


def get_user_permissions(user):
    """Get all permissions for a user"""
    if not user:
        return []
    
    role = user.get('role', 'viewer')
    
    if role == 'admin':
        return list(PERMISSIONS.keys())
    
    return [perm for perm, roles in PERMISSIONS.items() if role in roles]


# ============ Flask Decorators ============

def get_current_user():
    """Get the current user from request"""
    # Check for token in header
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        # Check for token in cookie
        token = request.cookies.get('auth_token')
    
    if not token:
        return None
    
    return validate_session(token)


def login_required(f):
    """Decorator to require login for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    """Decorator to require specific permission for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            if not has_permission(user, permission):
                return jsonify({'success': False, 'error': 'Permission denied'}), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*roles):
    """Decorator to require specific role(s) for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            if user.get('role') not in roles:
                return jsonify({'success': False, 'error': 'Insufficient privileges'}), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============ Activity Logging ============

def log_activity(user_id, action, resource_type=None, resource_id=None, details=None, dashboard='sms'):
    """Log user activity"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        ip_address = request.remote_addr if request else None
        
        cur.execute("""
            INSERT INTO auth_activity_log (user_id, action, resource_type, resource_id, details, ip_address, dashboard)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (user_id, action, resource_type, resource_id, 
              psycopg2.extras.Json(details) if details else None, 
              ip_address, dashboard))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error logging activity: {e}")
    finally:
        cur.close()
        conn.close()


# ============ Bootstrap Admin User ============

def create_admin_if_needed():
    """Create default admin user if no users exist"""
    conn = get_auth_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT COUNT(*) as count FROM auth_users;")
        count = cur.fetchone()['count']
        
        if count == 0:
            # Create default admin
            default_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'changeme123!')
            result = create_user(
                email='matt@tyeny.com',
                password=default_password,
                name='Matt',
                role='admin',
                allowed_dashboards=['sms', 'permits']
            )
            if result['success']:
                print("Default admin user created: matt@tyeny.com")
                print(f"Default password: {default_password}")
                print("IMPORTANT: Change this password immediately!")
            return result
        
        return {'success': True, 'message': 'Users already exist'}
        
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    # Initialize tables and create admin user
    print("Initializing auth tables...")
    init_auth_tables()
    print("\nChecking for admin user...")
    create_admin_if_needed()
