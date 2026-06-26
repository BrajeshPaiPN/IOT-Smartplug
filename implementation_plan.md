# Smart Solar Plug — Feature Expansion Plan (ROI Simulator & Maintenance Logs)

This plan details the implementation of two new advanced features to expand the smart solar plug dashboard:
1. **Interactive Solar ROI & Upgrade Simulator**: A dynamic, client-side simulation card with range sliders and an interactive Chart.js line chart comparing cumulative savings of the current system vs. a simulated upgraded system over 10 years.
2. **Panel Maintenance Logs & Cleaning History**: An SQLite-backed maintenance tracker that allows logging panel cleaning events. It automatically dismisses cleaning alerts and displays maintenance events as distinct markers (scatter points) on the live degradation trend chart.

---

## User Review Required

> [!IMPORTANT]
> The database schema will be updated with a new `maintenance_logs` table. FastAPI will automatically handle table creation at startup using SQLAlchemy.
> All calculations, including degradation compounding and inflation projections, will be computed live on the client side based on database records.

---

## Proposed Changes

### Component 1 — Database & Backend API

#### [MODIFY] [database.py](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/backend/database.py)
- Create a new SQLAlchemy ORM model `MaintenanceLog` to store panel cleaning records:
  - `id` (Integer, primary key, indexed)
  - `timestamp` (DateTime, default utcnow)
  - `performed_at` (DateTime, input by user)
  - `notes` (Text, user comments)
  - `current_degradation` (Float, degradation pct recorded at the time of cleaning)

#### [MODIFY] [schemas.py](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/backend/schemas.py)
- Add Pydantic schemas for the maintenance logs:
  - `MaintenanceLogIn`: validated payload (`performed_at`, `notes`, `current_degradation`)
  - `MaintenanceLogOut`: full database response model including auto-generated fields

#### [MODIFY] [main.py](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/backend/main.py)
- Add new endpoints for maintenance operations:
  - `POST /api/maintenance`: Create a maintenance log. When saved, it will also query the latest `TelemetryLog` record and reset `needs_cleaning` to `False`, and acknowledge any unread `CLEANING` alerts.
  - `GET /api/maintenance`: Retrieve a list of all maintenance logs, sorted newest-first.
  - `DELETE /api/maintenance/{log_id}`: Delete a maintenance log.

---

### Component 2 — Frontend Layout

#### [MODIFY] [index.html](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/frontend/index.html)
- **ROI Simulator Layout**: Add a new grid section under the dashboard view containing:
  - An **ROI Upgrade Simulator Controls** card:
    - Slider for "Simulate Panel Upgrade (+Watts)" (0W to 5000W, step 100W)
    - Slider for "Annual Tariff Inflation Rate (%)" (0% to 20%, step 1%)
    - Input for "Upgrade Cost" (numeric field, default 0)
    - Interactive KPIs: "Simulated Combined Capacity (W)", "Simulated Payback (yrs)", and "Additional 10-Yr Savings"
  - An **ROI Projection Chart** card containing a `<canvas id="simulationChart">` to render the 10-year cumulative savings projection.
- **Maintenance Logger Layout**: Add a new card in the **Degradation View** (`view-degradation`):
  - Form: "Log Cleaning Activity" (inputs: Date, Notes)
  - Timeline: Timeline table displaying recent cleanings with Notes, Date, and a "Delete" button.

---

### Component 3 — Frontend Logic (Charts & Simulation)

#### [MODIFY] [js/charts.js](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/frontend/js/charts.js)
- **Simulation Chart**: Add an `initSimulationChart()` function to draw a line chart for current vs. simulated savings. Implement a function to update its datasets (`currentPath` and `upgradedPath`) dynamically.
- **Maintenance Markers**: Modify `populateDegradationChart(records)` (or add a companion function) to accept the list of maintenance logs, and add a second scatter dataset `Maintenance Events` to the degradation chart. This will plot green star points at each cleaning event timestamp.

#### [MODIFY] [js/app.js](file:///c:/Users/Brajesh%20Pai%20P.N/Desktop/IOT-smart%20solar%20plug/frontend/js/app.js)
- **ROI Upgrade Simulation Math**:
  - Implement a simulator recalculation function:
    - Annual output for current system: base panel rating, degradation compounding over 10 years, and current electricity rate.
    - Annual output for upgraded system: combined panel rating, upgraded installation cost, and electricity rate compounded annually by the tariff inflation rate.
    - Plot both savings curves over a 10-year horizon.
  - Bind event listeners (`input` and `change`) on the sliders to trigger real-time updates.
- **Maintenance Log Actions**:
  - Load logged cleanings via `GET /api/maintenance` on startup and view changes.
  - Submit cleaning logs via `POST /api/maintenance`, which refreshes the alerts list and degradation chart markers.
  - Handle deleting logs via `DELETE /api/maintenance/{id}`.

---

## Verification Plan

### Automated Tests
- Verify the maintenance endpoints:
  - Create a test log:
    `curl -X POST -H "Content-Type: application/json" -d "{\"notes\":\"Hand scrubbed panel\",\"performed_at\":\"2026-06-24T12:00:00\"}" http://localhost:8000/api/maintenance`
  - Get logs:
    `curl http://localhost:8000/api/maintenance`

### Manual Verification
1. Login to the dashboard, scroll down to the new **Interactive ROI Upgrade Simulator**.
2. Drag the panel upgrade slider to `1000W`, set inflation rate to `5%`, and set upgrade cost to `40000`.
3. Verify that the 10-year savings line chart updates smoothly in real-time, and payback updates.
4. Go to the **Degradation View**, log a cleaning event with a note: "Heavy rain cleaning".
5. Verify that:
   - The log is successfully added to the timeline.
   - A green marker appears on the degradation line chart at the current time.
   - Any active cleaning alert is dismissed/cleared.
