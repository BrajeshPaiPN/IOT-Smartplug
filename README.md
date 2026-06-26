# ☀️ Smart Solar Plug — Full Stack IoT + ML Monitoring System

A complete end-to-end system for monitoring a solar panel via ESP32, uploading live telemetry to Firebase RTDB, running ML-based **cleaning alerts** and **degradation analysis**, and displaying results on a professional web dashboard.

---

## 🏗️ Architecture

```
ESP32 (Arduino)
    │  Firebase RTDB (sensor push every 5s)
    ▼
FastAPI Backend ◄──► SQLite Database
    │                    ├─ telemetry_log
    │ ML Models           ├─ alerts
    │  ├─ Cleaning Alert  └─ degradation_log
    │  └─ Degradation
    ▼
Frontend (HTML/CSS/JS)
    ├─ 📊 Live Dashboard (WebSocket + Firebase)
    ├─ 📈 Historical Charts
    ├─ 🔔 Alert Center
    ├─ 📉 Degradation Timeline
    └─ 📄 PDF / CSV Reports
```

---

## 📁 Project Structure

```
IOT-smart solar plug/
├── firebase admin key/      ← Firebase service account JSON
├── data/
│   ├── training/            ← India solar plant dataset (anikannal)
│   └── testing/             ← Kerala 5-year dataset (biswajitdas)
├── ml/
│   ├── 01_download_data.py  ← Kaggle API downloader
│   ├── 02_train_cleaning_alert_model.py  ← Random Forest
│   ├── 03_train_degradation_model.py     ← XGBoost
│   ├── models/              ← Saved .pkl model files
│   └── encoders/            ← Saved feature column lists
├── backend/
│   ├── main.py              ← FastAPI app
│   ├── database.py          ← SQLite + SQLAlchemy
│   ├── schemas.py           ← Pydantic models
│   ├── firebase_listener.py ← RTDB background thread
│   ├── ml_inference.py      ← Model loader & predictor
│   ├── report_generator.py  ← PDF + CSV reports
│   ├── requirements.txt
│   └── .env                 ← Environment config
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/
        ├── app.js           ← Main SPA logic
        ├── charts.js        ← Chart.js visualizations
        ├── firebase.js      ← Firebase + WebSocket connection
        └── reports.js       ← Report download handler
```

---

## ⚡ Setup Guide

### Step 1 — Python Environment

```powershell
cd "IOT-smart solar plug"
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt
```

### Step 2 — Download Real Datasets

**Option A: Kaggle API (automated)**
1. Go to https://www.kaggle.com → Account → API → Create Token
2. Place `kaggle.json` at `C:\Users\<you>\.kaggle\kaggle.json`
3. Run:
```powershell
python ml/01_download_data.py
```

**Option B: Manual download**
1. **Training data** → https://www.kaggle.com/datasets/anikannal/solar-power-generation-data
   - Download ZIP → extract `Plant_1_Generation_Data.csv` + `Plant_1_Weather_Sensor_Data.csv` → place in `data/training/`

2. **Testing data** → https://www.kaggle.com/datasets/biswajitdas/solar-power-dataset-kerala-2019-to-2024
   - Download ZIP → extract CSV(s) → place in `data/testing/`

### Step 3 — Train ML Models

```powershell
python ml/02_train_cleaning_alert_model.py   # ~2 minutes
python ml/03_train_degradation_model.py      # ~1 minute
```

Expected output:
- `ml/models/cleaning_alert_model.pkl`
- `ml/models/degradation_model.pkl`
- `ml/encoders/degradation_feature_cols.pkl`

### Step 4 — Start Backend

```powershell
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

### Step 5 — Open Frontend

Open `frontend/index.html` in your browser (or use VS Code Live Server).

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/telemetry/live` | Latest sensor reading |
| GET | `/api/telemetry/history?hours=24` | Historical data |
| GET | `/api/dashboard/stats` | KPI summary |
| GET | `/api/alerts` | All alerts |
| POST | `/api/alerts/acknowledge/{id}` | Mark alert read |
| POST | `/api/alerts/acknowledge-all` | Mark all read |
| GET | `/api/degradation` | Degradation history |
| GET | `/api/report/csv` | Download CSV |
| GET | `/api/report/pdf` | Download PDF |
| GET | `/api/health` | System health check |
| WS | `/ws/live` | Real-time WebSocket push |

---

## 🤖 ML Models

### Model 1 — Cleaning Alert (Random Forest)
- **Dataset**: India Solar Plant 2020 (anikannal) — 34 days, ~68K rows
- **Target**: `needs_cleaning` (1 = panel dirty, 0 = clean)
- **Logic**: Panel labelled as dirty when irradiance > 400 W/m² but power output < 78% of expected
- **Features**: Irradiance, ambient temperature, module temperature, temp delta, power ratio, hour

### Model 2 — Degradation Estimator (XGBoost)
- **Dataset**: Kerala Solar Power 2019–2024 (biswajitdas) — 5 years of data
- **Target**: `degradation_pct` (0–100%)
- **Logic**: Efficiency ratio vs. Year-1 baseline converted to degradation percentage
- **Features**: Irradiance, temperature, humidity, efficiency ratio, years in service, month, hour

---

## 📊 ESP32 Sensor Mapping

| Sensor | Firebase Path | Model Feature |
|--------|--------------|---------------|
| LDR (34) | `/telemetry/environment/light_intensity` | Irradiance proxy |
| DHT11 Temp (4) | `/telemetry/environment/temperature` | Ambient temperature |
| DHT11 Humidity | `/telemetry/environment/humidity` | Humidity |
| PZEM-004T Voltage | `/telemetry/electrical/voltage` | — |
| PZEM-004T Current | `/telemetry/electrical/current` | — |
| PZEM-004T Power | `/telemetry/electrical/power` | Power ratio input |
| PZEM-004T Energy | `/telemetry/electrical/energy` | — |

---

## 🚀 Technologies

- **IoT**: ESP32 + DHT11 + LDR + PZEM-004T + Firebase RTDB
- **ML**: scikit-learn (Random Forest), XGBoost — trained on real Kaggle datasets
- **Backend**: FastAPI + SQLAlchemy + SQLite + firebase-admin SDK
- **Reports**: reportlab (PDF) + pandas (CSV)
- **Frontend**: Vanilla HTML/CSS/JS + Chart.js + Firebase JS SDK
- **Real-time**: WebSocket (FastAPI) + Firebase RTDB
