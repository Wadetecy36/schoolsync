"""
Application Factory for SchoolSync Pro
=======================================
Table of Contents
-----------------
1.  Imports & Setup
2.  Application Factory
3.  Extension Init
4.  Logging Setup
5.  CLI Commands (init-db, seed-data, etc.)
6.  Entry Point

Main application entry point using the factory pattern.

Author: SchoolSync Team
Last Updated: 2026-02-13
"""

from flask import Flask
from config import config, validate_production_config, validate_development_config, get_config_info
from extensions import db, csrf, limiter, cache, migrate, mail, login_manager
import os
import logging
import sys
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables first
load_dotenv()


# ============================================
# APPLICATION FACTORY
# ============================================

def create_app(config_name=None):
    """
    Application factory pattern.
    
    Creates and configures the Flask application with all extensions,
    blueprints, and CLI commands.
    
    Args:
        config_name (str): Configuration environment ('development', 'production', or None for auto-detect)
        
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    
    # ============================================
    # LOAD CONFIGURATION
    # ============================================
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(config[config_name])
    
    # ============================================
    # INITIALIZE EXTENSIONS
    # ============================================
    
    # Database
    db.init_app(app)
    
    # CSRF Protection
    csrf.init_app(app)
    
    # Email
    mail.init_app(app)
    
    # Rate Limiter
    try:
        limiter.init_app(app)
        limiter.storage_uri = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
        
        # Override default limits if specified in config
        if app.config.get('RATELIMIT_DEFAULT'):
            limits = app.config.get('RATELIMIT_DEFAULT').split(';')
            limiter.default_limits = [limit.strip() for limit in limits]
            
        app.logger.info(f"Rate limiter initialized with {limiter.storage_uri}")
    except Exception as e:
        app.logger.warning(f"Rate limiter initialization failed: {e}")
    
    # Cache
    try:
        cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})
        app.logger.info("Cache initialized")
    except Exception as e:
        app.logger.warning(f"Cache initialization failed: {e}")
    
    # Database Migrations
    migrate.init_app(app, db)
    
    # ============================================
    # FLASK-LOGIN CONFIGURATION
    # ============================================
    
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """
        Load user by ID for Flask-Login.
        """
        from models import User
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    @login_manager.request_loader
    def request_loader(request):
        """
        Allows Node.js app to authenticate via X-Internal-Secret header.
        """
        secret = os.environ.get('INTERNAL_SECRET_KEY')
        if not secret:
            return None
            
        auth_header = request.headers.get('X-Internal-Secret')
        if auth_header == secret:
            from models import User
            # Return the first super_admin as the acting user
            return User.query.filter_by(role='super_admin').first()
        return None
    
    # ============================================
    # CREATE UPLOAD FOLDER
    # ============================================
    
    # Only works locally (Vercel has read-only filesystem)
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            app.logger.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")
        except OSError as e:
            app.logger.warning(f"Could not create upload folder (read-only filesystem): {e}")
    
    # ============================================
    # SETUP LOGGING
    # ============================================
    
    setup_logging(app)
    
    # ============================================
    # REGISTER BLUEPRINTS
    # ============================================
    
    from routes import main
    from auth import auth
    
    app.register_blueprint(main)
    app.register_blueprint(auth)
    
    app.logger.info("Blueprints registered")
    
    # ============================================
    # REGISTER CLI COMMANDS
    # ============================================
    
    register_cli_commands(app)
    
    # ============================================
    # LOG CONFIGURATION INFO
    # ============================================
    
    if app.debug or app.config.get('FLASK_ENV') == 'development':
        config_info = get_config_info()
        app.logger.info("Configuration:")
        for key, value in config_info.items():
            app.logger.info(f"  {key}: {value}")
    
    # ============================================
    # PROXY CONFIGURATION
    # ============================================
    
    # Render (and most cloud providers) use reverse proxies.
    # ProxyFix ensures Flask correctly identifies the actual client IP
    # by looking at the X-Forwarded-For header.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    
    return app


# ============================================
# LOGGING SETUP
# ============================================

def setup_logging(app):
    """
    Setup application logging (compatible with serverless platforms).
    
    Logs to stdout for cloud platforms like Render and Vercel.
    
    Args:
        app: Flask application instance
    """
    if not app.debug and not app.testing:
        # Configure console logging
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        ))
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('SchoolSync Pro startup')


# ============================================
# CLI COMMANDS
# ============================================

def register_cli_commands(app):
    """
    Register Flask CLI commands.
    
    Commands:
        - flask init-db: Initialize database and create default admin
        - flask create-admin: Create a new admin user
        - flask cleanup-tokens: Clean up expired password reset tokens
        
    Args:
        app: Flask application instance
    """
    
    @app.cli.command()
    def init_db():
        """
        Initialize the database and create default admin user.
        
        Creates all tables and adds a default admin account.
        Safe to run multiple times (won't create duplicates).
        """
        from models import User
        
        print("Creating database tables...")
        db.create_all()
        print("[OK] Database tables created")
        
        # Check if default admin exists
        admin = User.query.filter_by(username='admin').first()
        
        if admin is None:
            # Create default admin
            admin_user = User(
                username='admin',
                email='admin@schoolsync.com',
                full_name='System Administrator',
                role='super_admin',
                is_active=True
            )
            admin_user.set_password('Admin@123')
            
            db.session.add(admin_user)
            db.session.commit()
            
            print("\n[OK] Default admin user created:")
            print("  Username: admin")
            print("  Password: Admin@123")
            print("  [!]  IMPORTANT: Change this password immediately!\n")
        else:
            print("[OK] Admin user already exists")
    
    @app.cli.command()
    def create_admin():
        """
        Create a new admin user interactively.
        
        Prompts for username, email, password, and role.
        """
        import getpass
        from models import User
        
        print("\n=== Create New Admin User ===\n")
        
        # Get username
        while True:
            username = input("Username: ").strip()
            if User.query.filter_by(username=username).first():
                print("❌ Username already exists. Try another.")
                continue
            if len(username) < 3:
                print("❌ Username must be at least 3 characters.")
                continue
            break
        
        # Get email
        while True:
            email = input("Email: ").strip()
            if User.query.filter_by(email=email).first():
                print("❌ Email already in use. Try another.")
                continue
            if '@' not in email:
                print("❌ Invalid email format.")
                continue
            break
        
        # Get full name
        full_name = input("Full Name: ").strip()
        
        # Get password
        while True:
            password = getpass.getpass("Password: ")
            if not User.validate_password(password):
                print("❌ Password must be 8+ characters with uppercase, lowercase, number, and special character.")
                continue
            confirm = getpass.getpass("Confirm Password: ")
            if password != confirm:
                print("❌ Passwords do not match.")
                continue
            break
        
        # Get role
        while True:
            role = input("Role (admin/super_admin) [admin]: ").strip() or 'admin'
            if role not in ['admin', 'super_admin']:
                print("❌ Invalid role. Choose 'admin' or 'super_admin'.")
                continue
            break
        
        # Create user
        try:
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                role=role,
                is_active=True
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            print(f"\n[OK] Admin user '{username}' created successfully!\n")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error creating user: {e}\n")
    
    @app.cli.command()
    def cleanup_tokens():
        """
        Clean up expired password reset tokens (older than 24 hours).
        
        Helps keep the database clean by removing old one-time tokens.
        """
        from models import UsedPasswordResetToken
        from datetime import datetime, timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=24)
        
        deleted = UsedPasswordResetToken.query.filter(
            UsedPasswordResetToken.used_at < cutoff
        ).delete()
        
        db.session.commit()
        
        print(f"[OK] Cleaned up {deleted} expired password reset tokens")
    
    @app.cli.command()
    def show_config():
        """
        Display current configuration (sanitized, no secrets).
        """
        config_info = get_config_info()
        
        print("\n=== SchoolSync Pro Configuration ===\n")
        for key, value in config_info.items():
            print(f"  {key.replace('_', ' ').title()}: {value}")
        print()

    @app.cli.command()
    def seed_data():
        """
        Seed database with initial Programs and Halls.
        
        Populates the database with default values from constants.
        Safe to run multiple times (skips existing entries).
        """
        from models import Program, Hall, VALID_PROGRAMS, VALID_HALLS
        
        print("\n=== Seeding Reference Data ===\n")
        
        # Seed Programs
        print("Checking Programs...")
        added_programs = 0
        for p_name in VALID_PROGRAMS:
            if not Program.query.filter_by(name=p_name).first():
                db.session.add(Program(name=p_name))
                print(f"  + Added: {p_name}")
                added_programs += 1
        
        # Seed Halls
        print("Checking Halls...")
        added_halls = 0
        for h_name in VALID_HALLS:
            if not Hall.query.filter_by(name=h_name).first():
                db.session.add(Hall(name=h_name))
                print(f"  + Added: {h_name}")
                added_halls += 1
                
        if added_programs or added_halls:
            db.session.commit()
            print(f"\n[OK] Added {added_programs} programs and {added_halls} halls.")
        else:
            print("\n[OK] All reference data already exists.")
        print()


# ============================================
# CREATE GLOBAL APP INSTANCE (FOR WSGI SERVERS)
# ============================================

# This is required for deployment platforms like Render, Gunicorn, etc.
app = create_app()


# ============================================
# DEVELOPMENT SERVER
# ============================================

if __name__ == '__main__':
    # Run development server
    app.run(debug=True, host='0.0.0.0', port=5000)