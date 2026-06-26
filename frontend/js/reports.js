/**
 * Smart Solar Plug — Report Download Handler
 */

const API_BASE = "http://localhost:8000";

function getDateRange() {
  const startEl = document.getElementById("reportStart");
  const endEl   = document.getElementById("reportEnd");
  return {
    start: startEl?.value ? new Date(startEl.value).toISOString() : null,
    end:   endEl?.value   ? new Date(endEl.value).toISOString()   : null,
  };
}

function buildURL(endpoint) {
  const { start, end } = getDateRange();
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end)   params.set("end", end);
  const qs = params.toString();
  return `${API_BASE}${endpoint}${qs ? "?" + qs : ""}`;
}

async function downloadReport(type) {
  const endpoint = type === "csv" ? "/api/report/csv" : "/api/report/pdf";
  const url = buildURL(endpoint);
  const btn = type === "csv" ? document.getElementById("downloadCsvBtn") : document.getElementById("downloadPdfBtn");

  // Loading state
  const origText = btn.innerHTML;
  btn.innerHTML = `<span class="spinner"></span> Generating ${type.toUpperCase()}…`;
  btn.disabled = true;

  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err || `HTTP ${resp.status}`);
    }

    const blob     = await resp.blob();
    const blobUrl  = URL.createObjectURL(blob);
    const filename = (resp.headers.get("content-disposition") || "")
      .split("filename=")[1]?.replace(/"/g, "")
      || `solar_report_${Date.now()}.${type}`;

    // Trigger browser download
    const a = document.createElement("a");
    a.href     = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);

    showToast("✅ Download started", `${type.toUpperCase()} report ready`, "success");
  } catch(e) {
    console.error("[Report]", e);
    showToast("❌ Download failed", e.message, "danger");
  } finally {
    btn.innerHTML = origText;
    btn.disabled = false;
  }
}

// Set default date range to last 7 days
function initReportDateDefaults() {
  const endDate   = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 7);

  const fmt = (d) => d.toISOString().slice(0, 16);  // datetime-local format

  const startEl = document.getElementById("reportStart");
  const endEl   = document.getElementById("reportEnd");
  if (startEl) startEl.value = fmt(startDate);
  if (endEl)   endEl.value   = fmt(endDate);
}
