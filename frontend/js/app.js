/**
 * Smart Solar Plug — Main Application Logic (SPA Routing, Auth & ROI calculations)
 */

const API = "http://localhost:8000";

let currentUser = null;
let authMode = "LOGIN"; // LOGIN or REGISTER

// Solar Settings (persisted in SQLite, defaults loaded at startup)
let solarSettings = {
  panel_rating:      300.0,
  electricity_cost:  7.0,
  installation_cost: 25000.0,
  sunlight_hours:    4.5,
};

// State variables
let _lastCleaningState = null;
let historyHours = 24;
let historyLoaded = false;
let alertsData = [];
let alertFilter = "ALL";

// ── SPA Routing ──────────────────────────────────────────────────────────────
function showView(viewId) {
  // If not logged in, enforce login view
  if (!currentUser) {
    viewId = "view-login";
  }

  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));

  const view = document.getElementById(viewId);
  const link = document.querySelector(`[data-view="${viewId}"]`);
  if (view) view.classList.add("active");
  if (link) link.classList.add("active");

  // Load data depending on the view
  switch(viewId) {
    case "view-dashboard":  loadDashboardStats().then(() => { if (typeof runRoiSimulation === "function") runRoiSimulation(); }); break;
    case "view-history":    loadHistoryData(); break;
    case "view-alerts":     loadAlerts();      break;
    case "view-degradation":loadDegradation(); break;
    case "view-reports":    initReportDateDefaults(); break;
  }
}

// ── Authentication Management ─────────────────────────────────────────────────
function toggleAuthMode() {
  const title = document.querySelector("#view-login h2");
  const subtitle = document.getElementById("loginSubtitle");
  const submitBtn = document.getElementById("authSubmitBtn");
  const toggleText = document.getElementById("toggleAuthModeText");
  const errorMsg = document.getElementById("authErrorMessage");

  errorMsg.style.display = "none";

  if (authMode === "LOGIN") {
    authMode = "REGISTER";
    title.textContent = "Create Account";
    subtitle.textContent = "Sign up to track and optimize your solar plug parameters";
    submitBtn.textContent = "Register";
    toggleText.innerHTML = `Already have an account? <a href="javascript:void(0)" onclick="toggleAuthMode()" style="color: #2563EB; font-weight: 500; text-decoration: none;">Sign in here</a>`;
  } else {
    authMode = "LOGIN";
    title.textContent = "Smart Solar Plug";
    subtitle.textContent = "Sign in to monitor your solar energy generation";
    submitBtn.textContent = "Sign In";
    toggleText.innerHTML = `Don't have an account? <a href="javascript:void(0)" onclick="toggleAuthMode()" style="color: #2563EB; font-weight: 500; text-decoration: none;">Register here</a>`;
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const email = document.getElementById("authEmail").value;
  const password = document.getElementById("authPassword").value;
  const errorMsg = document.getElementById("authErrorMessage");
  const submitBtn = document.getElementById("authSubmitBtn");

  errorMsg.style.display = "none";
  submitBtn.disabled = true;
  submitBtn.textContent = authMode === "LOGIN" ? "Signing In..." : "Registering...";

  try {
    if (authMode === "LOGIN") {
      await signInWithEmail(email, password);
      showToast("🔐 Signed In", `Logged in as ${email}`, "success");
    } else {
      await signUpWithEmail(email, password);
      showToast("🎉 Registered", `Welcome! Account ${email} created successfully.`, "success");
    }
  } catch (err) {
    console.error("Auth error:", err);
    errorMsg.textContent = err.message || "An authentication error occurred.";
    errorMsg.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.textContent = authMode === "LOGIN" ? "Sign In" : "Register";
  }
}

async function handleGoogleLogin() {
  const errorMsg = document.getElementById("authErrorMessage");
  const googleBtn = document.getElementById("googleSignInBtn");

  try {
    errorMsg.style.display = "none";

    // Show loading state while waiting for Firebase to initialize
    if (googleBtn) {
      googleBtn.disabled = true;
      googleBtn.innerHTML = `<span style="display:flex;align-items:center;gap:8px;justify-content:center">
        <svg width="18" height="18" viewBox="0 0 38 38" xmlns="http://www.w3.org/2000/svg" stroke="currentColor">
          <g fill="none" fill-rule="evenodd"><g transform="translate(1 1)" stroke-width="2">
          <circle stroke-opacity=".3" cx="18" cy="18" r="18"/>
          <path d="M36 18c0-9.94-8.06-18-18-18"><animateTransform attributeName="transform" type="rotate" from="0 18 18" to="360 18 18" dur="0.8s" repeatCount="indefinite"/></path>
          </g></g></svg>
        Connecting...</span>`;
    }

    const result = await signInWithGoogle();
    const email = result.user ? result.user.email : "user";
    showToast("🔐 Google Sign-In", `Logged in as ${email}`, "success");
  } catch (err) {
    console.error("Google login error:", err);
    const msg = err.message || "Failed to sign in with Google.";
    errorMsg.textContent = msg;
    errorMsg.style.display = "block";
  } finally {
    // Always restore button
    if (googleBtn) {
      googleBtn.disabled = false;
      googleBtn.innerHTML = `<img src="https://www.google.com/favicon.ico" width="18" height="18" style="vertical-align:middle;margin-right:8px"> Sign In with Google`;
    }
  }
}

async function handleLogout() {
  try {
    await signOutUser();
    showToast("👋 Logged Out", "Successfully logged out of the system.", "info");
  } catch (err) {
    console.error("Logout error:", err);
    showToast("❌ Error", "Failed to sign out.", "danger");
  }
}

// ── Solar Settings Parameters Form ───────────────────────────────────────────
async function loadSolarSettings() {
  try {
    const resp = await fetch(`${API}/api/settings/solar`);
    if (!resp.ok) return;
    const settings = await resp.json();

    // Store in global settings
    solarSettings = settings;

    // Populate inputs in UI settings form
    const ratingInput = document.getElementById("settingsPanelRating");
    const costInput   = document.getElementById("settingsCostPerKwh");
    const installInput = document.getElementById("settingsInstallationCost");
    const sunHoursInput = document.getElementById("settingsSunlightHours");
    const ldrInput = document.getElementById("settingsLdrInverted");

    if (ratingInput) ratingInput.value = settings.panel_rating;
    if (costInput) costInput.value = settings.electricity_cost;
    if (installInput) installInput.value = settings.installation_cost;
    if (sunHoursInput) sunHoursInput.value = settings.sunlight_hours;
    if (ldrInput) ldrInput.checked = !!settings.ldr_inverted;

    // Update current units on dashboard UI
    updateCurrencyLabel(settings.electricity_cost);

    console.log("[Settings] Loaded settings:", settings);
  } catch (e) {
    console.warn("[Settings] API unreachable:", e.message);
  }
}

async function handleSettingsSubmit(e) {
  e.preventDefault();
  const panelRating = parseFloat(document.getElementById("settingsPanelRating").value);
  const costPerKwh  = parseFloat(document.getElementById("settingsCostPerKwh").value);
  const installCost = parseFloat(document.getElementById("settingsInstallationCost").value);
  const sunHours    = parseFloat(document.getElementById("settingsSunlightHours").value);
  const ldrInverted = document.getElementById("settingsLdrInverted")?.checked || false;
  const saveBtn     = document.getElementById("saveSettingsBtn");

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
  }

  try {
    const resp = await fetch(`${API}/api/settings/solar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        panel_rating: panelRating,
        electricity_cost: costPerKwh,
        installation_cost: installCost,
        sunlight_hours: sunHours,
        ldr_inverted: ldrInverted
      }),
    });

    if (!resp.ok) throw new Error("Failed to save solar settings.");
    const updated = await resp.json();
    solarSettings = updated;

    showToast("💾 Settings Saved", "Solar parameters updated successfully.", "success");

    // Force refresh ROI and savings calculations with latest parameters
    loadDashboardStats().then(() => {
      if (typeof runRoiSimulation === "function") runRoiSimulation();
    });

  } catch(err) {
    showToast("❌ Error", err.message, "danger");
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Parameters";
    }
  }
}

function updateCurrencyLabel(cost) {
  const label1 = document.getElementById("currency-unit-1");
  if (label1) {
    // Check if Indian rupees or generic dollars
    label1.textContent = cost > 50 ? "$" : "₹"; // Simple rule-based symbol
  }
}

// ── KPI & ROI Calculations ───────────────────────────────────────────────────
function fmt(v, dec=1) { return v != null && !isNaN(v) ? Number(v).toFixed(dec) : "—"; }

function updateKPIs(data) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = val;
      el.classList.add("kpi-flash");
      setTimeout(() => el.classList.remove("kpi-flash"), 600);
    }
  };

  // Base Telemetry Cards
  set("kpi-light",  fmt(data.light_intensity, 1));
  set("kpi-temp",   fmt(data.temperature, 1));
  set("kpi-humid",  fmt(data.humidity, 1));
  set("kpi-volt",   fmt(data.voltage, 1));
  set("kpi-curr",   fmt(data.current, 2));
  set("kpi-power",  fmt(data.power, 1));
  set("kpi-energy", fmt(data.energy, 3));

  let tsStr = data.timestamp;
  if (tsStr && !tsStr.endsWith("Z") && !tsStr.includes("+")) {
    tsStr += "Z"; // Assume UTC if no timezone is provided by backend SQLite naive datetime
  }
  const ts = tsStr ? new Date(tsStr).toLocaleString("en-IN") : "—";
  const lu = document.getElementById("lastUpdated");
  if (lu) lu.textContent = ts;

  // Status banner
  updateStatusBanner(data);

  // Degradation badge
  if (data.degradation_pct != null) {
    set("kpi-degrad", fmt(data.degradation_pct, 1));
  }

  // --- Real-time ROI and Environmental Savings Calculations ---
  const energyKwh = data.energy != null ? data.energy : 0.0;
  const ratingWatts = solarSettings.panel_rating;
  const costKwh = solarSettings.electricity_cost;
  const installCost = solarSettings.installation_cost;
  const sunlightHours = solarSettings.sunlight_hours;
  const degradation = data.degradation_pct != null ? data.degradation_pct : 0.0;

  // 1. CO2 Offset: grid average 0.79 kg CO2 per kWh
  const co2OffsetKg = energyKwh * 0.79;
  const treesPlanted = co2OffsetKg / 20.0; // 1 average tree absorbs ~20kg CO2 per year
  set("kpi-co2", fmt(co2OffsetKg, 1));
  const treesEl = document.getElementById("kpi-trees");
  if (treesEl) treesEl.textContent = `≈ ${fmt(treesPlanted, 1)} trees saved`;

  // 2. Projected Monthly bill savings & actual cumulative savings
  // Equation: (Rating in kW * daily sunlight * 30 days * cost/kWh * efficiency_loss)
  const ratingKw = ratingWatts / 1000.0;
  const efficiencyLoss = 1.0 - (degradation / 100.0);
  const monthlyGenKwh = ratingKw * sunlightHours * 30 * efficiencyLoss;
  const monthlySavingsVal = monthlyGenKwh * costKwh;
  const actualCumulativeSavings = energyKwh * costKwh;

  set("kpi-savings", fmt(monthlySavingsVal, 1));
  const savingsDetail = document.getElementById("kpi-savings-detail");
  const currencySymbol = costKwh > 50 ? "$" : "₹";
  if (savingsDetail) {
    savingsDetail.textContent = `Cumulative actual: ${currencySymbol}${fmt(actualCumulativeSavings, 1)}`;
  }

  // 3. Time to Payback ROI (Payback Period in years)
  // Annual projected savings = generation * cost * typical panel performance ratio (0.75)
  const annualGenKwh = ratingKw * sunlightHours * 365 * 0.75 * efficiencyLoss;
  const annualSavingsVal = annualGenKwh * costKwh;
  const paybackYears = annualSavingsVal > 0 ? (installCost / annualSavingsVal) : 0;
  const paybackMonths = Math.round(paybackYears * 12);

  if (paybackYears > 0) {
    set("kpi-payback", fmt(paybackYears, 1));
    const paybackDetail = document.getElementById("kpi-payback-detail");
    if (paybackDetail) {
      paybackDetail.textContent = `≈ ${paybackMonths} months to recover cost`;
    }
  } else {
    set("kpi-payback", "—");
    const paybackDetail = document.getElementById("kpi-payback-detail");
    if (paybackDetail) paybackDetail.textContent = "Payback ROI unavailable";
  }
}

function updateStatusBanner(data) {
  const banner     = document.getElementById("statusBanner");
  const bannerIcon = document.getElementById("bannerIcon");
  const bannerTitle= document.getElementById("bannerTitle");
  const bannerMsg  = document.getElementById("bannerMsg");
  if (!banner) return;

  if (data.needs_cleaning) {
    const sev = (data.cleaning_conf || 0) >= 0.8 ? "critical" : "warning";
    banner.className = `status-banner ${sev}`;
    bannerIcon.textContent = sev === "critical" ? "🚨" : "⚠️";
    bannerTitle.textContent = "Panel Cleaning Required";
    bannerMsg.textContent   = data.cleaning_reason || `Confidence: ${fmt((data.cleaning_conf||0)*100, 0)}%`;
  } else {
    banner.className = "status-banner clean";
    bannerIcon.textContent  = "✅";
    bannerTitle.textContent = "Panel Operating Normally";
    bannerMsg.textContent   = "No cleaning required at this time.";
  }
}

// ── Dashboard Stats (initial load) ───────────────────────────────────────────
async function loadDashboardStats() {
  if (!currentUser) return;
  try {
    const resp = await fetch(`${API}/api/dashboard/stats`);
    if (!resp.ok) return;
    const data = await resp.json();

    updateKPIs({
      light_intensity: data.latest_light,
      temperature:     data.latest_temperature,
      humidity:        data.latest_humidity,
      voltage:         data.latest_voltage,
      current:         data.latest_current,
      power:           data.latest_power,
      energy:          data.latest_energy,
      degradation_pct: data.current_degradation,
      needs_cleaning:  data.cleaning_needed,
      cleaning_conf:   data.cleaning_confidence,
      timestamp:       data.last_updated,
    });

    // Alert bell count
    updateAlertBell(data.unread_alerts);

    // Trigger ROI simulation update
    runRoiSimulation();
  } catch(e) {
    console.warn("[Stats] API unreachable:", e.message);
  }
}

function updateAlertBell(count) {
  const badge = document.getElementById("alertBadge");
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count > 99 ? "99+" : count;
    badge.style.display = "flex";
  } else {
    badge.style.display = "none";
  }
}

// ── History Data ─────────────────────────────────────────────────────────────
async function loadHistoryData(hours) {
  if (!currentUser) return;
  if (hours) historyHours = hours;
  const limit = Math.min(historyHours * 12, 1000);  // ~5min interval

  try {
    const resp = await fetch(`${API}/api/telemetry/history?hours=${historyHours}&limit=${limit}`);
    if (!resp.ok) return;
    const records = await resp.json();
    populateHistoryCharts(records);
    historyLoaded = true;
  } catch(e) {
    console.warn("[History]", e.message);
  }
}

// ── Alerts ────────────────────────────────────────────────────────────────────
async function loadAlerts() {
  if (!currentUser) return;
  try {
    const resp = await fetch(`${API}/api/alerts?limit=200`);
    if (!resp.ok) return;
    alertsData = await resp.json();
    renderAlerts();
  } catch(e) {
    console.warn("[Alerts]", e.message);
  }
}

function renderAlerts() {
  const tbody = document.getElementById("alertsTableBody");
  if (!tbody) return;

  const filtered = alertFilter === "ALL"
    ? alertsData
    : alertFilter === "UNREAD"
    ? alertsData.filter(a => !a.acknowledged)
    : alertsData.filter(a => a.alert_type === alertFilter);

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6">
      <div class="empty-state">
        <div class="empty-icon">🔔</div>
        <p>No alerts in this category.</p>
      </div></td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(a => {
    const ts = new Date(a.timestamp).toLocaleString("en-IN");
    const sevBadge = `<span class="badge badge-${a.severity.toLowerCase()}">${a.severity}</span>`;
    const typeBadge = `<span class="badge badge-${a.alert_type.toLowerCase()}">${a.alert_type}</span>`;
    const conf = a.confidence != null ? `${(a.confidence*100).toFixed(0)}%` : "—";
    const ackBtn = a.acknowledged
      ? `<span class="text-xs text-gray">✓ Acknowledged</span>`
      : `<button class="btn btn-outline btn-sm" onclick="ackAlert(${a.id})">Acknowledge</button>`;
    const rowCls = a.acknowledged ? "" : "unread";
    return `<tr class="${rowCls}" id="alert-row-${a.id}">
      <td>${ts}</td>
      <td>${typeBadge}</td>
      <td>${sevBadge}</td>
      <td>${a.message}</td>
      <td>${conf}</td>
      <td>${ackBtn}</td>
    </tr>`;
  }).join("");
}

async function ackAlert(id) {
  try {
    await fetch(`${API}/api/alerts/acknowledge/${id}`, { method: "POST" });
    const a = alertsData.find(x => x.id === id);
    if (a) a.acknowledged = true;
    renderAlerts();
    const stats = await fetch(`${API}/api/dashboard/stats`).then(r => r.json());
    updateAlertBell(stats.unread_alerts);
    showToast("✅ Alert acknowledged", "Alert marked as read.", "success");
  } catch(e) {
    showToast("❌ Error", e.message, "danger");
  }
}

async function ackAllAlerts() {
  try {
    await fetch(`${API}/api/alerts/acknowledge-all`, { method: "POST" });
    alertsData.forEach(a => a.acknowledged = true);
    renderAlerts();
    updateAlertBell(0);
    showToast("✅ All alerts acknowledged", "All alerts marked as read.", "success");
  } catch(e) {
    showToast("❌ Error", e.message, "danger");
  }
}

function setAlertFilter(filter) {
  alertFilter = filter;
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  document.querySelector(`[data-filter="${filter}"]`)?.classList.add("active");
  renderAlerts();
}

// ── Degradation & Maintenance Logs ───────────────────────────────────────────
async function loadDegradation() {
  if (!currentUser) return;
  try {
    const [degResp, maintResp] = await Promise.all([
      fetch(`${API}/api/degradation?limit=200`),
      fetch(`${API}/api/maintenance`)
    ]);

    if (!degResp.ok || !maintResp.ok) return;
    const records = await degResp.json();
    const maintLogs = await maintResp.json();

    if (records.length) {
      const latest = records[0];
      updateGauge(latest.degradation_pct);

      const trendEl = document.getElementById("degTrend");
      if (trendEl) {
        trendEl.className = `deg-trend-badge trend-${latest.trend.toLowerCase()}`;
        trendEl.textContent = `${latest.trend === "STABLE" ? "↔" : latest.trend === "DECLINING" ? "↓" : "⚠"} ${latest.trend}`;
      }
      const msgEl = document.getElementById("degMessage");
      if (msgEl) msgEl.textContent = `Latest reading: ${latest.degradation_pct?.toFixed(2)}% — ${latest.trend}`;
    } else {
      updateGauge(0);
    }

    // Populate Maintenance Timeline Table
    const tbody = document.getElementById("maintenanceLogsTableBody");
    if (tbody) {
      if (!maintLogs.length) {
        tbody.innerHTML = `<tr>
          <td colspan="4" style="text-align: center; color: var(--gray-400); padding: 20px;">
            No maintenance activities logged yet.
          </td>
        </tr>`;
      } else {
        tbody.innerHTML = maintLogs.map(log => {
          const dateStr = new Date(log.performed_at).toLocaleString("en-IN", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
          const notesStr = log.notes || "—";
          const degStr = log.current_degradation != null ? `${log.current_degradation.toFixed(1)}%` : "—";
          return `<tr>
            <td>${dateStr}</td>
            <td style="white-space: pre-wrap; max-width: 250px; text-align: left;">${notesStr}</td>
            <td style="text-align: center;">${degStr}</td>
            <td style="text-align: right;">
              <button class="btn btn-outline btn-sm" onclick="deleteMaintenanceLog(${log.id})" style="color: var(--danger); border-color: var(--danger-light); padding: 2px 6px;">Delete</button>
            </td>
          </tr>`;
        }).join("");
      }
    }

    // Pass logs to degradation chart to show event markers
    populateDegradationChart(records, maintLogs);

  } catch(e) {
    console.warn("[Degradation/Logs] Load error:", e.message);
  }
}

async function handleMaintenanceSubmit(e) {
  e.preventDefault();
  const dateInput = document.getElementById("maintDate").value;
  const notesInput = document.getElementById("maintNotes").value;
  const saveBtn = document.getElementById("saveMaintBtn");

  if (!dateInput) return;

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Logging...";
  }

  try {
    const payload = {
      performed_at: new Date(dateInput).toISOString(),
      notes: notesInput
    };

    const resp = await fetch(`${API}/api/maintenance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!resp.ok) throw new Error("Failed to save maintenance log.");
    
    showToast("🧹 Logged Maintenance", "Cleaning event recorded successfully.", "success");
    document.getElementById("maintNotes").value = "";
    
    // Reset date input
    const localNow = new Date();
    localNow.setMinutes(localNow.getMinutes() - localNow.getTimezoneOffset());
    document.getElementById("maintDate").value = localNow.toISOString().slice(0, 16);

    // Refresh dashboards and logs
    await loadDashboardStats();
    await loadAlerts();
    await loadDegradation();

  } catch(err) {
    showToast("❌ Error", err.message, "danger");
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "🧼 Log Cleaning Activity";
    }
  }
}

async function deleteMaintenanceLog(id) {
  if (!confirm("Are you sure you want to delete this maintenance log?")) return;
  try {
    const resp = await fetch(`${API}/api/maintenance/${id}`, { method: "DELETE" });
    if (!resp.ok) throw new Error("Failed to delete log.");
    showToast("🗑️ Log Deleted", "Maintenance log removed successfully.", "success");
    await loadDegradation();
  } catch(e) {
    showToast("❌ Error", e.message, "danger");
  }
}

async function loadMaintenanceLogs() {
  await loadDegradation();
}

// ── ROI SIMULATOR MATH ────────────────────────────────────────────────────────

function runRoiSimulation() {
  const upgradeWattsInput = document.getElementById("simUpgradeWatts");
  const inflationInput = document.getElementById("simInflation");
  const upgradeCostInput = document.getElementById("simUpgradeCost");

  if (!upgradeWattsInput || !inflationInput || !upgradeCostInput) return;

  const simUpgradeWatts = parseFloat(upgradeWattsInput.value);
  const simInflation = parseFloat(inflationInput.value);
  const simUpgradeCost = parseFloat(upgradeCostInput.value);

  // Update labels
  document.getElementById("simUpgradeWattsVal").textContent = `${simUpgradeWatts} W`;
  document.getElementById("simInflationVal").textContent = `${simInflation}%`;

  const ratingWatts = solarSettings.panel_rating;
  const costKwh = solarSettings.electricity_cost;
  const installCost = solarSettings.installation_cost;
  const sunlightHours = solarSettings.sunlight_hours;

  // Use current degradation reading from page or default to 1.5%
  const kpiDegVal = document.getElementById("kpi-degrad")?.textContent;
  const degradation = kpiDegVal && kpiDegVal !== "—" ? parseFloat(kpiDegVal) : 1.5;

  const currencySymbol = costKwh > 50 ? "$" : "₹";
  
  // Combined capacity display
  document.getElementById("simCombinedCapacity").textContent = `${Math.round(ratingWatts + simUpgradeWatts)} W`;

  // Plot year 0 to 10
  const currentPath = [ -installCost ];
  const upgradedPath = [ -(installCost + simUpgradeCost) ];
  
  let currentAccum = -installCost;
  let upgradedAccum = -(installCost + simUpgradeCost);

  for (let y = 1; y <= 10; y++) {
    const rate_y = costKwh * Math.pow(1 + simInflation / 100, y - 1);
    const degFactor = Math.pow(1 - degradation / 100, y);

    // Current system annual generation & savings
    const currentGenKwh = (ratingWatts / 1000.0) * sunlightHours * 365 * 0.75 * degFactor;
    const currentSavings_y = currentGenKwh * rate_y;
    currentAccum += currentSavings_y;
    currentPath.push(currentAccum);

    // Upgraded system annual generation & savings
    const upgradedGenKwh = ((ratingWatts + simUpgradeWatts) / 1000.0) * sunlightHours * 365 * 0.75 * degFactor;
    const upgradedSavings_y = upgradedGenKwh * rate_y;
    upgradedAccum += upgradedSavings_y;
    upgradedPath.push(upgradedAccum);
  }

  // Draw simulation chart
  updateSimulationChart(currentPath, upgradedPath, currencySymbol);

  // Calculate break-even / payback years
  let paybackYears = null;
  for (let y = 1; y <= 10; y++) {
    const prev = upgradedPath[y - 1];
    const curr = upgradedPath[y];
    if (prev < 0 && curr >= 0) {
      const annualAdd = curr - prev;
      paybackYears = (y - 1) + (-prev / annualAdd);
      break;
    }
  }

  const pbText = document.getElementById("simPayback");
  if (paybackYears !== null) {
    pbText.textContent = `${paybackYears.toFixed(1)} yrs`;
  } else {
    const lastDiff = upgradedPath[10] - upgradedPath[9];
    if (lastDiff > 0 && upgradedPath[10] < 0) {
      const extraYears = -upgradedPath[10] / lastDiff;
      pbText.textContent = `≈ ${(10 + extraYears).toFixed(1)} yrs`;
    } else if (upgradedPath[10] >= 0) {
      pbText.textContent = "Immediate";
    } else {
      pbText.textContent = ">10 yrs";
    }
  }

  // Savings upgrade delta at year 10
  const savingsDelta = upgradedAccum - currentAccum;
  const deltaEl = document.getElementById("simSavingsIncrease");
  if (deltaEl) {
    if (savingsDelta >= 0) {
      deltaEl.textContent = `+${currencySymbol}${Math.round(savingsDelta).toLocaleString("en-IN")}`;
      deltaEl.parentElement.style.background = "#F0FDF4";
      deltaEl.style.color = "#16A34A";
    } else {
      deltaEl.textContent = `-${currencySymbol}${Math.abs(Math.round(savingsDelta)).toLocaleString("en-IN")}`;
      deltaEl.parentElement.style.background = "#FEF2F2";
      deltaEl.style.color = "#DC2626";
    }
  }
}


// ── Toast Notifications ───────────────────────────────────────────────────────
function showToast(title, msg, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const colors = { success: "#16A34A", danger: "#DC2626", info: "#2563EB", warning: "#D97706" };
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.style.setProperty("--toast-color", colors[type] || colors.info);
  toast.innerHTML = `
    <div class="toast-icon">${type === "success" ? "✅" : type === "danger" ? "❌" : "ℹ️"}</div>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-msg">${msg}</div>
    </div>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("hiding");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function checkForNewAlerts(data) {
  if (data.needs_cleaning && !_lastCleaningState) {
    showToast("🚿 Panel Cleaning Alert", data.cleaning_reason || "Panel may need cleaning.", "warning");
  }
  _lastCleaningState = data.needs_cleaning;
}

// ── Flash animations ─────────────────────────────────────────────────────────
const style = document.createElement("style");
style.textContent = `
  @keyframes kpi-flash {
    0%  { color: var(--primary); }
    100%{ color: var(--gray-900); }
  }
  .kpi-flash .kpi-value, .kpi-flash { animation: kpi-flash .6s ease; }
`;
document.head.appendChild(style);

// ── App Initialization & Router Protection ───────────────────────────────────
function initApp() {
  // Init charts
  initDashboardCharts();
  initHistoryCharts();
  initDegradationChart();

  // 1. Setup Auth listener
  onAuthStateChangedListener((user) => {
    currentUser = user;

    const navbar = document.getElementById("mainNavbar");
    const profileWidget = document.getElementById("userProfileWidget");
    const emailText = document.getElementById("userEmailText");
    const avatar = document.getElementById("userAvatar");

    if (user) {
      // User is logged in
      navbar.style.display = "flex";
      profileWidget.style.display = "flex";
      emailText.textContent = user.email;
      avatar.textContent = user.email ? user.email.charAt(0).toUpperCase() : "U";

      // Load Settings & Stats
      loadSolarSettings().then(() => {
        loadDashboardStats().then(() => {
          if (typeof runRoiSimulation === "function") runRoiSimulation();
        });
      });

      // Show dashboard view
      showView("view-dashboard");

    } else {
      // User is logged out
      navbar.style.display = "none";
      profileWidget.style.display = "none";
      showView("view-login");
    }
  });

  // 2. Register live data listener from firebase.js / WebSocket
  onLiveData((data) => {
    if (!currentUser) return;
    if (data.type !== "telemetry") return;
    updateKPIs(data);
    updateDashboardCharts(data);
    checkForNewAlerts(data);

    // Refresh unread alert badge count periodically
    const badge = document.getElementById("alertBadge");
    if (badge) {
      fetch(`${API}/api/dashboard/stats`)
        .then(r => r.json())
        .then(s => updateAlertBell(s.unread_alerts))
        .catch(() => {});
    }
  });

  // Start connections (Fetches Firebase Config and initializes WebSocket/SDK)
  initConnections();

  // Initialize maintenance date input with current local time
  const maintDateInput = document.getElementById("maintDate");
  if (maintDateInput) {
    const localNow = new Date();
    localNow.setMinutes(localNow.getMinutes() - localNow.getTimezoneOffset());
    maintDateInput.value = localNow.toISOString().slice(0, 16);
  }

  // Poll stats every 5s — reliable always-on update
  setInterval(async () => {
    if (!currentUser) return;
    try {
      const resp = await fetch(`${API}/api/dashboard/stats`);
      if (!resp.ok) return;
      const data = await resp.json();
      updateKPIs({
        light_intensity: data.latest_light,
        temperature:     data.latest_temperature,
        humidity:        data.latest_humidity,
        voltage:         data.latest_voltage,
        current:         data.latest_current,
        power:           data.latest_power,
        energy:          data.latest_energy,
        degradation_pct: data.current_degradation,
        needs_cleaning:  data.cleaning_needed,
        cleaning_conf:   data.cleaning_confidence,
        timestamp:       data.last_updated,
      });
      updateAlertBell(data.unread_alerts);
    } catch(e) { /* backend unreachable, skip silently */ }
  }, 5000);

  console.log("[App] Smart Solar Plug dashboard initialized.");
}

// Bind actions to window object for inline HTML click/submit events
window.handleGoogleLogin = handleGoogleLogin;
window.handleAuthSubmit  = handleAuthSubmit;
window.handleLogout      = handleLogout;
window.toggleAuthMode    = toggleAuthMode;
window.handleSettingsSubmit = handleSettingsSubmit;
window.handleMaintenanceSubmit = handleMaintenanceSubmit;
window.deleteMaintenanceLog = deleteMaintenanceLog;
window.loadMaintenanceLogs = loadMaintenanceLogs;
window.runRoiSimulation = runRoiSimulation;

// Start when DOM is ready
document.addEventListener("DOMContentLoaded", initApp);


// ── Initialize Current Time ──────────────────────────────────────────────────
setInterval(() => {
  const ct = document.getElementById("currentTime");
  if (ct) {
    ct.textContent = new Date().toLocaleString("en-IN");
  }
}, 1000);
