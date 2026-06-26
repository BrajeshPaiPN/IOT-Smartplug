"""
Smart Solar Plug — Model 1: Cleaning Alert Classifier (v2 — AC Power)
=======================================================================
Dataset : Plant_1 + Plant_2 real India solar plant data (authentic, no synthetic)
         Each plant has 22 inverters, each ~1400W AC output — matching the
         scale of a residential/small-commercial system measured by PZEM-004T.

Why AC_POWER (not DC_POWER):
  - Our IoT device uses PZEM-004T which measures AC power (post-inverter)
  - AC_POWER from dataset directly reflects what our sensor measures
  - DC_POWER is the pre-inverter input — our sensor NEVER sees this value

Algorithm : GradientBoostingClassifier (better than RF for tabular data)
Target    : needs_cleaning (1 = panel needs cleaning, 0 = clean)

Cleaning Logic (physics-based labelling from real data):
  A panel needs cleaning when:
  - Good sunlight is available (IRRADIATION > 0.4 kW/m²)
  - BUT actual AC output is less than 78% of what that irradiation SHOULD
    produce for that inverter's capacity (efficiency_ratio < 0.78)
  This mismatch = soiling/dust reducing performance.

Normalization approach:
  - normalized_ac: AC_POWER / inverter_peak_capacity (per SOURCE_KEY)
    This makes the model panel-size-agnostic. A 300W home panel and a
    1400W inverter will both output ~0.0 when dirty under good sun.
  - normalized_irrad: IRRADIATION / 1.2  (max physical irradiation kW/m²)
  - efficiency_ratio = normalized_ac / normalized_irrad * 0.8 (system efficiency)

Key insight for LDR mapping:
  normalized_irrad (0-1) ≡ normalized LDR light intensity (0-1)
  So inference maps: (light_intensity% / 100) → normalized_irrad
"""

import os
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, f1_score
)
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

ROOT       = Path(__file__).parent.parent
TRAIN_DIR  = ROOT / "data" / "training"
MODEL_DIR  = Path(__file__).parent / "models"
ENC_DIR    = Path(__file__).parent / "encoders"
MODEL_DIR.mkdir(exist_ok=True)
ENC_DIR.mkdir(exist_ok=True)

# Both authentic plant datasets (same Kaggle download, no synthetic data)
GEN_FILE_1     = TRAIN_DIR / "Plant_1_Generation_Data.csv"
WEATHER_FILE_1 = TRAIN_DIR / "Plant_1_Weather_Sensor_Data.csv"
GEN_FILE_2     = TRAIN_DIR / "Plant_2_Generation_Data.csv"
WEATHER_FILE_2 = TRAIN_DIR / "Plant_2_Weather_Sensor_Data.csv"

# Physics-based thresholds (from soiling literature)
IRRADIATION_THRESHOLD  = 0.4    # kW/m² minimum "good sun" for reliable prediction
EFFICIENCY_THRESHOLD   = 0.78   # below = underperforming (soiling suspected)
MAX_IRRADIATION        = 1.2    # kW/m² — theoretical max for India (used for normalization)


def load_plant(gen_file: Path, weather_file: Path, plant_name: str) -> pd.DataFrame:
    """Load and merge one plant's generation + weather CSVs."""
    print(f"\n[+] Loading {plant_name}...")
    gen = pd.read_csv(gen_file)
    gen["DATE_TIME"] = pd.to_datetime(gen["DATE_TIME"], dayfirst=False)

    weather = pd.read_csv(weather_file)
    weather["DATE_TIME"] = pd.to_datetime(weather["DATE_TIME"], dayfirst=False)

    # Compute per-inverter AC peak capacity from real observed data
    inverter_peak = gen.groupby("SOURCE_KEY")["AC_POWER"].max().rename("inverter_peak_w")
    gen = gen.join(inverter_peak, on="SOURCE_KEY")

    df = pd.merge(
        gen[["DATE_TIME", "SOURCE_KEY", "AC_POWER", "inverter_peak_w", "DAILY_YIELD"]],
        weather[["DATE_TIME", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE", "IRRADIATION"]],
        on="DATE_TIME", how="inner"
    )
    df["plant"] = plant_name
    print(f"    Rows loaded: {len(df):,} | Inverters: {gen['SOURCE_KEY'].nunique()}")
    return df


def feature_engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Apply physics-based feature engineering using AC_POWER."""
    # Drop night-time / zero-irradiation rows
    df = df.dropna(subset=["IRRADIATION", "AC_POWER", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE"])
    df = df[df["IRRADIATION"] > 0]
    df = df[df["AC_POWER"] >= 0]
    df = df[df["inverter_peak_w"] > 0]

    # ── Core Features ──────────────────────────────────────────────────────
    # 1. Normalized AC output: actual AC output / inverter's observed peak
    #    This makes ANY panel size comparable (home 300W or commercial 1400W)
    df["normalized_ac"] = df["AC_POWER"] / df["inverter_peak_w"]

    # 2. Normalized irradiance (0–1 scale matching LDR 0–100% / 100)
    df["normalized_irrad"] = (df["IRRADIATION"] / MAX_IRRADIATION).clip(0, 1)

    # 3. Efficiency ratio: how much AC power is produced per unit of available light
    #    Expected: ~80% system efficiency (STC condition)
    #    efficiency_ratio = (actual normalized output) / (expected output at this irradiance)
    expected_normalized = df["normalized_irrad"] * 0.80
    df["efficiency_ratio"] = df["normalized_ac"] / (expected_normalized + 1e-6)
    df["efficiency_ratio"] = df["efficiency_ratio"].clip(0, 2.0)

    # 4. Temperature delta: module heating above ambient (higher = more dust trapping heat)
    df["temp_delta"] = df["MODULE_TEMPERATURE"] - df["AMBIENT_TEMPERATURE"]

    # 5. Hour of day (solar angle proxy — midday irradiance behaves differently)
    df["hour"] = df["DATE_TIME"].dt.hour

    # ── Physics-Based Labelling ─────────────────────────────────────────────
    # needs_cleaning = 1 when: good light available AND efficiency is low
    df["needs_cleaning"] = (
        (df["IRRADIATION"] > IRRADIATION_THRESHOLD) &
        (df["efficiency_ratio"] < EFFICIENCY_THRESHOLD)
    ).astype(int)

    return df


def load_and_prepare_all() -> pd.DataFrame:
    """Load both authentic plants, engineer features, and combine."""
    df1 = load_plant(GEN_FILE_1, WEATHER_FILE_1, "Plant_1")
    df2 = load_plant(GEN_FILE_2, WEATHER_FILE_2, "Plant_2")

    combined = pd.concat([df1, df2], ignore_index=True)
    print(f"\n[+] Total rows before feature engineering: {len(combined):,}")

    combined = feature_engineer(combined)
    print(f"[+] Total rows after cleaning: {len(combined):,}")

    print(f"\n[+] Class distribution:")
    print(combined["needs_cleaning"].value_counts())
    print(f"    Cleaning-needed ratio: {combined['needs_cleaning'].mean()*100:.1f}%")

    return combined


def build_features(df: pd.DataFrame):
    """Select final feature columns for model training."""
    feature_cols = [
        "normalized_irrad",    # Normalized irradiance = normalized LDR (key feature!)
        "normalized_ac",       # Actual normalized AC output (maps to PZEM-004T reading)
        "efficiency_ratio",    # Core signal: how efficient is the panel right now
        "AMBIENT_TEMPERATURE", # Ambient temp (DHT11 sensor)
        "MODULE_TEMPERATURE",  # Module surface temp (proxy for heating)
        "temp_delta",          # Module − ambient (dust trapping heat indicator)
        "hour",                # Time of day (avoid false positives at dawn/dusk)
    ]
    X = df[feature_cols].copy()
    y = df["needs_cleaning"].copy()
    return X, y, feature_cols


def train_model(X_train: pd.DataFrame, y_train: pd.Series, feature_cols: list):
    """Train GradientBoostingClassifier — handles imbalanced classes and
    non-linear relationships better than RandomForest for efficiency metrics."""
    print("\n[+] Training GradientBoostingClassifier...")

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("gb", GradientBoostingClassifier(
            n_estimators=300,
            learning_rate=0.08,
            max_depth=6,
            min_samples_leaf=20,
            subsample=0.85,
            max_features="sqrt",
            random_state=42,
        )),
    ])

    # Cross-validation before final fit
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_roc = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"    CV ROC-AUC: {cv_roc.mean():.4f} ± {cv_roc.std():.4f}")

    pipeline.fit(X_train, y_train)
    return pipeline


def evaluate_model(model, X_test, y_test, feature_cols):
    """Evaluate model and print metrics."""
    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print("\n" + "="*60)
    print("  CLASSIFICATION REPORT (AC Power — Panel-Agnostic Model)")
    print("="*60)
    print(classification_report(y_test, y_pred, target_names=["Clean", "Needs Cleaning"]))
    print(f"  ROC-AUC : {roc_auc_score(y_test, y_proba):.4f}")
    print(f"  F1      : {f1_score(y_test, y_pred):.4f}")

    # Feature importances
    gb_step = model.named_steps["gb"]
    fi = pd.DataFrame({
        "feature": feature_cols,
        "importance": gb_step.feature_importances_
    }).sort_values("importance", ascending=False)
    print("\n  FEATURE IMPORTANCES:")
    print(fi.to_string(index=False))

    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  Confusion Matrix (rows=Actual, cols=Predicted):\n{cm}")
    print(f"  False Positives (unnecessary cleaning alerts): {cm[0,1]}")
    print(f"  False Negatives (missed cleaning alerts):      {cm[1,0]}")


def save_artifacts(model, feature_cols):
    """Save model pipeline and feature column names."""
    model_path = MODEL_DIR / "cleaning_alert_model.pkl"
    cols_path  = ENC_DIR  / "cleaning_feature_cols.pkl"
    joblib.dump(model, model_path)
    joblib.dump(feature_cols, cols_path)
    print(f"\n[SUCCESS] Model saved  : {model_path}")
    print(f"[SUCCESS] Feature cols : {cols_path}")


def main():
    print("=" * 60)
    print("  CLEANING ALERT MODEL v2 — AC Power, Panel-Agnostic")
    print("=" * 60)

    for f in [GEN_FILE_1, WEATHER_FILE_1, GEN_FILE_2, WEATHER_FILE_2]:
        if not f.exists():
            print(f"[ERROR] Missing: {f}")
            print("  Run: python ml/01_download_data.py  first")
            sys.exit(1)

    df = load_and_prepare_all()
    X, y, feature_cols = build_features(df)

    # Stratified split — 80% train, 20% test
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"\n[+] Train: {len(X_train):,}  |  Test: {len(X_test):,}")
    print(f"[+] Features: {feature_cols}")

    model = train_model(X_train, y_train, feature_cols)
    evaluate_model(model, X_test, y_test, feature_cols)
    save_artifacts(model, feature_cols)

    print("\n[SUCCESS] Cleaning alert model training complete!")
    print("    Next step: python ml/03_train_degradation_model.py")


if __name__ == "__main__":
    main()
