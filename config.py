import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    
    # SMS Dashboard Database (local)
    DATABASE_URL = os.getenv('DATABASE_URL') or 'sqlite:///sms_dashboard.db'
    
    # External Leads Database (Railway - for syncing contacts)
    LEADS_DATABASE_URL = os.getenv('LEADS_DATABASE_URL')
    
    # Flask
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Webhook
    WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:5000')
