"""
Smart Solar Plug — Telemetry Processor
Shared logic for processing incoming telemetry from both Firebase and MQTT.
"""

from datetime import datetime, timezone
from typing import Callable

# Callback registry — main.py registers WebSocket broadcast here
_on_new_data_callbacks: list[Callable] = []

def register_callback(fn: Callable):
    """Register a callback to be called when new telemetry arrives."""
    _on_new_data_callbacks.append(fn)

def process_telemetry(raw_data: dict, db_session_factory, ml_predict_cleaning, ml_predict_degradation):
    """
    Parse raw telemetry, run ML, persist to SQLite, fire callbacks.
    """
    import json
    from datetime import datetime
    from database import TelemetryLog, Alert, DegradationLog, SolarSettings

    try:
        env   = raw_data.get("environment", {}) or {}
        elec  = raw_data.get("electrical",  {}) or {}

        light_intensity = env.get("light_intensity")
        temperature     = env.get("temperature")
        humidity        = env.get("humidity")
        voltage         = elec.get("voltage")
        current         = elec.get("current")
        power           = elec.get("power")
        energy          = elec.get("energy")

        # Safe float conversion
        def _f(v):
            try: return float(v) if v is not None else None
            except: return None

        light_intensity = _f(light_intensity)
        temperature     = _f(temperature)
        humidity        = _f(humidity)
        voltage         = _f(voltage)
        current         = _f(current)
        power           = _f(power)
        energy          = _f(energy)

        # ── ADC Normalisation ────────────────────────────────────────
        # ESP32 sends light_intensity as a raw 12-bit ADC value (0–4095).
        # Normalise to a 0–100% scale so the rest of the pipeline
        # (ML inference, database, frontend) works unchanged.
        # If the value is already in 0–100 range (legacy percentage),
        # leave it as-is to avoid double-normalisation.
        if light_intensity is not None and light_intensity > 100:
            light_intensity = round((light_intensity / 4095.0) * 100.0, 2)

        now = datetime.now(timezone.utc)

        with db_session_factory() as session:
            # Fetch Solar Settings for ML logic
            settings = session.query(SolarSettings).first()
            panel_capacity_w = settings.panel_rating if settings else 300.0
            ldr_inverted = settings.ldr_inverted if settings else False

            # ML Predictions
            cleaning_result = None
            degradation_result = None

            if light_intensity is not None and temperature is not None and humidity is not None:
                cleaning_result   = ml_predict_cleaning(
                    light_intensity, temperature, humidity, power, voltage,
                    panel_capacity_w=panel_capacity_w, ldr_inverted=ldr_inverted
                )
                degradation_result = ml_predict_degradation(
                    light_intensity, temperature, humidity, power,
                    panel_capacity_w=panel_capacity_w, ldr_inverted=ldr_inverted
                )

            # Persist telemetry
            record = TelemetryLog(
                timestamp       = now,
                light_intensity = light_intensity,
                temperature     = temperature,
                humidity        = humidity,
                voltage         = voltage,
                current         = current,
                power           = power,
                energy          = energy,
                needs_cleaning  = cleaning_result["alert"]      if cleaning_result else None,
                cleaning_conf   = cleaning_result["confidence"] if cleaning_result else None,
                degradation_pct = degradation_result["degradation_pct"] if degradation_result else None,
            )
            session.add(record)

            # Create alert if cleaning needed
            if cleaning_result and cleaning_result["alert"]:
                alert = Alert(
                    timestamp  = now,
                    alert_type = "CLEANING",
                    severity   = cleaning_result["severity"],
                    message    = cleaning_result["reason"],
                    confidence = cleaning_result["confidence"],
                )
                session.add(alert)

            # Create degradation alert if critical/declining
            if degradation_result and degradation_result["trend"] in ("DECLINING", "CRITICAL"):
                deg_alert = Alert(
                    timestamp  = now,
                    alert_type = "DEGRADATION",
                    severity   = "CRITICAL" if degradation_result["trend"] == "CRITICAL" else "MEDIUM",
                    message    = degradation_result["message"],
                    confidence = None,
                )
                session.add(deg_alert)

                deg_log = DegradationLog(
                    timestamp       = now,
                    degradation_pct = degradation_result["degradation_pct"],
                    efficiency_ratio= degradation_result["efficiency_ratio"],
                    trend           = degradation_result["trend"],
                )
                session.add(deg_log)

            session.commit()

        # Build broadcast payload
        payload = {
            "type":             "telemetry",
            "timestamp":        now.isoformat(),
            "light_intensity":  light_intensity,
            "temperature":      temperature,
            "humidity":         humidity,
            "voltage":          voltage,
            "current":          current,
            "power":            power,
            "energy":           energy,
            "needs_cleaning":   cleaning_result["alert"]           if cleaning_result else None,
            "cleaning_conf":    cleaning_result["confidence"]      if cleaning_result else None,
            "cleaning_reason":  cleaning_result["reason"]          if cleaning_result else None,
            "degradation_pct":  degradation_result["degradation_pct"] if degradation_result else None,
            "degradation_trend":degradation_result["trend"]        if degradation_result else None,
        }

        with open("callbacks_log.txt", "a") as f:
            f.write(f"[{datetime.now()}] Callbacks count: {len(_on_new_data_callbacks)}\n")

        for cb in _on_new_data_callbacks:
            try:
                cb(payload)
            except Exception as e:
                print(f"[TelemetryProcessor] Callback error: {e}")

    except Exception as e:
        print(f"[TelemetryProcessor] Process error: {e}")
