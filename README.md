# SMS Dashboard for PNYC Building Permits

A clean, modern dashboard for managing and scheduling bulk SMS messages via Twilio. Built to integrate with your PNYC building permit scraper database on Railway.

## Features

- 📱 Send individual and bulk SMS messages
- 💬 View and respond to conversations in real-time
- 📅 Schedule messages for future delivery
- 👥 **Live contacts from your PNYC leads database** (no sync needed!)
- 📝 Create and use message templates
- 📊 Dashboard with message statistics
- 🔗 Twilio webhook integration for incoming messages
- 🚀 **Railway deployment ready**

## Architecture

This dashboard uses a **live query architecture**:
- **Contacts**: Queried directly from your Railway PostgreSQL leads database (52,666+ contacts)
- **Messages/Templates/Scheduled**: Stored locally in SQLite (or PostgreSQL on Railway)

This means your contacts are always up-to-date with your permit scraper - no syncing required!

## Project Structure

```
├── app.py                 # Flask backend API
├── config.py              # Configuration settings
├── database.py            # SQLAlchemy models (messages, templates, scheduled)
├── leads_service.py       # Live query service for leads database
├── twilio_service.py      # Twilio integration
├── scheduler.py           # Message scheduling
├── requirements.txt       # Python dependencies
├── Procfile               # Railway/Heroku deployment
├── .env.example           # Environment template
├── templates/
│   └── index.html         # Dashboard HTML
└── static/
    ├── css/
    │   └── style.css      # Styles
    └── js/
        └── app.js         # Frontend JavaScript
```

## Railway Deployment

### 1. Create New Railway Service

1. Go to your Railway project
2. Click **"New Service"** → **"GitHub Repo"**
3. Select the `SINY_texts` repository

### 2. Configure Environment Variables

In Railway, add these environment variables:

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
LEADS_DATABASE_URL=postgresql://postgres:xxx@maglev.proxy.rlwy.net:26571/railway
DATABASE_URL=sqlite:///sms_dashboard.db
```

> **Note**: `LEADS_DATABASE_URL` should point to your existing PNYC leads database on Railway.

### 3. Deploy

Railway will automatically:
- Detect Python from `requirements.txt`
- Use `Procfile` to run gunicorn
- Deploy your app

### 4. Configure Twilio Webhooks

Once deployed, update your Twilio phone number webhooks:
- **Incoming Messages**: `https://your-app.railway.app/api/webhook/incoming`
- **Status Callbacks**: `https://your-app.railway.app/api/webhook/status`

## Local Development

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Initialize Database

```bash
python -c "from database import init_db; init_db()"
```

### 4. Run the Application

```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## API Endpoints

### Messages
- `GET /api/messages` - Get message history
- `POST /api/messages/send` - Send a single SMS
- `POST /api/messages/bulk` - Send bulk SMS

### Conversations
- `GET /api/conversations` - Get all conversations
- `GET /api/conversations/<phone>` - Get messages for a conversation

### Contacts (Live from Leads DB)
- `GET /api/contacts` - Get contacts with pagination & filters
- `GET /api/contacts/stats` - Get contact counts
- `POST /api/contacts` - Create a contact
- `PUT /api/contacts/<id>` - Update a contact
- `DELETE /api/contacts/<id>` - Delete a contact
- `POST /api/contacts/import` - Import contacts from JSON

### Scheduling
- `GET /api/scheduled` - Get scheduled messages
- `POST /api/scheduled` - Schedule a new message
- `DELETE /api/scheduled/<id>` - Cancel a scheduled message

### Templates
- `GET /api/templates` - Get all templates
- `POST /api/templates` - Create a template
- `DELETE /api/templates/<id>` - Delete a template

### Stats
- `GET /api/stats` - Get dashboard statistics

## Importing Contacts from Permit Scraper

You can import contacts directly from your permit scraper database. Example JSON format:

```json
[
  {
    "phone_number": "+12125551234",
    "name": "John Doe",
    "company": "ABC Construction",
    "permit_number": "P2024-001234",
    "address": "123 Main St, New York, NY"
  }
]
```

Use the Import feature in the Contacts section or POST to `/api/contacts/import`.

## Database Integration

To connect to your existing permit scraper database, update `DATABASE_URL` in `.env`:

```
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost/dbname

# MySQL
DATABASE_URL=mysql://user:password@localhost/dbname

# SQLite (default)
DATABASE_URL=sqlite:///sms_dashboard.db
```

## Production Deployment

1. Set `FLASK_DEBUG=False` in `.env`
2. Generate a secure `FLASK_SECRET_KEY`
3. Use gunicorn for production:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## License

MIT
