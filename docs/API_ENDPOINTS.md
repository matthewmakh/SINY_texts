# API Endpoints Reference

## Authentication

All API endpoints require authentication via session cookie (except `/api/auth/login`).

---

## Authentication API

### POST /api/auth/login

Authenticate a user and create a session.

**Request Body:**
```json
{
    "email": "user@example.com",
    "password": "yourpassword"
}
```

**Response (Success):**
```json
{
    "success": true,
    "user": {
        "id": 1,
        "email": "user@example.com",
        "name": "John Doe",
        "role": "admin",
        "allowed_dashboards": ["sms", "permits"]
    }
}
```

**Response (Error):**
```json
{
    "success": false,
    "error": "Invalid credentials"
}
```

**Note:** On success, sets `auth_token` cookie (HttpOnly, 7 day expiry).

---

### POST /api/auth/logout

End the current session.

**Response:**
```json
{
    "success": true
}
```

---

### GET /api/auth/me

Get current authenticated user info.

**Response (Authenticated):**
```json
{
    "success": true,
    "user": {
        "id": 1,
        "email": "user@example.com",
        "name": "John Doe",
        "role": "admin",
        "allowed_dashboards": ["sms", "permits"]
    }
}
```

**Response (Not Authenticated):**
```json
{
    "success": false,
    "error": "Not authenticated"
}
```

---

### POST /api/auth/change-password

Change the current user's password.

**Request Body:**
```json
{
    "current_password": "oldpassword",
    "new_password": "newpassword123"
}
```

**Response:**
```json
{
    "success": true
}
```

---

## User Management API (Admin Only)

### GET /api/users

List all users. Requires `admin` role.

**Response:**
```json
{
    "success": true,
    "users": [
        {
            "id": 1,
            "email": "admin@example.com",
            "name": "Admin User",
            "role": "admin",
            "is_active": true,
            "last_login": "2025-12-29T10:30:00",
            "created_at": "2025-12-29T08:00:00",
            "allowed_dashboards": ["sms", "permits"]
        }
    ]
}
```

---

### POST /api/users

Create a new user. Requires `admin` role.

**Request Body:**
```json
{
    "email": "newuser@example.com",
    "password": "temppassword123",
    "name": "New User",
    "role": "agent",
    "allowed_dashboards": ["sms"]
}
```

**Response:**
```json
{
    "success": true,
    "user": {
        "id": 2,
        "email": "newuser@example.com",
        "name": "New User",
        "role": "agent",
        "is_active": true,
        "allowed_dashboards": ["sms"]
    }
}
```

---

### PUT /api/users/<id>

Update a user. Requires `admin` role.

**Request Body:**
```json
{
    "name": "Updated Name",
    "role": "manager",
    "is_active": true,
    "allowed_dashboards": ["sms", "permits"]
}
```

**Response:**
```json
{
    "success": true,
    "user": {
        "id": 2,
        "email": "user@example.com",
        "name": "Updated Name",
        "role": "manager",
        "is_active": true,
        "allowed_dashboards": ["sms", "permits"]
    }
}
```

---

### DELETE /api/users/<id>

Delete a user. Requires `admin` role.

**Response:**
```json
{
    "success": true
}
```

---

### POST /api/users/<id>/reset-password

Reset a user's password. Requires `admin` role.

**Request Body:**
```json
{
    "new_password": "newpassword123"
}
```

**Response:**
```json
{
    "success": true
}
```

---

## Contacts API

### GET /api/contacts

Retrieve contacts from leads database and manual contacts.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | - | Search name, phone, company |
| `mobile_only` | boolean | true | Only return mobile numbers |
| `source` | string | 'all' | 'permit', 'owner', or 'all' |
| `limit` | int | 100 | Max results |
| `offset` | int | 0 | Pagination offset |
| `borough` | string | - | MANHATTAN, BROOKLYN, QUEENS, BRONX, STATEN ISLAND |
| `role` | string | - | Owner, Permittee |
| `neighborhood` | string | - | NTA name (e.g., "Midtown-Midtown South") |
| `zip_code` | string | - | 5-digit zip |
| `job_type` | string | - | A1, A2, A3, NB, DM, SG |
| `work_type` | string | - | OT, PL, EQ, MH, SP, FP, BL, SD |
| `permit_type` | string | - | EW, PL, EQ, AL, NB, DM, SG, FO |
| `permit_status` | string | - | ISSUED, RE-ISSUED, IN PROCESS |
| `bldg_type` | string | - | 1, 2 |
| `residential` | string | - | YES |

**Response:**
```json
{
    "success": true,
    "contacts": [
        {
            "id": 12345,
            "phone_number": "+12125551234",
            "name": "John Smith",
            "company": "ABC Construction",
            "permit_number": "123456789",
            "address": "123 Main St, Manhattan",
            "role": "Owner",
            "source": "permit_contact",
            "is_mobile": true,
            "borough": "MANHATTAN",
            "neighborhood": "Midtown-Midtown South",
            "zip_code": "10001",
            "job_type": "A1",
            "work_type": "OT",
            "permit_type": "AL",
            "permit_status": "ISSUED",
            "bldg_type": "2",
            "residential": "YES"
        }
    ],
    "total": 17050,
    "limit": 100,
    "offset": 0
}
```

**Example:**
```javascript
// Get all mobile contacts for Brooklyn owners with new building permits
const response = await API.get('/contacts?mobile_only=true&borough=BROOKLYN&role=Owner&job_type=NB');
```

---

### GET /api/contacts/filter-options

Get dynamic filter options (neighborhoods, zip codes) for dropdowns.

**Response:**
```json
{
    "success": true,
    "neighborhoods": [
        {"value": "Midtown-Midtown South", "label": "Midtown-Midtown South (5,523)"},
        {"value": "Hudson Yards-Chelsea-...", "label": "Hudson Yards-Chelsea-... (2,701)"}
    ],
    "zip_codes": [
        {"value": "10022", "label": "10022 (2,001)"},
        {"value": "10019", "label": "10019 (1,645)"}
    ]
}
```

---

### GET /api/contacts/stats

Get statistics about available contacts.

**Response:**
```json
{
    "success": true,
    "stats": {
        "total_contacts": 17050,
        "mobile_contacts": 17050,
        "by_role": {
            "Owner": 13080,
            "Permittee": 3970
        }
    }
}
```

---

### POST /api/contacts/manual

Add a manual contact.

**Request Body:**
```json
{
    "name": "Jane Doe",
    "phone_number": "+12125559999",
    "company": "XYZ Corp",
    "role": "Owner",
    "notes": "Met at trade show"
}
```

**Response:**
```json
{
    "success": true,
    "contact": {
        "id": 1,
        "name": "Jane Doe",
        "phone_number": "+12125559999",
        "company": "XYZ Corp",
        "role": "Owner",
        "notes": "Met at trade show",
        "source": "manual"
    }
}
```

---

### PUT /api/contacts/manual/<id>

Update a manual contact.

---

### DELETE /api/contacts/manual/<id>

Delete a manual contact.

---

### POST /api/contacts/manual/upload

Bulk upload manual contacts from CSV file.

**Request:** `multipart/form-data` with file field named `file`

**CSV Format:**
```csv
name,phone,company,role
John Smith,+12125551234,ABC Corp,Manager
Jane Doe,2125555678,XYZ Inc,Director
```

**Response:**
```json
{
    "success": true,
    "imported": 2,
    "skipped": 0,
    "errors": []
}
```

---

## Contact Notes API

### GET /api/contacts/notes/<phone>

Get notes for a leads database contact.

**Response:**
```json
{
    "success": true,
    "notes": "Called on 12/29, interested in follow-up"
}
```

---

### POST /api/contacts/notes

Save notes for a leads database contact.

**Request Body:**
```json
{
    "phone_normalized": "+12125551234",
    "notes": "Called on 12/29, interested in follow-up"
}
```

**Response:**
```json
{
    "success": true,
    "notes": "Called on 12/29, interested in follow-up"
}
```

---

## Messages API

### GET /api/conversations

Get list of all conversations (grouped by phone number).

**Response:**
```json
{
    "success": true,
    "conversations": [
        {
            "phone": "+12125551234",
            "name": "John Smith",
            "company": "ABC Corp",
            "last_message": "Thanks for the info!",
            "last_message_time": "2025-12-29T15:30:00Z",
            "direction": "inbound",
            "unread_count": 2
        }
    ]
}
```

---

### GET /api/messages/<phone>

Get message history for a specific phone number.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Max messages |

**Response:**
```json
{
    "success": true,
    "messages": [
        {
            "sid": "SM123...",
            "body": "Hello!",
            "direction": "outbound-api",
            "status": "delivered",
            "date_sent": "2025-12-29T15:30:00Z"
        }
    ],
    "contact": {
        "name": "John Smith",
        "company": "ABC Corp",
        "source": "permit_contact"
    }
}
```

---

### POST /api/messages/send

Send an SMS message.

**Request Body:**
```json
{
    "recipients": ["+12125551234", "+12125555678"],
    "message": "Hello {name}, this is a test message."
}
```

**Response:**
```json
{
    "success": true,
    "sent": 2,
    "failed": 0,
    "results": [
        {"phone": "+12125551234", "status": "sent", "sid": "SM123..."},
        {"phone": "+12125555678", "status": "sent", "sid": "SM456..."}
    ]
}
```

**Safety Limit:** Maximum 50 recipients per request.

---

### POST /api/messages/schedule

Schedule a message for later.

**Request Body:**
```json
{
    "recipients": ["+12125551234"],
    "message": "Scheduled message",
    "scheduled_time": "2025-12-30T10:00:00Z",
    "is_recurring": false
}
```

**For recurring:**
```json
{
    "recipients": ["+12125551234"],
    "message": "Weekly reminder",
    "scheduled_time": "2025-12-30T10:00:00Z",
    "is_recurring": true,
    "recurrence_type": "weekly",
    "recurrence_days": [1, 3, 5]
}
```

---

## Templates API

### GET /api/templates

Get all message templates.

---

### POST /api/templates

Create a new template.

**Request Body:**
```json
{
    "name": "Follow Up",
    "body": "Hi {name}, following up on the permit at {address}."
}
```

---

### PUT /api/templates/<id>

Update a template.

---

### DELETE /api/templates/<id>

Delete a template.

---

## Scheduled Messages API

### GET /api/scheduled

Get all scheduled messages.

---

### DELETE /api/scheduled/<id>

Cancel a scheduled message.

---

### POST /api/scheduled/<id>/pause

Pause a recurring scheduled message.

**Response:**
```json
{
    "success": true,
    "message": "Schedule paused"
}
```

---

### POST /api/scheduled/<id>/resume

Resume a paused recurring scheduled message.

**Response:**
```json
{
    "success": true,
    "message": "Schedule resumed"
}
```

---

## Auth API

### POST /api/login

Authenticate user.

**Request Body:**
```json
{
    "username": "admin",
    "password": "secret"
}
```

---

### POST /api/logout

End session.

---

### POST /api/change-password

Change current user's password.

**Request Body:**
```json
{
    "current_password": "old",
    "new_password": "new"
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
    "success": false,
    "error": "Error message description"
}
```

HTTP Status Codes:
- `200` - Success
- `400` - Bad request (validation error)
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not found
- `500` - Server error
