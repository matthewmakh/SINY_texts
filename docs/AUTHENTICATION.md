# Authentication System

## Overview

The SMS Dashboard uses a shared authentication system that works across multiple SINY dashboards (SMS Dashboard, DOB Permit Dashboard). User credentials and sessions are stored in the shared PostgreSQL leads database.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (app.js)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Login Screen│  │  User Menu  │  │   User Management       │  │
│  │             │  │  (sidebar)  │  │   (admin only)          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (auth.py)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Decorators  │  │  Password   │  │   Session Management    │  │
│  │ @login_req  │  │  Hashing    │  │   (token-based)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              PostgreSQL (Shared Leads Database)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ auth_users  │  │auth_sessions│  │   auth_roles            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Roles & Permissions

### Available Roles

| Role | Description |
|------|-------------|
| **admin** | Full access to all features, can manage users |
| **manager** | Can view all data, send messages, manage contacts |
| **agent** | Can send messages, view assigned data |
| **viewer** | Read-only access |

### Permission Matrix

| Permission | Admin | Manager | Agent | Viewer |
|------------|:-----:|:-------:|:-----:|:------:|
| **SMS** |
| Send messages | ✓ | ✓ | ✓ | |
| Bulk send | ✓ | ✓ | | |
| View all messages | ✓ | ✓ | | |
| Create templates | ✓ | ✓ | | |
| Edit templates | ✓ | ✓ | | |
| Delete templates | ✓ | | | |
| Schedule messages | ✓ | ✓ | | |
| **Contacts** |
| View contacts | ✓ | ✓ | ✓ | ✓ |
| Create contacts | ✓ | ✓ | | |
| Edit contacts | ✓ | ✓ | | |
| Delete contacts | ✓ | | | |
| Export contacts | ✓ | ✓ | | |
| **Admin** |
| View users | ✓ | | | |
| Create users | ✓ | | | |
| Edit users | ✓ | | | |
| Delete users | ✓ | | | |

## Authentication Flow

### Login
1. User enters email/password on login screen
2. Frontend calls `POST /api/auth/login`
3. Backend verifies credentials against `auth_users` table
4. On success, creates session token in `auth_sessions` table
5. Token stored in `auth_token` cookie (7 day expiry)
6. Frontend hides login screen, shows app

### Session Validation
1. Every API call checks for `auth_token` cookie
2. Token validated against `auth_sessions` table
3. If valid, `last_activity` timestamp updated
4. If invalid/expired, returns 401 Unauthorized
5. Frontend shows login screen on 401

### Logout
1. User clicks logout in user menu
2. Frontend calls `POST /api/auth/logout`
3. Backend deletes session from `auth_sessions`
4. Cookie cleared, login screen shown

## Database Schema

### auth_users
```sql
CREATE TABLE auth_users (
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
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    preferences JSONB DEFAULT '{}',
    allowed_dashboards TEXT[] DEFAULT ARRAY['sms', 'permits']
);
```

### auth_sessions
```sql
CREATE TABLE auth_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dashboard VARCHAR(50) DEFAULT 'sms'
);
```

### auth_roles
```sql
CREATE TABLE auth_roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions TEXT[] DEFAULT ARRAY[]::TEXT[],
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Password Security

- Passwords hashed with SHA-256
- 10,000 iterations (PBKDF2-like)
- Random 32-byte salt per user
- Timing-safe comparison to prevent attacks

## Default Admin Account

On first run (when no users exist), a default admin is created:

| Field | Value |
|-------|-------|
| Email | `matt@tyeny.com` |
| Password | `changeme123!` (or `DEFAULT_ADMIN_PASSWORD` env var) |
| Role | `admin` |

**⚠️ IMPORTANT: Change this password immediately after first login!**

## API Endpoints

See [API_ENDPOINTS.md](API_ENDPOINTS.md#authentication-api) for full endpoint documentation.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Authenticate user |
| `/api/auth/logout` | POST | End session |
| `/api/auth/me` | GET | Get current user |
| `/api/auth/change-password` | POST | Change password |
| `/api/users` | GET | List all users (admin) |
| `/api/users` | POST | Create user (admin) |
| `/api/users/:id` | PUT | Update user (admin) |
| `/api/users/:id` | DELETE | Delete user (admin) |
| `/api/users/:id/reset-password` | POST | Reset password (admin) |

## Frontend Components

### Login Screen
- Full-screen overlay (`#login-screen`)
- Shows on page load if not authenticated
- Hidden after successful login

### User Menu
- Located in sidebar footer
- Shows current user name and role
- Dropdown with "Change Password" and "Sign Out"

### User Management (Admin Only)
- Separate view in navigation
- Table of all users with role badges
- Create/edit/delete users
- Reset user passwords

## Decorators

### @login_required
Requires valid session for route access.

```python
@app.route('/api/some-route')
@login_required
def some_route():
    user = g.current_user  # Access current user
    return jsonify({'success': True})
```

### @role_required(*roles)
Requires specific role(s).

```python
@app.route('/api/admin-only')
@role_required('admin')
def admin_only():
    return jsonify({'success': True})
```

### @permission_required(permission)
Requires specific permission.

```python
@app.route('/api/send-sms')
@permission_required('sms.send')
def send_sms():
    return jsonify({'success': True})
```

## Branch Status

| Branch | Auth Status |
|--------|-------------|
| `main` | No auth (public access) |
| `staging` | Auth enabled (login required) |

Auth will be merged to main after testing on staging.
