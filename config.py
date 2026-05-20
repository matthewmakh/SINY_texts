import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


class Config:
    # Twilio
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    
    # SMS Dashboard Database (can be SQLite locally or PostgreSQL on Railway)
    DATABASE_URL = os.getenv('DATABASE_URL') or 'sqlite:///sms_dashboard.db'
    
    # External Leads Database (Railway PostgreSQL - for live contact queries)
    LEADS_DATABASE_URL = os.getenv('LEADS_DATABASE_URL')
    
    # Flask
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Webhook
    WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:5000')

    # Public base URL for tracking pixels / click redirects / unsubscribe links / OAuth callback
    # Falls back to WEBHOOK_BASE_URL if not set explicitly.
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL') or os.getenv('WEBHOOK_BASE_URL', 'http://localhost:5000')

    # Google OAuth — for connecting Gmail / Workspace mailboxes (Instantly-style rotation)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
        'GOOGLE_OAUTH_REDIRECT_URI',
        f"{PUBLIC_BASE_URL.rstrip('/')}/api/email/oauth/callback"
    )

    # Anthropic API — for AI personalization on email campaigns
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')

    @classmethod
    def validate(cls):
        """Validate required configuration on startup"""
        required = {
            'TWILIO_ACCOUNT_SID': cls.TWILIO_ACCOUNT_SID,
            'TWILIO_AUTH_TOKEN': cls.TWILIO_AUTH_TOKEN,
            'TWILIO_PHONE_NUMBER': cls.TWILIO_PHONE_NUMBER,
            'LEADS_DATABASE_URL': cls.LEADS_DATABASE_URL,
        }
        
        missing = [k for k, v in required.items() if not v]
        
        if missing:
            logging.error(f"Missing required environment variables: {', '.join(missing)}")
            logging.error("Please set these in Railway environment variables")
            return False
        
        logging.info("✓ Configuration validated successfully")
        return True
