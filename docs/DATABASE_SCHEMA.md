# Database Schema

## Overview

The SMS Dashboard uses two databases:

1. **Local SQLite** (`sms_dashboard.db`) - App-specific data
2. **PostgreSQL** (Railway hosted) - Leads/permit data

---

## Local SQLite Database

Defined in `database.py`

### Users Table

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',  -- 'admin' or 'user'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME
);
```

### Templates Table

```sql
CREATE TABLE templates (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    body TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);
```

**Template Variables:**
- `{name}` - Contact name
- `{company}` - Company name
- `{role}` - Contact role
- `{phone}` - Contact phone number
- `{date}` - Current date (Eastern Time)
- `{time}` - Current time (Eastern Time)

### Manual Contacts Table

```sql
CREATE TABLE manual_contacts (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    phone_number VARCHAR(20) UNIQUE NOT NULL,  -- E.164 format
    company VARCHAR(100),
    role VARCHAR(50),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);
```

### Messages Table

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    twilio_sid VARCHAR(50) UNIQUE,      -- Twilio message SID
    phone_number VARCHAR(20) NOT NULL,  -- E.164 format
    body TEXT NOT NULL,
    direction VARCHAR(20) DEFAULT 'outbound',  -- outbound, inbound
    status VARCHAR(20) DEFAULT 'pending',      -- pending, sent, delivered, failed
    scheduled_at DATETIME,
    sent_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);
```

### Scheduled Messages Table

```sql
CREATE TABLE scheduled_bulk_messages (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    recipient_phones TEXT NOT NULL,     -- JSON array of phone numbers
    scheduled_at DATETIME NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_progress, completed, cancelled, failed, paused
    total_recipients INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- Recurring schedule fields
    is_recurring BOOLEAN DEFAULT FALSE,
    recurrence_type VARCHAR(20),        -- daily, weekly, monthly
    recurrence_days VARCHAR(50),        -- For weekly: "mon,wed,fri" etc.
    recurrence_end_date DATETIME,       -- Optional end date (null = forever)
    last_sent_at DATETIME,              -- Track last successful send
    send_count INTEGER DEFAULT 0        -- Total times this schedule has sent
);
```

### Contact Notes Table

```sql
CREATE TABLE contact_notes (
    id INTEGER PRIMARY KEY,
    phone_number VARCHAR(20) UNIQUE NOT NULL,  -- Links to leads contact (E.164)
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);
```

---

## PostgreSQL Leads Database

Connected via `leads_service.py` using `LEADS_DATABASE_URL` env var.

### Permits Table (~83,000 records)

```sql
CREATE TABLE permits (
    id SERIAL PRIMARY KEY,
    permit_no VARCHAR(50),
    address TEXT,
    borough VARCHAR(50),              -- MANHATTAN, BROOKLYN, QUEENS, BRONX, STATEN ISLAND
    zip_code VARCHAR(10),
    nta_name VARCHAR(100),            -- Neighborhood name (e.g., "Midtown-Midtown South")
    job_type VARCHAR(10),             -- A1, A2, A3, NB, DM, SG
    work_type VARCHAR(10),            -- OT, PL, EQ, MH, SP, FP, BL, SD
    permit_type VARCHAR(10),          -- EW, PL, EQ, AL, NB, DM, SG, FO
    permit_status VARCHAR(20),        -- ISSUED, RE-ISSUED, IN PROCESS
    bldg_type VARCHAR(5),             -- 1 (One/Two Family), 2 (Multiple Dwelling)
    residential VARCHAR(10),          -- YES or NULL
    owner_business_name TEXT,
    filing_date DATE,
    issuance_date DATE,
    expiration_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Job Types:**
| Code | Description |
|------|-------------|
| A1 | Alteration Type 1 (major) |
| A2 | Alteration Type 2 (minor) |
| A3 | Alteration Type 3 (cosmetic) |
| NB | New Building |
| DM | Demolition |
| SG | Sign |

**Work Types:**
| Code | Description |
|------|-------------|
| OT | Other |
| PL | Plumbing |
| EQ | Equipment |
| MH | Mechanical/HVAC |
| SP | Sprinkler |
| FP | Fire Protection |
| BL | Boiler |
| SD | Standpipe |

### Contacts Table (~17,050 mobile records)

```sql
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    phone VARCHAR(20),                -- 10-digit format (no +1)
    role VARCHAR(50),                 -- Owner, Permittee
    is_mobile BOOLEAN,                -- Carrier lookup result
    carrier_name VARCHAR(100),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Stats (Dec 2025):**
- Total mobile contacts: **17,050**
- Owners: **13,080**
- Permittees: **3,970**
- No duplicate phone numbers

### Permit Contacts Junction Table

```sql
CREATE TABLE permit_contacts (
    id SERIAL PRIMARY KEY,
    permit_id INTEGER REFERENCES permits(id),
    contact_id INTEGER REFERENCES contacts(id),
    UNIQUE(permit_id, contact_id)
);
```

---

## Query Patterns

### Get Contacts with Permit Data (used in Contact Picker)

```sql
SELECT DISTINCT ON (c.phone)
    c.id,
    c.name,
    c.phone,
    c.role,
    c.is_mobile,
    p.permit_no,
    p.address,
    p.owner_business_name as company,
    p.borough,
    p.nta_name as neighborhood,
    p.zip_code,
    p.job_type,
    p.work_type,
    p.permit_type,
    p.permit_status,
    p.bldg_type,
    p.residential
FROM contacts c
LEFT JOIN permit_contacts pc ON c.id = pc.contact_id
LEFT JOIN permits p ON pc.permit_id = p.id
WHERE c.phone IS NOT NULL 
AND c.is_mobile = true
-- Additional filters applied dynamically
ORDER BY c.phone, c.updated_at DESC
```

### Get Top Neighborhoods (for filter dropdown)

```sql
SELECT nta_name as value, COUNT(*) as cnt 
FROM permits 
WHERE nta_name IS NOT NULL AND nta_name != ''
GROUP BY nta_name 
ORDER BY cnt DESC 
LIMIT 50
```

### Get Top Zip Codes (for filter dropdown)

```sql
SELECT zip_code as value, COUNT(*) as cnt 
FROM permits 
WHERE zip_code IS NOT NULL AND zip_code != ''
GROUP BY zip_code 
ORDER BY cnt DESC 
LIMIT 50
```

---

## Phone Number Formats

| Database | Format | Example |
|----------|--------|---------|
| Leads DB (contacts.phone) | 10 digits | `2125551234` |
| Local DB (manual_contacts.phone_number) | E.164 | `+12125551234` |
| Twilio | E.164 | `+12125551234` |

**Normalization in leads_service.py:**
```python
def normalize_phone(phone):
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) == 10:
        return f'+1{digits}'
    elif len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    return phone
```
