import enum
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from flask_login import UserMixin

db = SQLAlchemy()

json_type = JSONB().with_variant(JSON, 'sqlite')

class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(db.Model, UserMixin):

    __tablename__ = "usuarios"

    user_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(50), nullable=False)
    user_email = db.Column(db.String(100), nullable=False, unique=True)
    active_user = db.Column(db.Boolean, default=True, nullable=False)
    user_role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.USER)
    user_password = db.Column(db.Text, nullable=False)
    creation_date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def get_id(self):
        return self.user_id

    def __repr__():
        return f'<Usuario {self.user_name}>'

class Vehicle(db.Model):

    __tablename__ = "vehicle"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.String(25), unique=True)
    vehicle_type = db.Column(db.String(20))
    harwdare_id = db.Column(db.BigInteger, unique=True)
    # currently only a name in the future a driver object
    current_driver = db.Column(db.String(40))
    telemetry = db.relationship("VehicleTelemetry", backref="parent_vehicle", uselist=False)

def __repr__(self):
    return f"<Vehicle: {self.vehicle_id}, Driver: {self.current_driver}>"


class VehicleTelemetry(db.Model):

    __tablename__ = "telemetria"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id", ondelete="CASCADE"), unique=True)
    max_registered_speed = db.Column(db.Float, default=0.0)
    mean_speed = db.Column(db.Float, default=0.0)
    sample_size = db.Column(db.Integer, default=0)
    last_lat = db.Column(db.Float, default=0.0)
    last_lon = db.Column(db.Float, default=0.0)
    speed = db.Column(db.Float, default=0.0)
    accumulated_distance = db.Column(db.Float, default=0.0)
    # calc base in last message posiiton arguments
    is_moving = db.Column(db.Boolean, default=False)
    raw_data = db.Column(json_type, nullable=False) 
    last_update = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


    def __repr__(self):
        return f'<Telmetry for vehicle: {self.parent_vehicle.vehicle_id}>'

class SystemConfig(db.Model):
    __tablename__ = "shared_state"

    id = db.Column(db.Integer, primary_key=True)
    worker_enabled = db.Column(db.Boolean, default=True)


@event.listens_for(User.user_email, 'set', retval=True)
def upper_email(target, value, oldvalue, initiator):
    if value:
        return value.upper().strip()
    return value

@event.listens_for(User.user_name, 'set', retval=True)
def upper_name(target, value, oldvalue, initiator):
    if value:
        return value.upper().strip()
    return value
