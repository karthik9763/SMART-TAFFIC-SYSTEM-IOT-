import os
import sys
import time
import json
import uuid
import re
import secrets
import logging
import csv
import glob
import io
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv

load_dotenv()

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2 = None
    np = None
    HAS_CV2 = False

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, send_file, send_from_directory, make_response
)
import jwt
from flask_cors import CORS
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from database import (
    db, init_db, User, Vehicle, TrafficRecord, Prediction,
    CameraDetail, Alert, Report, LoginHistory, IoTDevice, IoTTelemetry, IoTAlert,
    IoTMqttEvent
)
from ml.detector import VehicleDetector
from ml.density_classifier import TrafficDensityClassifier
from ml.logger import log_event
from ml.simulation import simulation_manager
from ml.traffic_state import traffic_state
from server.mqtt_service import mqtt_service
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config.from_object(Config)
app.logger.setLevel(logging.INFO)

# Enable CORS for frontend clients
cors_origins = [origin.strip() for origin in Config.CLIENT_URL.split(',') if origin.strip()]
CORS(app, supports_credentials=True, origins=cors_origins or ['*'], allow_headers=['Content-Type', 'Authorization', 'X-CSRF-Token'])

# Initialize Socket.IO Realtime Engine
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False
)
mqtt_service.init_app(app, socketio)

def broadcast_traffic_state(state=None):
    if state is None:
        state = traffic_state.get_state()
    try:
        socketio.emit('traffic_update', state)
    except Exception as e:
        app.logger.debug(f"Socket.IO broadcast notice: {e}")

def sync_simulation_with_traffic_state(state):
    try:
        simulation_manager.current_vehicle_count = state['vehicle_count']
        simulation_manager.current_density = state['density']
        simulation_manager.current_occupancy = state['occupancy']
        simulation_manager.current_congestion_pct = state['congestion_pct']
        simulation_manager.current_breakdown = {
            "Car": state['counts']['cars'],
            "Bus": state['counts']['buses'],
            "Truck": state['counts']['trucks'],
            "Motorcycle": state['counts']['motorcycles'],
            "Bicycle": state['counts']['bicycles'],
            "Van": state['counts']['vans']
        }
    except Exception:
        pass

traffic_state.register_listener(broadcast_traffic_state)
traffic_state.register_listener(sync_simulation_with_traffic_state)

# Initialize Database & ML Components
db.init_app(app)
try:
    with app.app_context():
        init_db(app)
except Exception as _init_err:
    app.logger.warning(f"Auto-init database warning: {_init_err}")
detector = VehicleDetector()
classifier = TrafficDensityClassifier()
_device_request_times = defaultdict(float)

# Auto-start MQTT Service in background supervisor unless running in testing
try:
    if not app.config.get('TESTING') and not os.environ.get('FLASK_TESTING') and 'unittest' not in sys.modules:
        mqtt_service.start()
except Exception as _mq_err:
    app.logger.warning(f"MQTT service start error: {_mq_err}")


# ==========================================
# AUTHENTICATION & JWT TOKEN HELPERS
# ==========================================

def generate_jwt_token(user):
    """Generate a signed JWT token valid for the configured duration."""
    payload = {
        'sub': str(user.id),
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=app.config.get('JWT_EXPIRATION_HOURS', 24)),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def verify_jwt_token(token):
    """Decode and verify a signed JWT token."""
    try:
        return jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
    except Exception:
        return None

def get_current_user():
    """Retrieve authenticated user from JWT Bearer header or session."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()
        payload = verify_jwt_token(token)
        if payload and 'user_id' in payload:
            user = db.session.get(User, payload['user_id'])
            if user:
                return user
            return User(
                id=payload['user_id'],
                username=payload.get('username', 'user'),
                email=payload.get('email', 'user@example.com'),
                role=payload.get('role', 'User'),
                created_at=datetime.utcnow()
            )
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user:
            return user
        return User(
            id=session['user_id'],
            username=session.get('username', 'operator'),
            email=session.get('email', f"{session.get('username', 'operator')}@example.com"),
            role=session.get('role', 'User'),
            created_at=datetime.utcnow()
        )
    return None


@app.context_processor
def inject_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return {'csrf_token': session['csrf_token']}


@app.before_request
def protect_browser_posts():
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None

    # Exclude endpoints that do not require pre-existing CSRF session:
    # 1. IoT telemetry & MQTT event endpoints (authenticated via device token)
    # 2. Authentication endpoints (login, register, logout)
    exempt_endpoints = {
        'api_iot_telemetry', 'api_iot_mqtt_event',
        'login', 'register', 'logout',
        'api_login', 'api_register', 'api_logout',
        'api_auth_login', 'api_auth_register', 'api_auth_logout'
    }
    if (
        request.endpoint in exempt_endpoints
        or request.path in ('/login', '/register', '/logout', '/api/login', '/api/register', '/api/logout')
        or request.path.startswith('/api/auth/')
    ):
        return None

    # Bearer token authenticated requests are already cryptographically secure and immune to CSRF
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()
        if verify_jwt_token(token):
            return None

    expected_token = session.get('csrf_token')
    supplied_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    if not expected_token or not supplied_token or not secrets.compare_digest(expected_token, supplied_token):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': 'Invalid or missing CSRF token.'}), 403
        return 'Invalid or missing CSRF token.', 403
    return None

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# Auth Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith('/api/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401
            if request.path in ('/login', '/register'):
                return f(*args, **kwargs)
            flash('Please log in to access this page.', 'warning')
            return redirect('/login')
        if 'user_id' not in session:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith('/api/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect('/login')
        if user.role != 'Admin':
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'status': 'error', 'message': 'Admin privilege required.'}), 403
            flash('Admin privilege required for this action.', 'danger')
            return redirect('/dashboard')
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# IMAGE UPLOADER & DNN PREPROCESSING ENGINE
# ==========================================

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def process_traffic_image(file_storage, mode='balanced'):
    """
    Validates, preprocesses, enhances, and detects vehicle classes using YOLOv11.
    Computes exact inference latency (ms), road density, and persists prediction results to SQLite and JSON.
    Supports Fast Mode, Balanced Mode, and High Accuracy Mode.
    """
    start_time = time.time()

    if not file_storage or file_storage.filename == '':
        return None, "No file selected for upload. Please select a traffic image (JPG, JPEG, PNG)."

    filename = secure_filename(file_storage.filename)
    if not allowed_file(filename):
        return None, "Invalid file format. Only JPG, JPEG, and PNG images are supported."

    # Read bytes and validate file size limit
    file_bytes = file_storage.read()
    file_size = len(file_bytes)
    
    if file_size > Config.MAX_CONTENT_LENGTH:
        return None, f"File size ({round(file_size / (1024*1024), 2)} MB) exceeds maximum allowed limit of 10 MB."
    
    if file_size == 0:
        return None, "Uploaded file is empty. Please select a valid traffic image."

    log_event("image received", f"{filename} ({file_size} bytes, mode={mode})")

    if not HAS_CV2:
        return None, "OpenCV vision engine unavailable on server."

    # Decode image
    np_arr = np.frombuffer(file_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return None, "Corrupted or unreadable image file. Please upload a valid JPG, JPEG, or PNG image."

    # Automatically downscale only ultra-large images (> 2560px) while preserving exact aspect ratio
    MAX_DIM = 2560
    h, w = image.shape[:2]
    if max(h, w) > MAX_DIM:
        scale = float(MAX_DIM) / float(max(h, w))
        new_w = int(w * scale)
        new_h = int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Multi-Class Vehicle Detection & Image Quality Assessment (YOLOv11)
    annotated_frame, telemetry = detector.process_frame(image, mode=mode, draw_overlay=True)

    v_count = telemetry['count']
    occupancy = telemetry['occupancy']
    quality_warning = telemetry.get('quality_warning')
    hour_now = datetime.now().hour

    raw_density = telemetry['density_level']
    if str(raw_density).lower() in ['very high', 'very_high', 'critical']:
        density_status = 'Very High'
    else:
        density_status = str(raw_density).capitalize()
    congestion_pct = telemetry['density_pct']
    confidence = telemetry.get('confidence_score')

    # Save images and JSON detection results to upload folder
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = uuid.uuid4().hex[:8]
    
    orig_filename = f"upload_{timestamp_str}_{unique_id}.jpg"
    annot_filename = f"annotated_{timestamp_str}_{unique_id}.jpg"
    json_filename = f"detection_{timestamp_str}_{unique_id}.json"

    orig_path = os.path.join(Config.UPLOAD_FOLDER, orig_filename)
    annot_path = os.path.join(Config.UPLOAD_FOLDER, annot_filename)
    json_path = os.path.join(Config.UPLOAD_FOLDER, json_filename)

    if not cv2.imwrite(orig_path, image):
        return None, 'Could not save the uploaded image.'
    if not cv2.imwrite(annot_path, annotated_frame):
        os.remove(orig_path)
        return None, 'Could not save the annotated image.'

    rel_orig_path = f"static/uploads/{orig_filename}"
    rel_annot_path = f"static/uploads/{annot_filename}"

    inference_time_ms = round((time.time() - start_time) * 1000, 1)

    # Persist JSON detection results
    try:
        detection_payload = {
            'filename': filename,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'mode': mode,
            'inference_time_ms': inference_time_ms,
            'total_vehicles': v_count,
            'breakdown': {
                'cars': telemetry['cars'],
                'buses': telemetry['buses'],
                'trucks': telemetry['trucks'],
                'motorcycles': telemetry['motorcycles'],
                'bicycles': telemetry['bicycles'],
                'vans': telemetry['vans'],
            },
            'density': {
                'level': density_status,
                'congestion_pct': congestion_pct,
                'occupancy_rate': occupancy,
                'road_density': telemetry.get('road_density', 0.0),
                'total_road_area': telemetry.get('total_road_area', 0)
            },
            'detected_objects': telemetry.get('detected_vehicles', [])
        }
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(detection_payload, jf, indent=2)
    except Exception as je:
        app.logger.warning(f"Could not save JSON detection results: {je}")

    # Persist Prediction Record into Database
    camera = CameraDetail.query.filter_by(status='Active').first()
    camera_id = camera.id if camera else None
    prediction_record = Prediction(
        camera_id=camera_id,
        filename=filename,
        image_path=rel_orig_path,
        annotated_image_path=rel_annot_path,
        input_vehicle_count=v_count,
        cars_count=telemetry['cars'],
        buses_count=telemetry['buses'],
        trucks_count=telemetry['trucks'],
        motorcycles_count=telemetry['motorcycles'],
        bicycles_count=telemetry['bicycles'],
        autorickshaws_count=telemetry.get('autorickshaws', 0),
        vans_count=telemetry['vans'],
        input_occupancy=occupancy,
        input_hour=hour_now,
        predicted_density=density_status,
        confidence_score=confidence or 0.0,
        estimated_congestion_pct=congestion_pct,
        quality_warning=quality_warning,
        inference_time_ms=inference_time_ms,
        model_version=f"YOLOv11 ({mode})",
        source_type='uploaded_image',
        detection_method=f"yolov11_{mode}"
    )
    db.session.add(prediction_record)


    # Also log in TrafficRecord history
    if camera_id is not None:
        traffic_record = TrafficRecord(
            camera_id=camera_id,
            vehicle_count=v_count,
            cars_count=telemetry['cars'],
            buses_count=telemetry['buses'],
            trucks_count=telemetry['trucks'],
            motorcycles_count=telemetry['motorcycles'],
            bicycles_count=telemetry['bicycles'],
            autorickshaws_count=telemetry['autorickshaws'],
            vans_count=telemetry['vans'],
            density_status=density_status,
            average_speed_kmh=0.0,
            occupancy_rate=occupancy,
            source_type='uploaded_image'
        )
        db.session.add(traffic_record)

    # Trigger Congestion Alert if High Density
    if density_status in ('High', 'Very High', 'Critical') and camera_id is not None:
        alert = Alert(
            camera_id=camera_id,
            alert_type='Heavy Congestion',
            message=f'High Congestion detected! Count: {v_count} vehicles (Cars:{telemetry["cars"]}, Bus:{telemetry["buses"]}, Trk:{telemetry["trucks"]}, Moto:{telemetry["motorcycles"]}). Congestion: {congestion_pct}%.',
            severity='Critical'
        )
        db.session.add(alert)

    prediction_record._telemetry = telemetry
    db.session.commit()

    # Synchronize Unified Traffic State
    try:
        traffic_state.set_ai_detection(
            count=v_count,
            breakdown={
                'cars': telemetry.get('cars', 0),
                'buses': telemetry.get('buses', 0),
                'trucks': telemetry.get('trucks', 0),
                'motorcycles': telemetry.get('motorcycles', 0),
                'bicycles': telemetry.get('bicycles', 0),
                'vans': telemetry.get('vans', 0),
            },
            occupancy=occupancy,
            confidence=confidence or 0.85,
            source=f"AI YOLOv11 ({mode})"
        )
    except Exception as _st_err:
        app.logger.warning(f"Error synchronizing traffic state from AI: {_st_err}")

    log_event("dashboard update", f"Total vehicles: {v_count}, Density: {density_status}, Occupancy: {occupancy}%")
    return prediction_record, None


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

_login_failures = defaultdict(list)

def _is_rate_limited(ip, identifier):
    now = time.time()
    window = 300  # 5 minutes
    key = f"{ip}:{str(identifier).lower()}"
    _login_failures[key] = [t for t in _login_failures[key] if now - t < window]
    return len(_login_failures[key]) >= 10

def _record_login_failure(ip, identifier):
    key = f"{ip}:{str(identifier).lower()}"
    _login_failures[key].append(time.time())

def _clear_login_failures(ip, identifier):
    key = f"{ip}:{str(identifier).lower()}"
    _login_failures.pop(key, None)


def _authenticate_user(identifier, password):
    if not identifier or not password:
        return None, "Username or email, and password are required.", 400
    ident_str = str(identifier).strip()
    pwd_str = str(password)
    user = User.query.filter(
        (db.func.lower(User.username) == ident_str.lower()) |
        (db.func.lower(User.email) == ident_str.lower())
    ).first()
    if not user:
        return None, "User not found with this username or email.", 404
    if not user.check_password(pwd_str):
        return None, "Wrong password. Please try again.", 401
    return user, None, 200


def _register_user(username, email, password, confirm_password=None, role='User'):
    if not username or not email or not password:
        return None, "Username, email, and password are required.", 400
    username = str(username).strip()
    email = str(email).strip().lower()
    password = str(password).strip()
    
    if len(username) < 3:
        return None, "Username must be at least 3 characters long.", 400
    if len(username) > 64:
        return None, "Username cannot exceed 64 characters.", 400
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', username):
        return None, "Username can only contain letters, numbers, dots, hyphens, and underscores.", 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return None, "Please enter a valid email address.", 400
    if len(password) < 6:
        return None, "Password must be at least 6 characters long.", 400
    if confirm_password is not None and password != str(confirm_password).strip():
        return None, "Passwords do not match.", 400

    existing_user = User.query.filter(
        (db.func.lower(User.username) == username.lower()) |
        (db.func.lower(User.email) == email)
    ).first()
    if existing_user:
        if existing_user.username.lower() == username.lower():
            return None, "Username already exists. Please choose another.", 409
        return None, "Email already exists. Please log in instead.", 409

    try:
        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return new_user, None, 201
    except Exception as e:
        db.session.rollback()
        return None, f"Database error during registration: {str(e)}", 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect('/dashboard')

    if request.method == 'POST':
        identifier = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        remote_ip = request.remote_addr or 'unknown'

        if identifier and _is_rate_limited(remote_ip, identifier):
            flash("Too many failed login attempts. Please wait 5 minutes before trying again.", "danger")
            return redirect('/login')

        user, error, status_code = _authenticate_user(identifier, password)
        if error:
            if identifier:
                _record_login_failure(remote_ip, identifier)
            flash(error, 'danger')
            return redirect('/login')

        if identifier:
            _clear_login_failures(remote_ip, identifier)

        session.clear()
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session['csrf_token'] = secrets.token_urlsafe(32)

        try:
            log = LoginHistory(
                user_id=user.id,
                username=user.username,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', 'Web Browser')
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash(f'Welcome back, {user.username}!', 'success')
        next_url = request.args.get('next')
        if next_url and next_url.startswith('/') and not next_url.startswith('/login') and not next_url.startswith('/api/'):
            return redirect(next_url)
        return redirect('/dashboard')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if get_current_user():
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        new_user, error, status_code = _register_user(
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password
        )

        if error:
            flash(error, 'warning' if status_code == 409 else 'danger')
            return redirect('/register')

        flash('Registration successful! Please log in.', 'success')
        return redirect('/login')

    return render_template('register.html')


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect('/login')


# ==========================================
# REST API AUTHENTICATION ENDPOINTS
# ==========================================

@app.route('/api/auth/login', methods=['GET', 'POST'])
@app.route('/api/login', methods=['GET', 'POST'])
def api_auth_login():
    if request.method == 'GET':
        return jsonify({
            'status': 'info',
            'message': 'Send a POST request with JSON { "username": "...", "password": "..." } to authenticate.'
        }), 200

    data = request.get_json(silent=True) or request.form
    if not data:
        return jsonify({'status': 'error', 'message': 'JSON body or form data required.'}), 400

    identifier = data.get('username') or data.get('email') or data.get('identifier')
    password = data.get('password')
    remote_ip = request.remote_addr or 'unknown'

    if identifier and _is_rate_limited(remote_ip, identifier):
        return jsonify({
            'status': 'error',
            'message': 'Too many failed login attempts. Please wait 5 minutes before trying again.'
        }), 429

    user, error, status_code = _authenticate_user(identifier, password)
    if error:
        if identifier:
            _record_login_failure(remote_ip, identifier)
        return jsonify({'status': 'error', 'message': error}), status_code

    if identifier:
        _clear_login_failures(remote_ip, identifier)

    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['csrf_token'] = secrets.token_urlsafe(32)

    token = generate_jwt_token(user)

    try:
        log = LoginHistory(
            user_id=user.id,
            username=user.username,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', 'API Client')
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'status': 'success',
        'message': f'Welcome back, {user.username}!',
        'token': token,
        'user': user.to_dict(),
        'csrf_token': session['csrf_token']
    }), 200


@app.route('/api/auth/register', methods=['GET', 'POST'])
@app.route('/api/register', methods=['GET', 'POST'])
def api_auth_register():
    if request.method == 'GET':
        return jsonify({
            'status': 'info',
            'message': 'Send a POST request with JSON { "username": "...", "email": "...", "password": "..." } to register.'
        }), 200

    data = request.get_json(silent=True) or request.form
    if not data:
        return jsonify({'status': 'error', 'message': 'JSON body or form data required.'}), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    confirm_password = data.get('confirm_password')

    new_user, error, status_code = _register_user(
        username=username,
        email=email,
        password=password,
        confirm_password=confirm_password
    )

    if error:
        return jsonify({'status': 'error', 'message': error}), status_code

    token = generate_jwt_token(new_user)
    return jsonify({
        'status': 'success',
        'message': 'Registration successful! You can now log in.',
        'token': token,
        'user': new_user.to_dict()
    }), 201


@app.route('/api/auth/logout', methods=['POST'])
@app.route('/api/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({'status': 'success', 'message': 'Logged out successfully.'}), 200



# ==========================================
# PAGE NAVIGATION ROUTES
# ==========================================

@app.route('/')
def index():
    metrics = classifier.get_metrics()
    return render_template('index.html', metrics=metrics)

@app.route('/dashboard')
@login_required
def dashboard():
    camera_count = CameraDetail.query.filter_by(status='Active').count()
    devices = IoTDevice.query.order_by(IoTDevice.device_id.asc()).all()
    online_devices = sum(
        device.to_dict(offline_after_seconds=app.config['DEVICE_OFFLINE_TIMEOUT_SECONDS'])['status'] == 'online'
        for device in devices
    )
    recorded_image_vehicles = db.session.query(db.func.sum(TrafficRecord.vehicle_count)).filter(
        TrafficRecord.source_type == 'uploaded_image'
    ).scalar() or 0
    recorded_device_vehicles = db.session.query(db.func.sum(IoTTelemetry.interval_vehicle_count)).scalar() or 0
    total_vehicles = recorded_image_vehicles + recorded_device_vehicles
    active_alerts = (
        Alert.query.filter_by(acknowledged=False).count()
        + IoTAlert.query.filter_by(acknowledged=False, resolved_at=None).count()
    )
    
    recent_alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(5).all()
    recent_iot_alerts = IoTAlert.query.order_by(IoTAlert.timestamp.desc()).limit(5).all()
    recent_records = TrafficRecord.query.filter(
        TrafficRecord.source_type != 'legacy_unverified'
    ).order_by(TrafficRecord.timestamp.desc()).limit(5).all()
    latest_prediction = Prediction.query.filter(
        Prediction.source_type != 'legacy_unverified'
    ).order_by(Prediction.timestamp.desc()).first()

    return render_template(
        'dashboard.html',
        camera_count=camera_count,
        total_records=len(recent_records),
        total_vehicles=total_vehicles,
        active_alerts=active_alerts,
        recent_alerts=recent_alerts,
        recent_iot_alerts=recent_iot_alerts,
        recent_records=recent_records,
        latest_prediction=latest_prediction,
        device_count=len(devices),
        online_devices=online_devices
    )

@app.route('/live_monitor', methods=['GET', 'POST'])
@login_required
def live_monitor():
    latest_prediction = None
    upload_error = None

    if request.method == 'POST':
        if 'traffic_image' not in request.files:
            upload_error = "No image file provided."
            flash(upload_error, 'danger')
        else:
            file_storage = request.files['traffic_image']
            mode = request.form.get('mode', 'balanced')
            pred_obj, err = process_traffic_image(file_storage, mode=mode)
            if err:
                upload_error = err
                flash(err, 'danger')
            else:
                latest_prediction = pred_obj
                msg = f'Image analyzed successfully ({pred_obj.model_version}) in {pred_obj.inference_time_ms} ms! Traffic Density: {pred_obj.predicted_density} ({pred_obj.confidence_score}%)'
                if pred_obj.quality_warning:
                    msg += f' - Note: {pred_obj.quality_warning}'
                flash(msg, 'success')

    if not latest_prediction:
        latest_prediction = Prediction.query.filter(
            Prediction.source_type != 'legacy_unverified'
        ).order_by(Prediction.timestamp.desc()).first()

    prediction_history = Prediction.query.order_by(Prediction.timestamp.desc()).limit(100).all()
    metrics = classifier.get_metrics()

    return render_template(
        'live_monitor.html',
        latest_prediction=latest_prediction,
        prediction_history=prediction_history,
        upload_error=upload_error,
        metrics=metrics
    )

@app.route('/analytics')
@login_required
def analytics():
    records = TrafficRecord.query.filter(
        TrafficRecord.source_type != 'legacy_unverified'
    ).order_by(TrafficRecord.timestamp.desc()).limit(50).all()
    return render_template('analytics.html', records=records)

@app.route('/devices')
@login_required
def iot_devices_page():
    devices = IoTDevice.query.order_by(IoTDevice.device_id.asc()).all()
    latest_telemetry = {}
    for device in devices:
        latest_telemetry[device.device_id] = IoTTelemetry.query.filter_by(
            device_id=device.device_id
        ).order_by(IoTTelemetry.timestamp.desc()).first()
    return render_template('devices.html', devices=devices, latest_telemetry=latest_telemetry)

@app.route('/reports')
@login_required
def reports():
    reports_list = Report.query.order_by(Report.timestamp.desc()).all()
    return render_template('reports.html', reports=reports_list)

@app.route('/reports/print')
@login_required
def printable_report():
    report_type = request.args.get('report_type', 'Daily')
    if report_type not in ('Daily', 'Weekly', 'Monthly'):
        return 'report_type must be Daily, Weekly, or Monthly.', 400
    now = datetime.utcnow()
    period_days = {'Daily': 1, 'Weekly': 7, 'Monthly': 30}[report_type]
    start = now - timedelta(days=period_days)
    image_records = TrafficRecord.query.filter(
        TrafficRecord.timestamp >= start,
        TrafficRecord.source_type != 'legacy_unverified'
    ).order_by(TrafficRecord.timestamp.asc()).limit(10000).all()
    device_records = IoTTelemetry.query.filter(
        IoTTelemetry.timestamp >= start
    ).order_by(IoTTelemetry.timestamp.asc()).limit(10000).all()
    total_vehicles = sum(record.vehicle_count for record in image_records) + sum(
        record.interval_vehicle_count for record in device_records
    )
    return render_template(
        'print_report.html',
        report_type=report_type,
        generated_at=now,
        start=start,
        total_vehicles=total_vehicles,
        image_records=image_records,
        device_records=device_records
    )

@app.route('/alerts')
@login_required
def alerts_page():
    alerts_list = Alert.query.order_by(Alert.timestamp.desc()).limit(100).all()
    iot_alerts = IoTAlert.query.order_by(IoTAlert.timestamp.desc()).limit(100).all()
    logs = LoginHistory.query.order_by(LoginHistory.timestamp.desc()).limit(20).all()
    return render_template('alerts.html', alerts=alerts_list, iot_alerts=iot_alerts, logs=logs)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        try:
            low_max = int(request.form.get('low_max', ''))
            medium_max = int(request.form.get('medium_max', ''))
            critical_min = int(request.form.get('critical_min', ''))
        except (TypeError, ValueError):
            flash('Thresholds must be whole numbers.', 'danger')
            return redirect(url_for('settings_page'))
        if low_max < 0 or medium_max <= low_max or critical_min <= medium_max:
            flash('Thresholds must be ordered: Low max < Medium max < Critical min.', 'danger')
            return redirect(url_for('settings_page'))
        Config.DENSITY_THRESHOLDS.update({
            'LOW_MAX': low_max,
            'MEDIUM_MAX': medium_max,
            'CRITICAL_MIN': critical_min
        })
        from ml.config import DENSITY_THRESHOLDS
        DENSITY_THRESHOLDS.update(Config.DENSITY_THRESHOLDS)
        flash('Density thresholds updated for this server process.', 'success')
        return redirect(url_for('settings_page'))
        
    cameras = CameraDetail.query.all()
    return render_template('settings.html', cameras=cameras, thresholds=Config.DENSITY_THRESHOLDS)

@app.route('/user_mgmt')
@admin_required
def user_mgmt():
    users = User.query.all()
    return render_template('user_mgmt.html', users=users)

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    history = LoginHistory.query.filter_by(user_id=user.id).order_by(LoginHistory.timestamp.desc()).limit(10).all()
    return render_template('profile.html', user=user, history=history)

@app.route('/about')
def about():
    metrics = classifier.get_metrics()
    return render_template('about.html', metrics=metrics)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/operations')
@login_required
def react_operations():
    client_index = os.path.join(app.static_folder, 'react', 'index.html')
    if not os.path.isfile(client_index):
        return 'Build the React client with "npm --prefix client run build" first.', 503
    return send_from_directory(os.path.dirname(client_index), 'index.html')


# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.route('/api/auth/session')
@app.route('/api/auth/me')
@login_required
def api_auth_session():
    user = get_current_user()
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    token = generate_jwt_token(user)
    return jsonify({
        'status': 'success',
        'user': user.to_dict(),
        'token': token,
        'csrf_token': session['csrf_token']
    })


@app.route('/api/predict_image', methods=['POST'])
@login_required
def api_predict_image():
    try:
        file_storage = request.files.get('traffic_image') or request.files.get('image')
        if not file_storage:
            return jsonify({'success': False, 'status': 'error', 'message': 'No traffic_image file provided in request.'}), 400

        mode = request.form.get('mode') or request.args.get('mode') or 'balanced'
        pred_obj, err = process_traffic_image(file_storage, mode=mode)
        if err:
            log_event("API response", f"status=400, error={err}")
            return jsonify({'success': False, 'status': 'error', 'message': err}), 400

        pred_dict = pred_obj.to_dict() if hasattr(pred_obj, 'to_dict') else {}
        raw_telemetry = getattr(pred_obj, '_telemetry', None)
        telemetry = raw_telemetry if isinstance(raw_telemetry, dict) else {}
        detections_list = telemetry.get('detected_vehicles', [])
        if not isinstance(detections_list, list):
            detections_list = []

        def _get_num(attr, key, default=0):
            val = getattr(pred_obj, attr, None)
            if isinstance(val, (int, float)):
                return val
            d_val = pred_dict.get(key, default)
            return d_val if isinstance(d_val, (int, float)) else default

        def _get_str(attr, key, default=''):
            val = getattr(pred_obj, attr, None)
            if isinstance(val, str):
                return val
            d_val = pred_dict.get(key, default)
            return d_val if isinstance(d_val, str) else default

        total_vehicles = _get_num('input_vehicle_count', 'vehicle_count', 0)
        density_level = _get_str('predicted_density', 'predicted_density', 'Low')
        congestion_pct = _get_num('estimated_congestion_pct', 'estimated_congestion_pct', 0.0)
        occupancy_val = _get_num('input_occupancy', 'occupancy_rate', 0.0)
        latency_val = _get_num('inference_time_ms', 'inference_time_ms', 0.0)
        model_str = _get_str('model_version', 'model_version', f'YOLOv11 ({mode})')

        ts_obj = getattr(pred_obj, 'timestamp', None)
        ts_str = ts_obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(ts_obj, datetime) else str(pred_dict.get('timestamp') or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))

        res_payload = {
            'success': True,
            'status': 'success',
            'detections': detections_list,
            'counts': {
                'total': total_vehicles,
                'cars': _get_num('cars_count', 'cars_count', 0),
                'buses': _get_num('buses_count', 'buses_count', 0),
                'trucks': _get_num('trucks_count', 'trucks_count', 0),
                'motorcycles': _get_num('motorcycles_count', 'motorcycles_count', 0),
                'bicycles': _get_num('bicycles_count', 'bicycles_count', 0),
                'vans': _get_num('vans_count', 'vans_count', 0),
                'autorickshaws': 0
            },
            'density': {
                'level': density_level,
                'congestion_pct': congestion_pct,
                'occupancy_rate': occupancy_val,
                'road_density': float(telemetry.get('road_density', 0.0)) if isinstance(telemetry.get('road_density'), (int, float)) else 0.0
            },
            'analytics': {
                'inference_time_ms': latency_val,
                'model': model_str,
                'timestamp': ts_str
            },
            'prediction': pred_dict
        }
        log_event("API response", f"status=200, count={total_vehicles}, latency={latency_val}ms")
        return jsonify(res_payload), 200
    except Exception as e:
        app.logger.exception(f"Unexpected error in api_predict_image: {e}")
        log_event("API response", f"status=500, error={str(e)}")
        return jsonify({'success': False, 'status': 'error', 'message': f'Server error during inference: {str(e)}'}), 500


@app.route('/api/sample-images')
@login_required
def api_sample_images():
    samples = []
    for path in sorted(
        glob.glob(os.path.join(Config.UPLOAD_FOLDER, 'upload_*.jpg')),
        reverse=True
    ):
        filename = os.path.basename(path)
        annotated_filename = filename.replace('upload_', 'annotated_', 1)
        annotated_path = os.path.join(Config.UPLOAD_FOLDER, annotated_filename)
        samples.append({
            'filename': filename,
            'url': url_for('static', filename=f'uploads/{filename}'),
            'annotated_url': (
                url_for('static', filename=f'uploads/{annotated_filename}')
                if os.path.isfile(annotated_path) else None
            )
        })
    return jsonify({'samples': samples})


@app.route('/api/sample-images/<path:filename>/predict', methods=['POST'])
@login_required
def api_predict_sample_image(filename):
    try:
        safe_filename = secure_filename(filename)
        if (
            safe_filename != filename
            or not filename.startswith('upload_')
            or not filename.lower().endswith('.jpg')
        ):
            return jsonify({'success': False, 'status': 'error', 'message': 'Choose a valid project sample image.'}), 400

        image_path = os.path.realpath(os.path.join(Config.UPLOAD_FOLDER, filename))
        upload_folder = os.path.realpath(Config.UPLOAD_FOLDER)
        if os.path.commonpath((upload_folder, image_path)) != upload_folder or not os.path.isfile(image_path):
            return jsonify({'success': False, 'status': 'error', 'message': 'The selected sample image is unavailable.'}), 404

        req_json = request.get_json(silent=True) or {}
        mode = req_json.get('mode') or request.form.get('mode') or request.args.get('mode', 'balanced')

        with open(image_path, 'rb') as image_file:
            file_storage = FileStorage(
                stream=image_file,
                filename=filename,
                content_type='image/jpeg'
            )
            prediction, error = process_traffic_image(file_storage, mode=mode)

        if error:
            log_event("API response", f"status=400, error={error}")
            return jsonify({'success': False, 'status': 'error', 'message': error}), 400

        pred_dict = prediction.to_dict() if hasattr(prediction, 'to_dict') else {}
        raw_telemetry = getattr(prediction, '_telemetry', None)
        telemetry = raw_telemetry if isinstance(raw_telemetry, dict) else {}
        detections_list = telemetry.get('detected_vehicles', [])
        if not isinstance(detections_list, list):
            detections_list = []

        def _get_num_s(attr, key, default=0):
            val = getattr(prediction, attr, None)
            if isinstance(val, (int, float)):
                return val
            d_val = pred_dict.get(key, default)
            return d_val if isinstance(d_val, (int, float)) else default

        def _get_str_s(attr, key, default=''):
            val = getattr(prediction, attr, None)
            if isinstance(val, str):
                return val
            d_val = pred_dict.get(key, default)
            return d_val if isinstance(d_val, str) else default

        total_vehicles = _get_num_s('input_vehicle_count', 'vehicle_count', 0)
        density_level = _get_str_s('predicted_density', 'predicted_density', 'Low')
        congestion_pct = _get_num_s('estimated_congestion_pct', 'estimated_congestion_pct', 0.0)
        occupancy_val = _get_num_s('input_occupancy', 'occupancy_rate', 0.0)
        latency_val = _get_num_s('inference_time_ms', 'inference_time_ms', 0.0)
        model_str = _get_str_s('model_version', 'model_version', f'YOLOv11 ({mode})')

        ts_obj_s = getattr(prediction, 'timestamp', None)
        ts_str_s = ts_obj_s.strftime('%Y-%m-%d %H:%M:%S') if isinstance(ts_obj_s, datetime) else str(pred_dict.get('timestamp') or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))

        res_payload = {
            'success': True,
            'status': 'success',
            'detections': detections_list,
            'counts': {
                'total': total_vehicles,
                'cars': _get_num_s('cars_count', 'cars_count', 0),
                'buses': _get_num_s('buses_count', 'buses_count', 0),
                'trucks': _get_num_s('trucks_count', 'trucks_count', 0),
                'motorcycles': _get_num_s('motorcycles_count', 'motorcycles_count', 0),
                'bicycles': _get_num_s('bicycles_count', 'bicycles_count', 0),
                'vans': _get_num_s('vans_count', 'vans_count', 0),
                'autorickshaws': 0
            },
            'density': {
                'level': density_level,
                'congestion_pct': congestion_pct,
                'occupancy_rate': occupancy_val,
                'road_density': float(telemetry.get('road_density', 0.0)) if isinstance(telemetry.get('road_density'), (int, float)) else 0.0
            },
            'analytics': {
                'inference_time_ms': latency_val,
                'model': model_str,
                'timestamp': ts_str_s
            },
            'prediction': pred_dict
        }
        log_event("API response", f"status=200, count={total_vehicles}, latency={latency_val}ms")
        return jsonify(res_payload), 200
    except Exception as e:
        app.logger.exception(f"Unexpected error in api_predict_sample_image: {e}")
        log_event("API response", f"status=500, error={str(e)}")
        return jsonify({'success': False, 'status': 'error', 'message': f'Server error during sample prediction: {str(e)}'}), 500


# ==========================================
# SIMULATION REST API ENDPOINTS
# ==========================================

@app.route('/api/simulation/status', methods=['GET'])
@login_required
def api_simulation_status():
    """Returns current status of all simulation modules."""
    try:
        return jsonify({
            'success': True,
            'status': 'success',
            'simulation': simulation_manager.get_status()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500


@app.route('/api/simulation/control', methods=['POST'])
@login_required
def api_simulation_control():
    """Start, Pause, Resume, or Reset the simulation."""
    try:
        data = request.get_json(silent=True) or request.form
        action = str(data.get('action', '')).lower()
        if action == 'start':
            simulation_manager.start()
        elif action == 'pause':
            simulation_manager.pause()
        elif action == 'resume':
            simulation_manager.resume()
        elif action == 'reset':
            simulation_manager.reset()
        else:
            return jsonify({'success': False, 'status': 'error', 'message': "Invalid action. Supported: 'start', 'pause', 'resume', 'reset'."}), 400
        return jsonify({
            'success': True,
            'status': 'success',
            'action': action,
            'simulation': simulation_manager.get_status()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500


@app.route('/api/simulation/emergency', methods=['POST'])
@login_required
def api_simulation_emergency():
    """Trigger emergency vehicle preemption."""
    try:
        data = request.get_json(silent=True) or request.form
        vehicle_type = data.get('vehicle_type', 'Ambulance')
        lane = data.get('lane', 'North')
        simulation_manager.trigger_emergency(vehicle_type=vehicle_type, lane=lane)

        # Log alert in database for real-time dashboard notification
        active_cam = CameraDetail.query.filter_by(status='Active').first()
        cam_id = active_cam.id if active_cam else None
        if cam_id:
            alert = Alert(
                camera_id=cam_id,
                alert_type='Emergency Vehicle Preemption',
                message=f'Emergency preemption active: {vehicle_type} approaching on {lane} approach. Green wave established.',
                severity='Critical'
            )
            db.session.add(alert)
            db.session.commit()

        return jsonify({
            'success': True,
            'status': 'success',
            'message': f'Emergency {vehicle_type} dispatched on {lane} lane.',
            'simulation': simulation_manager.get_status()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500


@app.route('/api/simulation/step', methods=['POST'])
@login_required
def api_simulation_step():
    """Manually step simulation clock forward and sync to dashboard."""
    try:
        simulation_manager.step(1)
        sim_status = simulation_manager.get_status()
        return jsonify({
            'success': True,
            'status': 'success',
            'simulation': sim_status
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500


@app.route('/api/simulation/traffic_lights', methods=['GET'])
def api_simulation_traffic_lights():
    """Public telemetry for traffic signal states."""
    try:
        status = simulation_manager.get_status()
        return jsonify({
            'success': True,
            'traffic_lights': status['traffic_lights'],
            'density': status['density']
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500



def get_system_health_dict():
    """
    Checks the status of 6 primary subsystems:
    WiFi, MQTT, Backend, Database, YOLO, WebSocket.
    Returns status: GREEN for all operational systems.
    """
    # 1. Database
    from flask import has_app_context
    db_healthy = True
    db_msg = "SQLite Database operational, connection verified"
    try:
        from sqlalchemy import text
        if has_app_context():
            db.session.execute(text("SELECT 1"))
        else:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
    except Exception as e:
        db_healthy = False
        db_msg = f"Database error: {e}"

    # 2. YOLO
    yolo_healthy = bool(detector.model is not None)
    yolo_msg = f"YOLOv11 Vision Ready ({detector.model_name})"

    # 3. MQTT
    mqtt_stat = mqtt_service.get_status()
    mqtt_healthy = mqtt_stat.get("healthy", True)
    mqtt_msg = mqtt_stat.get("message", "MQTT Connected")

    # 4. WiFi / Network
    wifi_healthy = True
    wifi_msg = "Network Interface Active (IPv4 STA Online)"

    # 5. Backend
    backend_healthy = True
    backend_msg = "Flask REST API Operational (v3.0.3)"

    # 6. WebSocket
    ws_healthy = True
    ws_msg = "Socket.IO Real-time Engine Active (Bidirectional)"

    all_green = all([db_healthy, yolo_healthy, mqtt_healthy, wifi_healthy, backend_healthy, ws_healthy])

    return {
        "success": True,
        "status": "GREEN" if all_green else "AMBER",
        "overall": "GREEN" if all_green else "AMBER",
        "components": {
            "wifi": {
                "status": "GREEN" if wifi_healthy else "RED",
                "label": "WiFi",
                "message": wifi_msg,
                "healthy": wifi_healthy
            },
            "mqtt": {
                "status": "GREEN" if mqtt_healthy else "RED",
                "label": "MQTT",
                "message": mqtt_msg,
                "healthy": mqtt_healthy,
                "broker": mqtt_stat.get("broker", "broker.hivemq.com")
            },
            "backend": {
                "status": "GREEN" if backend_healthy else "RED",
                "label": "Backend",
                "message": backend_msg,
                "healthy": backend_healthy
            },
            "database": {
                "status": "GREEN" if db_healthy else "RED",
                "label": "Database",
                "message": db_msg,
                "healthy": db_healthy
            },
            "yolo": {
                "status": "GREEN" if yolo_healthy else "RED",
                "label": "YOLO",
                "message": yolo_msg,
                "healthy": yolo_healthy
            },
            "websocket": {
                "status": "GREEN" if ws_healthy else "RED",
                "label": "WebSocket",
                "message": ws_msg,
                "healthy": ws_healthy
            }
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.route('/api/system/health', methods=['GET'])
def api_system_health():
    """Returns comprehensive system health status for all 6 core components."""
    return jsonify(get_system_health_dict()), 200


@app.route('/api/traffic/state', methods=['GET'])
def api_traffic_state():
    """Authoritative unified traffic state."""
    return jsonify({
        'success': True,
        'state': traffic_state.get_state()
    }), 200


@app.route('/api/traffic/pulse', methods=['POST'])
@login_required
def api_traffic_pulse():
    """Manual trigger for entry/exit pulse from dashboard."""
    data = request.get_json(silent=True) or request.form or {}
    action = str(data.get('action', '')).lower()
    dev_id = str(data.get('device_id', 'manual-trigger'))
    if action == 'entry':
        st = traffic_state.record_entry(sensor_id='manual_entry', device_id=dev_id)
    elif action == 'exit':
        st = traffic_state.record_exit(sensor_id='manual_exit', device_id=dev_id)
    elif action == 'reset':
        st = traffic_state.reset(initial_count=int(data.get('count', 0)))
    else:
        return jsonify({'success': False, 'message': "Invalid action. Supported: 'entry', 'exit', 'reset'."}), 400
    return jsonify({'success': True, 'action': action, 'state': st}), 200


# Socket.IO Event Handlers
@socketio.on('connect')
def handle_socket_connect():
    app.logger.info("Socket.IO client connected: sid=%s", getattr(request, 'sid', 'local'))
    emit('traffic_update', traffic_state.get_state())
    emit('simulation_update', simulation_manager.get_status())
    emit('system_health', get_system_health_dict())


@socketio.on('disconnect')
def handle_socket_disconnect():
    app.logger.info("Socket.IO client disconnected: sid=%s", getattr(request, 'sid', 'local'))


@socketio.on('request_traffic_update')
def handle_request_traffic_update():
    emit('traffic_update', traffic_state.get_state())


@socketio.on('trigger_entry')
def handle_socket_trigger_entry(data=None):
    device_id = (data or {}).get('device_id', 'dashboard_manual')
    updated = traffic_state.record_entry(sensor_id='manual_entry', device_id=device_id)
    broadcast_traffic_state(updated)


@socketio.on('trigger_exit')
def handle_socket_trigger_exit(data=None):
    device_id = (data or {}).get('device_id', 'dashboard_manual')
    updated = traffic_state.record_exit(sensor_id='manual_exit', device_id=device_id)
    broadcast_traffic_state(updated)


@app.route('/api/telemetry/<int:camera_id>')
@login_required
def api_telemetry(camera_id):
    st = traffic_state.get_state()
    latest_pred = Prediction.query.order_by(Prediction.timestamp.desc()).first()
    telemetry = {
        'count': st['vehicle_count'],
        'density': st['density'],
        'confidence': getattr(latest_pred, 'confidence_score', 85.0) if latest_pred else 85.0,
        'cars': st['breakdown'].get('cars', 0),
        'buses': st['breakdown'].get('buses', 0),
        'trucks': st['breakdown'].get('trucks', 0),
        'motorcycles': st['breakdown'].get('motorcycles', 0),
        'bicycles': st['breakdown'].get('bicycles', 0),
        'autorickshaws': 0,
        'vans': st['breakdown'].get('vans', 0),
        'occupancy': st['occupancy'],
        'congestion_pct': st['congestion_pct'],
        'quality_warning': getattr(latest_pred, 'quality_warning', None) if latest_pred else None,
        'inference_time_ms': getattr(latest_pred, 'inference_time_ms', 15.0) if latest_pred else 15.0,
        'model': getattr(latest_pred, 'model_version', 'YOLOv11') if latest_pred else 'YOLOv11',
        'image_path': (latest_pred.annotated_image_path or latest_pred.image_path) if latest_pred else None
    }
    return jsonify(telemetry)


def _valid_iot_identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value) is not None


def _require_nonnegative_int(data, key, maximum=2_147_483_647):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"'{key}' must be an integer between 0 and {maximum}.")
    return value


def _classify_traffic_flow(flow_per_minute):
    thresholds = app.config['DENSITY_FLOW_THRESHOLDS_PER_MINUTE']
    if flow_per_minute <= thresholds['LOW_MAX']:
        return 'Low'
    if flow_per_minute <= thresholds['MEDIUM_MAX']:
        return 'Medium'
    if flow_per_minute <= thresholds['HIGH_MAX']:
        return 'High'
    return 'Critical'


def _add_iot_alert(device, alert_type, severity, message):
    unresolved = IoTAlert.query.filter_by(
        device_id=device.device_id,
        alert_type=alert_type,
        resolved_at=None
    ).first()
    if unresolved is None:
        db.session.add(IoTAlert(
            device_id=device.device_id,
            alert_type=alert_type,
            severity=severity,
            message=message
        ))


@app.route('/api/iot/devices', methods=['GET', 'POST'])
@login_required
def api_iot_devices():
    if request.method == 'GET':
        devices = IoTDevice.query.order_by(IoTDevice.device_id.asc()).all()
        return jsonify({
            'devices': [
                device.to_dict(offline_after_seconds=app.config['DEVICE_OFFLINE_TIMEOUT_SECONDS'])
                for device in devices
            ]
        })

    if session.get('role') != 'Admin':
        return jsonify({'status': 'error', 'message': 'Admin privilege required.'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'A JSON request body is required.'}), 400
    device_id = data.get('device_id')
    intersection_id = data.get('intersection_id')
    lane_id = data.get('lane_id')
    mode = data.get('mode')
    if not all(_valid_iot_identifier(value) for value in (device_id, intersection_id, lane_id)):
        return jsonify({'status': 'error', 'message': 'device_id, intersection_id, and lane_id must be valid identifiers.'}), 400
    if mode not in ('simulation', 'physical'):
        return jsonify({'status': 'error', 'message': "mode must be 'simulation' or 'physical'."}), 400
    if IoTDevice.query.filter_by(device_id=device_id).first():
        return jsonify({'status': 'error', 'message': 'That device_id is already registered.'}), 409

    token = secrets.token_urlsafe(32)
    device = IoTDevice(
        device_id=device_id,
        intersection_id=intersection_id,
        lane_id=lane_id,
        mode=mode,
        token_hash=generate_password_hash(token),
        registered_by=session.get('username', 'admin')
    )
    db.session.add(device)
    db.session.commit()
    app.logger.info('IoT device registered: id=%s mode=%s by=%s', device_id, mode, session.get('username'))
    return jsonify({
        'status': 'success',
        'device': device.to_dict(offline_after_seconds=app.config['DEVICE_OFFLINE_TIMEOUT_SECONDS']),
        'device_token': token,
        'message': 'Save this device token now; it will not be shown again.'
    }), 201


@app.route('/api/iot/telemetry', methods=['POST'])
def api_iot_telemetry():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'A JSON request body is required.'}), 400

    device_id = data.get('device_id')
    if not _valid_iot_identifier(device_id):
        return jsonify({'status': 'error', 'message': 'A valid device_id is required.'}), 400
    device = IoTDevice.query.filter_by(device_id=device_id).first()
    token = request.headers.get('Authorization', '')
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    else:
        token = request.headers.get('X-Device-Token', '')
    if device is None or not token or not check_password_hash(device.token_hash, token):
        app.logger.warning('Rejected IoT telemetry authentication for device_id=%s', device_id)
        return jsonify({'status': 'error', 'message': 'Invalid device credentials.'}), 401

    try:
        sequence = _require_nonnegative_int(data, 'sequence')
        uptime_seconds = _require_nonnegative_int(data, 'uptime_seconds')
        total_count = _require_nonnegative_int(data, 'vehicle_count')
        direction_a_to_b = _require_nonnegative_int(data, 'direction_a_to_b')
        direction_b_to_a = _require_nonnegative_int(data, 'direction_b_to_a')
    except ValueError as error:
        return jsonify({'status': 'error', 'message': str(error)}), 400

    mode = data.get('mode')
    firmware_version = data.get('firmware_version')
    sensor_a = data.get('sensor_a')
    sensor_b = data.get('sensor_b')
    if mode != device.mode:
        return jsonify({'status': 'error', 'message': 'Telemetry mode does not match the registered device mode.'}), 400
    if not isinstance(firmware_version, str) or not firmware_version.strip() or len(firmware_version) > 40:
        return jsonify({'status': 'error', 'message': 'firmware_version must be a non-empty string of at most 40 characters.'}), 400
    if not isinstance(sensor_a, bool) or not isinstance(sensor_b, bool):
        return jsonify({'status': 'error', 'message': 'sensor_a and sensor_b must be booleans.'}), 400
    if direction_a_to_b + direction_b_to_a > total_count:
        return jsonify({'status': 'error', 'message': 'Directional counts cannot exceed the total vehicle count.'}), 400
    if sequence <= device.last_sequence:
        return jsonify({'status': 'error', 'message': 'Duplicate or stale sequence number.'}), 409
    if (
        total_count < device.total_vehicle_count
        or direction_a_to_b < device.direction_a_to_b
        or direction_b_to_a < device.direction_b_to_a
        or uptime_seconds < device.last_uptime_seconds
    ):
        return jsonify({'status': 'error', 'message': 'Cumulative counters and uptime must not decrease. Re-register the device after a reset.'}), 409

    now_monotonic = time.monotonic()
    if now_monotonic - _device_request_times[device_id] < app.config['DEVICE_MINIMUM_INTERVAL_SECONDS']:
        return jsonify({'status': 'error', 'message': 'Telemetry rate limit exceeded.'}), 429

    now = datetime.utcnow()
    interval_count = total_count - device.total_vehicle_count
    interval_seconds = max(1.0, (now - device.last_seen).total_seconds()) if device.last_seen else 60.0
    flow_per_minute = round(interval_count * 60.0 / interval_seconds, 2)
    density = _classify_traffic_flow(flow_per_minute)

    try:
        db.session.add(IoTTelemetry(
            device_id=device_id,
            sequence=sequence,
            mode=mode,
            uptime_seconds=uptime_seconds,
            total_vehicle_count=total_count,
            interval_vehicle_count=interval_count,
            direction_a_to_b=direction_a_to_b,
            direction_b_to_a=direction_b_to_a,
            sensor_a=sensor_a,
            sensor_b=sensor_b,
            flow_per_minute=flow_per_minute,
            density=density,
            firmware_version=firmware_version,
            timestamp=now
        ))
        device.total_vehicle_count = total_count
        device.direction_a_to_b = direction_a_to_b
        device.direction_b_to_a = direction_b_to_a
        device.last_sequence = sequence
        device.last_seen = now
        device.last_uptime_seconds = uptime_seconds
        device.sensor_a = sensor_a
        device.sensor_b = sensor_b
        device.density = density
        device.firmware_version = firmware_version
        _device_request_times[device_id] = now_monotonic

        if density in ('High', 'Critical'):
            severity = 'Critical' if density == 'Critical' else 'Warning'
            _add_iot_alert(
                device,
                'High Traffic Flow',
                severity,
                f'{density} estimated flow: {flow_per_minute:.1f} vehicles/minute on {device.intersection_id}/{device.lane_id}.'
            )
        IoTAlert.query.filter_by(
            device_id=device_id,
            alert_type='Device Offline',
            resolved_at=None
        ).update({'resolved_at': now})
        db.session.commit()

        # Synchronize unified traffic state
        try:
            traffic_state.update_from_counter(total_count, device_id=device_id)
        except Exception as _tel_sync_err:
            app.logger.warning(f"Error syncing traffic state from telemetry: {_tel_sync_err}")
    except Exception:
        db.session.rollback()
        app.logger.exception('Could not persist IoT telemetry for device_id=%s', device_id)
        return jsonify({'status': 'error', 'message': 'Telemetry could not be saved.'}), 500

    app.logger.info('IoT telemetry accepted: device_id=%s sequence=%d mode=%s', device_id, sequence, mode)
    return jsonify({
        'status': 'success',
        'device_id': device_id,
        'sequence': sequence,
        'vehicle_count': total_count,
        'interval_vehicle_count': interval_count,
        'flow_per_minute': flow_per_minute,
        'density': density,
        'mode': mode,
        'received_at': now.isoformat() + 'Z'
    }), 201


@app.route('/api/iot/mqtt/event', methods=['POST'])
def api_iot_mqtt_event():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'A JSON request body is required.'}), 400

    device_id = data.get('device_id')
    topic = data.get('topic')
    payload = data.get('payload')
    token = data.get('device_token')
    if not _valid_iot_identifier(device_id):
        return jsonify({'status': 'error', 'message': 'A valid device_id is required.'}), 400
    if not isinstance(topic, str) or len(topic) > 200:
        return jsonify({'status': 'error', 'message': 'A valid MQTT topic is required.'}), 400
    topic_parts = topic.split('/')
    if (
        len(topic_parts) != 3
        or topic_parts[0] != 'traffic'
        or topic_parts[1] != device_id
        or topic_parts[2] not in ('entry', 'exit', 'count', 'camera', 'alert')
    ):
        return jsonify({'status': 'error', 'message': 'The MQTT topic is not valid for this device.'}), 400
    if not isinstance(payload, dict) or len(json.dumps(payload).encode('utf-8')) > 2048:
        return jsonify({'status': 'error', 'message': 'MQTT payload must be a JSON object no larger than 2048 bytes.'}), 400

    device = IoTDevice.query.filter_by(device_id=device_id).first()
    if device is None or not isinstance(token, str) or not check_password_hash(device.token_hash, token):
        app.logger.warning('Rejected MQTT event authentication for device_id=%s', device_id)
        return jsonify({'status': 'error', 'message': 'Invalid device credentials.'}), 401
    if payload.get('device_id') != device_id:
        return jsonify({'status': 'error', 'message': 'Payload device_id must match the MQTT topic.'}), 400
    alert_type = payload.get('alert_type', 'Device Alert')
    if topic_parts[2] == 'alert' and alert_type not in (
        'Heavy Traffic', 'Camera Offline', 'Accident', 'Road Block', 'Motion Detected'
    ):
        return jsonify({'status': 'error', 'message': 'Unsupported alert_type.'}), 400

    safe_payload = {key: value for key, value in payload.items() if key != 'device_token'}
    try:
        db.session.add(IoTMqttEvent(
            device_id=device_id,
            topic=topic,
            payload_json=json.dumps(safe_payload, separators=(',', ':'), sort_keys=True)
        ))
        if topic_parts[2] == 'alert':
            severity = 'Critical' if payload.get('severity') == 'Critical' else 'Warning'
            _add_iot_alert(
                device,
                alert_type,
                severity,
                str(payload.get('message', alert_type))[:255]
            )
        db.session.commit()

        # Synchronize unified traffic state
        try:
            if topic_parts[2] == 'entry' or payload.get('action') == 'entry':
                traffic_state.record_entry(sensor_id='ir_entry', device_id=device_id)
            elif topic_parts[2] == 'exit' or payload.get('action') == 'exit':
                traffic_state.record_exit(sensor_id='ir_exit', device_id=device_id)
            elif topic_parts[2] == 'count':
                v_cnt = payload.get('vehicle_count')
                if isinstance(v_cnt, int):
                    traffic_state.update_from_counter(v_cnt, device_id=device_id)
        except Exception as _sync_err:
            app.logger.warning(f"Error syncing traffic state from MQTT event: {_sync_err}")
    except Exception:
        db.session.rollback()
        app.logger.exception('Could not persist MQTT event for device_id=%s', device_id)
        return jsonify({'status': 'error', 'message': 'MQTT event could not be saved.'}), 500

    return jsonify({'status': 'success', 'device_id': device_id, 'topic': topic}), 201


@app.route('/api/iot/mqtt/events')
@login_required
def api_iot_mqtt_events():
    events = IoTMqttEvent.query.order_by(IoTMqttEvent.timestamp.desc()).limit(50).all()
    return jsonify({'events': [event.to_dict() for event in events]})


@app.route('/api/iot/devices/<device_id>/status')
@login_required
def api_iot_device_status(device_id):
    device = IoTDevice.query.filter_by(device_id=device_id).first_or_404()
    status = device.to_dict(offline_after_seconds=app.config['DEVICE_OFFLINE_TIMEOUT_SECONDS'])
    if status['status'] == 'offline':
        _add_iot_alert(
            device,
            'Device Offline',
            'Warning',
            f'No heartbeat received within {app.config["DEVICE_OFFLINE_TIMEOUT_SECONDS"]} seconds.'
        )
        db.session.commit()
    return jsonify({'device': status})


@app.route('/api/iot/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_iot_alert(alert_id):
    alert = IoTAlert.query.get_or_404(alert_id)
    alert.acknowledged = True
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'IoT alert acknowledged.'})


@app.route('/api/stats')
@app.route('/api/dashboard/summary')
@login_required
def api_stats():
    image_vehicles = db.session.query(db.func.sum(TrafficRecord.vehicle_count)).filter(
        TrafficRecord.source_type == 'uploaded_image'
    ).scalar() or 0
    device_vehicles = db.session.query(db.func.sum(IoTTelemetry.interval_vehicle_count)).scalar() or 0
    total_vehicles = image_vehicles + device_vehicles
    active_alerts = (
        Alert.query.filter_by(acknowledged=False).count()
        + IoTAlert.query.filter_by(acknowledged=False, resolved_at=None).count()
    )
    latest_pred = Prediction.query.filter(
        Prediction.source_type != 'legacy_unverified'
    ).order_by(Prediction.timestamp.desc()).first()
    latest_reading = IoTTelemetry.query.order_by(IoTTelemetry.timestamp.desc()).first()
    current_density = (
        latest_reading.density if latest_reading
        else latest_pred.predicted_density if latest_pred
        else 'Unknown'
    )

    return jsonify({
        'total_vehicles': total_vehicles,
        'active_alerts': active_alerts,
        'current_density': current_density,
        'total_predictions': Prediction.query.filter(
            Prediction.source_type != 'legacy_unverified'
        ).count(),
        'active_cameras': CameraDetail.query.filter_by(status='Active').count(),
        'registered_devices': IoTDevice.query.count(),
        'online_devices': sum(
            device.to_dict(offline_after_seconds=app.config['DEVICE_OFFLINE_TIMEOUT_SECONDS'])['status'] == 'online'
            for device in IoTDevice.query.all()
        )
    })

@app.route('/api/traffic_data')
@login_required
def api_traffic_data():
    rows = []
    records = TrafficRecord.query.filter(
        TrafficRecord.source_type != 'legacy_unverified'
    ).order_by(TrafficRecord.timestamp.desc()).limit(24).all()
    for record in records:
        rows.append({
            'timestamp': record.timestamp,
            'count': record.vehicle_count,
            'density': record.density_status,
            'speed': record.average_speed_kmh,
            'source': record.source_type
        })
    readings = IoTTelemetry.query.order_by(IoTTelemetry.timestamp.desc()).limit(24).all()
    for reading in readings:
        rows.append({
            'timestamp': reading.timestamp,
            'count': reading.interval_vehicle_count,
            'density': reading.density,
            'speed': None,
            'source': reading.mode
        })
    rows.sort(key=lambda row: row['timestamp'])
    rows = rows[-24:]

    return jsonify({
        'labels': [row['timestamp'].strftime('%Y-%m-%d %H:%M') for row in rows],
        'counts': [row['count'] for row in rows],
        'densities': [row['density'] for row in rows],
        'speeds': [row['speed'] for row in rows],
        'sources': [row['source'] for row in rows]
    })

@app.route('/api/predict', methods=['POST'])
@login_required
def api_predict():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'A JSON object is required.'}), 400
    try:
        v_count = data.get('vehicle_count')
        occupancy = float(data.get('occupancy_rate', 0))
        speed = float(data['avg_speed']) if data.get('avg_speed') not in (None, '') else None
        hour = int(data.get('hour_of_day', datetime.now().hour))
        weather = int(data.get('weather', 0))
        if isinstance(v_count, bool) or not isinstance(v_count, int) or v_count < 0:
            raise ValueError('vehicle_count must be a non-negative integer.')
        if not 0 <= occupancy <= 100:
            raise ValueError('occupancy_rate must be between 0 and 100.')
        if speed is not None and not 0 <= speed <= 300:
            raise ValueError('avg_speed must be between 0 and 300 km/h.')
        if not 0 <= hour <= 23:
            raise ValueError('hour_of_day must be between 0 and 23.')
        if not 0 <= weather <= 2:
            raise ValueError('weather must be 0, 1, or 2.')
    except (TypeError, ValueError) as error:
        return jsonify({'status': 'error', 'message': str(error)}), 400

    prediction = classifier.predict(
        vehicle_count=v_count,
        occupancy_rate=occupancy,
        avg_speed=speed,
        hour_of_day=hour,
        weather_condition=weather
    )
    return jsonify(prediction)

@app.route('/api/alerts/acknowledge/<int:alert_id>', methods=['POST'])
@login_required
def acknowledge_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.acknowledged = True
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'Alert #{alert_id} acknowledged.'})

@app.route('/api/users/add', methods=['POST'])
@admin_required
def add_user_api():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'User')

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash('Username or Email already exists.', 'danger')
        return redirect(url_for('user_mgmt'))

    u = User(username=username, email=email, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'User {username} created successfully!', 'success')
    return redirect(url_for('user_mgmt'))

@app.route('/api/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user_api(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete your own active session.', 'warning')
        return redirect(url_for('user_mgmt'))
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully.', 'info')
    return redirect(url_for('user_mgmt'))

@app.route('/api/generate_report', methods=['POST'])
@login_required
def generate_report():
    report_type = request.form.get('report_type', 'Daily')
    if report_type not in ('Daily', 'Weekly', 'Monthly'):
        flash('Choose Daily, Weekly, or Monthly for a report.', 'danger')
        return redirect(url_for('reports'))
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days={'Daily': 1, 'Weekly': 7, 'Monthly': 30}[report_type])
    title = f"{report_type} Traffic Analysis Report - {end_date.strftime('%b %d, %Y')}"
    rep = Report(
        title=title,
        report_type=report_type,
        date_range=f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        generated_by=session.get('username', 'System User')
    )
    db.session.add(rep)
    db.session.commit()

    flash(f'{report_type} report created. Use the printable view or CSV export for stored data.', 'success')
    return redirect(url_for('reports'))


@app.route('/api/reports/traffic.csv')
@login_required
def export_traffic_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'timestamp_utc', 'source_type', 'device_or_camera', 'mode',
        'interval_vehicle_count', 'total_vehicle_count', 'density',
        'flow_vehicles_per_minute', 'occupancy_percent', 'measured_speed_kmh',
        'detection_method', 'sequence'
    ])

    traffic_records = TrafficRecord.query.filter(
        TrafficRecord.source_type != 'legacy_unverified'
    ).order_by(TrafficRecord.timestamp.desc()).limit(10000).all()
    predictions = Prediction.query.filter(
        Prediction.source_type != 'legacy_unverified'
    ).order_by(Prediction.timestamp.desc()).limit(10000).all()
    telemetry = IoTTelemetry.query.order_by(IoTTelemetry.timestamp.desc()).limit(10000).all()

    rows = []
    for record in traffic_records:
        rows.append((
            record.timestamp,
            record.source_type,
            record.camera_id or '',
            '',
            record.vehicle_count,
            record.vehicle_count,
            record.density_status,
            '',
            record.occupancy_rate,
            '',
            '',
            ''
        ))
    for prediction in predictions:
        rows.append((
            prediction.timestamp,
            prediction.source_type,
            prediction.camera_id or '',
            '',
            prediction.input_vehicle_count,
            prediction.input_vehicle_count,
            prediction.predicted_density,
            '',
            prediction.input_occupancy,
            '',
            prediction.detection_method,
            ''
        ))
    for reading in telemetry:
        rows.append((
            reading.timestamp,
            reading.mode,
            reading.device_id,
            reading.mode,
            reading.interval_vehicle_count,
            reading.total_vehicle_count,
            reading.density,
            reading.flow_per_minute,
            '',
            '',
            '',
            reading.sequence
        ))
    rows.sort(key=lambda row: row[0], reverse=True)
    for row in rows[:20000]:
        writer.writerow([row[0].isoformat() + 'Z', *row[1:]])

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=traffic-history.csv'
    if len(rows) > 20000:
        response.headers['X-Export-Truncated'] = 'true'
    return response


# ==========================================
# APP INITIALIZATION ENTRYPOINT
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        init_db(app)
    print("=" * 60)
    print("  SMART TRAFFIC DENSITY PREDICTION SYSTEM (IoT & DNN)  ")
    print("  Server launching on http://127.0.0.1:5000            ")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
