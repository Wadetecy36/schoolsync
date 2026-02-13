"""
Configuration Module for SchoolSync Pro
========================================
Table of Contents
-----------------
1.  Imports & Setup
2.  Config Class
    2.1 Security Settings
    2.2 Database Config
    2.3 File Uploads
    2.4 Email & SMS
    2.5 Rate Limiting
3.  Environment Validation
4.  Config Exports

Handles environment-based configuration for development and production.

Author: SchoolSync Team
Last Updated: 2026-02-13
"""

import os
from datetime import timedelta
import sys


# ============================================
# CONFIGURATION CLASS
# ============================================

class Config:
    """
    Base configuration class.
    
    Loads settings from environment variables with sensible defaults.
    Supports both development (SQLite) and production (PostgreSQL) databases.
    """
    
    # ============================================
    # SECURITY SETTINGS
    # ============================================
    
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True if os.environ.get('VERCEL') or os.environ.get('PRODUCTION') else False
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ============================================
    # DATABASE CONFIGURATION
    # ============================================
    
    # Get database URL from environment
    uri = os.environ.get('DATABASE_URL')
    
    # Fix Heroku/Render postgres:// to postgresql://
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    # Use PostgreSQL in production, SQLite in development
    SQLALCHEMY_DATABASE_URI = uri or 'sqlite:///school.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection Pool Settings (Prevents connection issues on serverless)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Verify connections before using
        "pool_recycle": 300,    # Recycle connections every 5 minutes
        "pool_size": 10,        # Connection pool size
        "max_overflow": 20      # Maximum overflow connections
    }
    
    # ============================================
    # FILE UPLOAD SETTINGS
    # ============================================
    
    # Upload folder (use /tmp on serverless platforms)
    UPLOAD_FOLDER = '/tmp' if os.environ.get('VERCEL') else 'static/uploads'
    
    # Maximum upload size: 16MB (for file uploads, images are limited separately)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # ============================================
    # EMAIL CONFIGURATION (FIXED TLS/SSL CONFLICT)
    # ============================================
    
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    
    # FIX: Auto-detect TLS vs SSL based on port
    # Port 587 = TLS (STARTTLS)
    # Port 465 = SSL (SMTPS)
    # Port 25 = No encryption (not recommended)
    if MAIL_PORT == 587:
        MAIL_USE_TLS = True
        MAIL_USE_SSL = False
    elif MAIL_PORT == 465:
        MAIL_USE_TLS = False
        MAIL_USE_SSL = True
    else:
        # Allow manual override for custom ports
        MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False') == 'True'
        MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME
    
    # ============================================
    # SMS CONFIGURATION (TWILIO - OPTIONAL)
    # ============================================
    
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    
    # ============================================
    # RATE LIMITING CONFIGURATION
    # ============================================
    
    # Use Redis in production, memory in development
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '5000 per day;1000 per hour')
    
    # ============================================
    # APPLICATION SETTINGS
    # ============================================
    
    # Application name
    APP_NAME = 'SchoolSync Pro'
    
    # Pagination
    STUDENTS_PER_PAGE = 20
    
    # Timezone
    TIMEZONE = 'UTC'


# ============================================
# ENVIRONMENT VALIDATION
# ============================================

def validate_production_config():
    """
    Validate that required environment variables are set for production.
    
    Raises:
        ValueError: If required variables are missing
    """
    required_vars = {
        'SECRET_KEY': 'Application secret key for security',
        'DATABASE_URL': 'PostgreSQL database connection string',
        'MAIL_SERVER': 'SMTP server for sending emails',
        'MAIL_USERNAME': 'Email account username',
        'MAIL_PASSWORD': 'Email account password (or app password)',
    }
    
    missing = []
    for var, description in required_vars.items():
        if not os.environ.get(var):
            missing.append(f"  - {var}: {description}")
    
    if missing:
        error_msg = "Missing required environment variables:\n" + "\n".join(missing)
        print(f"\n❌ CONFIGURATION ERROR:\n{error_msg}\n", file=sys.stderr)
        raise ValueError(error_msg)


def validate_development_config():
    """
    Validate development configuration and show warnings.
    """
    warnings = []
    
    if Config.SECRET_KEY == 'dev-key-please-change-in-production':
        warnings.append("Using default SECRET_KEY (only safe for development)")
    
    if not os.environ.get('MAIL_SERVER'):
        warnings.append("MAIL_SERVER not set - email features will not work")
    
    if Config.SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        warnings.append("Using SQLite database (switch to PostgreSQL for production)")
    
    if warnings:
        print("\n⚠️  Development Configuration Warnings:", file=sys.stdout)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stdout)
        print()


def get_config_info():
    """
    Get configuration information for debugging.
    
    Returns:
        dict: Configuration summary (sanitized, no secrets)
    """
    return {
        'database': 'PostgreSQL' if 'postgresql' in Config.SQLALCHEMY_DATABASE_URI else 'SQLite',
        'email_configured': bool(Config.MAIL_SERVER and Config.MAIL_USERNAME),
        'email_port': Config.MAIL_PORT,
        'email_encryption': 'TLS' if Config.MAIL_USE_TLS else ('SSL' if Config.MAIL_USE_SSL else 'None'),
        'sms_configured': bool(Config.TWILIO_ACCOUNT_SID),
        'session_secure': Config.SESSION_COOKIE_SECURE,
        'rate_limit_backend': 'Redis' if 'redis' in Config.RATELIMIT_STORAGE_URL else 'Memory'
    }


# ============================================
# CONFIGURATION DICT
# ============================================

config = {
    'development': Config,
    'production': Config,
    'default': Config
}


# ============================================
# AUTO-VALIDATION
# ============================================

# Automatically validate on import if PRODUCTION is set
if os.environ.get('PRODUCTION') or os.environ.get('VERCEL'):
    try:
        validate_production_config()
        print("✅ Production configuration validated", file=sys.stdout)
    except ValueError:
        # Let application handle this, don't crash on import
        pass
elif os.environ.get('FLASK_ENV') == 'development':
    validate_development_config()