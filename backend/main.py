"""
Smart Solar Plug — FastAPI Backend
All API endpoints + WebSocket + Firebase listener integration.
"""

import asyncio
from asyncio import Queue
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from database import get_db, create_tables, SessionLocal, TelemetryLog, Alert, DegradationLog, SolarSettings, MaintenanceLog
from schemas import (
    TelemetryOut, AlertOut, DegradationOut, DashboardStats,
    CleaningPrediction, DegradationPrediction, SolarSettingsIn, SolarSettingsOut,
    MaintenanceLogIn, MaintenanceLogOut
)
from ml_inference import load_models, predict_cleaning_alert, predict_degradation, models_available
from firebase_listener import start_listener, stop_listener
from telemetry_processor import register_callback
from mqtt_listener import start_mqtt_listener, stop_mqtt_listener
from report_generator import generate_csv, generate_pdf


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.sse_queues: List[Queue] = []  # SSE subscriber queues

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    def add_sse_subscriber(self) -> Queue:
        q = Queue(maxsize=50)
        self.sse_queues.append(q)
        return q

    def remove_sse_subscriber(self, q: Queue):
        if q in self.sse_queues:
            self.sse_queues.remove(q)

    async def broadcast(self, message: str):
        # Broadcast to WebSocket clients
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        # Broadcast to SSE subscribers
        dead_sse = []
        for q in self.sse_queues:
            try:
                if not q.full():
                    q.put_nowait(message)
            except Exception:
                dead_sse.append(q)
        for q in dead_sse:
            self.remove_sse_subscriber(q)

manager = ConnectionManager()

# ─── Broadcast callback (runs in sync context from listener thread) ───────────

_main_loop = None

def _sync_broadcast(payload: dict):
    """Called by background threads (MQTT/Firebase) to schedule coroutines on the main loop."""
    global _main_loop
    if _main_loop and _main_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(payload, default=str)),
                _main_loop
            )
        except Exception as e:
            print(f"[WS] Broadcast failed: {e}")
    else:
        print(f"[WS] Broadcast skipped: main loop not ready.")

# ─── App Lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    print("[APP] Starting up...")
    
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    
    create_tables()
    load_models()
    register_callback(_sync_broadcast)

    # --- TRUE HYBRID MODEL ---
    # Start both listeners simultaneously. The ESP32 intelligently routes data to one or the other.
    # Whichever protocol receives the data will pass it to the shared telemetry_processor!
    
    start_mqtt_listener(
        db_session_factory=lambda: SessionLocal(),
        ml_predict_cleaning=predict_cleaning_alert,
        ml_predict_degradation=predict_degradation,
    )

    start_listener(
        db_session_factory=lambda: SessionLocal(),
        ml_predict_cleaning=predict_cleaning_alert,
        ml_predict_degradation=predict_degradation,
    )
    
    yield
    print("[APP] Shutting down...")
    stop_mqtt_listener()
    stop_listener()

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart Solar Plug API",
    description="IoT Solar Panel Monitoring — ML Alerts, Degradation Analysis & Reports",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time telemetry push via WebSocket with heartbeat."""
    await manager.connect(websocket)
    try:
        while True:
            # Race: either the client sends something, or we send a heartbeat every 20s
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=20.0)
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)

# ─── Server-Sent Events (SSE) Endpoint — reliable browser-native fallback ─────

@app.get("/api/telemetry/stream")
async def telemetry_stream():
    """SSE stream: browser auto-reconnects if connection drops."""
    queue = manager.add_sse_subscriber()

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send a keep-alive comment so browser doesn't disconnect
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            manager.remove_sse_subscriber(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

# ─── Config Endpoint ────────────────────────────────────────────────────────────

@app.get("/api/config/firebase", tags=["Config"])
def get_firebase_config():
    """Provides Firebase web configuration to the frontend dynamically."""
    # This prevents hardcoding the API key in the frontend JS files.
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", "AIzaSyDH41ABgPFEnBt9UKp4Fr8B5SmCdn8TF_0"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", "smart-power-meter-873a6.firebaseapp.com"),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL", "https://smart-power-meter-873a6-default-rtdb.firebaseio.com/"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", "smart-power-meter-873a6"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", "smart-power-meter-873a6.appspot.com"),
    }

# ─── Telemetry Endpoints ──────────────────────────────────────────────────────

@app.get("/api/telemetry/live", response_model=TelemetryOut, tags=["Telemetry"])
def get_latest_telemetry(db: Session = Depends(get_db)):
    """Get the most recent telemetry reading."""
    record = db.query(TelemetryLog).order_by(TelemetryLog.timestamp.desc()).first()
    if not record:
        raise HTTPException(status_code=404, detail="No telemetry data yet.")
    return record


@app.get("/api/telemetry/history", response_model=List[TelemetryOut], tags=["Telemetry"])
def get_telemetry_history(
    hours: int = Query(24, ge=1, le=8760, description="Hours of history to fetch"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Get historical telemetry for the past N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    records = (
        db.query(TelemetryLog)
        .filter(TelemetryLog.timestamp >= cutoff)
        .order_by(TelemetryLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return records

# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@app.get("/api/dashboard/stats", response_model=DashboardStats, tags=["Dashboard"])
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Aggregated KPIs for the main dashboard."""
    latest = db.query(TelemetryLog).order_by(TelemetryLog.timestamp.desc()).first()
    unread = db.query(Alert).filter(Alert.acknowledged == False).count()
    total  = db.query(Alert).count()
    latest_deg = db.query(DegradationLog).order_by(DegradationLog.timestamp.desc()).first()

    if not latest:
        return DashboardStats(unread_alerts=unread, total_alerts=total)

    return DashboardStats(
        latest_light        = latest.light_intensity,
        latest_temperature  = latest.temperature,
        latest_humidity     = latest.humidity,
        latest_voltage      = latest.voltage,
        latest_current      = latest.current,
        latest_power        = latest.power,
        latest_energy       = latest.energy,
        current_degradation = latest_deg.degradation_pct if latest_deg else latest.degradation_pct,
        degradation_trend   = latest_deg.trend            if latest_deg else None,
        unread_alerts       = unread,
        total_alerts        = total,
        cleaning_needed     = bool(latest.needs_cleaning),
        cleaning_confidence = latest.cleaning_conf,
        last_updated        = latest.timestamp,
    )

# ─── Alerts Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/alerts", response_model=List[AlertOut], tags=["Alerts"])
def get_alerts(
    alert_type: Optional[str] = Query(None, description="Filter: CLEANING or DEGRADATION"),
    unread_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List all alerts with optional filters."""
    q = db.query(Alert).order_by(Alert.timestamp.desc())
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type.upper())
    if unread_only:
        q = q.filter(Alert.acknowledged == False)
    return q.limit(limit).all()


@app.post("/api/alerts/acknowledge/{alert_id}", tags=["Alerts"])
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark a single alert as acknowledged."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.acknowledged = True
    db.commit()
    return {"status": "acknowledged", "id": alert_id}


@app.post("/api/alerts/acknowledge-all", tags=["Alerts"])
def acknowledge_all_alerts(db: Session = Depends(get_db)):
    """Mark all unread alerts as acknowledged."""
    count = db.query(Alert).filter(Alert.acknowledged == False).update({"acknowledged": True})
    db.commit()
    return {"status": "ok", "acknowledged": count}

# ─── Degradation Endpoints ────────────────────────────────────────────────────

@app.get("/api/degradation", response_model=List[DegradationOut], tags=["Degradation"])
def get_degradation_history(
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Full degradation history."""
    return (
        db.query(DegradationLog)
        .order_by(DegradationLog.timestamp.desc())
        .limit(limit)
        .all()
    )

# ─── Report Endpoints ─────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get_records_for_report(db: Session, start: Optional[datetime], end: Optional[datetime]):
    q = db.query(TelemetryLog).order_by(TelemetryLog.timestamp.desc())
    if start:
        q = q.filter(TelemetryLog.timestamp >= start)
    if end:
        q = q.filter(TelemetryLog.timestamp <= end)
    return q.limit(5000).all()


def _get_alerts_for_report(db: Session, start: Optional[datetime], end: Optional[datetime]):
    q = db.query(Alert).order_by(Alert.timestamp.desc())
    if start:
        q = q.filter(Alert.timestamp >= start)
    if end:
        q = q.filter(Alert.timestamp <= end)
    return q.limit(500).all()


@app.get("/api/report/csv", tags=["Reports"])
def download_csv(
    start: Optional[str] = Query(None, description="ISO 8601 start datetime"),
    end:   Optional[str] = Query(None, description="ISO 8601 end datetime"),
    db: Session = Depends(get_db),
):
    """Download telemetry data as CSV."""
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)
    records  = _get_records_for_report(db, start_dt, end_dt)
    csv_bytes = generate_csv(records, start_dt, end_dt)

    filename = f"solar_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/report/pdf", tags=["Reports"])
def download_pdf(
    start: Optional[str] = Query(None),
    end:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Download a professional PDF monitoring report."""
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)
    records  = _get_records_for_report(db, start_dt, end_dt)
    alerts   = _get_alerts_for_report(db, start_dt, end_dt)
    pdf_bytes = generate_pdf(records, alerts, start_dt, end_dt)

    filename = f"solar_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

# ─── Config & Settings Endpoints ──────────────────────────────────────────────

@app.get("/api/config/firebase", tags=["System"])
def get_firebase_config():
    """Retrieve public Firebase configuration credentials dynamically."""
    project_id = "smart-power-meter-873a6"
    try:
        cred_path = os.getenv("FIREBASE_CRED_PATH")
        if cred_path and os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                cred_data = json.load(f)
                project_id = cred_data.get("project_id", project_id)
    except Exception:
        pass

    return {
        "apiKey":      os.getenv("FIREBASE_API_KEY", "AIzaSyDH41ABgPFEnBt9UKp4Fr8B5SmCdn8TF_0"),
        "authDomain":  os.getenv("FIREBASE_AUTH_DOMAIN", f"{project_id}.firebaseapp.com"),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL", f"https://{project_id}-default-rtdb.firebaseio.com/"),
        "projectId":   project_id
    }


@app.get("/api/settings/solar", response_model=SolarSettingsOut, tags=["Settings"])
def get_solar_settings(db: Session = Depends(get_db)):
    """Retrieve current solar installation settings or return defaults."""
    settings = db.query(SolarSettings).first()
    if not settings:
        settings = SolarSettings(
            panel_rating=300.0,
            electricity_cost=7.0,
            installation_cost=25000.0,
            sunlight_hours=4.5
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@app.post("/api/settings/solar", response_model=SolarSettingsOut, tags=["Settings"])
def update_solar_settings(payload: SolarSettingsIn, db: Session = Depends(get_db)):
    """Update or create solar panel rating and electricity cost settings."""
    settings = db.query(SolarSettings).first()
    if not settings:
        settings = SolarSettings()
        db.add(settings)

    settings.panel_rating      = payload.panel_rating
    settings.electricity_cost  = payload.electricity_cost
    settings.installation_cost = payload.installation_cost
    settings.sunlight_hours    = payload.sunlight_hours if payload.sunlight_hours is not None else 4.5

    db.commit()
    db.refresh(settings)
    return settings


@app.post("/api/maintenance", response_model=MaintenanceLogOut, tags=["Maintenance"])
def create_maintenance_log(payload: MaintenanceLogIn, db: Session = Depends(get_db)):
    """Create a panel cleaning maintenance log and clear outstanding cleaning alerts."""
    log = MaintenanceLog(
        performed_at=payload.performed_at,
        notes=payload.notes,
        current_degradation=payload.current_degradation
    )
    
    # Auto-fill current degradation if not provided
    if log.current_degradation is None:
        latest_deg = db.query(DegradationLog).order_by(DegradationLog.timestamp.desc()).first()
        if latest_deg:
            log.current_degradation = latest_deg.degradation_pct
        else:
            latest_tel = db.query(TelemetryLog).order_by(TelemetryLog.timestamp.desc()).first()
            if latest_tel:
                log.current_degradation = latest_tel.degradation_pct

    db.add(log)
    
    # Reset unacknowledged cleaning alerts
    db.query(Alert).filter(Alert.alert_type == "CLEANING", Alert.acknowledged == False).update({"acknowledged": True})
    
    # Reset latest telemetry needs_cleaning flag
    latest = db.query(TelemetryLog).order_by(TelemetryLog.timestamp.desc()).first()
    if latest:
        latest.needs_cleaning = False
        latest.cleaning_conf = 0.0
        
        unread = db.query(Alert).filter(Alert.acknowledged == False).count()
        total = db.query(Alert).count()
        latest_deg = db.query(DegradationLog).order_by(DegradationLog.timestamp.desc()).first()
        
        # Broadcast the updated status live to the frontend immediately
        payload_dict = {
            "type": "telemetry",
            "source": "maintenance-reset",
            "timestamp": latest.timestamp.isoformat(),
            "light_intensity": latest.light_intensity,
            "temperature": latest.temperature,
            "humidity": latest.humidity,
            "voltage": latest.voltage,
            "current": latest.current,
            "power": latest.power,
            "energy": latest.energy,
            "needs_cleaning": False,
            "cleaning_conf": 0.0,
            "degradation_pct": latest_deg.degradation_pct if latest_deg else latest.degradation_pct,
            "unread_alerts": unread,
            "total_alerts": total
        }
        _sync_broadcast(payload_dict)

    db.commit()
    db.refresh(log)
    return log


@app.get("/api/maintenance", response_model=List[MaintenanceLogOut], tags=["Maintenance"])
def get_maintenance_logs(db: Session = Depends(get_db)):
    """Retrieve all panel maintenance logs, sorted newest-first."""
    return db.query(MaintenanceLog).order_by(MaintenanceLog.performed_at.desc()).all()


@app.delete("/api/maintenance/{log_id}", tags=["Maintenance"])
def delete_maintenance_log(log_id: int, db: Session = Depends(get_db)):
    """Delete a maintenance log entry."""
    log = db.query(MaintenanceLog).filter(MaintenanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Maintenance log not found.")
    db.delete(log)
    db.commit()
    return {"status": "deleted", "id": log_id}


# ─── Health Check ─────────────────────────────────────────────────────────────


@app.get("/api/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """API health check."""
    record_count = db.query(TelemetryLog).count()
    alert_count  = db.query(Alert).count()
    return {
        "status":         "ok",
        "models_loaded":  models_available(),
        "telemetry_rows": record_count,
        "alert_count":    alert_count,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
