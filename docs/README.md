# SINY SMS Dashboard

## Project Overview

The SINY SMS Dashboard is a web application for managing SMS communications with building permit contacts in New York City. It integrates with Twilio for SMS and connects to a PostgreSQL leads database containing permit and contact information.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Dashboard  │  │   Compose   │  │   Contact Picker        │  │
│  │  (Messages) │  │   (Send)    │  │   (Filters + Pagination)│  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask Backend (app.py)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Auth       │  │  API        │  │  Twilio Service         │  │
│  │  (auth.py)  │  │  Endpoints  │  │  (twilio_service.py)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Local SQLite DB       │     │   PostgreSQL Leads DB   │
│   (sms_dashboard.db)    │     │   (Railway hosted)      │
│   - Users               │     │   - permits (83k)       │
│   - Templates           │     │   - contacts (17k mob)  │
│   - Manual Contacts     │     │   - permit_contacts     │
│   - Scheduled Messages  │     │                         │
└─────────────────────────┘     └─────────────────────────┘
```

## Tech Stack

- **Backend**: Python/Flask
- **Frontend**: Vanilla JavaScript, HTML, CSS
- **Databases**: 
  - SQLite (local app data)
  - PostgreSQL (leads data via `leads_service.py`)
- **SMS**: Twilio API
- **Hosting**: Railway (staging + production)
- **Version Control**: GitHub (`matthewmakh/SINY_texts`)

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Main Flask application, all API endpoints |
| `auth.py` | Authentication module - login, sessions, user management, permissions |
| `database.py` | SQLite models (Templates, ManualContacts, ScheduledMessages) |
| `leads_service.py` | PostgreSQL leads database queries |
| `twilio_service.py` | Twilio SMS integration |
| `scheduler.py` | Background job scheduler for scheduled messages |
| `config.py` | Environment configuration |
| `static/js/app.js` | Frontend JavaScript (1900+ lines) |
| `static/css/style.css` | Styling (2100+ lines) |
| `templates/index.html` | Main HTML template |

## Authentication

The dashboard uses role-based authentication (currently on `staging` branch).

| Role | Description |
|------|-------------|
| admin | Full access, user management |
| manager | Send messages, view all, manage contacts |
| agent | Send messages, view assigned |
| viewer | Read-only |

See [AUTHENTICATION.md](AUTHENTICATION.md) for full documentation.

## Deployment

### Branches
- `main` → Production (texts.installersny.com)
- `staging` → Staging environment

### Deploy Commands
```bash
# Push to staging
git add -A && git commit -m "message" && git push origin staging

# Deploy to production
git checkout main && git merge staging && git push origin main
```

## Environment Variables

Required in `.env`:
```
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+1xxx
LEADS_DATABASE_URL=postgresql://...
SECRET_KEY=xxx
```

## Safety Limits

- **Max 50 recipients** per message (enforced in frontend and backend)
- Scheduled messages require explicit recipient selection
- No "send to all" functionality for safety
