"""
Base Package Initialization
Flask application factory with all configuration
"""
import os
import sys
import warnings

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from datetime import timedelta
from pathlib import Path
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from concurrent.futures import ThreadPoolExecutor
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
from flask_socketio import SocketIO
from sympy import false

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# ============================================
# CREATE FLASK APP
# ============================================
app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25,
    logger=False,
    engineio_logger=False
)

# ============================================
# SECRET KEY CONFIGURATION
# ============================================
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if os.getenv('FLASK_ENV') == 'production':
        raise ValueError("❌ SECRET_KEY must be set in production environment")
    else:
        SECRET_KEY = '9f4c8e1b7a3d2f6c5e9a1d4b8f7c2e6a9d3c7b5e1f8a4c6d2e9b7a3f1c5d8e6'
        print("⚠️  Using development SECRET_KEY")

app.config['SECRET_KEY'] = SECRET_KEY
app.secret_key = SECRET_KEY

# ============================================
# ENVIRONMENT CONFIGURATION
# ============================================
flask_env = os.getenv('FLASK_ENV', 'development')

if flask_env == 'production':
    app.config['DEBUG'] = False
    app.config['TESTING'] = False
    print("🔒 Running in PRODUCTION mode")
else:
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    app.config['TESTING'] = False
    print("🔧 Running in DEVELOPMENT mode")

# ============================================
# DATABASE CONFIGURATION
# ============================================
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    if os.getenv('FLASK_ENV') == 'production':
        print("⚠️  WARNING: DATABASE_URL not set in production!")
    DATABASE_URL = 'mysql+pymysql://root:root@localhost:3306/chatbot_panel'
    print("⚠️  Using local development database")
else:
    print("✅ Using configured database")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = os.getenv('SQLALCHEMY_ECHO', 'False').lower() == 'true'
app.config['SQLALCHEMY_MAX_OVERFLOW'] = int(os.getenv('SQLALCHEMY_MAX_OVERFLOW', '20'))

# Connection pool settings
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': int(os.getenv('SQLALCHEMY_POOL_SIZE', 10)),
    'pool_recycle': int(os.getenv('SQLALCHEMY_POOL_RECYCLE', 3600)),
    'pool_pre_ping': os.getenv('SQLALCHEMY_POOL_PRE_PING', 'True').lower() == 'true',
    'max_overflow': int(os.getenv('SQLALCHEMY_MAX_OVERFLOW', 20)),
    'pool_timeout': 30,
    'connect_args': {'connect_timeout': 10}
}

# ============================================
# SESSION CONFIGURATION
# ============================================
# ============================================
# SESSION & SECURITY CONFIGURATION
# ============================================
# ★ FIX: Only set to True if you actually have an SSL (HTTPS) certificate installed!
# For now, we will set it to False so HTTP connections don't drop the session.
app.config['SESSION_COOKIE_SECURE'] = False

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ============================================
# FILE STORAGE CONFIGURATION
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATA_FOLDER = os.getenv('BASE_DATA_FOLDER', os.path.join(BASE_DIR, '..', 'data'))

# Ensure data folder exists
os.makedirs(BASE_DATA_FOLDER, exist_ok=True)

app.config['BASE_DATA_FOLDER'] = BASE_DATA_FOLDER
app.config['USER_DATA_FOLDER'] = os.getenv(
    'USER_DATA_FOLDER',
    os.path.join(BASE_DATA_FOLDER, 'users')
)
app.config['UPLOAD_FOLDER'] = os.getenv(
    'UPLOAD_FOLDER',
    os.path.join(BASE_DATA_FOLDER, 'uploads')
)
app.config['AVATARS_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')

# Create upload directories
os.makedirs(app.config['USER_DATA_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AVATARS_FOLDER'], exist_ok=True)

# File size limits
max_content_mb = int(os.getenv('MAX_CONTENT_LENGTH', '52428800'))  # 50MB default
app.config['MAX_CONTENT_LENGTH'] = max_content_mb

print(f"✅ Data folder: {BASE_DATA_FOLDER}")

# File upload configuration
allowed_ext_str = os.getenv('ALLOWED_EXTENSIONS', 'png,jpg,jpeg,gif,svg')
ALLOWED_EXTENSIONS = set(ext.strip() for ext in allowed_ext_str.split(','))
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '2097152'))  # 2MB

# ============================================
# EMAIL CONFIGURATION (PROPERLY ORDERED)
# ============================================
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_FROM_ADDRESS')

if app.config['MAIL_PASSWORD']:
    print(f"✅ Email configured: {app.config['MAIL_USERNAME']} (Password Loaded from .env!)")
else:
    print("⚠️  Email not configured - Password is BLANK!")

# ============================================
# PERFORMANCE & CACHING
# ============================================
# Version for cache busting
app.config['VERSION'] = os.getenv('APP_VERSION', '1.0.0')

# Different cache settings for dev vs production
if flask_env == 'production':
    # Cache static files for 1 year in production
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000
    print("✅ Static file caching: ENABLED (1 year)")
else:
    # No caching in development for easier CSS/JS changes
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    print("✅ Static file caching: DISABLED (development mode)")

# ============================================
# SECURITY HEADERS
# ============================================
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""

    # Only disable caching for HTML pages, not static files
    if response.mimetype == 'text/html':
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Surrogate-Control"] = "no-store"
    elif flask_env != 'production':
        # In development, also disable caching for CSS/JS
        if response.mimetype in ['text/css', 'application/javascript', 'application/x-javascript']:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # Security headers for all responses
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ✅ Allow iFrame embedding from any website
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        # Remove X-Frame-Options — it overrides CSP and blocks iFrames

    return response

# ============================================
# INITIALIZE EXTENSIONS
# ============================================
db = SQLAlchemy(app)
app.app_context().push()
migrate = Migrate(app, db)

# MUST BE INITIALIZED AFTER app.config ABOVE
mail = Mail(app)

# Thread pool executor for async tasks
executor = ThreadPoolExecutor(max_workers=10)

# URL serializer for tokens
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# ============================================
# TEMPLATE FILTERS
# ============================================
@app.template_filter('from_json')
def from_json_filter(s):
    """Safely parse JSON in templates"""
    import json
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return {}

# ============================================
# TEMPLATE CONTEXT PROCESSORS
# ============================================
@app.context_processor
def inject_version():
    """Inject version number for cache busting in templates"""
    return {
        'app_version': app.config['VERSION'],
        'flask_env': flask_env
    }

# ============================================
# CREATE DIRECTORY STRUCTURE
# ============================================
def create_directory_structure():
    """Create all necessary directory structure"""
    directories = [
        app.config['USER_DATA_FOLDER'],
        app.config['UPLOAD_FOLDER'],
        app.config['AVATARS_FOLDER'],
        os.path.join(BASE_DATA_FOLDER, 'temp'),
        os.path.join(BASE_DATA_FOLDER, 'backups')
    ]

    # Add log directory if configured
    log_file = os.getenv('LOG_FILE')
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            directories.append(log_dir)

    for directory in directories:
        try:
            os.makedirs(directory, mode=0o755, exist_ok=True)
            if app.config.get('DEBUG'):
                print(f"✓ Directory ready: {directory}")
        except Exception as e:
            print(f"✗ Failed to create {directory}: {e}")
            raise

create_directory_structure()

# ============================================
# CONFIGURE LOGGING (Production)
# ============================================
if os.getenv('LOG_FILE'):
    import logging
    from logging.handlers import RotatingFileHandler

    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE')
    max_bytes = int(os.getenv('LOG_MAX_BYTES', '10485760'))  # 10MB
    backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))

    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    handler.setLevel(getattr(logging, log_level))
    app.logger.addHandler(handler)
    app.logger.setLevel(getattr(logging, log_level))

# ============================================
# INITIALIZE SUBSCRIPTION PLANS (First Request)
# ============================================
@app.before_request
def setup_once():
    """Initialize subscription plans on first request"""
    if not hasattr(app, 'initialized'):
        with app.app_context():
            from base.com.dao.subscription_dao import initialize_subscription_plans
            initialize_subscription_plans()
        app.initialized = True

# ============================================
# IMPORT MODELS (Register with SQLAlchemy)
# ============================================
from base.com.vo import (
    user_vo,
    chatbot_vo,
    qa_pair_vo,
    subscription_vo,
    session_vo
)

# ============================================
# REGISTER CONTROLLERS (Blueprints)
# ============================================
from base.com.controller import *

# ============================================
# EXPORT FOR EXTERNAL USE
# ============================================
__all__ = ['app', 'db', 'mail', 'migrate', 'executor', 'serializer']


@app.after_request
def add_security_headers(response):
    from flask import request as flask_request

    # Allow iFrame for embed routes
    if '/embed/' in flask_request.path:
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        response.headers.pop("X-Frame-Options", None)
    else:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

    # Rest of your headers...
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response