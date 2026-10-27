import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    JWT_SECRET = os.environ.get('JWT_SECRET') or os.environ.get('SECRET_KEY') or 'smart-traffic-jwt-super-secret-key-32b'
    CLIENT_URL = os.environ.get('CLIENT_URL', 'http://localhost:5173,http://127.0.0.1:5173')
    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', '24'))
    _raw_db_url = os.environ.get('DATABASE_URL')
    if _raw_db_url and _raw_db_url.startswith('sqlite:///') and not _raw_db_url.startswith('sqlite:////') and ':' not in _raw_db_url[10:]:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, _raw_db_url[10:]).replace('\\', '/')
    elif _raw_db_url:
        SQLALCHEMY_DATABASE_URI = _raw_db_url
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'smart_traffic.db').replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    DEVICE_OFFLINE_TIMEOUT_SECONDS = int(os.environ.get('DEVICE_OFFLINE_TIMEOUT_SECONDS', '30'))
    DEVICE_MINIMUM_INTERVAL_SECONDS = float(os.environ.get('DEVICE_MINIMUM_INTERVAL_SECONDS', '0.5'))
    DENSITY_FLOW_THRESHOLDS_PER_MINUTE = {
        'LOW_MAX': 10,
        'MEDIUM_MAX': 25,
        'HIGH_MAX': 45,
    }
    
    # Upload & Media Configurations
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB limit
    MODEL_FOLDER = os.path.join(BASE_DIR, 'ml', 'models')
    SAMPLE_VIDEO_DIR = os.path.join(BASE_DIR, 'static', 'video')
    
    # Traffic Density Thresholds (Vehicle Count per Frame / ROI)
    DENSITY_THRESHOLDS = {
        'LOW_MAX': 5,       # 0 - 5 vehicles => Low Traffic
        'MEDIUM_MAX': 12,   # 6 - 12 vehicles => Medium Traffic
        'HIGH_MAX': 25,      # 13 - 25 vehicles => High Traffic
        'CRITICAL_MIN': 26,  # 26+ vehicles => Critical Traffic
    }
    
    # Detection Settings
    CONFIDENCE_THRESHOLD = 0.4
    NMS_THRESHOLD = 0.4
    
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.MODEL_FOLDER, exist_ok=True)
os.makedirs(Config.SAMPLE_VIDEO_DIR, exist_ok=True)
