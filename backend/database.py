"""
Smart Solar Plug — SQLite Database Setup (SQLAlchemy)
"""

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./solar_plug.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # needed for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── ORM Models ───────────────────────────────────────────────────────────────

class TelemetryLog(Base):
    __tablename__ = "telemetry_log"

    id              = Column(Integer, primary_key=True, index=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    # Environment
    light_intensity = Column(Float, nullable=True)   # LDR % (0–100)
    temperature     = Column(Float, nullable=True)   # DHT11 °C
    humidity        = Column(Float, nullable=True)   # DHT11 %
    # Electrical (PZEM-004T)
    voltage         = Column(Float, nullable=True)   # Volts AC
    current         = Column(Float, nullable=True)   # Amperes
    power           = Column(Float, nullable=True)   # Watts
    energy          = Column(Float, nullable=True)   # kWh cumulative
    # ML inference cache
    needs_cleaning  = Column(Boolean, nullable=True)
    cleaning_conf   = Column(Float, nullable=True)
    degradation_pct = Column(Float, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id           = Column(Integer, primary_key=True, index=True)
    timestamp    = Column(DateTime, default=datetime.utcnow, index=True)
    alert_type   = Column(String(20))      # 'CLEANING' | 'DEGRADATION'
    severity     = Column(String(10))      # 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
    message      = Column(Text)
    confidence   = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False)


class DegradationLog(Base):
    __tablename__ = "degradation_log"

    id              = Column(Integer, primary_key=True, index=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    degradation_pct = Column(Float)
    efficiency_ratio= Column(Float, nullable=True)
    trend           = Column(String(15))   # 'STABLE' | 'DECLINING' | 'CRITICAL'


class SolarSettings(Base):
    __tablename__ = "solar_settings"

    id                = Column(Integer, primary_key=True, index=True)
    panel_rating      = Column(Float, default=300.0)      # Watts
    electricity_cost  = Column(Float, default=7.0)        # Per kWh
    installation_cost = Column(Float, default=25000.0)    # Payback baseline
    sunlight_hours    = Column(Float, default=4.5)        # Average daily peak sun
    ldr_inverted      = Column(Boolean, default=False)    # High value = Low Light


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"

    id                  = Column(Integer, primary_key=True, index=True)
    timestamp           = Column(DateTime, default=datetime.utcnow, index=True)
    performed_at        = Column(DateTime, default=datetime.utcnow)
    notes               = Column(Text, nullable=True)
    current_degradation = Column(Float, nullable=True)



# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_db():
    """Dependency for FastAPI route injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created / verified.")
