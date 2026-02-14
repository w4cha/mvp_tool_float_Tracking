from sqlalchemy import Column, Integer, String, BigInteger, Boolean, Float, DateTime, Text, ForeignKey
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

json_type = JSONB().with_variant(JSON, 'sqlite')

class Vehicle(Base):
    __tablename__ = "vehicle"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(String(25), unique=True)
    vehicle_type = Column(String(20))
    harwdare_id = Column(BigInteger, unique=True)
    current_driver = Column(String(40))
    
    # Optional: helps navigate from vehicle to telemetry in the script
    telemetry = relationship("VehicleTelemetry", backref="parent_vehicle", uselist=False)

class VehicleTelemetry(Base):
    __tablename__ = "telemetria"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicle.id", ondelete="CASCADE"), unique=True)
    accumulated_distance = Column(Float, default=0.0)
    max_registered_speed = Column(Float, default=0.0)
    mean_speed = Column(Float, default=0.0)
    sample_size = Column(Integer, default=0)
    last_lat = Column(Float, default=0.0)
    last_lon = Column(Float, default=0.0)
    speed = Column(Float, default=0)
    is_moving = Column(Boolean, default=False)
    raw_data = Column(json_type, nullable=False) 
    last_update = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SystemConfig(Base):
    __tablename__ = "shared_state"

    id = Column(Integer, primary_key=True)
    worker_enabled = Column(Boolean, default=True)

#TODO ADDAPT ROUTE TO THE NEW CLASS HIEARACHY
#CHANGE TIME TO LOCAL WHEN DISPLAYING IN FRONTEND
# SOME STYLING CHANGES