import enum
import re
import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, event, ForeignKey, MetaData, func, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, validates
from flask_login import UserMixin
from datetime import datetime, timezone, timedelta

# 1. Naming Conventions
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)

db = SQLAlchemy(model_class=Base)
json_type = JSONB().with_variant(JSON, 'sqlite')

# 2. Mixins & Enums
class TimestampMixin:
    # Use timezone=True to match your Telemetry models
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), 
                           default=lambda: datetime.now(timezone.utc), 
                           onupdate=lambda: datetime.now(timezone.utc))
class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"

class VehicleState(enum.Enum):
    ACTIVO = "activo"
    MANTENIMIENTO = "mantenimiento"
    INACTIVO = "fuera de servicio"
    RETIRADO = "no forma parte de la flota"

class Subject(enum.Enum):
    OTRO = "otro"
    EXCESO_VELOCIDAD = "exceso de velocidad detectado"
    MANTENIMIENTO_PROXIMO = "mantenimiento cercano"
    RETRASO_PLANIFICACION = "atraso en ruta/itinerario"
    COMPORTAMIENTO_CONDUCCION = "alerta de comportamiento"
    INCIDENTE = "incidente o siniestro"

# 3. Models
class User(db.Model, UserMixin):
    __tablename__ = "usuarios"
    user_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(50), nullable=False)
    user_email = db.Column(db.String(100), nullable=False, unique=True)
    user_password = db.Column(db.Text, nullable=False)
    active_user = db.Column(db.Boolean, default=True)
    user_role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.USER)
    
    def get_id(self): 
        return self.user_id
    def __repr__(self): 
        return f'<Usuario {self.user_name}>'

class Driver(db.Model, TimestampMixin):
    __tablename__ = "conductores"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True)
    driver_email = db.Column(db.String(100), nullable=False, unique=True)
    
    assigned_vehicles = relationship("Vehicle", back_populates="current_driver")

    @validates('phone')
    def validate_chilean_phone(self, key, value):
        if not value: return None
        clean_number = re.sub(r'[^\d+]', '', value)
        if clean_number.startswith('0'):
            clean_number = '+56' + clean_number[1:]
        if not clean_number.startswith('+'):
            if len(clean_number) == 9:
                clean_number = '+56' + clean_number
            elif clean_number.startswith('56') and len(clean_number) == 11:
                clean_number = '+' + clean_number
        if not re.match(r'^\+56\d{9}$', clean_number):
            raise ValueError(f"Formato de teléfono inválido: {value}")
        return clean_number

    def __repr__(self): return f"<Conductor: {self.name}>"

class Vehicle(db.Model):
    __tablename__ = "vehiculo"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.String(25), unique=True)
    driver_id = db.Column(db.Integer, ForeignKey("conductores.id", ondelete="SET NULL"))
    vehicle_state = db.Column(db.Enum(VehicleState), nullable=False, default=VehicleState.ACTIVO)
    current_driver = relationship("Driver", back_populates="assigned_vehicles")
    telemetry_data = relationship("VehicleTelemetry", back_populates="parent_vehicle", uselist=False)
    telemetry_history = relationship("VehicleTelemetryHistory", back_populates="parent_vehicle")
    annotations_list = relationship("VehicleAnnotations", back_populates="parent_vehicle")
    completed_routes = relationship("VehicleRoute", back_populates="parent_vehicle", cascade="all, delete-orphan")

    def __repr__(self):
        d_name = self.current_driver.name if self.current_driver else "Sin conductor"
        return f"<Vehiculo: {self.vehicle_id}, Conductor: {d_name}>"

class VehicleAnnotations(db.Model, TimestampMixin):
    __tablename__ = "comentarios"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, ForeignKey("vehiculo.id", ondelete="CASCADE"))
    subject = db.Column(db.Enum(Subject), nullable=False, default=Subject.OTRO)
    comment = db.Column(db.String(200))
    
    parent_vehicle = relationship("Vehicle", back_populates="annotations_list")

    def __repr__(self): return f'<Annotation for: {self.parent_vehicle.vehicle_id}>'

class VehicleTelemetry(db.Model):
    # a combination of engine state and is moving
    # differenciates between a vehicle with engine
    # on and not moving and a vehicle with engine off
    # and not moving
    __tablename__ = "telemetria"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehiculo.id", ondelete="CASCADE"), unique=True, nullable=False)
    max_registered_speed = db.Column(db.Float, default=0.0)
    mean_speed = db.Column(db.Float, default=0.0)
    sample_size = db.Column(db.Integer, default=0)
    last_lat = db.Column(db.Float, default=0.0)
    last_lon = db.Column(db.Float, default=0.0)
    speed = db.Column(db.Float, default=0.0)
    accumulated_distance = db.Column(db.Float, default=0.0)
    is_moving = db.Column(db.Boolean, default=False)
    engine_state = db.Column(db.Boolean, default=False)
    raw_data = db.Column(json_type, nullable=False) 
    last_update = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    parent_vehicle = relationship("Vehicle", back_populates="telemetry_data")

    def __repr__(self): 
        return f'<Telemetry: {self.parent_vehicle.vehicle_id}>'

class VehicleTelemetryHistory(db.Model):
    __tablename__ = "telemetria_historial"
    
    # In PostgreSQL Partitioning, the partition key (timestamp) 
    # MUST be part of the Primary Key.
    id = db.Column(BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True, autoincrement=True)
    vehicle_id = db.Column(db.String(25), db.ForeignKey("vehiculo.vehicle_id", ondelete="CASCADE"), index=True, nullable=False)
    
    speed = db.Column(db.Float, default=0.0)
    last_lat = db.Column(db.Float, default=0.0)
    last_lon = db.Column(db.Float, default=0.0)
    is_moving = db.Column(db.Boolean, default=False)
    engine_state = db.Column(db.Boolean, default=False)
    
    # 1. Change: Timestamp is now the partition key
    timestamp = db.Column(db.DateTime(timezone=True), 
                          default=lambda: datetime.now(timezone.utc), 
                          primary_key=os.getenv("FLASK_ENV") != "development",
                          index=True)

    if os.getenv("FLASK_ENV") != "development":
        __table_args__ = (
            db.PrimaryKeyConstraint('id', 'timestamp'), # Composite PK
            {'postgresql_partition_by': 'RANGE (timestamp)'}
        )
        
    else:
        __table_args__ = ()

    parent_vehicle = relationship("Vehicle", back_populates="telemetry_history")

    def __repr__(self): 
        return f'<History: {self.vehicle_id} @ {self.timestamp}>'

class VehicleTelemetryBackup(db.Model):
    """Cold storage for all telemetry ever recorded. Not partitioned."""
    __tablename__ = "telemetria_backup"
    
    id = db.Column(BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    vehicle_id = db.Column(db.String(25), index=True)
    speed = db.Column(db.Float)
    last_lat = db.Column(db.Float)
    last_lon = db.Column(db.Float)
    is_moving = db.Column(db.Boolean)
    engine_state = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc))

    def __repr__(self): 
        return f'<Backup: {self.vehicle_id} @ {self.timestamp}>'

class VehicleRoute(db.Model, TimestampMixin):
    __tablename__ = "rutas_completadas"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.String(25), db.ForeignKey("vehiculo.vehicle_id", ondelete="CASCADE"), index=True, nullable=False)
    
    # Temporal Data
    start_time = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    duration_minutes = db.Column(db.Float) # (end - start)
    
    # Metrics
    distance_km = db.Column(db.Float, default=0.0)
    max_speed = db.Column(db.Float, default=0.0)
    avg_speed = db.Column(db.Float, default=0.0)
    idle_minutes = db.Column(db.Float, default=0.0) # Engine ON but speed < threshold
    
    # Geometry (The "Breadcrumb" trail)
    # Encoded Polyline string (e.g., "_p~iF~ps|U_ulLnnqC...")
    # This is much lighter than JSONB for long routes
    # no point in having a route with no route info
    total_points = db.Column(db.Integer, nullable=False)
    route_polyline = db.Column(db.Text, nullable=False)
    
    # Metadata
    start_lat = db.Column(db.Float)
    start_lon = db.Column(db.Float)
    end_lat = db.Column(db.Float)
    end_lon = db.Column(db.Float)

    parent_vehicle = relationship("Vehicle", back_populates="completed_routes")

    def __repr__(self):
        return f'<Route {self.vehicle_id}: {self.start_time} to {self.end_time}>'

class RegistrationToken(db.Model, TimestampMixin):
    """
    Gatekeeper for new user registrations.
    Tokens are unique strings sent to invited users.
    """
    __tablename__ = "tokens_registro"
    
    id = db.Column(db.Integer, primary_key=True)
    # The actual random string (e.g., a8f3b2...)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # Becomes True once a user successfully registers with it
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    # Security: Tokens shouldn't last forever
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    
    # created_at and updated_at are provided by TimestampMixin

    @property
    def is_expired(self):
        """Returns True if the current time is past the expiry date"""
        # Aseguramos que la comparación sea entre dos objetos con zona horaria (UTC)
        now = datetime.now(timezone.utc)
        
        # Si expires_at es naive (cosa rara con timezone=True pero posible en SQLite),
        # le forzamos UTC para la comparación.
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
            
        return now > expires

    @staticmethod
    def generate(hours_valid=48):
        """
        Creates and returns a new RegistrationToken instance.
        Note: You must db.session.add() and commit() where you call this.
        """
        return RegistrationToken(
            token=secrets.token_hex(24),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=hours_valid)
        )

    def __repr__(self):
        status = "USED" if self.is_used else ("EXPIRED" if self.is_expired else "ACTIVE")
        return f"<Token {self.token[:8]}... [{status}]>"

class SystemConfig(db.Model):
    __tablename__ = "shared_state"
    id = db.Column(db.Integer, primary_key=True)
    worker_enabled = db.Column(db.Boolean, default=True)
    last_maintenance_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# 4. Global Event Listeners
@event.listens_for(User.user_name, 'set', retval=True)
@event.listens_for(User.user_email, 'set', retval=True)
@event.listens_for(Driver.name, 'set', retval=True)
def upper_value(target, value, oldvalue, initiator):
    return value.upper().strip() if value else value