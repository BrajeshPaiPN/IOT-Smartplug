"""
Smart Solar Plug — Pydantic Schemas
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TelemetryBase(BaseModel):
    timestamp:       Optional[datetime] = None
    light_intensity: Optional[float] = None
    temperature:     Optional[float] = None
    humidity:        Optional[float] = None
    voltage:         Optional[float] = None
    current:         Optional[float] = None
    power:           Optional[float] = None
    energy:          Optional[float] = None
    needs_cleaning:  Optional[bool]  = None
    cleaning_conf:   Optional[float] = None
    degradation_pct: Optional[float] = None

class TelemetryOut(TelemetryBase):
    id: int
    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    id:           int
    timestamp:    datetime
    alert_type:   str
    severity:     str
    message:      str
    confidence:   Optional[float] = None
    acknowledged: bool

    class Config:
        from_attributes = True


class DegradationOut(BaseModel):
    id:               int
    timestamp:        datetime
    degradation_pct:  float
    efficiency_ratio: Optional[float] = None
    trend:            str

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    latest_light:       Optional[float] = None
    latest_temperature: Optional[float] = None
    latest_humidity:    Optional[float] = None
    latest_voltage:     Optional[float] = None
    latest_current:     Optional[float] = None
    latest_power:       Optional[float] = None
    latest_energy:      Optional[float] = None
    current_degradation:Optional[float] = None
    degradation_trend:  Optional[str]   = None
    unread_alerts:      int = 0
    total_alerts:       int = 0
    cleaning_needed:    bool = False
    cleaning_confidence:Optional[float] = None
    last_updated:       Optional[datetime] = None


class CleaningPrediction(BaseModel):
    alert:      bool
    confidence: float
    severity:   str
    reason:     str


class DegradationPrediction(BaseModel):
    degradation_pct: float
    efficiency_ratio:float
    trend:           str
    message:         str


class SolarSettingsIn(BaseModel):
    panel_rating:      float
    electricity_cost:  float
    installation_cost: float
    sunlight_hours:    Optional[float] = 4.5
    ldr_inverted:      Optional[bool] = False


class SolarSettingsOut(BaseModel):
    id:                int
    panel_rating:      float
    electricity_cost:  float
    installation_cost: float
    sunlight_hours:    float
    ldr_inverted:      bool

    class Config:
        from_attributes = True


class MaintenanceLogIn(BaseModel):
    performed_at: datetime
    notes: Optional[str] = None
    current_degradation: Optional[float] = None


class MaintenanceLogOut(BaseModel):
    id: int
    timestamp: datetime
    performed_at: datetime
    notes: Optional[str] = None
    current_degradation: Optional[float] = None

    class Config:
        from_attributes = True

