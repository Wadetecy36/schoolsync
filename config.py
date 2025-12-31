import os
from datetime import timedelta

class Config:
    """Base configuration"""
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change'
    
    # Database
    # Vercel provides DATABASE_URL. If missing, fallback to sqlite.
    uri = os.environ.get('DATABASE_URL')
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = uri or 'sqlite:///school.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection Pool Settings (Prevents Vercel 500 Errors)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # Upload settings
    UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True if os.environ.get('VERCEL') else False
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Mail & 2FA
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

config = {
    'development': Config,
    'production': Config,
    'default': Config
}