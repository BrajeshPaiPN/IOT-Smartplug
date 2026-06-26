"""
Smart Solar Plug — ML Inference Module (v2)
============================================
Aligns with the v2 training script that uses AC_POWER (not DC_POWER)
and panel-capacity-agnostic normalization.

Sensor → Feature mapping:
  LDR (light_intensity %)   → normalized_irrad  = light_intensity / 100
  PZEM AC power (W)         → normalized_ac      = power / panel_capacity_w
  efficiency_ratio          = normalized_ac / (normalized_irrad * 0.80)
  DHT11 temperature (°C)    → AMBIENT_TEMPERATURE
  Module temp (estimated)   → MODULE_TEMPERATURE = ambient + irrad * 12
  temp_delta                = module_temp - ambient_temp
  hour                      = current local hour
"""

import os
import datetime
import joblib
import numpy as np
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent

CLEANING_MODEL_PATH         = Path(os.getenv("CLEANING_MODEL_PATH",    str(ROOT / "ml/models/cleaning_alert_model.pkl")))
DEGRADATION_MODEL_PATH      = Path(os.getenv("DEGRADATION_MODEL_PATH", str(ROOT / "ml/models/degradation_model.pkl")))
DEGRADATION_FEAT_COLS_PATH  = Path(os.getenv("DEGRADATION_FEATURE_COLS_PATH", str(ROOT / "ml/encoders/degradation_feature_cols.pkl")))

# Maximum solar irradiance (India) used during training normalization
MAX_IRRADIATION = 1.2   # kW/m²

# Globals loaded at startup
_cleaning_model    = None
_degradation_model = None
_degradation_cols  = None
_models_loaded     = False


def load_models():
    """Load both ML models from disk. Called once at app startup."""
    global _cleaning_model, _degradation_model, _degradation_cols, _models_loaded

    if _models_loaded:
        return

    errors = []

    # Cleaning alert model
    if CLEANING_MODEL_PATH.exists():
        try:
            _cleaning_model = joblib.load(CLEANING_MODEL_PATH)
            print(f"[ML] Cleaning model loaded: {CLEANING_MODEL_PATH.name}")
        except Exception as e:
            errors.append(f"Cleaning model load error: {e}")
    else:
        errors.append(f"Cleaning model not found at: {CLEANING_MODEL_PATH}")

    # Degradation model
    if DEGRADATION_MODEL_PATH.exists():
        try:
            _degradation_model = joblib.load(DEGRADATION_MODEL_PATH)
            print(f"[ML] Degradation model loaded: {DEGRADATION_MODEL_PATH.name}")
        except Exception as e:
            errors.append(f"Degradation model load error: {e}")
    else:
        errors.append(f"Degradation model not found at: {DEGRADATION_MODEL_PATH}")

    # Degradation feature columns
    if DEGRADATION_FEAT_COLS_PATH.exists():
        try:
            _degradation_cols = joblib.load(DEGRADATION_FEAT_COLS_PATH)
        except Exception as e:
            errors.append(f"Feature cols load error: {e}")

    if errors:
        for e in errors:
            print(f"[ML WARNING] {e}")
        print("[ML] Models not fully loaded — run training scripts first.")
    else:
        _models_loaded = True
        print("[ML] All models loaded successfully.")


def models_available() -> bool:
    return _cleaning_model is not None or _degradation_model is not None


def predict_cleaning_alert(
    light_intensity: float,      # LDR % (0–100), already ADC-normalized
    temperature: float,          # Ambient °C from DHT11
    humidity: float,             # % from DHT11
    power: Optional[float],      # AC Watts from PZEM-004T
    voltage: Optional[float],    # AC Volts from PZEM-004T
    panel_capacity_w: float = 300.0,   # User's panel watt-peak rating
    ldr_inverted: bool = False,        # True if high LDR value = low light
) -> dict:
    """
    Predict whether solar panel needs cleaning using the AC-power trained model.

    Feature vector (must match 02_train_cleaning_alert_model.py):
      [normalized_irrad, normalized_ac, efficiency_ratio,
       AMBIENT_TEMPERATURE, MODULE_TEMPERATURE, temp_delta, hour]
    """
    if _cleaning_model is None:
        return _rule_based_cleaning(light_intensity, temperature, humidity, power, panel_capacity_w)

    try:
        # ── 1. Handle LDR Inversion ─────────────────────────────────────────
        if ldr_inverted:
            light_intensity = 100.0 - light_intensity

        # ── 2. Normalize irradiance (LDR % / 100, same scale as training) ──
        normalized_irrad = max(min(light_intensity / 100.0, 1.0), 0.0)

        # ── 3. Normalize AC power by user's panel capacity ──────────────────
        if power is not None and panel_capacity_w > 0:
            normalized_ac = power / panel_capacity_w
        else:
            # Estimate: if no power reading, assume ~75% of irradiation-derived expected
            normalized_ac = normalized_irrad * 0.75

        # ── 4. Efficiency ratio = actual output / expected output at this light ──
        expected_normalized = normalized_irrad * 0.80
        efficiency_ratio = min(normalized_ac / (expected_normalized + 1e-6), 2.0)
        efficiency_ratio = max(efficiency_ratio, 0.0)

        # ── 5. Module temperature estimate ──────────────────────────────────
        module_temp = temperature + (normalized_irrad * 12.0)
        temp_delta  = module_temp - temperature

        # ── 6. Hour of day ──────────────────────────────────────────────────
        hour = datetime.datetime.now().hour

        X = np.array([[
            normalized_irrad,
            normalized_ac,
            efficiency_ratio,
            temperature,      # AMBIENT_TEMPERATURE
            module_temp,      # MODULE_TEMPERATURE
            temp_delta,
            hour,
        ]])

        prob  = _cleaning_model.predict_proba(X)[0][1]
        alert = bool(prob >= 0.5)

        # ── Severity + Human-readable reason ────────────────────────────────
        pct_efficient = efficiency_ratio * 100
        expected_w    = panel_capacity_w * normalized_irrad * 0.80
        actual_w      = power if power is not None else normalized_ac * panel_capacity_w

        if prob >= 0.80:
            severity = "CRITICAL"
            reason   = (
                f"Panel is severely underperforming: producing {actual_w:.0f}W "
                f"vs expected {expected_w:.0f}W (efficiency {pct_efficient:.0f}%) "
                f"under {normalized_irrad*100:.0f}% light intensity. Cleaning required."
            )
        elif prob >= 0.60:
            severity = "HIGH"
            reason   = (
                f"Significant dust accumulation suspected. Output is {actual_w:.0f}W "
                f"vs {expected_w:.0f}W expected at current light level."
            )
        elif prob >= 0.50:
            severity = "MEDIUM"
            reason   = "Moderate soiling suspected. Consider scheduling a cleaning."
        else:
            severity = "LOW"
            reason   = (
                f"Panel operating normally — efficiency {pct_efficient:.0f}% at "
                f"{normalized_irrad*100:.0f}% light intensity."
            )

        return {
            "alert":           alert,
            "confidence":      round(float(prob), 4),
            "severity":        severity,
            "reason":          reason,
            "efficiency_ratio": round(efficiency_ratio, 4),
            "normalized_irrad": round(normalized_irrad, 4),
        }

    except Exception as e:
        print(f"[ML] Cleaning prediction error: {e}")
        return _rule_based_cleaning(light_intensity, temperature, humidity, power, panel_capacity_w)


def _rule_based_cleaning(light_intensity, temperature, humidity, power, panel_capacity_w=300.0):
    """Rule-based fallback when model is not loaded."""
    normalized_irrad = light_intensity / 100.0
    expected_w = panel_capacity_w * normalized_irrad * 0.80

    if power is not None and expected_w > 0:
        efficiency = power / expected_w
        needs = (normalized_irrad > 0.4) and (efficiency < 0.78)
    else:
        needs = (light_intensity > 60) and (power is not None) and (power < panel_capacity_w * 0.3)

    severity = "MEDIUM" if needs and humidity > 70 else ("HIGH" if needs else "LOW")
    return {
        "alert":      needs,
        "confidence": 0.65 if needs else 0.30,
        "severity":   severity,
        "reason":     "Rule-based estimate (model not loaded). Run training script.",
        "efficiency_ratio": 0.0,
        "normalized_irrad": normalized_irrad,
    }


def predict_degradation(
    light_intensity: float,
    temperature: float,
    humidity: float,
    power: Optional[float],
    years_in_service: float = 0.0,
    month: int = 6,
    hour: int = 12,
    panel_capacity_w: float = 300.0,
    ldr_inverted: bool = False,
) -> dict:
    """
    Predict panel degradation percentage.
    Returns a dict with degradation_pct, efficiency_ratio, trend, message.
    """
    if _degradation_model is None:
        return _rule_based_degradation(years_in_service)

    try:
        # Handle LDR Inversion
        if ldr_inverted:
            light_intensity = 100.0 - light_intensity

        normalized_irrad = max(min(light_intensity / 100.0, 1.0), 0.0)
        
        # [NEW FIX] Inverter Offline Check
        if power is not None and power <= 2.0 and normalized_irrad > 0.1:
            return {
                "degradation_pct": 0.0,
                "efficiency_ratio": 0.0,
                "trend": "OFFLINE",
                "message": "Inverter appears to be offline. Power output is 0W despite adequate sunlight."
            }

        expected_power   = panel_capacity_w * normalized_irrad * 0.80
        efficiency_ratio = min((power / expected_power), 1.5) if (power is not None and expected_power > 0) else 0.85

        feat_map = {
            "irradiance":        normalized_irrad * MAX_IRRADIATION * 1000,  # back to W/m²
            "temperature":       temperature,
            "humidity":          humidity,
            "efficiency_ratio":  efficiency_ratio,
            "years_in_service":  years_in_service,
            "month":             month,
            "hour":              hour,
        }

        cols = _degradation_cols if _degradation_cols else list(feat_map.keys())
        X = np.array([[feat_map.get(c, 0.0) for c in cols]])

        deg_pct = float(np.clip(_degradation_model.predict(X)[0], 0, 100))

        if deg_pct < 5:
            trend   = "STABLE"
            message = f"Panel performance is excellent. Degradation: {deg_pct:.1f}%"
        elif deg_pct < 15:
            trend   = "DECLINING"
            message = f"Gradual degradation detected ({deg_pct:.1f}%). Monitor regularly."
        elif deg_pct < 30:
            trend   = "DECLINING"
            message = f"Significant degradation ({deg_pct:.1f}%). Schedule maintenance."
        else:
            trend   = "CRITICAL"
            message = f"Critical degradation ({deg_pct:.1f}%). Panel replacement recommended."

        return {
            "degradation_pct":  round(deg_pct, 2),
            "efficiency_ratio": round(efficiency_ratio, 4),
            "trend":            trend,
            "message":          message,
        }

    except Exception as e:
        print(f"[ML] Degradation prediction error: {e}")
        return _rule_based_degradation(years_in_service)


def _rule_based_degradation(years_in_service):
    """Simple rule-based degradation fallback."""
    deg = min(years_in_service * 0.6, 30.0)
    trend = "STABLE" if deg < 5 else "DECLINING" if deg < 20 else "CRITICAL"
    return {
        "degradation_pct":  round(deg, 2),
        "efficiency_ratio": round(1 - deg / 100, 4),
        "trend":            trend,
        "message":          f"Rule-based estimate: {deg:.1f}% after {years_in_service:.1f} years.",
    }
