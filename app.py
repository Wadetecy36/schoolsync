from flask import Flask
from config import config
from models import db
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_migrate import Migrate
from flask_mail import Mail
import os
import logging
import sys  # Required for Vercel logging
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Initialize extensions
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
cache = Cache()
migrate = Migrate()
mail = Mail()

def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    
    # Initialize limiter
    try:
        limiter.init_app(app)
        limiter.storage_uri = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
    except Exception as e:
        app.logger.warning(f"Rate limiter initialization failed: {e}")
    
    # Initialize cache
    try:
        cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})
    except Exception as e:
        app.logger.warning(f"Cache initialization failed: {e}")
    
    # Initialize migrations
    migrate.init_app(app, db)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return db.session.get(User, int(user_id))
    
    # Create upload folder (Only works locally, ignored on Vercel)
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        try:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        except OSError:
            pass  # Read-only filesystem on Vercel
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    from routes import main
    from auth import auth
    app.register_blueprint(main)
    app.register_blueprint(auth)
    
    # CLI commands
    register_cli_commands(app)
    
    return app

def setup_logging(app):
    """Setup application logging (Compatible with Vercel)"""
    if not app.debug and not app.testing:
        # Log to stdout (Console) instead of a file
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('SchoolSync Pro startup')

def register_cli_commands(app):
    @app.cli.command()
    def init_db():
        """Initialize the database and create default admin"""
        db.create_all()
        
        from models import User
        if User.query.filter_by(username='admin').first() is None:
            user = User(
                username='admin',
                email='admin@schoolsync.com',
                full_name='System Administrator',
                role='super_admin'
            )
            user.set_password('Admin@123')
            db.session.add(user)
            db.session.commit()
            print("✓ Database initialized and default admin created.")
        else:
            print("✓ Database initialized (Admin already exists).")

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)