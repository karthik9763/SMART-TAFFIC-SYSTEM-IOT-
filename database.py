import os
from datetime import datetime
from sqlalchemy import UniqueConstraint, inspect
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='User') # 'Admin' or 'User'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        """Hashes password using bcrypt with 12 salt rounds."""
        if not password:
            raise ValueError("Password cannot be empty.")
        if isinstance(password, str):
            password = password.strip().encode('utf-8')
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(password, salt).decode('utf-8')

    def check_password(self, password):
        """
        Securely compares password using bcrypt.checkpw().
        Supports exact string and trimmed string.
        Falls back to werkzeug for backwards compatibility with pre-existing hashes.
        """
        if not self.password_hash or not password:
            return False
        pwd_str = str(password)
        pwd_bytes = pwd_str.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')

        # Check bcrypt hash ($2a$, $2b$, $2y$)
        if self.password_hash.startswith(('$2a$', '$2b$', '$2y$')):
            try:
                if bcrypt.checkpw(pwd_bytes, hash_bytes):
                    return True
                # Check trimmed version if user had accidental whitespace
                if pwd_str.strip() != pwd_str:
                    if bcrypt.checkpw(pwd_str.strip().encode('utf-8'), hash_bytes):
                        return True
            except Exception:
                pass
            return False

        # Fallback check for legacy werkzeug hashes (scrypt, pbkdf2)
        try:
            if check_password_hash(self.password_hash, pwd_str):
                return True
            if pwd_str.strip() != pwd_str and check_password_hash(self.password_hash, pwd_str.strip()):
                return True
        except Exception:
            pass
        return False

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera_details.id'), nullable=True)
    vehicle_type = db.Column(db.String(50), nullable=False) # Car, Bus, Truck, Motorbike
    confidence = db.Column(db.Float, nullable=False)
    bbox = db.Column(db.String(100), nullable=True) # x,y,w,h
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class TrafficRecord(db.Model):
    __tablename__ = 'traffic_records'
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera_details.id'), nullable=False)
    vehicle_count = db.Column(db.Integer, nullable=False)
    cars_count = db.Column(db.Integer, default=0)
    buses_count = db.Column(db.Integer, default=0)
    trucks_count = db.Column(db.Integer, default=0)
    motorcycles_count = db.Column(db.Integer, default=0)
    bicycles_count = db.Column(db.Integer, default=0)
    autorickshaws_count = db.Column(db.Integer, default=0)
    vans_count = db.Column(db.Integer, default=0)
    density_status = db.Column(db.String(20), nullable=False) # Low, Medium, High
    average_speed_kmh = db.Column(db.Float, default=45.0)
    occupancy_rate = db.Column(db.Float, default=0.0) # Percentage lane coverage
    source_type = db.Column(db.String(30), nullable=False, default='legacy_unverified')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'vehicle_count': self.vehicle_count,
            'cars_count': self.cars_count,
            'buses_count': self.buses_count,
            'trucks_count': self.trucks_count,
            'motorcycles_count': self.motorcycles_count,
            'bicycles_count': self.bicycles_count,
            'autorickshaws_count': self.autorickshaws_count,
            'vans_count': self.vans_count,
            'density_status': self.density_status,
            'average_speed_kmh': round(self.average_speed_kmh, 1),
            'occupancy_rate': round(self.occupancy_rate, 2),
            'source_type': self.source_type,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class Prediction(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera_details.id'), nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    annotated_image_path = db.Column(db.String(255), nullable=True)
    input_vehicle_count = db.Column(db.Integer, nullable=False, default=0)
    cars_count = db.Column(db.Integer, default=0)
    buses_count = db.Column(db.Integer, default=0)
    trucks_count = db.Column(db.Integer, default=0)
    motorcycles_count = db.Column(db.Integer, default=0)
    bicycles_count = db.Column(db.Integer, default=0)
    autorickshaws_count = db.Column(db.Integer, default=0)
    vans_count = db.Column(db.Integer, default=0)
    input_occupancy = db.Column(db.Float, nullable=False, default=0.0)
    input_hour = db.Column(db.Integer, nullable=False, default=12)
    predicted_density = db.Column(db.String(20), nullable=False) # Low, Medium, High
    confidence_score = db.Column(db.Float, nullable=False)
    estimated_congestion_pct = db.Column(db.Float, default=0.0)
    quality_warning = db.Column(db.String(255), nullable=True)
    inference_time_ms = db.Column(db.Float, default=0.0)
    model_version = db.Column(db.String(50), default='DNN-v2.0-YOLO-MLP')
    source_type = db.Column(db.String(30), nullable=False, default='legacy_unverified')
    detection_method = db.Column(db.String(50), nullable=False, default='legacy_unverified')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'image_path': self.image_path,
            'annotated_image_path': self.annotated_image_path or self.image_path,
            'vehicle_count': self.input_vehicle_count,
            'cars_count': self.cars_count,
            'buses_count': self.buses_count,
            'trucks_count': self.trucks_count,
            'motorcycles_count': self.motorcycles_count,
            'bicycles_count': self.bicycles_count,
            'autorickshaws_count': self.autorickshaws_count,
            'vans_count': self.vans_count,
            'occupancy_rate': round(self.input_occupancy, 1),
            'predicted_density': self.predicted_density,
            'confidence_score': round(self.confidence_score, 1) if self.confidence_score > 0 else None,
            'estimated_congestion_pct': round(self.estimated_congestion_pct, 1) if self.estimated_congestion_pct is not None else None,
            'quality_warning': self.quality_warning,
            'inference_time_ms': round(self.inference_time_ms, 1),
            'model_version': self.model_version,
            'source_type': self.source_type,
            'detection_method': self.detection_method,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class CameraDetail(db.Model):
    __tablename__ = 'camera_details'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    stream_url = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='Active') # Active, Standby, Inactive
    ip_address = db.Column(db.String(50), default='192.168.1.100')
    fps = db.Column(db.Integer, default=25)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'stream_url': self.stream_url,
            'status': self.status,
            'ip_address': self.ip_address,
            'fps': self.fps,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class Alert(db.Model):
    __tablename__ = 'alerts'
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera_details.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False) # Heavy Congestion, Camera Offline, Speed Anomaly
    message = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(20), default='Warning') # Info, Warning, Critical
    acknowledged = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'alert_type': self.alert_type,
            'message': self.message,
            'severity': self.severity,
            'acknowledged': self.acknowledged,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    report_type = db.Column(db.String(50), nullable=False) # Daily, Weekly, Monthly
    date_range = db.Column(db.String(100), nullable=False)
    generated_by = db.Column(db.String(64), nullable=False)
    file_path = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LoginHistory(db.Model):
    __tablename__ = 'login_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    username = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(50), default='127.0.0.1')
    user_agent = db.Column(db.String(255), default='Web Browser')
    status = db.Column(db.String(20), default='Success')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class IoTDevice(db.Model):
    __tablename__ = 'iot_devices'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    intersection_id = db.Column(db.String(80), nullable=False)
    lane_id = db.Column(db.String(80), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    token_hash = db.Column(db.String(256), nullable=False)
    total_vehicle_count = db.Column(db.Integer, nullable=False, default=0)
    direction_a_to_b = db.Column(db.Integer, nullable=False, default=0)
    direction_b_to_a = db.Column(db.Integer, nullable=False, default=0)
    last_sequence = db.Column(db.Integer, nullable=False, default=-1)
    last_seen = db.Column(db.DateTime, nullable=True, index=True)
    last_uptime_seconds = db.Column(db.Integer, nullable=False, default=0)
    sensor_a = db.Column(db.Boolean, nullable=True)
    sensor_b = db.Column(db.Boolean, nullable=True)
    density = db.Column(db.String(20), nullable=True)
    firmware_version = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    registered_by = db.Column(db.String(64), nullable=False)

    def to_dict(self, now=None, offline_after_seconds=30):
        now = now or datetime.utcnow()
        is_online = (
            self.last_seen is not None
            and (now - self.last_seen).total_seconds() <= offline_after_seconds
        )
        return {
            'device_id': self.device_id,
            'intersection_id': self.intersection_id,
            'lane_id': self.lane_id,
            'mode': self.mode,
            'status': 'online' if is_online else 'offline',
            'total_vehicle_count': self.total_vehicle_count,
            'direction_a_to_b': self.direction_a_to_b,
            'direction_b_to_a': self.direction_b_to_a,
            'last_sequence': self.last_sequence,
            'last_seen': self.last_seen.isoformat() + 'Z' if self.last_seen else None,
            'firmware_version': self.firmware_version,
            'density': self.density,
        }


class IoTTelemetry(db.Model):
    __tablename__ = 'iot_telemetry'
    __table_args__ = (
        UniqueConstraint('device_id', 'sequence', name='uq_iot_telemetry_device_sequence'),
        db.Index('ix_iot_telemetry_device_timestamp', 'device_id', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), db.ForeignKey('iot_devices.device_id'), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    uptime_seconds = db.Column(db.Integer, nullable=False)
    total_vehicle_count = db.Column(db.Integer, nullable=False)
    interval_vehicle_count = db.Column(db.Integer, nullable=False, default=0)
    direction_a_to_b = db.Column(db.Integer, nullable=False)
    direction_b_to_a = db.Column(db.Integer, nullable=False)
    sensor_a = db.Column(db.Boolean, nullable=False)
    sensor_b = db.Column(db.Boolean, nullable=False)
    flow_per_minute = db.Column(db.Float, nullable=False, default=0.0)
    density = db.Column(db.String(20), nullable=False)
    firmware_version = db.Column(db.String(40), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class IoTAlert(db.Model):
    __tablename__ = 'iot_alerts'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), db.ForeignKey('iot_devices.device_id'), nullable=False, index=True)
    alert_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

class IoTMqttEvent(db.Model):
    __tablename__ = 'iot_mqtt_events'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(80), db.ForeignKey('iot_devices.device_id'), nullable=False, index=True)
    topic = db.Column(db.String(200), nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'topic': self.topic,
            'payload': self.payload_json,
            'timestamp': self.timestamp.isoformat() + 'Z'
        }


def init_db(app):
    with app.app_context():
        db.create_all()

        # Preserve existing local databases and label records without provenance.
        if db.engine.dialect.name == 'sqlite':
            with db.engine.begin() as connection:
                existing_columns = {
                    table: {column['name'] for column in inspect(db.engine).get_columns(table)}
                    for table in ('traffic_records', 'predictions')
                }
                additions = {
                    'traffic_records': {
                        'source_type': "VARCHAR(30) NOT NULL DEFAULT 'legacy_unverified'"
                    },
                    'predictions': {
                        'source_type': "VARCHAR(30) NOT NULL DEFAULT 'legacy_unverified'",
                        'detection_method': "VARCHAR(50) NOT NULL DEFAULT 'legacy_unverified'",
                    },
                }
                for table, columns in additions.items():
                    for column, declaration in columns.items():
                        if column not in existing_columns[table]:
                            connection.exec_driver_sql(
                                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}'
                            )

        admin_username = os.environ.get('BOOTSTRAP_ADMIN_USERNAME') or 'admin'
        admin_email = os.environ.get('BOOTSTRAP_ADMIN_EMAIL') or 'admin@smarttraffic.ai'
        admin_password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD') or '123456'

        admin = User.query.filter(
            (db.func.lower(User.username) == admin_username.lower()) |
            (db.func.lower(User.email) == admin_email.lower())
        ).first()

        if not admin:
            admin = User(username=admin_username, email=admin_email, role='Admin')
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f"[Database] Automatically created default administrator '{admin_username}' ({admin_email}) with bcrypt.")
        else:
            updated = False
            if admin.email != admin_email:
                admin.email = admin_email
                updated = True
            if admin.role != 'Admin':
                admin.role = 'Admin'
                updated = True
            if not admin.check_password(admin_password):
                admin.set_password(admin_password)
                updated = True
                print(f"[Database] Synchronized default administrator '{admin_username}' password to required credentials.")
            if updated:
                db.session.commit()

        # Seed default ESP32 / Wokwi counter devices if not present
        default_devices = [
            ("wokwi-counter-01", "Intersection-1", "Lane-North", "simulation", "default-sim-token"),
            ("esp32-counter-01", "Intersection-1", "Lane-South", "simulation", "default-sim-token"),
        ]
        for dev_id, inter_id, lane_id, mode, raw_tok in default_devices:
            dev = IoTDevice.query.filter_by(device_id=dev_id).first()
            if not dev:
                dev = IoTDevice(
                    device_id=dev_id,
                    intersection_id=inter_id,
                    lane_id=lane_id,
                    mode=mode,
                    token_hash=generate_password_hash(raw_tok),
                    registered_by="bootstrap"
                )
                db.session.add(dev)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
