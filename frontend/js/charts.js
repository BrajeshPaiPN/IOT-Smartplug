/**
 * Smart Solar Plug — Chart.js Visualizations
 * All chart instances and update functions.
 */

// Shared Chart.js defaults
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.color = "#6B7280";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.tooltip.backgroundColor = "#1F2937";
Chart.defaults.plugins.tooltip.titleFont = { weight: "700", size: 12 };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.displayColors = true;
Chart.defaults.plugins.tooltip.boxPadding = 4;

// Color palette
const COLORS = {
  blue:        "#2563EB",
  blueLight:   "rgba(37,99,235,.12)",
  green:       "#16A34A",
  greenLight:  "rgba(22,163,74,.12)",
  amber:       "#D97706",
  amberLight:  "rgba(217,119,6,.12)",
  red:         "#DC2626",
  redLight:    "rgba(220,38,38,.12)",
  cyan:        "#0891B2",
  cyanLight:   "rgba(8,145,178,.12)",
  purple:      "#7C3AED",
  purpleLight: "rgba(124,58,237,.12)",
  gray:        "#9CA3AF",
};

// ── DASHBOARD CHARTS ──────────────────────────────────────────────────────────

let envChart   = null;
let powerChart = null;

function initDashboardCharts() {
  // Environment: Temperature + Humidity on left axis, Light on right
  const envCtx = document.getElementById("envChart")?.getContext("2d");
  if (envCtx && !envChart) {
    envChart = new Chart(envCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Temperature (°C)",
            data: [], yAxisID: "y",
            borderColor: COLORS.red,
            backgroundColor: COLORS.redLight,
            borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
            tension: 0.4, fill: true,
          },
          {
            label: "Humidity (%)",
            data: [], yAxisID: "y",
            borderColor: COLORS.blue,
            backgroundColor: COLORS.blueLight,
            borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
            tension: 0.4, fill: true,
          },
          {
            label: "Light (%)",
            data: [], yAxisID: "y2",
            borderColor: COLORS.amber,
            backgroundColor: "transparent",
            borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
            tension: 0.4, fill: false,
            borderDash: [5, 3],
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "top" } },
        scales: {
          x: { grid: { color: "#F3F4F6" }, ticks: { maxTicksLimit: 8, maxRotation: 0 } },
          y: {
            position: "left",
            title: { display: true, text: "Temp / Humidity" },
            grid: { color: "#F3F4F6" },
          },
          y2: {
            position: "right",
            title: { display: true, text: "Light %" },
            grid: { drawOnChartArea: false },
            min: 0, max: 100,
          },
        },
      },
    });
  }

  // Power / Voltage / Current
  const pwrCtx = document.getElementById("powerChart")?.getContext("2d");
  if (pwrCtx && !powerChart) {
    powerChart = new Chart(pwrCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Power (W)",
            data: [], yAxisID: "y",
            borderColor: COLORS.green,
            backgroundColor: COLORS.greenLight,
            borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
            tension: 0.4, fill: true,
          },
          {
            label: "Voltage (V)",
            data: [], yAxisID: "y2",
            borderColor: COLORS.purple,
            backgroundColor: "transparent",
            borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
            tension: 0.4, borderDash: [5, 3],
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "top" } },
        scales: {
          x: { grid: { color: "#F3F4F6" }, ticks: { maxTicksLimit: 8, maxRotation: 0 } },
          y:  { position: "left",  title: { display: true, text: "Watts" },  grid: { color: "#F3F4F6" } },
          y2: { position: "right", title: { display: true, text: "Volts" },  grid: { drawOnChartArea: false } },
        },
      },
    });
  }
}

// Rolling buffer for live dashboard charts (max 60 points)
const MAX_LIVE_POINTS = 60;

function pushLivePoint(chart, label, datasets) {
  if (!chart) return;
  if (chart.data.labels.length >= MAX_LIVE_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets.forEach(ds => ds.data.shift());
  }
  chart.data.labels.push(label);
  datasets.forEach((val, i) => {
    chart.data.datasets[i].data.push(val ?? null);
  });
  chart.update("none");
}

function updateDashboardCharts(data) {
  const ts = data.timestamp ? new Date(data.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--";

  pushLivePoint(envChart, ts, [data.temperature, data.humidity, data.light_intensity]);
  pushLivePoint(powerChart, ts, [data.power, data.voltage]);
}

// ── HISTORY CHARTS ────────────────────────────────────────────────────────────

let historyTempChart    = null;
let historyPowerChart   = null;
let historyLightChart   = null;
let historyEnergyChart  = null;

function initHistoryCharts() {
  const makeOpts = (yLabel, yLabel2) => ({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { position: "top" }, decimation: { enabled: true, algorithm: "lttb", samples: 200 } },
    scales: {
      x: { grid: { color: "#F3F4F6" }, ticks: { maxTicksLimit: 10, maxRotation: 0 } },
      y: { grid: { color: "#F3F4F6" }, title: { display: !!yLabel, text: yLabel } },
      ...(yLabel2 ? { y2: { position: "right", title: { display: true, text: yLabel2 }, grid: { drawOnChartArea: false } } } : {}),
    },
  });

  historyTempChart = _makeChart("historyTempChart", {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Temperature (°C)", data: [], borderColor: COLORS.red,  backgroundColor: COLORS.redLight,  borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: true, yAxisID: "y" },
      { label: "Humidity (%)",     data: [], borderColor: COLORS.blue, backgroundColor: COLORS.blueLight, borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: true, yAxisID: "y" },
    ]},
    options: makeOpts("°C / %"),
  });

  historyPowerChart = _makeChart("historyPowerChart", {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Power (W)",  data: [], borderColor: COLORS.green,  backgroundColor: COLORS.greenLight, borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: true, yAxisID: "y" },
      { label: "Current (A)",data: [], borderColor: COLORS.cyan,   backgroundColor: "transparent",     borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: "y2" },
    ]},
    options: makeOpts("Watts", "Amperes"),
  });

  historyLightChart = _makeChart("historyLightChart", {
    type: "bar",
    data: { labels: [], datasets: [
      { label: "Light Intensity (%)", data: [], backgroundColor: COLORS.amberLight, borderColor: COLORS.amber, borderWidth: 1.5, borderRadius: 4 },
    ]},
    options: makeOpts("Light %"),
  });

  historyEnergyChart = _makeChart("historyEnergyChart", {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Cumulative Energy (kWh)", data: [], borderColor: COLORS.purple, backgroundColor: COLORS.purpleLight, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true },
    ]},
    options: makeOpts("kWh"),
  });
}

function _makeChart(id, config) {
  const ctx = document.getElementById(id)?.getContext("2d");
  if (!ctx) return null;
  return new Chart(ctx, config);
}

function populateHistoryCharts(records) {
  // records arrives newest-first; reverse for chronological
  const rev = [...records].reverse();
  const labels = rev.map(r => {
    const d = new Date(r.timestamp);
    return d.toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  });

  function setData(chart, datasets) {
    if (!chart) return;
    chart.data.labels = labels;
    datasets.forEach(([i, vals]) => { chart.data.datasets[i].data = vals; });
    chart.update();
  }

  setData(historyTempChart, [
    [0, rev.map(r => r.temperature)],
    [1, rev.map(r => r.humidity)],
  ]);
  setData(historyPowerChart, [
    [0, rev.map(r => r.power)],
    [1, rev.map(r => r.current)],
  ]);
  setData(historyLightChart, [[0, rev.map(r => r.light_intensity)]]);
  setData(historyEnergyChart, [[0, rev.map(r => r.energy)]]);
}

// ── DEGRADATION CHART ─────────────────────────────────────────────────────────

let degradationChart = null;

function initDegradationChart() {
  degradationChart = _makeChart("degradationChart", {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Degradation %",
          data: [],
          borderColor: COLORS.red,
          backgroundColor: COLORS.redLight,
          borderWidth: 2, pointRadius: 3, pointHoverRadius: 6,
          tension: 0.4, fill: true,
        },
        {
          label: "Maintenance Events",
          data: [],
          type: "scatter",
          borderColor: COLORS.green,
          backgroundColor: COLORS.green,
          pointStyle: "star",
          pointRadius: 10,
          pointHoverRadius: 12,
          showLine: false,
        }
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top" },
        annotation: {
          annotations: {
            warningLine: {
              type: "line", yMin: 15, yMax: 15,
              borderColor: COLORS.amber, borderWidth: 2, borderDash: [6,3],
              label: { content: "Warning threshold", enabled: true, position: "start" },
            },
            criticalLine: {
              type: "line", yMin: 30, yMax: 30,
              borderColor: COLORS.red, borderWidth: 2, borderDash: [6,3],
              label: { content: "Critical threshold", enabled: true, position: "start" },
            },
          },
        },
      },
      scales: {
        x: { grid: { color: "#F3F4F6" }, ticks: { maxTicksLimit: 10, maxRotation: 0 } },
        y: { min: 0, max: 100, title: { display: true, text: "Degradation (%)" }, grid: { color: "#F3F4F6" } },
      },
    },
  });
}

function populateDegradationChart(records, maintLogs = []) {
  if (!degradationChart || !records.length) return;
  const rev = [...records].reverse();
  const labels = rev.map(r =>
    new Date(r.timestamp).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  );
  degradationChart.data.labels = labels;
  degradationChart.data.datasets[0].data = rev.map(r => r.degradation_pct);

  // Plot maintenance events as scatter points mapped to closest category label
  const scatterData = [];
  maintLogs.forEach(log => {
    const logTime = new Date(log.performed_at).getTime();
    let bestIndex = -1;
    let minDiff = Infinity;
    
    rev.forEach((r, idx) => {
      const diff = Math.abs(new Date(r.timestamp).getTime() - logTime);
      if (diff < minDiff) {
        minDiff = diff;
        bestIndex = idx;
      }
    });

    if (bestIndex !== -1) {
      scatterData.push({
        x: labels[bestIndex],
        y: log.current_degradation ?? rev[bestIndex].degradation_pct
      });
    }
  });
  
  degradationChart.data.datasets[1].data = scatterData;
  degradationChart.update();
}


// ── ROI SIMULATION CHART ──────────────────────────────────────────────────────

let simulationChart = null;

function initSimulationChart() {
  const simCtx = document.getElementById("simulationChart")?.getContext("2d");
  if (simCtx && !simulationChart) {
    simulationChart = new Chart(simCtx, {
      type: "line",
      data: {
        labels: ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Year 6", "Year 7", "Year 8", "Year 9", "Year 10"],
        datasets: [
          {
            label: "Current System",
            data: [],
            borderColor: COLORS.amber,
            backgroundColor: COLORS.amberLight,
            borderWidth: 2.5,
            pointRadius: 4,
            tension: 0.3,
            fill: false,
          },
          {
            label: "Simulated Upgraded System",
            data: [],
            borderColor: COLORS.blue,
            backgroundColor: COLORS.blueLight,
            borderWidth: 2.5,
            pointRadius: 4,
            tension: 0.3,
            fill: false,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              label: function(context) {
                let label = context.dataset.label || "";
                if (label) label += ": ";
                if (context.parsed.y !== null) {
                  label += "₹" + Math.round(context.parsed.y).toLocaleString("en-IN");
                }
                return label;
              }
            }
          }
        },
        scales: {
          x: { grid: { color: "#F3F4F6" } },
          y: {
            title: { display: true, text: "Cumulative Savings (₹)" },
            grid: { color: "#F3F4F6" },
            ticks: {
              callback: function(value) {
                return "₹" + value.toLocaleString("en-IN");
              }
            }
          }
        }
      }
    });
  }
}

function updateSimulationChart(currentPath, upgradedPath, currencySymbol = "₹") {
  if (!simulationChart) {
    initSimulationChart();
  }
  if (!simulationChart) return;

  simulationChart.data.datasets[0].data = currentPath;
  simulationChart.data.datasets[1].data = upgradedPath;
  
  // Update currency labels
  simulationChart.options.scales.y.title.text = `Cumulative Savings (${currencySymbol})`;
  simulationChart.options.scales.y.ticks.callback = function(value) {
    return currencySymbol + value.toLocaleString("en-IN");
  };
  simulationChart.options.plugins.tooltip.callbacks.label = function(context) {
    let label = context.dataset.label || "";
    if (label) label += ": ";
    if (context.parsed.y !== null) {
      label += currencySymbol + Math.round(context.parsed.y).toLocaleString("en-IN");
    }
    return label;
  };
  
  simulationChart.update();
}


// ── GAUGE (SVG semi-circle) ───────────────────────────────────────────────────

function updateGauge(pct) {
  const fill    = document.getElementById("gaugeFill");
  const valText = document.getElementById("gaugeValue");
  if (!fill || !valText) return;

  const clamped = Math.max(0, Math.min(100, pct || 0));
  // Semi-circle: r=80, circumference ≈ π*80 = 251.3
  const circumference = Math.PI * 80;
  const offset = circumference * (1 - clamped / 100);

  fill.style.strokeDasharray  = `${circumference}`;
  fill.style.strokeDashoffset = `${offset}`;

  // Color based on severity
  const color = clamped < 15 ? "#16A34A" : clamped < 30 ? "#D97706" : "#DC2626";
  fill.setAttribute("stroke", color);
  valText.textContent = `${clamped.toFixed(1)}%`;
}
