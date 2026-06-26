"""
Smart Solar Plug — Report Generator
Generates CSV and PDF reports from SQLite telemetry data.
"""

import io
import os
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[Report] reportlab not installed — PDF export disabled.")


def generate_csv(records: list, start_dt: Optional[datetime], end_dt: Optional[datetime]) -> bytes:
    """Convert telemetry records to CSV bytes."""
    if not records:
        df = pd.DataFrame(columns=[
            "id", "timestamp", "light_intensity", "temperature", "humidity",
            "voltage", "current", "power", "energy",
            "needs_cleaning", "cleaning_conf", "degradation_pct"
        ])
    else:
        rows = []
        for r in records:
            rows.append({
                "id":              r.id,
                "timestamp":       r.timestamp.isoformat() if r.timestamp else "",
                "light_intensity": r.light_intensity,
                "temperature":     r.temperature,
                "humidity":        r.humidity,
                "voltage":         r.voltage,
                "current":         r.current,
                "power":           r.power,
                "energy":          r.energy,
                "needs_cleaning":  r.needs_cleaning,
                "cleaning_conf":   r.cleaning_conf,
                "degradation_pct": r.degradation_pct,
            })
        df = pd.DataFrame(rows)

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def generate_pdf(
    records: list,
    alerts: list,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> bytes:
    """Generate a professional PDF report."""

    if not REPORTLAB_AVAILABLE:
        return b"PDF generation requires reportlab. Install with: pip install reportlab"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    BLUE   = colors.HexColor("#2563EB")
    LBLUE  = colors.HexColor("#EFF6FF")
    AMBER  = colors.HexColor("#D97706")
    RED    = colors.HexColor("#DC2626")
    GREEN  = colors.HexColor("#16A34A")
    GRAY   = colors.HexColor("#6B7280")
    LGRAY  = colors.HexColor("#F9FAFB")

    title_style = ParagraphStyle("Title", parent=styles["Title"],
        textColor=BLUE, fontSize=20, spaceAfter=6, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle("Sub", parent=styles["Normal"],
        textColor=GRAY, fontSize=11, spaceAfter=4, alignment=TA_CENTER)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"],
        textColor=BLUE, fontSize=13, spaceBefore=16, spaceAfter=6)
    normal = styles["Normal"]
    normal.fontSize = 9

    story = []

    # ─── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph("☀ Smart Solar Plug — Monitoring Report", title_style))
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    period_str = ""
    if start_dt or end_dt:
        s = start_dt.strftime("%Y-%m-%d") if start_dt else "—"
        e = end_dt.strftime("%Y-%m-%d")   if end_dt   else "—"
        period_str = f"Period: {s} → {e}"
    story.append(Paragraph(f"Generated: {now_str}   {period_str}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=12))

    # ─── Summary KPIs ─────────────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", section_style))

    if records:
        df = pd.DataFrame([{
            "light": r.light_intensity, "temp": r.temperature,
            "hum":   r.humidity,        "volt": r.voltage,
            "curr":  r.current,         "pwr":  r.power,
            "nrg":   r.energy,          "deg":  r.degradation_pct,
        } for r in records])

        kpi_data = [
            ["Metric", "Average", "Minimum", "Maximum"],
            ["Light Intensity (%)",
             f"{df['light'].mean():.1f}", f"{df['light'].min():.1f}", f"{df['light'].max():.1f}"],
            ["Temperature (°C)",
             f"{df['temp'].mean():.1f}",  f"{df['temp'].min():.1f}",  f"{df['temp'].max():.1f}"],
            ["Humidity (%)",
             f"{df['hum'].mean():.1f}",   f"{df['hum'].min():.1f}",   f"{df['hum'].max():.1f}"],
            ["Voltage (V)",
             f"{df['volt'].mean():.1f}",  f"{df['volt'].min():.1f}",  f"{df['volt'].max():.1f}"],
            ["Power (W)",
             f"{df['pwr'].mean():.1f}",   f"{df['pwr'].min():.1f}",   f"{df['pwr'].max():.1f}"],
        ]
        if df["deg"].notna().any():
            kpi_data.append([
                "Degradation (%)",
                f"{df['deg'].mean():.2f}", f"{df['deg'].min():.2f}", f"{df['deg'].max():.2f}"
            ])

        kpi_table = Table(kpi_data, colWidths=[5.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), BLUE),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 9),
            ("ALIGN",       (1,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [LGRAY, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ("BOTTOMPADDING",(0,0),(-1,-1), 6),
            ("TOPPADDING",  (0,0),(-1,-1), 6),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("No telemetry data for this period.", normal))

    # ─── Alerts Summary ───────────────────────────────────────────────────────
    story.append(Paragraph("Alerts", section_style))
    if alerts:
        severity_color = {"LOW": GREEN, "MEDIUM": AMBER, "HIGH": RED, "CRITICAL": RED}
        alert_data = [["Timestamp", "Type", "Severity", "Message"]]
        for a in alerts[:30]:  # cap at 30 rows
            ts = a.timestamp.strftime("%Y-%m-%d %H:%M") if a.timestamp else "—"
            alert_data.append([ts, a.alert_type, a.severity, a.message[:60]])

        alert_table = Table(alert_data, colWidths=[4*cm, 3*cm, 2.5*cm, 6.5*cm])
        alert_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), BLUE),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [LGRAY, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("TOPPADDING",  (0,0),(-1,-1), 4),
            ("WORDWRAP",    (3,1), (3,-1), True),
        ]))
        story.append(alert_table)
    else:
        story.append(Paragraph("No alerts for this period.", normal))

    # ─── Telemetry Data Table (latest 50 rows) ────────────────────────────────
    story.append(Paragraph("Recent Telemetry (latest 50 readings)", section_style))
    if records:
        sample = records[:50]
        tbl_data = [["Timestamp", "Light%", "Temp°C", "Hum%", "Voltage", "Power W", "Degrad%"]]
        for r in sample:
            ts = r.timestamp.strftime("%m-%d %H:%M") if r.timestamp else "—"
            tbl_data.append([
                ts,
                f"{r.light_intensity:.1f}" if r.light_intensity else "—",
                f"{r.temperature:.1f}"     if r.temperature     else "—",
                f"{r.humidity:.1f}"        if r.humidity        else "—",
                f"{r.voltage:.1f}"         if r.voltage         else "—",
                f"{r.power:.1f}"           if r.power           else "—",
                f"{r.degradation_pct:.2f}" if r.degradation_pct else "—",
            ])

        data_table = Table(tbl_data, colWidths=[3*cm, 2.2*cm, 2.2*cm, 2*cm, 2.2*cm, 2.2*cm, 2.2*cm])
        data_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), BLUE),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 7.5),
            ("ALIGN",       (1,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [LGRAY, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("TOPPADDING",  (0,0),(-1,-1), 4),
        ]))
        story.append(data_table)

    # ─── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=GRAY))
    story.append(Paragraph(
        "Smart Solar Plug Monitoring System — IoT + ML powered solar health analytics.",
        ParagraphStyle("footer", parent=normal, textColor=GRAY, alignment=TA_CENTER, fontSize=8)
    ))

    doc.build(story)
    return buf.getvalue()
