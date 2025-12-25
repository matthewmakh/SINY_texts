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
