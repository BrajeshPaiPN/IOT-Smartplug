"""
Smart Solar Plug — Model 2: Degradation Estimator
Uses: Kerala Solar Power Dataset 2019–2024 (5-year longitudinal data)

Algorithm : XGBoost Regressor
Target    : degradation_pct  (0..100 — % performance degraded from baseline)

Degradation logic:
  - Baseline efficiency = 95th percentile power yield for given irradiance band in Year 1
  - degradation_pct = 100 * (1 - current_efficiency / baseline_efficiency)
  - Clipped to [0, 100]
"""

import os
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline

try:
    import xgboost as xgb
except ImportError:
    print("[ERROR] xgboost not installed. Run: pip install xgboost")
    sys.exit(1)

warnings.filterwarnings("ignore")

ROOT      = Path(__file__).parent.parent
TEST_DIR  = ROOT / "data" / "testing"
MODEL_DIR = Path(__file__).parent / "models"
ENC_DIR   = Path(__file__).parent / "encoders"
MODEL_DIR.mkdir(exist_ok=True)
ENC_DIR.mkdir(exist_ok=True)


def find_kerala_csv():
    """Find the main Kerala dataset CSV."""
    csvs = sorted(TEST_DIR.glob("*.csv"))
    if not csvs:
        return None
    # Prefer files with 'solar' or 'power' in name
    for csv in csvs:
        if any(kw in csv.name.lower() for kw in ["solar", "power", "kerala"]):
            return csv
    return csvs[0]


def load_kerala_data(csv_path: Path) -> pd.DataFrame:
    """Load and normalise the Kerala dataset."""
    print(f"[+] Loading Kerala dataset: {csv_path.name}")
    df = pd.read_csv(csv_path)
    print(f"    Shape: {df.shape}")
    print(f"    Columns: {list(df.columns)}")

    # --- Normalise column names ---
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Map common Kerala dataset column names to our standard
    rename_map = {}
    col_lower = {c.lower(): c for c in df.columns}

    possible_date  = ["date", "datetime", "time", "date_time", "timestamp"]
    possible_irrad = ["irradiance", "solar_irradiance", "ghi", "irradiation", "solar_radiation"]
    possible_temp  = ["temperature", "ambient_temperature", "temp", "air_temperature"]
    possible_hum   = ["humidity", "relative_humidity", "rh"]
    possible_yield = ["total_yield", "yield", "power_output", "energy", "kwh", "ac_power", "generation"]

    def find_col(candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    date_col  = find_col(possible_date)
    irrad_col = find_col(possible_irrad)
    temp_col  = find_col(possible_temp)
    hum_col   = find_col(possible_hum)
    yield_col = find_col(possible_yield)

    if date_col:
        try:
            df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
            df = df.rename(columns={date_col: "datetime"})
        except Exception:
            pass

    if irrad_col and irrad_col != "irradiance":
        df = df.rename(columns={irrad_col: "irradiance"})
    if temp_col and temp_col != "temperature":
        df = df.rename(columns={temp_col: "temperature"})
    if hum_col and hum_col != "humidity":
        df = df.rename(columns={hum_col: "humidity"})
    if yield_col and yield_col != "total_yield":
        df = df.rename(columns={yield_col: "total_yield"})

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature engineer and compute degradation_pct from 5-year trend."""
    required_cols = {"datetime", "irradiance", "total_yield"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"[WARNING] Missing columns: {missing}")
        print("  Attempting to use available numeric columns as proxies...")

        # If no date, create synthetic index
        if "datetime" not in df.columns:
            df["datetime"] = pd.date_range("2019-01-01", periods=len(df), freq="h")

        # Use first numeric column as irradiance proxy
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if "irradiance" not in df.columns and num_cols:
            df["irradiance"] = df[num_cols[0]]
        if "total_yield" not in df.columns and len(num_cols) > 1:
            df["total_yield"] = df[num_cols[-1]]

    # Drop nulls in critical columns
    df = df.dropna(subset=["irradiance", "total_yield"])
    df = df[df["irradiance"] > 0]
    df = df[df["total_yield"] >= 0]
    
    # [NEW FIX] Outlier Filter: If irradiance is high but power is 0, the inverter is likely offline/tripped.
    # We must exclude these from degradation calculations otherwise the model learns that "high light + 0 power = 100% degradation"
    offline_mask = (df["irradiance"] > 50) & (df["total_yield"] <= 0.5)
    df = df[~offline_mask]

    # Extract year for baseline calculation
    if "datetime" in df.columns:
        df["year"]  = pd.to_datetime(df["datetime"], errors="coerce").dt.year
        df["month"] = pd.to_datetime(df["datetime"], errors="coerce").dt.month
        df["hour"]  = pd.to_datetime(df["datetime"], errors="coerce").dt.hour
    else:
        df["year"]  = 2019
        df["month"] = 1
        df["hour"]  = 12

    df["years_in_service"] = df["year"] - df["year"].min()

    # Irradiance bands
    df["irrad_band"] = pd.cut(df["irradiance"], bins=8, labels=False)

    # Baseline: 95th percentile yield for each irradiance band in Year 1
    year1 = df["year"].min()
    baseline = (
        df[df["year"] == year1]
        .groupby("irrad_band", observed=True)["total_yield"]
        .quantile(0.95)
        .rename("baseline_yield")
    )
    df = df.merge(baseline, on="irrad_band", how="left")

    # Fill missing baselines with median
    df["baseline_yield"] = df["baseline_yield"].fillna(df["total_yield"].median())

    # Efficiency ratio and degradation
    df["efficiency_ratio"] = (df["total_yield"] / (df["baseline_yield"] + 1e-6)).clip(0, 1.5)
    df["degradation_pct"]  = (100 * (1 - df["efficiency_ratio"])).clip(0, 100)

    # Additional features
    if "temperature" not in df.columns:
        df["temperature"] = 28.0  # default ambient if not available
    if "humidity" not in df.columns:
        df["humidity"] = 60.0

    print(f"[+] Degradation stats:")
    print(f"    Mean  : {df['degradation_pct'].mean():.2f}%")
    print(f"    Median: {df['degradation_pct'].median():.2f}%")
    print(f"    Max   : {df['degradation_pct'].max():.2f}%")

    return df


def build_features(df: pd.DataFrame):
    feature_cols = [
        "irradiance",
        "temperature",
        "humidity",
        "efficiency_ratio",
        "years_in_service",
        "month",
        "hour",
    ]
    # Use only columns that exist
    feature_cols = [c for c in feature_cols if c in df.columns]
    X = df[feature_cols].fillna(df[feature_cols].median())
    y = df["degradation_pct"]
    return X, y, feature_cols


def train_xgb(X_train, y_train):
    print("[+] Training XGBoost Regressor...")
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )

    # Wrap in scaler pipeline
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("xgb",   model),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def evaluate_model(model, X_test, y_test, feature_cols):
    y_pred = model.predict(X_test)
    y_pred = np.clip(y_pred, 0, 100)

    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    mae  = mean_absolute_error(y_test, y_pred)
    r2   = r2_score(y_test, y_pred)

    print("\n" + "="*60)
    print("  DEGRADATION MODEL — EVALUATION (Kerala Hold-out Test)")
    print("="*60)
    print(f"  RMSE : {rmse:.4f}%")
    print(f"  MAE  : {mae:.4f}%")
    print(f"  R²   : {r2:.4f}")

    # Feature importances (XGBoost)
    xgb_step = model.named_steps["xgb"]
    importances = xgb_step.feature_importances_
    fi_df = pd.DataFrame({"feature": feature_cols, "importance": importances})
    fi_df = fi_df.sort_values("importance", ascending=False)
    print("\n  FEATURE IMPORTANCES:")
    print(fi_df.to_string(index=False))
    return r2


def main():
    print("=" * 60)
    print("  DEGRADATION MODEL — Training (Kerala 5-Year Dataset)")
    print("=" * 60)

    csv_path = find_kerala_csv()
    if csv_path is None:
        print(f"[ERROR] No CSV found in {TEST_DIR}")
        print("  Run: python ml/01_download_data.py  first")
        sys.exit(1)

    df = load_kerala_data(csv_path)
    df = engineer_features(df)
    X, y, feature_cols = build_features(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    print(f"[+] Train: {len(X_train):,}  |  Test: {len(X_test):,}")

    model = train_xgb(X_train, y_train)
    r2 = evaluate_model(model, X_test, y_test, feature_cols)

    # Save
    model_path  = MODEL_DIR / "degradation_model.pkl"
    scaler_path = ENC_DIR   / "degradation_feature_cols.pkl"
    joblib.dump(model,        model_path)
    joblib.dump(feature_cols, scaler_path)

    print(f"\n[SUCCESS] Model saved : {model_path}")
    print(f"[SUCCESS] Feat cols   : {scaler_path}")

    if r2 < 0.5:
        print("\n[WARNING] R2 < 0.5 — consider using more data or feature tuning.")
    else:
        print(f"\n[SUCCESS] Degradation model trained successfully (R2={r2:.3f})")

    print("    Next step: cd backend && uvicorn main:app --reload")


if __name__ == "__main__":
    main()
