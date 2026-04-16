"""dashboard.py -- Atlas-H2 Digital Infrastructure Twin v10.0
Streamlit dashboard for the 4-way rail propulsion comparison.

Run with:
    streamlit run dashboard.py
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

import io
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from typing import Dict

from config import cfg, TrainProfile, RouteProfile, ROUTE_SJ_MONCTON
from atlas_engine import (
    PayloadAnalyzer, PayloadAnalysisResult,
    EconomicsEngine, LCOHResult,
    ThermalEfficiencyModule, HeatRecoveryResult,
    SensitivityEngine,
    corridor_trip_energy_kwh,
    apply_degradation,
)
from carbon_abatement import CarbonAbatementCalculator


# chart colors by energy_type

BRAND_COLORS: dict[str, str] = {
    "diesel":   "#64748B",   # Slate gray
    "battery":  "#F59E0B",   # Amber
    "h2_ltpem": "#38BDF8",   # Sky blue
    "h2_htpem": "#10B981",   # Emerald green
}

# tonal palettes for pie slices
BRAND_TONES: dict[str, list[str]] = {
    "h2_ltpem": ["#075985", "#0284C7", "#38BDF8"],
    "h2_htpem": ["#064E3B", "#059669", "#6EE7B7"],
}

# display labels for chart axes and legends
PROFILE_LABELS: dict[str, str] = {
    "diesel":   "Legacy Diesel",
    "battery":  "Battery EV",
    "h2_ltpem": "LTPEM H₂",
    "h2_htpem": "HTPEM H₂",
}


# TOOLTIP DEFINITIONS
# Each help string cites its primary source so users can verify claims independently.
HELP_LCOH = (
    "Levelized Cost of Hydrogen: the all-in cost to produce one kg of H₂, "
    "including amortised equipment cost, annual maintenance, and electricity over the analysis period. "
    "Formula: (Net CAPEX + 10-yr OPEX + 10-yr electricity) ÷ total H₂ produced. "
    "CAPEX source: IRENA (2022) / BNEF H2 Outlook 2024 (C$1,200/kW central estimate). "
    "OPEX: NREL H2A v3.0 (2% of CAPEX/yr). "
    "Electricity: NB Power GRA 2025/26, Schedule 2-B (C$0.1023/kWh). "
    "Federal ITC: Government of Canada Budget 2023 / Bill C-59 (40% of adjusted CAPEX)."
)
HELP_LCOA = (
    "Levelized Cost of Abatement: the net incremental cost to eliminate one tonne of CO₂, "
    "calculated as total H₂ system cost minus avoided diesel purchases divided by CO₂ abated. "
    "A negative value indicates the H₂ system costs less to operate than the diesel baseline. "
    "Diesel CO₂ factor: 2.68 kg CO₂/L tank-to-wheel (Transport Canada GHG Factors 2024). "
    "Diesel consumption: 4.5 L/km (RAC LEM Report 2019). "
    "Carbon price schedule: Canada Carbon Pollution Pricing Act, Schedule 1 (ECCC 2023). "
    "Social cost of carbon: ECCC Technical Update 2023 (C$210/t CO₂e)."
)
HELP_HTPEM = (
    "The core difference lies in the membrane's chemical composition: standard LTPEM units use "
    "a water-saturated polymer (Nafion) that fails if temperatures exceed 80°C and the water "
    "boils off, whereas HTPEM systems utilize an acid-doped PBI membrane. Because this "
    "acid-based chemistry does not rely on water to conduct protons, the fuel cell can maintain "
    "high performance at 160°C, allowing the system to recycle high-grade waste heat and "
    "tolerate lower-purity hydrogen. "
    "Source: Advent Technologies HT-PEM stack (2023); IRENA Green Hydrogen Cost Reduction (2022)."
)
HELP_GRAVIMETRIC = (
    "The reduction in available freight or passenger capacity caused by the mass "
    "of onboard energy storage (batteries or H₂ tanks) relative to the diesel baseline, "
    "which carries negligible storage weight. "
    "Battery density: 250 Wh/kg system-level (CATL Qilin NMC, 2024). "
    "LTPEM system density: 1,500 Wh/kg (Ballard FCmove + Hexagon Purus 700-bar tanks). "
    "HTPEM system density: 1,800 Wh/kg (Advent Technologies + simplified BOP, IRENA 2022). "
    "Train base mass: 114.3 t (Stadler FLIRT H2 3-car consist, 2024)."
)
HELP_CARBON_PRICE = (
    "Federal carbon price for the selected year. "
    "Schedule 2026–2030 confirmed by ECCC regulatory update 2023 "
    "(Canada Carbon Pollution Pricing Act, Schedule 1). "
    "Post-2030 values extrapolated at +C$15/t/yr, consistent with ECCC long-run marginal "
    "abatement cost modelling."
)
HELP_ITC = (
    "40% refundable Investment Tax Credit on eligible clean hydrogen production equipment. "
    "Source: Government of Canada Budget 2023; Income Tax Act s. 127.48 (enacted via Bill C-59, 2024). "
    "The Clean Technology ITC (s. 127.45, 30%) cannot be stacked with this credit."
)
HELP_TANK_RANGE = (
    "Maximum one-way range on a single H₂ fill. "
    "Tank capacity: 56 kg at 700 bar (Hexagon Purus Type IV composite tanks; Stadler Rail 2022). "
    "Consumption: 0.25 kg H₂/km (Alstom Coradia iLint baseline; calibrated to SJ–Moncton profile). "
    "At 155 km, the train uses approximately 38.75 kg — well within the 56 kg tank."
)


# PAGE CONFIG
st.set_page_config(
    page_title="Atlas-H2 | Demilade Giwa",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# UI PALETTE
C_BG      = "#13293D"
C_SURFACE = "#16324F"
C_BORDER  = "#18435A"
C_ACCENT2 = "#2A628F"
C_ACCENT  = "#3E92CC"
C_TEXT    = "#E2E8F0"
C_MUTED   = "#7A9BB5"
C_GREEN   = "#22c55e"
C_RED     = "#f87171"
C_ORANGE  = "#fb923c"

# Shorthand aliases pointing to brand colors
C_HTPEM  = BRAND_COLORS["h2_htpem"]   # "#10B981" emerald
C_LTPEM  = BRAND_COLORS["h2_ltpem"]   # "#38BDF8" sky blue
C_BATT   = BRAND_COLORS["battery"]    # "#F59E0B" amber
C_DIESEL = BRAND_COLORS["diesel"]     # "#64748B" slate


# GLOBAL CSS
st.markdown(f"""
<style>
/* ---- design tokens ---- */
:root {{
  --ease-std:      cubic-bezier(0.2, 0, 0, 1);
  --ease-spring:   cubic-bezier(0.05, 0.7, 0.1, 1);
  --ease-out:      cubic-bezier(0, 0, 0.2, 1);
  --ease-in:       cubic-bezier(0.4, 0, 1, 1);
  --dur-fast:      120ms;
  --dur-mid:       220ms;
  --dur-slow:      380ms;
  --dur-enter:     480ms;
  --radius-sm:     8px;
  --radius-md:     12px;
  --radius-lg:     16px;
  --shadow-low:    0 1px 3px rgba(0,0,0,.18), 0 2px 8px rgba(0,0,0,.12);
  --shadow-mid:    0 4px 16px rgba(0,0,0,.22), 0 8px 32px rgba(0,0,0,.14);
  --shadow-high:   0 8px 28px rgba(0,0,0,.28), 0 16px 56px rgba(0,0,0,.18);
}}
@media (max-width: 768px) {{
  :root {{ --dur-enter: 320ms; }}
}}

/* ---- base ---- */
header[data-testid="stHeader"] {{
    background-color: {C_BG};
    border-bottom: 1px solid {C_BORDER};
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
}}
[data-testid="stToolbar"] {{ background-color: {C_BG}; }}
.stApp {{ background-color: {C_BG}; }}
.main .block-container {{
    background-color: {C_BG};
    padding-top: 1.5rem;
    padding-bottom: 4rem;
    max-width: 100%;
}}
html, body, [class*="css"] {{
    font-family: "Inter", "Google Sans", system-ui, -apple-system, sans-serif;
    color: {C_TEXT};
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}}
h1, h2, h3 {{
    color: {C_TEXT};
    letter-spacing: -0.015em;
    font-weight: 700;
    word-break: break-word;
}}
h1 {{ font-size: 1.5rem; line-height: 1.3; }}
h2 {{ font-size: 1.05rem; }}
h3 {{ font-size: 0.95rem; letter-spacing: 0.01em; }}

/* ---- keyframes ---- */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(20px) scale(0.98); }}
    to   {{ opacity: 1; transform: translateY(0)    scale(1); }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}
@keyframes slideInLeft {{
    from {{ opacity: 0; transform: translateX(-24px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
}}
@keyframes slideInRight {{
    from {{ opacity: 0; transform: translateX(24px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
}}
@keyframes scaleIn {{
    from {{ opacity: 0; transform: scale(0.94); }}
    to   {{ opacity: 1; transform: scale(1); }}
}}
@keyframes floatIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes pulse {{
    0%   {{ box-shadow: 0 0 0 0   {C_GREEN}88; }}
    65%  {{ box-shadow: 0 0 0 7px {C_GREEN}00; }}
    100% {{ box-shadow: 0 0 0 0   {C_GREEN}00; }}
}}
@keyframes accentPulse {{
    0%   {{ box-shadow: 0 0 0 0    {C_ACCENT}44; }}
    65%  {{ box-shadow: 0 0 0 8px  {C_ACCENT}00; }}
    100% {{ box-shadow: 0 0 0 0    {C_ACCENT}00; }}
}}
@keyframes borderGlow {{
    0%, 100% {{ border-color: {C_BORDER};    box-shadow: none; }}
    50%       {{ border-color: {C_ACCENT}55; box-shadow: 0 0 12px {C_ACCENT}18; }}
}}
@keyframes gradientShift {{
    0%   {{ background-position: 0%   50%; }}
    50%  {{ background-position: 100% 50%; }}
    100% {{ background-position: 0%   50%; }}
}}
@keyframes shimmer {{
    0%   {{ background-position: -200% center; }}
    100% {{ background-position:  200% center; }}
}}
@keyframes tabIndicator {{
    from {{ transform: scaleX(0); opacity: 0; }}
    to   {{ transform: scaleX(1); opacity: 1; }}
}}

/* ---- staggered entrance sequences ---- */
.kpi-card {{ animation: fadeInUp var(--dur-enter) var(--ease-spring) both; }}
.kpi-card:nth-child(1) {{ animation-delay: 0ms;   }}
.kpi-card:nth-child(2) {{ animation-delay: 55ms;  }}
.kpi-card:nth-child(3) {{ animation-delay: 110ms; }}
.kpi-card:nth-child(4) {{ animation-delay: 165ms; }}
.kpi-card:nth-child(5) {{ animation-delay: 220ms; }}

[data-baseweb="tab-panel"] > div {{
    animation: fadeInUp 340ms var(--ease-spring) both;
}}
[data-testid="stPlotlyChart"] {{
    animation: slideInLeft 420ms var(--ease-spring) both;
    border-radius: var(--radius-md);
    overflow: hidden;
}}
[data-testid="stVerticalBlock"] > div:last-child [data-testid="stMetric"],
[data-testid="stVerticalBlock"] > div:last-child [data-testid="stDataFrame"] {{
    animation: slideInRight 400ms var(--ease-spring) both;
}}
[data-testid="stDataFrame"] {{
    animation: fadeInUp 360ms var(--ease-spring) both;
}}
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {{
    animation: fadeIn 280ms var(--ease-out) both;
}}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{
    background: {C_SURFACE};
    border-radius: 10px 10px 0 0;
    border-bottom: 1px solid {C_BORDER};
    gap: 2px;
    padding: 5px 8px 0;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 7px 7px 0 0;
    color: {C_MUTED};
    padding: 9px 18px;
    font-size: 0.78rem;
    font-weight: 500;
    letter-spacing: 0.015em;
    border: 1px solid transparent;
    transition:
        color      var(--dur-mid) var(--ease-std),
        background var(--dur-mid) var(--ease-std),
        transform  var(--dur-fast) var(--ease-out);
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {C_TEXT};
    background: {C_ACCENT2}28;
    transform: translateY(-1px);
}}
.stTabs [aria-selected="true"] {{
    background: {C_BG} !important;
    color: {C_HTPEM} !important;
    font-weight: 700;
    border-color: {C_BORDER} {C_BORDER} {C_BG} !important;
    animation: accentPulse 0.9s var(--ease-out) 1;
    position: relative;
}}
.stTabs [aria-selected="true"]::after {{
    content: "";
    position: absolute;
    bottom: -1px; left: 10%; right: 10%;
    height: 2px;
    background: {C_HTPEM};
    border-radius: 2px 2px 0 0;
    animation: tabIndicator 280ms var(--ease-spring) both;
    transform-origin: center;
}}
.legend-pill:nth-child(1) {{ animation-delay: 40ms;  }}
.legend-pill:nth-child(2) {{ animation-delay: 80ms;  }}
.legend-pill:nth-child(3) {{ animation-delay: 120ms; }}
.legend-pill:nth-child(4) {{ animation-delay: 160ms; }}

/* ---- KPI row ---- */
.kpi-row {{
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 8px;
    scrollbar-width: thin;
    scrollbar-color: {C_BORDER} transparent;
}}
.kpi-row::-webkit-scrollbar       {{ height: 3px; }}
.kpi-row::-webkit-scrollbar-track {{ background: transparent; }}
.kpi-row::-webkit-scrollbar-thumb {{ background: {C_BORDER}; border-radius: 4px; }}

.kpi-card {{
    flex: 1 0 190px;
    min-width: 190px;
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-top: 2px solid transparent;
    border-radius: var(--radius-md);
    padding: 20px 18px 15px;
    cursor: default;
    position: relative;
    overflow: hidden;
    will-change: transform, box-shadow;
    transition:
        border-color     var(--dur-slow) var(--ease-std),
        border-top-color var(--dur-slow) var(--ease-std),
        box-shadow       var(--dur-slow) var(--ease-std),
        transform        var(--dur-slow) var(--ease-spring);
}}
.kpi-card::before {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, {C_HTPEM}0a 0%, transparent 60%);
    opacity: 0;
    transition: opacity var(--dur-slow) var(--ease-std);
    pointer-events: none;
}}
.kpi-card::after {{
    content: "";
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, {C_HTPEM}44 50%, transparent 100%);
    opacity: 0;
    transition: opacity var(--dur-slow) var(--ease-std);
}}
.kpi-card:hover {{
    border-top-color: {C_HTPEM};
    border-color: {C_HTPEM}55;
    box-shadow: var(--shadow-mid), inset 0 1px 0 {C_HTPEM}14;
    transform: translateY(-5px) scale(1.01);
}}
.kpi-card:hover::before {{ opacity: 1; }}
.kpi-card:hover::after  {{ opacity: 1; }}

.kpi-label {{
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: {C_MUTED};
    margin-bottom: 8px;
    line-height: 1.25;
}}
.kpi-value {{
    font-size: 1.25rem;
    font-weight: 700;
    color: {C_TEXT};
    letter-spacing: -0.025em;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
}}
.kpi-delta {{
    font-size: 0.74rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 3px;
    line-height: 1.3;
}}
.kpi-delta.pos  {{ color: {C_GREEN};  }}
.kpi-delta.neg  {{ color: {C_RED};    }}
.kpi-delta.neu  {{ color: {C_MUTED};  }}
.kpi-delta.warn {{ color: {C_ORANGE}; }}

/* ---- st.metric ---- */
[data-testid="stMetric"] {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: var(--radius-md);
    padding: 20px 18px;
    will-change: transform, box-shadow;
    animation: fadeInUp 400ms var(--ease-spring) both;
    transition:
        border-color var(--dur-mid) var(--ease-std),
        box-shadow   var(--dur-mid) var(--ease-std),
        transform    var(--dur-mid) var(--ease-spring);
}}
[data-testid="stMetric"]:hover {{
    border-color: {C_HTPEM}44;
    box-shadow: var(--shadow-mid);
    transform: translateY(-3px);
}}
[data-testid="stMetricLabel"] {{
    color: {C_MUTED};
    font-size: 1.1rem !important;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    font-weight: 700;
    line-height: 1.3;
}}
[data-testid="stMetricValue"] {{
    color: {C_TEXT};
    font-weight: 600 !important;
    font-size: 2.2rem !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em;
    line-height: 1.2;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.85rem;
    font-weight: 500;
    line-height: 1.3;
}}

/* ---- sidebar ---- */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] .block-container {{
    background: {C_SURFACE};
    border-right: 1px solid {C_BORDER};
}}
.stExpander {{
    background: {C_BG} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: var(--radius-sm) !important;
    transition:
        border-color var(--dur-mid) var(--ease-std),
        box-shadow   var(--dur-mid) var(--ease-std) !important;
}}
.stExpander:hover {{
    border-color: {C_ACCENT}44 !important;
    box-shadow: 0 0 0 1px {C_ACCENT}18 !important;
}}
.stExpander:focus-within {{
    border-color: {C_HTPEM}66 !important;
    box-shadow: 0 0 0 3px {C_HTPEM}14 !important;
}}
.stExpander summary {{
    color: {C_MUTED};
    font-size: 0.80rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    transition: color var(--dur-fast) var(--ease-out);
}}
.stExpander:hover summary {{ color: {C_TEXT}; }}

/* ---- sliders ---- */
[data-testid="stSlider"] [role="slider"] {{
    transition:
        transform  var(--dur-fast) var(--ease-spring),
        box-shadow var(--dur-fast) var(--ease-std);
}}
[data-testid="stSlider"] [role="slider"]:hover {{
    transform: scale(1.28);
    box-shadow: 0 0 0 8px {C_HTPEM}18;
}}
[data-testid="stSlider"] [role="slider"]:focus-visible {{
    box-shadow: 0 0 0 10px {C_HTPEM}28;
}}

/* ---- buttons ---- */
div[data-testid="stButton"] button,
div[data-testid="stDownloadButton"] button {{
    position: relative;
    overflow: hidden;
    width: 100%;
    background: transparent;
    border: 1px solid {C_BORDER};
    color: {C_MUTED};
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: 0.78rem;
    letter-spacing: 0.04em;
    line-height: 1.3;
    transition:
        border-color var(--dur-mid) var(--ease-std),
        color        var(--dur-mid) var(--ease-std),
        box-shadow   var(--dur-mid) var(--ease-std),
        transform    var(--dur-fast) var(--ease-spring);
}}
div[data-testid="stButton"] button:hover {{
    border-color: {C_HTPEM};
    color: {C_HTPEM};
    box-shadow: 0 0 0 1px {C_HTPEM}33, 0 4px 14px {C_HTPEM}20;
    transform: translateY(-1px);
}}
div[data-testid="stButton"] button:active {{
    transform: translateY(0) scale(0.98);
    transition-duration: var(--dur-fast);
}}
div[data-testid="stDownloadButton"] button {{
    border-color: {C_GREEN}55;
    color: {C_GREEN};
}}
div[data-testid="stDownloadButton"] button:hover {{
    border-color: {C_GREEN};
    box-shadow: 0 0 0 1px {C_GREEN}33, 0 4px 14px {C_GREEN}1a;
    background: {C_GREEN}0a;
    transform: translateY(-1px);
}}

/* ---- misc ---- */
hr {{ border-color: {C_BORDER} !important; opacity: 1 !important; }}
[data-testid="stDataFrame"] {{
    border: 1px solid {C_BORDER};
    border-radius: var(--radius-md);
    overflow: hidden;
    transition: box-shadow var(--dur-mid) var(--ease-std);
}}
[data-testid="stDataFrame"]:hover {{ box-shadow: var(--shadow-low); }}
.stCaption, small {{
    color: {C_MUTED} !important;
    font-size: 0.80rem !important;
    line-height: 1.4;
}}

/* ---- eyebrow / legend / badges ---- */
.eyebrow {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: {C_HTPEM};
    margin-bottom: 4px;
    animation: fadeIn 400ms var(--ease-out) both;
}}
.legend-row {{
    display: flex;
    gap: 7px;
    flex-wrap: wrap;
    margin-bottom: 14px;
    margin-top: 2px;
}}
.legend-pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    animation: scaleIn 300ms var(--ease-spring) both;
    transition:
        opacity    var(--dur-fast) var(--ease-std),
        transform  var(--dur-fast) var(--ease-spring),
        box-shadow var(--dur-fast) var(--ease-std);
}}
.legend-pill:hover {{
    opacity: 0.8;
    transform: scale(0.96);
}}
.route-badge {{
    display: inline-block;
    background: {C_HTPEM}14;
    border: 1px solid {C_HTPEM}38;
    border-radius: 20px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    color: {C_HTPEM};
    letter-spacing: 0.04em;
    animation: floatIn 450ms var(--ease-spring) 80ms both;
    margin-left: 8px;
    vertical-align: middle;
}}
.age-badge {{
    display: inline-block;
    border-radius: 20px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    animation: floatIn 450ms var(--ease-spring) 140ms both;
    margin-left: 6px;
    vertical-align: middle;
}}

/* ---- sidebar status / colour legend ---- */
.status-dot {{
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: {C_GREEN};
    animation: pulse 2.6s var(--ease-out) infinite;
    margin-right: 8px;
    vertical-align: middle;
    flex-shrink: 0;
}}
.status-bar {{
    display: flex;
    align-items: center;
    background: {C_BG};
    border: 1px solid {C_BORDER};
    border-radius: var(--radius-sm);
    padding: 7px 12px;
    font-size: 0.70rem;
    font-weight: 700;
    color: {C_GREEN};
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 10px;
    animation: borderGlow 5.5s var(--ease-std) infinite;
}}
.color-legend {{
    background: {C_BG};
    border: 1px solid {C_BORDER};
    border-radius: var(--radius-sm);
    padding: 12px 14px;
    margin: 0 0 4px;
    transition: border-color var(--dur-mid) var(--ease-std);
}}
.color-legend:hover {{ border-color: {C_ACCENT}44; }}
.color-legend-title {{
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: {C_MUTED};
    margin-bottom: 10px;
}}
.color-legend-row {{
    display: flex;
    align-items: center;
    gap: 9px;
    margin-bottom: 7px;
    font-size: 0.78rem;
    color: {C_TEXT};
    font-weight: 500;
    transition: opacity var(--dur-fast) var(--ease-std);
}}
.color-legend-row:last-child {{ margin-bottom: 0; }}
.color-legend-row:hover {{ opacity: 0.85; }}
.color-swatch {{
    width: 10px; height: 10px;
    border-radius: 3px;
    flex-shrink: 0;
    transition: transform var(--dur-fast) var(--ease-spring);
}}
.color-legend-row:hover .color-swatch {{ transform: scale(1.3); }}
.color-legend-winner {{
    font-size: 0.62rem;
    background: {C_HTPEM}14;
    border: 1px solid {C_HTPEM}33;
    border-radius: 4px;
    padding: 1px 6px;
    color: {C_HTPEM};
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-left: auto;
}}

/* ---- callouts ---- */
.info-callout {{
    background: {C_HTPEM}0a;
    border: 1px solid {C_HTPEM}28;
    border-left: 3px solid {C_HTPEM};
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 16px 20px;
    font-size: 0.95rem;
    color: {C_MUTED};
    line-height: 1.65;
    margin: 10px 0 6px;
    animation: slideInLeft 360ms var(--ease-spring) both;
    transition: box-shadow var(--dur-mid) var(--ease-std);
}}
.info-callout:hover {{ box-shadow: var(--shadow-low); }}
.info-callout strong {{ color: {C_TEXT}; font-weight: 600; }}

.warn-callout {{
    background: {C_ORANGE}0a;
    border: 1px solid {C_ORANGE}28;
    border-left: 3px solid {C_ORANGE};
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 16px 20px;
    font-size: 0.95rem;
    color: {C_MUTED};
    line-height: 1.65;
    margin: 10px 0 6px;
    animation: slideInLeft 360ms var(--ease-spring) both;
}}
.warn-callout strong {{ color: {C_ORANGE}; font-weight: 600; }}

/* ---- section accent ---- */
.section-accent {{
    border-left: 3px solid {C_HTPEM};
    padding-left: 10px;
    margin-bottom: 10px;
    animation: fadeIn 300ms var(--ease-out) both;
}}
.section-accent h3 {{
    margin: 0;
    font-size: 0.88rem;
    color: {C_TEXT};
    font-weight: 700;
}}
.section-accent p {{
    margin: 2px 0 0;
    font-size: 0.75rem;
    color: {C_MUTED};
}}

/* ---- header accent bar ---- */
.header-accent-bar {{
    height: 2px;
    width: 100%;
    border-radius: 2px;
    background: linear-gradient(
        90deg,
        {C_BG}, {C_ACCENT2}, {C_HTPEM}, {C_LTPEM}, {C_ACCENT2}, {C_BG}
    );
    background-size: 400% 100%;
    animation: gradientShift 7s var(--ease-std) infinite;
    margin: 10px 0 20px;
    opacity: 0.90;
}}

/* ---- guide chips ---- */
.how-to-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: {C_HTPEM}10;
    border: 1px solid {C_HTPEM}28;
    border-radius: 20px;
    padding: 6px 13px;
    font-size: 0.76rem;
    font-weight: 600;
    color: {C_HTPEM};
    letter-spacing: 0.02em;
    margin: 4px 4px 4px 0;
    transition:
        background   var(--dur-fast) var(--ease-std),
        border-color var(--dur-fast) var(--ease-std),
        transform    var(--dur-fast) var(--ease-spring),
        box-shadow   var(--dur-fast) var(--ease-std);
}}
.how-to-chip:hover {{
    background: {C_HTPEM}1e;
    border-color: {C_HTPEM}55;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px {C_HTPEM}18;
}}

/* ---- markdown typography ---- */
.stMarkdown p, .stMarkdown li {{
    font-size: 1.15rem !important;
    line-height: 1.6 !important;
    color: {C_TEXT} !important;
}}
.stMarkdown h3 {{
    font-size: 1.4rem !important;
    font-weight: 600 !important;
    color: {C_TEXT} !important;
}}
.stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a {{ display: none !important; }}
</style>
""", unsafe_allow_html=True)


# CONSTANTS
ALL_PROFILES  = cfg.ALL_PROFILES
PROFILE_NAMES = [PROFILE_LABELS[p.energy_type] for p in ALL_PROFILES]
PROFILE_COLORS_LIST = [BRAND_COLORS[p.energy_type] for p in ALL_PROFILES]

PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", size=13, color=C_MUTED),
    title_font=dict(size=14, color=C_TEXT, family="Inter, system-ui, sans-serif", weight="bold"),
    hoverlabel=dict(
        bgcolor=C_SURFACE, bordercolor=C_HTPEM,
        font_size=13, font_family="Inter, system-ui, sans-serif", font_color=C_TEXT,
        namelength=-1,
    ),
    transition=dict(duration=350, easing="cubic-in-out"),
    # global legend: bottom-anchored so it never overlaps chart area on mobile
    legend=dict(
        orientation="h", yanchor="top", y=-0.2, x=0.5, xanchor="center",
        font=dict(size=12, color=C_MUTED, family="Inter, system-ui, sans-serif"),
        bgcolor="rgba(0,0,0,0)",
    ),
)


# SESSION STATE
DEFAULTS: dict = {
    "corridor_km":      int(ROUTE_SJ_MONCTON.corridor_km),
    "system_age_years": 0,
    "electrolyzer_kw":  1000,
    "capacity_factor":  80,
    "fc_power":         int(cfg.TRAIN_POWER_KW),
    "trips_per_year":   ROUTE_SJ_MONCTON.trips_per_year,
    "electricity_rate": cfg.NB_POWER_INDUSTRIAL_RATE,
    "diesel_price":     cfg.DIESEL_PRICE_LITER,
    "fc_efficiency":    int(cfg.FC_SYSTEM_EFFICIENCY * 100),
    "winter_temp":      int(ROUTE_SJ_MONCTON.winter_ambient_temp_c),
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_to_defaults() -> None:
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


# ROUTE LABEL
def route_label(km: int) -> str:
    if 140 <= km <= 170: return f"~Saint John to Moncton ({km} km)"
    if  95 <= km <= 115: return f"~Saint John to Fredericton ({km} km)"
    if 185 <= km <= 215: return f"~Moncton to Charlottetown ({km} km)"
    if km < 95:          return f"~Short Regional ({km} km)"
    if km > 400:         return f"~Long Haul Corridor ({km} km)"
    return f"Custom Route ({km} km)"


# SIDEBAR
with st.sidebar:
    st.markdown(
        '<div class="eyebrow" style="margin-bottom:8px;">Atlas-H2 · By Demilade Giwa</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="status-bar"><span class="status-dot"></span>Live Simulation · Active</div>',
        unsafe_allow_html=True,
    )
    st.button("Reset to Defaults", on_click=reset_to_defaults, use_container_width=True)
    st.divider()

    # color legend
    st.markdown(f"""
    <div class="color-legend">
      <div class="color-legend-title">Colour Key</div>
      <div class="color-legend-row">
        <div class="color-swatch" style="background:{C_DIESEL};"></div>
        <span>Legacy Diesel</span>
        <span style="font-size:0.65rem;color:{C_MUTED};margin-left:auto;">baseline</span>
      </div>
      <div class="color-legend-row">
        <div class="color-swatch" style="background:{C_BATT};"></div>
        <span>Battery Electric</span>
        <span style="font-size:0.65rem;color:{C_MUTED};margin-left:auto;">high weight</span>
      </div>
      <div class="color-legend-row">
        <div class="color-swatch" style="background:{C_LTPEM};"></div>
        <span>LTPEM Hydrogen</span>
        <span style="font-size:0.65rem;color:{C_MUTED};margin-left:auto;">70 °C limit</span>
      </div>
      <div class="color-legend-row">
        <div class="color-swatch" style="background:{C_HTPEM};"></div>
        <span>HTPEM Hydrogen</span>
        <div class="color-legend-winner">RECOMMENDED</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    with st.expander("Route", expanded=True):
        st.slider("Route Distance (km)", 50, 500, step=5, key="corridor_km",
                  help="Corridor length in km. Scales trip energy and HVAC duration proportionally.")
        st.slider("Trips Per Year", 200, 1460, step=10, key="trips_per_year",
                  help="Total one-way trips per year. Default: 730 (2 round trips/day × 365 days).")
        st.slider("Engine Age (years)", 0, 10, step=1, key="system_age_years",
                  help="FC stack efficiency degrades at 1.5%/yr; electrolyzer H₂ yield at 1%/yr.")

    with st.expander("Train", expanded=False):
        st.slider("Engine Power (kW)", 200, 1200, step=50, key="fc_power",
                  help="FC stack rated output. Higher power increases waste heat available for cabin heating.")
        st.slider("Engine Efficiency (%)", 30, 60, step=1, key="fc_efficiency",
                  help=HELP_HTPEM)
        st.slider("Winter Temperature (°C)", -30, 10, step=1, key="winter_temp",
                  help="Ambient design temperature. Drives cabin heating demand via the UA·ΔT model.")

    with st.expander("Hydrogen Plant", expanded=False):
        st.slider("Plant Size (kW)", 250, 5000, step=250, key="electrolyzer_kw",
                  help="Electrolyzer rated capacity. Determines H₂ output volume and total capital cost.")
        st.slider("Plant Utilisation (%)", 40, 95, step=5, key="capacity_factor",
                  help="Fraction of rated hours the plant operates annually. Higher utilisation lowers LCOH.")

    with st.expander("Costs", expanded=False):
        st.slider("Electricity Price (C$/kWh)", 0.05, 0.25, step=0.005,
                  format="C$%.4f", key="electricity_rate",
                  help="Industrial electricity rate. The dominant variable cost driver for LCOH.")
        st.slider("Diesel Price (C$/L)", 1.00, 5.00, step=0.05,
                  format="C$%.2f", key="diesel_price",
                  help="Regional diesel reference price. Scales avoided fuel cost in the LCOA calculation.")

    st.divider()
    st.caption(
        f"Atlas-H2 v10.0 · Federal ITC **{cfg.FEDERAL_H2_ITC*100:.0f}%** · "
        f"NB Grid **{cfg.NB_GRID_CARBON_INTENSITY} kg CO₂/kWh** · "
        f"[Sources: Canada Budget 2023 / ECCC NIR 2023]"
    )


# READ SLIDERS
corridor_km      = st.session_state.get("corridor_km",      DEFAULTS["corridor_km"])
system_age_years = st.session_state.get("system_age_years", DEFAULTS["system_age_years"])
electrolyzer_kw  = st.session_state.get("electrolyzer_kw",  DEFAULTS["electrolyzer_kw"])
capacity_factor  = st.session_state.get("capacity_factor",  DEFAULTS["capacity_factor"])
fc_power         = st.session_state.get("fc_power",         DEFAULTS["fc_power"])
trips_per_year   = st.session_state.get("trips_per_year",   DEFAULTS["trips_per_year"])
electricity_rate = st.session_state.get("electricity_rate", DEFAULTS["electricity_rate"])
diesel_price     = st.session_state.get("diesel_price",     DEFAULTS["diesel_price"])
fc_efficiency    = st.session_state.get("fc_efficiency",    DEFAULTS["fc_efficiency"])
winter_temp      = st.session_state.get("winter_temp",      DEFAULTS["winter_temp"])

electricity_rate = round(electricity_rate, 4)
diesel_price     = round(diesel_price,     4)
trip_energy_kwh  = int(corridor_trip_energy_kwh(corridor_km, ROUTE_SJ_MONCTON))


# run all engines, cached by slider values
@st.cache_data
def run_all(
    corridor_km: int, system_age_years: int, electrolyzer_kw: int,
    capacity_factor_pct: int, fc_power: int, trips_yr: int,
    electricity_rate: float, diesel_price: float, fc_eff_pct: int,
    winter_temp: int,
) -> dict:
    # build a route from the current slider state so all engines share the same source
    route = RouteProfile(
        name="slider",
        corridor_km=float(corridor_km),
        trip_energy_kwh=corridor_trip_energy_kwh(float(corridor_km), ROUTE_SJ_MONCTON),
        winter_ambient_temp_c=float(winter_temp),
        cabin_target_temp_c=ROUTE_SJ_MONCTON.cabin_target_temp_c,
        trips_per_year=trips_yr,
    )
    payload_engine = PayloadAnalyzer(route=route)
    thermal_engine = ThermalEfficiencyModule(fc_power_kw=fc_power, trips_per_year=trips_yr, route=route)
    econ_engine    = EconomicsEngine(
        electrolyzer_size_kw=electrolyzer_kw,
        capacity_factor=capacity_factor_pct / 100.0,
    )
    payload = payload_engine.compare_all_profiles(corridor_km=float(corridor_km))
    thermal = thermal_engine.calculate_all_profiles(
        dynamic_efficiency=fc_eff_pct / 100.0,
        dynamic_ambient_temp=float(winter_temp),
        dynamic_corridor_km=float(corridor_km),
        dynamic_electricity_rate=electricity_rate,
        system_age_years=system_age_years,
    )
    econ_ltpem = econ_engine.calculate_lcoh(
        dynamic_electricity_rate=electricity_rate,
        dynamic_capacity_factor=capacity_factor_pct / 100.0,
        profile=cfg.BASELINE_LTPEM,
        system_age_years=system_age_years,
    )
    econ_htpem = econ_engine.calculate_lcoh(
        dynamic_electricity_rate=electricity_rate,
        dynamic_capacity_factor=capacity_factor_pct / 100.0,
        profile=cfg.INNOVATION_HTPEM,
        system_age_years=system_age_years,
    )
    # annual H2 cost includes amortised CAPEX so LCOA reflects true all-in cost
    annual_h2_cost_cad = (
        econ_htpem.net_capex_after_itc_cad / EconomicsEngine.ANALYSIS_PERIOD_YEARS
        + econ_htpem.annual_opex_cad
        + econ_htpem.annual_electricity_cost_cad
    )
    carbon = CarbonAbatementCalculator(
        route=route,
        annual_h2_cost_cad=annual_h2_cost_cad,
    ).calculate_lifetime(dynamic_diesel_price=diesel_price)
    return dict(payload=payload, thermal=thermal,
                econ_ltpem=econ_ltpem, econ_htpem=econ_htpem, carbon=carbon)


@st.cache_data
def run_sensitivity(
    electrolyzer_kw: int,
    capacity_factor_pct: int,
    system_age_years: int,
    profile: TrainProfile = cfg.INNOVATION_HTPEM,
) -> tuple:
    # profile is TrainProfile (frozen=True, hashable) so Streamlit can key the cache on it
    se = SensitivityEngine()
    rates, capexes, grid = se.compute_lcoh_grid(
        electrolyzer_size_kw=float(electrolyzer_kw),
        capacity_factor=capacity_factor_pct / 100.0,
        profile=profile,
        system_age_years=system_age_years,
    )
    curve = se.compute_degradation_curve(
        electrolyzer_size_kw=float(electrolyzer_kw),
        capacity_factor=capacity_factor_pct / 100.0,
        electricity_rate=cfg.NB_POWER_INDUSTRIAL_RATE,
        capex_per_kw=cfg.ELECTROLYZER_CAPEX_PER_KW,
        profile=profile,
    )
    return rates, capexes, grid, curve


results    = run_all(
    corridor_km, system_age_years, electrolyzer_kw, capacity_factor,
    fc_power, trips_per_year, electricity_rate, diesel_price, fc_efficiency, winter_temp,
)
payload:    Dict[str, PayloadAnalysisResult] = results["payload"]
thermal:    Dict[str, HeatRecoveryResult]    = results["thermal"]
econ_ltpem: LCOHResult                       = results["econ_ltpem"]
econ_htpem: LCOHResult                       = results["econ_htpem"]
carbon                                       = results["carbon"]


# PHYSICAL FEASIBILITY CHECKS
# These run on every slider change and surface st.warning banners when the
# selected corridor parameters approach or exceed physical design limits.

_h2_required_kg: float = cfg.AVG_CONSUMPTION_KG_KM * corridor_km
_battery_mass_kg: float = payload["battery"].storage_system_mass_kg
_htpem_mass_kg: float   = payload["h2_htpem"].storage_system_mass_kg

# Check 1 — H₂ range: does the corridor exceed a single tank fill?
if _h2_required_kg > cfg.TRAIN_H2_TANK_CAPACITY_KG:
    _overage_kg = _h2_required_kg - cfg.TRAIN_H2_TANK_CAPACITY_KG
    st.warning(
        f"**H₂ Range Constraint:** At {corridor_km} km this corridor requires "
        f"{_h2_required_kg:.1f} kg of H₂ per trip, which exceeds the "
        f"{cfg.TRAIN_H2_TANK_CAPACITY_KG:.0f} kg tank capacity by "
        f"{_overage_kg:.1f} kg. "
        f"A mid-corridor refuelling stop or extended tank pack would be required. "
        f"Source: Hexagon Purus 700-bar Type IV tanks; Stadler FLIRT H2 factsheet (2022).",
        icon="⚠️",
    )

# Check 2 — Battery storage mass: does it exceed the structural limit?
if _battery_mass_kg > cfg.STORAGE_MASS_LIMIT_KG:
    _excess_t = (_battery_mass_kg - cfg.STORAGE_MASS_LIMIT_KG) / 1_000.0
    st.warning(
        f"**Battery Payload Infeasibility:** The Battery-EV storage system would weigh "
        f"{_battery_mass_kg:,.0f} kg at {corridor_km} km, exceeding the practical "
        f"onboard storage limit of {cfg.STORAGE_MASS_LIMIT_KG/1000:.0f} t "
        f"by {_excess_t:.1f} t. "
        f"This would breach NB track loading tolerances and cannot be accommodated "
        f"within the Stadler FLIRT H2 3-car consist (base mass {cfg.TRAIN_BASE_MASS_TONNES} t). "
        f"H₂ propulsion is unaffected — HTPEM storage remains "
        f"{_htpem_mass_kg:,.0f} kg at this corridor length.",
        icon="⚠️",
    )

# Check 3 — HTPEM storage mass (long-haul edge case)
if _htpem_mass_kg > cfg.STORAGE_MASS_LIMIT_KG:
    st.warning(
        f"**H₂ Storage Mass Limit:** Even the lighter HTPEM storage system "
        f"({_htpem_mass_kg:,.0f} kg) exceeds the structural limit of "
        f"{cfg.STORAGE_MASS_LIMIT_KG/1000:.0f} t at {corridor_km} km. "
        f"This corridor length would require a purpose-built or articulated consist. "
        f"All LCOH and abatement figures remain mathematically valid but reflect a "
        f"hypothetical configuration beyond current Stadler FLIRT H2 specs.",
        icon="⚠️",
    )


# CSV EXPORT
@st.cache_data
def build_export_csv(
    _corridor_km: int, _system_age_years: int, _electrolyzer_kw: int,
    _capacity_factor: int, _fc_power: int, _trips_per_year: int,
    _electricity_rate: float, _diesel_price: float, _fc_efficiency: int,
    _winter_temp: int,
) -> bytes:
    _results  = run_all(
        _corridor_km, _system_age_years, _electrolyzer_kw, _capacity_factor,
        _fc_power, _trips_per_year, _electricity_rate, _diesel_price,
        _fc_efficiency, _winter_temp,
    )
    _payload = _results["payload"]; _thermal = _results["thermal"]
    _econ_lt = _results["econ_ltpem"]; _econ_ht = _results["econ_htpem"]
    _carbon  = _results["carbon"]
    _trip_kwh = int(corridor_trip_energy_kwh(_corridor_km, ROUTE_SJ_MONCTON))
    rows = []
    for p in ALL_PROFILES:
        pl = _payload[p.energy_type]; th = _thermal[p.energy_type]
        row: dict = {
            "Profile": p.name, "Energy Type": p.energy_type,
            "Corridor (km)": _corridor_km, "Trip Energy (kWh)": _trip_kwh,
            "Stack Age (yr)": _system_age_years,
            "Storage Mass (kg)": pl.storage_system_mass_kg,
            "Freight Loss (t)": pl.freight_capacity_loss_tonnes,
            "Stack Temp (°C)": p.operating_temp_c,
            "FC Efficiency": th.effective_fc_efficiency,
            "Trip Duration (hr)": th.trip_duration_hr,
            "HVAC Penalty kWh/trip": th.hvac_penalty_kwh_per_trip,
            "Heat Recovery kWh/trip": th.electricity_saved_kwh_per_trip,
            "Net Thermal C$/yr": th.net_annual_impact_cad,
            "CO₂ Abated 5yr (t)": _carbon.total_co2_abated_tonnes,
            "Carbon Credits 5yr (C$)": _carbon.total_carbon_credit_value_cad,
            "Avoided Fuel 5yr (C$)": _carbon.total_avoided_fuel_cost_cad,
        }
        if p.energy_type in ("h2_ltpem", "h2_htpem"):
            econ = _econ_lt if p.energy_type == "h2_ltpem" else _econ_ht
            row.update({
                "Fuel Cost per kg (C$)": econ.lcoh_cad_per_kg,
                "Gross Equipment Cost (C$)": econ.electrolyzer_capex_cad,
                "BOP Saving (C$)": econ.bop_saving_cad,
                "Federal ITC Saving (C$)": econ.itc_savings_cad,
                "Net Equipment Cost (C$)": econ.net_capex_after_itc_cad,
                "Annual Power Bill (C$)": econ.annual_electricity_cost_cad,
                "H₂ Yield": econ.effective_h2_efficiency,
            })
        else:
            row.update({k: "N/A" for k in (
                "Fuel Cost per kg (C$)", "Gross Equipment Cost (C$)", "BOP Saving (C$)",
                "Federal ITC Saving (C$)", "Net Equipment Cost (C$)",
                "Annual Power Bill (C$)", "H₂ Yield",
            )})
        rows.append(row)
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


@st.cache_data
def build_feasibility_csv(
    _corridor_km: int, _electrolyzer_kw: int, _capacity_factor: int,
    _trips_per_year: int, _electricity_rate: float, _diesel_price: float,
    _fc_efficiency: int, _winter_temp: int,
) -> bytes:
    """
    Generates a 10-year annual time-series CSV for external analysis.
    Columns: Year, Engine Age, LCOH (C$/kg), H₂ Efficiency (%),
             Annual H₂ Demand (kg), CO₂ Abated (t), NOx Abated (kg),
             Carbon Price (C$/t), Carbon Credits (C$), Avoided Fuel Cost (C$),
             Social Benefit (C$), Cumulative CO₂ Abated (t).
    All values respond to the current sidebar slider state.
    """
    from carbon_abatement import CarbonAbatementCalculator, get_carbon_price

    _route = RouteProfile(
        name="feasibility_export",
        corridor_km=float(_corridor_km),
        trip_energy_kwh=corridor_trip_energy_kwh(float(_corridor_km), ROUTE_SJ_MONCTON),
        winter_ambient_temp_c=float(_winter_temp),
        cabin_target_temp_c=ROUTE_SJ_MONCTON.cabin_target_temp_c,
        trips_per_year=_trips_per_year,
    )
    _econ = EconomicsEngine(
        electrolyzer_size_kw=float(_electrolyzer_kw),
        electricity_rate=_electricity_rate,
        capacity_factor=_capacity_factor / 100.0,
    )
    _annual_h2_cost_base = (
        _econ.calculate_lcoh(
            dynamic_electricity_rate=_electricity_rate,
            profile=cfg.INNOVATION_HTPEM,
            system_age_years=0,
        ).net_capex_after_itc_cad / EconomicsEngine.ANALYSIS_PERIOD_YEARS
        + _econ.calculate_lcoh(
            dynamic_electricity_rate=_electricity_rate,
            profile=cfg.INNOVATION_HTPEM,
            system_age_years=0,
        ).annual_opex_cad
        + _econ.calculate_lcoh(
            dynamic_electricity_rate=_electricity_rate,
            profile=cfg.INNOVATION_HTPEM,
            system_age_years=0,
        ).annual_electricity_cost_cad
    )
    _abatement = CarbonAbatementCalculator(
        route=_route,
        annual_h2_cost_cad=_annual_h2_cost_base,
    )

    rows: list[dict] = []
    cumulative_co2 = 0.0
    start_year = 2026

    for age in range(EconomicsEngine.ANALYSIS_PERIOD_YEARS):
        _year = start_year + age
        _lcoh_r = _econ.calculate_lcoh(
            dynamic_electricity_rate=_electricity_rate,
            profile=cfg.INNOVATION_HTPEM,
            system_age_years=age,
        )
        # H₂ demand scales inversely with FC efficiency degradation
        _base_fc_eff = _fc_efficiency / 100.0
        _degraded_eff = apply_degradation(_base_fc_eff, age)
        _base_demand_kg = cfg.AVG_CONSUMPTION_KG_KM * _corridor_km * _trips_per_year
        _annual_demand_kg = _base_demand_kg * (_base_fc_eff / _degraded_eff)

        _ann = _abatement.calculate_annual(_year, dynamic_diesel_price=_diesel_price)
        cumulative_co2 += _ann.co2_abated_tonnes

        rows.append({
            "Year":                    _year,
            "Engine Age (yr)":         age,
            "LCOH (C$/kg)":            round(_lcoh_r.lcoh_cad_per_kg, 4),
            "H2 Electrolyzer Yield (%)": round(_lcoh_r.effective_h2_efficiency * 100, 2),
            "FC Efficiency (%)":       round(_degraded_eff * 100, 2),
            "Annual H2 Demand (kg)":   round(_annual_demand_kg, 1),
            "CO2 Abated (t)":          _ann.co2_abated_tonnes,
            "NOx Abated (kg)":         _ann.nox_abated_kg,
            "Carbon Price (C$/t)":     _ann.carbon_price_cad_per_tonne,
            "Carbon Credits (C$)":     _ann.carbon_credit_value_cad,
            "Avoided Fuel Cost (C$)":  _ann.avoided_fuel_cost_cad,
            "Social Benefit (C$)":     _ann.social_benefit_cad,
            "Cumulative CO2 Abated (t)": round(cumulative_co2, 2),
        })

    _buf = io.StringIO()
    pd.DataFrame(rows).to_csv(_buf, index=False)
    return _buf.getvalue().encode()


with st.sidebar:
    st.divider()
    st.download_button(
        label="Export Full Report (CSV)",
        data=build_export_csv(
            corridor_km, system_age_years, electrolyzer_kw, capacity_factor,
            fc_power, trips_per_year, electricity_rate, diesel_price, fc_efficiency, winter_temp,
        ),
        file_name=f"AtlasH2_Report_{corridor_km}km_age{system_age_years}yr.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        label="Download Feasibility Data (10-Year CSV)",
        data=build_feasibility_csv(
            corridor_km, electrolyzer_kw, capacity_factor,
            trips_per_year, electricity_rate, diesel_price, fc_efficiency, winter_temp,
        ),
        file_name=f"AtlasH2_Feasibility_{corridor_km}km_10yr.csv",
        mime="text/csv",
        use_container_width=True,
        help=(
            "Annual simulation over a 10-year horizon: LCOH, H₂ demand, CO₂ abated, "
            "carbon credits, and avoided fuel cost — updated to your current sidebar settings. "
            "Use this data for external NPV modelling, grant applications, or regulatory filings."
        ),
    )


# HELPERS
def kpi_row(cards: list[dict]) -> None:
    html = '<div class="kpi-row">'
    for c in cards:
        dc    = c.get("delta_class", "pos")
        arrow = "↓" if dc == "neg" else "↑"
        html += (
            f'<div class="kpi-card">'
            f'  <div class="kpi-label">{c["label"]}</div>'
            f'  <div class="kpi-value">{c["value"]}</div>'
            f'  <div class="kpi-delta {dc}">{arrow} {c["delta"]}</div>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def profile_legend() -> None:
    pills = "".join(
        f'<span class="legend-pill" '
        f'style="background:{BRAND_COLORS[p.energy_type]}18;'
        f'border:1px solid {BRAND_COLORS[p.energy_type]}88;'
        f'color:{BRAND_COLORS[p.energy_type]}">'
        f'● {PROFILE_LABELS[p.energy_type]}</span>'
        for p in ALL_PROFILES
    )
    st.markdown(f'<div class="legend-row">{pills}</div>', unsafe_allow_html=True)


def _axis(fig: go.Figure, x_grid: bool = False, y_grid: bool = False) -> None:
    fig.update_xaxes(
        showgrid=x_grid, zeroline=False, automargin=True,
        linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
    )
    fig.update_yaxes(
        showgrid=y_grid, gridcolor="rgba(24,67,90,0.53)", automargin=True,
        zeroline=False, tickfont_color=C_MUTED,
    )


def _axis_lines(fig: go.Figure) -> None:
    fig.update_xaxes(
        showgrid=False, zeroline=False, automargin=True,
        linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="rgba(24,67,90,0.40)", automargin=True,
        zeroline=False, tickfont_color=C_MUTED,
    )


# PAGE HEADER
age_color      = C_GREEN if system_age_years == 0 else (C_ORANGE if system_age_years < 6 else C_RED)
age_badge_text = (
    "New Engine"
    if system_age_years == 0
    else f"Year {system_age_years} · H₂ efficiency {econ_htpem.effective_h2_efficiency*100:.1f}%"
)

st.markdown('<p class="eyebrow">Atlas-H2 · Digital Infrastructure Twin · v10.0</p>', unsafe_allow_html=True)
st.markdown('<h1 style="margin-bottom: 1rem;">4-Way Rail Propulsion Comparison — SJ–Moncton Corridor</h1>', unsafe_allow_html=True)
st.markdown(
    f"<span style='color:{C_MUTED}'>Technologies evaluated: &nbsp;</span>"
    f"<span style='color:{C_DIESEL};font-weight:600;'>Diesel</span>"
    f"<span style='color:{C_MUTED}'> &nbsp;·&nbsp; </span>"
    f"<span style='color:{C_BATT};font-weight:600;'>Battery Electric</span>"
    f"<span style='color:{C_MUTED}'> &nbsp;·&nbsp; </span>"
    f"<span style='color:{C_LTPEM};font-weight:600;'>LTPEM Hydrogen</span>"
    f"<span style='color:{C_MUTED}'> &nbsp;·&nbsp; </span>"
    f"<span style='color:{C_HTPEM};font-weight:700;'>HTPEM Hydrogen</span>"
    f'<span class="route-badge">{route_label(corridor_km)}</span>'
    f'<span class="age-badge" style="background:{age_color}18;border:1px solid {age_color}44;'
    f'color:{age_color}">{age_badge_text}</span>',
    unsafe_allow_html=True,
)
st.markdown('<div class="header-accent-bar"></div>', unsafe_allow_html=True)


# KPI ROW
htpem_payload   = payload["h2_htpem"]
htpem_thermal   = thermal["h2_htpem"]
ltpem_thermal   = thermal["h2_ltpem"]
battery_loss_t  = payload["battery"].freight_capacity_loss_tonnes
htpem_loss_t    = htpem_payload.freight_capacity_loss_tonnes
freight_saved_t = battery_loss_t - htpem_loss_t
thermal_swing   = htpem_thermal.net_annual_impact_cad - ltpem_thermal.net_annual_impact_cad
lcoh_delta      = econ_ltpem.lcoh_cad_per_kg - econ_htpem.lcoh_cad_per_kg

kpi_row([
    {
        "label": "HTPEM LCOH",
        "value": f"C${econ_htpem.lcoh_cad_per_kg:.2f} /kg",
        "delta": f"C${lcoh_delta:.2f} below LTPEM",
        "delta_class": "pos",
    },
    {
        "label": "Payload Advantage vs Battery",
        "value": f"{freight_saved_t:.2f} t / trip",
        "delta": f"{corridor_km} km corridor",
        "delta_class": "pos",
    },
    {
        "label": "CO₂ Abated — 5-Year Total",
        "value": f"{carbon.total_co2_abated_tonnes:,.0f} t",
        "delta": f"equiv. {carbon.equivalent_cars_removed:,} passenger cars/yr",
        "delta_class": "pos",
    },
    {
        "label": "Available Incentives",
        "value": f"C${econ_htpem.itc_savings_cad + econ_htpem.bop_saving_cad:,.0f}",
        "delta": f"40% Federal ITC + C${econ_htpem.bop_saving_cad:,.0f} BOP reduction",
        "delta_class": "pos",
    },
    {
        "label": "Annual Thermal Advantage",
        "value": f"C${thermal_swing:,.0f} /yr",
        "delta": "HTPEM vs LTPEM — no electric HVAC draw",
        "delta_class": "pos" if system_age_years == 0 else "warn",
    },
])

st.divider()


# TABS
tab_guide, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Guide",
    "Weight Penalty",
    "Fuel Cost",
    "Winter Heating",
    "Carbon Impact",
    "Sensitivity",
])


# TAB 0 · GUIDE

with tab_guide:

    # header panel
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {C_SURFACE} 0%, {C_ACCENT2}3a 55%, {C_SURFACE} 100%);
        border: 1px solid {C_HTPEM}2a;
        border-radius: 14px;
        padding: 30px 34px 26px;
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
        animation: fadeInUp 0.50s cubic-bezier(0.22,1,0.36,1) both;">
      <div style="
          position:absolute;inset:0;
          background:linear-gradient(108deg,transparent 38%,{C_HTPEM}07 50%,transparent 62%);
          background-size:250% 100%;
          animation:shimmer 6s ease infinite;
          pointer-events:none;border-radius:14px;"></div>
      <div style="position:relative;">
        <p style="margin:0 0 7px;font-size:0.62rem;font-weight:700;letter-spacing:0.18em;
                  text-transform:uppercase;color:{C_HTPEM};">
          Atlas-H2 &nbsp;&middot;&nbsp; Python-Based Simulation
        </p>
        <h2 style="margin:0 0 10px;font-size:1.42rem;font-weight:800;color:{C_TEXT};
                   line-height:1.2;letter-spacing:-0.02em;">
          4-Way Rail Propulsion Comparison — SJ–Moncton Corridor
        </h2>
        <p style="margin:0 0 16px;font-size:0.88rem;color:{C_MUTED};line-height:1.65;max-width:720px;">
          This study evaluates Diesel, Battery-EV, LTPEM Hydrogen, and HTPEM Hydrogen propulsion
          on three quantitative dimensions: storage mass penalty, thermal energy balance,
          and levelized fuel cost. All parameters are adjustable via the sidebar.
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <div style="background:{C_BG};border:1px solid {C_BORDER};border-radius:8px;
                      padding:8px 16px;font-size:0.78rem;color:{C_TEXT};font-weight:600;">
            {route_label(corridor_km)}
          </div>
          <div style="background:{C_BG};border:1px solid {C_BORDER};border-radius:8px;
                      padding:8px 16px;font-size:0.78rem;color:{C_TEXT};font-weight:600;">
            Winter design temperature: {winter_temp} °C
          </div>
          <div style="background:{C_HTPEM}18;border:1px solid {C_HTPEM}33;border-radius:8px;
                      padding:8px 16px;font-size:0.78rem;color:{C_HTPEM};font-weight:700;">
            HTPEM LCOH: C${econ_htpem.lcoh_cad_per_kg:.2f}/kg
          </div>
          <div style="background:{C_GREEN}10;border:1px solid {C_GREEN}33;border-radius:8px;
                      padding:8px 16px;font-size:0.78rem;color:{C_GREEN};font-weight:700;">
            CO₂ abated (5 yr): {carbon.total_co2_abated_tonnes:,.0f} t
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # membrane chemistry explanation
    st.markdown(f"""
    <p style="margin:0 0 14px;font-size:0.62rem;font-weight:700;letter-spacing:0.16em;
              text-transform:uppercase;color:{C_LTPEM}aa;">Fuel Cell Technology: Membrane Chemistry</p>
    <div class="info-callout">
      <strong>Why HTPEM outperforms LTPEM in sub-zero rail service:</strong>
      The core difference lies in the membrane's chemical composition: standard LTPEM units use
      a water-saturated polymer (Nafion) that fails if temperatures exceed 80°C and the water
      boils off, whereas HTPEM systems utilize an acid-doped PBI membrane. Because this
      acid-based chemistry does not rely on water to conduct protons, the fuel cell can maintain
      high performance at 160°C, allowing the system to recycle high-grade waste heat and
      tolerate lower-purity hydrogen. On the SJ–Moncton corridor, this translates to three
      measurable advantages: the 160°C exhaust fully covers the 30°C cabin heating load
      (eliminating the 50 kW electric HVAC draw), the simplified balance-of-plant removes the
      PSA purification unit (15% CAPEX reduction), and the higher operating temperature enables
      a more energy-dense storage system (1,800 vs 1,500 Wh/kg).
    </div>
    """, unsafe_allow_html=True)

    # thermal constraint cards
    st.markdown(f"""
    <p style="margin:18px 0 14px;font-size:0.62rem;font-weight:700;letter-spacing:0.16em;
              text-transform:uppercase;color:{C_RED}aa;">Thermal Constraint: Sub-Zero Operation</p>
    """, unsafe_allow_html=True)

    wall_cards = [
        (C_RED, "01 — Winter Heating Load",
         "Battery-EV and LTPEM incur a mandatory electric heating penalty.",
         f"At {winter_temp} °C, cabin heating requires {cfg.BASELINE_LTPEM.hvac_power_draw_kw:.0f} kW "
         f"of continuous power. Battery-EV and LTPEM stacks cannot supply this from waste heat, "
         f"so they draw from their traction energy store on every trip. "
         f"This increases effective energy consumption and reduces available payload capacity.",
         "0.06s"),
        (C_ORANGE, "02 — LTPEM Stack Temperature Limitation",
         "LTPEM stack operating temperature (70 °C) is below the cabin heating threshold.",
         f"Cabin heating requires a supply temperature above approximately 55–60 °C. "
         f"LTPEM stacks (Ballard FCmove architecture) operate at 70 °C — marginal at best "
         f"and insufficient at higher flow rates. In practice, a separate "
         f"{cfg.BASELINE_LTPEM.hvac_power_draw_kw:.0f} kW electric HVAC unit is required, "
         f"identical to the Battery-EV penalty.",
         "0.14s"),
        (C_MUTED, "03 — Quantified Impact",
         f"Storage penalty: Battery-EV {battery_loss_t:.2f} t, HTPEM {htpem_loss_t:.2f} t per trip.",
         f"Across {trips_per_year:,} annual trips at C${electricity_rate:.4f}/kWh, "
         f"the electric HVAC draw costs approximately C${ltpem_thermal.hvac_annual_cost_cad:,.0f}/yr "
         f"for both LTPEM and Battery-EV configurations. "
         f"HTPEM avoids this cost entirely through waste heat recovery.",
         "0.22s"),
    ]

    for num_str, tag, headline, body, delay in wall_cards:
        st.markdown(f"""
        <div style="
            display:flex;gap:14px;align-items:flex-start;
            background:{C_SURFACE};border:1px solid {C_BORDER};
            border-left:3px solid {C_RED};
            border-radius:0 12px 12px 0;
            padding:17px 19px;margin-bottom:10px;
            transition:border-color 0.28s cubic-bezier(0.22,1,0.36,1),
                       box-shadow 0.28s ease,transform 0.28s cubic-bezier(0.22,1,0.36,1);
            animation:fadeInUp 0.42s cubic-bezier(0.22,1,0.36,1) both;
            animation-delay:{delay};">
          <div style="flex-shrink:0;width:32px;height:32px;border-radius:9px;
              background:{C_RED}15;border:1px solid {C_RED}33;
              display:flex;align-items:center;justify-content:center;
              font-size:0.62rem;font-weight:800;color:{C_RED};
              letter-spacing:0.04em;margin-top:1px;">{num_str[:2]}</div>
          <div style="min-width:0;">
            <p style="margin:0 0 3px;font-size:0.62rem;font-weight:700;
                      letter-spacing:0.10em;text-transform:uppercase;color:{C_RED}99;">{tag}</p>
            <p style="margin:0 0 7px;font-size:0.88rem;font-weight:700;
                      color:{C_TEXT};line-height:1.3;">{headline}</p>
            <p style="margin:0;font-size:0.82rem;color:{C_MUTED};line-height:1.62;">{body}</p>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # navigation chips
    st.markdown(f"""
    <div style="
        background:{C_SURFACE};border:1px solid {C_BORDER};
        border-radius:12px;padding:20px 24px;margin-top:6px;
        animation:fadeInUp 0.46s cubic-bezier(0.22,1,0.36,1) both;animation-delay:0.32s;">
      <p style="margin:0 0 10px;font-size:0.62rem;font-weight:700;letter-spacing:0.16em;
                text-transform:uppercase;color:{C_HTPEM};">Navigation</p>
      <p style="margin:0 0 6px;font-size:0.88rem;color:{C_TEXT};font-weight:600;">
        All displayed values update in response to the sidebar sliders.
      </p>
      <p style="margin:0 0 14px;font-size:0.84rem;color:{C_MUTED};line-height:1.6;max-width:820px;">
        Adjust the <strong style="color:{C_TEXT};">Winter Temperature</strong> slider to vary
        the HVAC heating demand. Adjust <strong style="color:{C_TEXT};">Electricity Price</strong>
        to stress-test the LCOH and LCOA figures. Each tab below isolates one evaluation dimension.
      </p>
      <div style="display:flex;flex-wrap:wrap;gap:8px;">
        <span class="how-to-chip">Weight Penalty — Storage mass vs diesel baseline</span>
        <span class="how-to-chip">Fuel Cost — LCOH breakdown: CAPEX, OPEX, electricity</span>
        <span class="how-to-chip">Winter Heating — Annual thermal energy balance</span>
        <span class="how-to-chip">Carbon Impact — CO₂ abated and net abatement cost</span>
        <span class="how-to-chip">Sensitivity — LCOH grid across electricity rate and CAPEX</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # glossary cards
    st.markdown("<br>", unsafe_allow_html=True)
    gc1, gc2, gc3, gc4 = st.columns(4)
    gloss = [
        (gc1, "LCOH", "Levelized Cost of Hydrogen", HELP_LCOH, C_HTPEM, "0.36s"),
        (gc2, "LCOA", "Levelized Cost of Abatement", HELP_LCOA, C_LTPEM, "0.42s"),
        (gc3, "HTPEM vs LTPEM", "Membrane Chemistry", HELP_HTPEM, C_ORANGE, "0.48s"),
        (gc4, "Gravimetric Penalty", "Storage Mass vs Diesel", HELP_GRAVIMETRIC, C_MUTED, "0.54s"),
    ]
    for col, term, subtitle, defn, color, delay in gloss:
        with col:
            col.markdown(f"""
            <div style="background:{C_BG};border:1px solid {C_BORDER};
                        border-top:2px solid {color};
                        border-radius:0 0 10px 10px;padding:14px 15px;
                        animation:fadeInUp 0.4s cubic-bezier(0.22,1,0.36,1) both;
                        animation-delay:{delay};">
              <p style="margin:0 0 3px;font-size:0.85rem;font-weight:700;
                        color:{color};letter-spacing:-0.01em;">{term}</p>
              <p style="margin:0 0 8px;font-size:0.72rem;color:{C_MUTED};
                        font-weight:500;">{subtitle}</p>
              <p style="margin:0;font-size:0.80rem;font-weight:400;color:{C_MUTED};
                        line-height:1.58;">{defn}</p>
            </div>
            """, unsafe_allow_html=True)


# TAB 1 · WEIGHT PENALTY (Payload)

with tab1:
    with st.container():
        st.subheader("Weight Penalty — How Much Cargo Capacity Does Each Technology Lose?")
        st.caption(
            f"Based on {trip_energy_kwh:,} kWh needed per trip · {corridor_km} km corridor · "
            f"Diesel = zero reference (fuel tank weight is negligible)"
        )
        profile_legend()

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        loss_values = [payload[p.energy_type].freight_capacity_loss_tonnes for p in ALL_PROFILES]
        fig_payload = go.Figure(go.Bar(
            x=PROFILE_NAMES, y=loss_values,
            marker_color=PROFILE_COLORS_LIST, marker_line_width=0,
            text=[f"−{v:.2f} t" if v > 0 else "Ref." for v in loss_values],
            textposition="outside", textfont=dict(size=12, color=C_TEXT, family="Inter, system-ui, sans-serif"),
            width=0.5, cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Cargo Lost: <b>%{y:.3f} tonnes</b><extra></extra>",
        ))
        fig_payload.update_layout(
            **PLOTLY_BASE,
            title=dict(text=f"Tonnes of Cargo Lost Due to Equipment Weight — {corridor_km} km Route", font_size=13, font_color=C_TEXT),
            height=460, margin=dict(t=50, b=80, l=60, r=20),
            yaxis_title=dict(text="Tonnes of Cargo Lost", font_size=12, font_color=C_MUTED),
            xaxis_title=None, showlegend=False,
        )
        fig_payload.update_xaxes(
            tickfont=dict(color=C_MUTED, size=11), linewidth=2, linecolor=C_BORDER,
            gridwidth=1, gridcolor="rgba(24,67,90,0.25)",
        )
        fig_payload.update_yaxes(
            zeroline=True, zerolinecolor=C_BORDER, zerolinewidth=2,
            tickfont=dict(color=C_MUTED, size=11),
            gridcolor="rgba(24,67,90,0.25)", gridwidth=1, linewidth=2, linecolor=C_BORDER,
        )
        st.plotly_chart(fig_payload, use_container_width=True, config={"displayModeBar": False})

    with col_panel:
        st.markdown(
            f'<div class="section-accent"><h3>Storage System Comparison</h3>'
            f'<p>Why batteries carry the largest mass penalty</p></div>',
            unsafe_allow_html=True,
        )
        rows = []
        for p in ALL_PROFILES:
            r = payload[p.energy_type]
            rows.append({
                "Technology": PROFILE_LABELS[p.energy_type],
                "Energy Density": "— diesel" if p.energy_type == "diesel"
                                  else f"{p.system_energy_density_wh_kg:,.0f} Wh/kg",
                "System Weight": "~0 kg" if p.energy_type == "diesel"
                                 else f"{r.storage_system_mass_kg:,.0f} kg",
                "Cargo Lost": "Baseline" if p.energy_type == "diesel"
                              else f"−{r.freight_capacity_loss_tonnes:.3f} t",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Technology"), use_container_width=True)
        st.divider()
        htpem_vs_ltpem = payload["h2_ltpem"].freight_capacity_loss_tonnes - htpem_loss_t
        st.metric("HTPEM vs Battery EV",
                  f"−{freight_saved_t:.2f} t",
                  "more cargo capacity per trip",
                  help=HELP_GRAVIMETRIC)
        st.metric("HTPEM vs Low-Temp H₂",
                  f"−{htpem_vs_ltpem:.3f} t",
                  "higher energy density storage system",
                  help=HELP_GRAVIMETRIC)
        st.markdown(
            f'<div class="info-callout">'
            f'<strong>Why does this matter?</strong> '
            f'Every tonne of batteries or tanks added is a tonne of revenue-generating '
            f'cargo removed. On a commercial route, this directly impacts the economics.'
            f'</div>',
            unsafe_allow_html=True,
        )


# TAB 2 · FUEL COST (LCOH)

with tab2:
    age_note = (
        f" · H₂ efficiency {econ_htpem.effective_h2_efficiency*100:.1f}% (aged engine)"
        if system_age_years > 0 else ""
    )
    with st.container():
        st.subheader("Hydrogen Fuel Cost — What Does It Cost to Make the Fuel On-Site?")
        st.caption(
            f"{electrolyzer_kw:,} kW plant · {capacity_factor}% utilisation · "
            f"C${electricity_rate:.4f}/kWh electricity{age_note}"
        )

    col_lt, col_ht, col_panel = st.columns([1.0, 1.0, 0.85])

    with col_lt:
        fig_lt = go.Figure(go.Pie(
            labels=["Equipment (net)", "10-yr Maintenance", "10-yr Power Bill"],
            values=[
                econ_ltpem.net_capex_after_itc_cad,
                econ_ltpem.annual_opex_cad * 10,
                econ_ltpem.annual_electricity_cost_cad * 10,
            ],
            hole=0.56,
            marker_colors=["#075985", "#0284C7", "#38BDF8"],
            marker_line=dict(color=C_BG, width=2),
            textinfo="percent", textfont=dict(size=14, color=C_TEXT, family="Inter, system-ui, sans-serif"),
            hovertemplate="<b>%{label}</b><br>C$%{value:,.0f} · %{percent}<extra></extra>",
        ))
        fig_lt.update_layout(
            **PLOTLY_BASE,
            title=dict(text=f"Low-Temp H₂ · C${econ_ltpem.lcoh_cad_per_kg:.2f} per kg", font_size=13, font_color=C_TEXT),
            height=320, margin=dict(t=50, b=20, l=8, r=8), showlegend=False,
            annotations=[dict(
                text=f"<b>C${econ_ltpem.total_10yr_cost_cad/1e6:.2f}M</b><br><span style='font-size:11px'>10-yr total</span>",
                x=0.5, y=0.5, font=dict(size=14, color=C_TEXT, family="Inter, system-ui, sans-serif"), showarrow=False,
            )],
        )
        st.plotly_chart(fig_lt, use_container_width=True, config={"displayModeBar": False})

    with col_ht:
        fig_ht = go.Figure(go.Pie(
            labels=["Equipment (net)", "10-yr Maintenance", "10-yr Power Bill"],
            values=[
                econ_htpem.net_capex_after_itc_cad,
                econ_htpem.annual_opex_cad * 10,
                econ_htpem.annual_electricity_cost_cad * 10,
            ],
            hole=0.56,
            marker_colors=["#064E3B", "#059669", "#6EE7B7"],
            marker_line=dict(color=C_BG, width=2),
            textinfo="percent", textfont=dict(size=14, color=C_TEXT, family="Inter, system-ui, sans-serif"),
            hovertemplate="<b>%{label}</b><br>C$%{value:,.0f} · %{percent}<extra></extra>",
        ))
        fig_ht.update_layout(
            **PLOTLY_BASE,
            title=dict(text=f"HTPEM H₂ (Recommended) · C${econ_htpem.lcoh_cad_per_kg:.2f} per kg", font_size=13, font_color=C_TEXT),
            height=320, margin=dict(t=50, b=20, l=8, r=8), showlegend=False,
            annotations=[dict(
                text=f"<b>C${econ_htpem.total_10yr_cost_cad/1e6:.2f}M</b><br><span style='font-size:11px'>10-yr total</span>",
                x=0.5, y=0.5, font=dict(size=14, color=C_TEXT, family="Inter, system-ui, sans-serif"), showarrow=False,
            )],
        )
        st.plotly_chart(fig_ht, use_container_width=True, config={"displayModeBar": False})

    with col_panel:
        st.markdown(
            f'<div class="section-accent"><h3>Cost Breakdown</h3>'
            f'<p>Low-Temp vs High-Temp over 10 years</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"""
| Cost Item | LTPEM | HTPEM |
|--|--:|--:|
| Equipment cost | C${econ_ltpem.electrolyzer_capex_cad:,.0f} | C${econ_htpem.electrolyzer_capex_cad:,.0f} |
| Equipment saving | — | **C${econ_htpem.bop_saving_cad:,.0f}** |
| Federal grant (40%) | C${econ_ltpem.itc_savings_cad:,.0f} | C${econ_htpem.itc_savings_cad:,.0f} |
| Net equipment cost | C${econ_ltpem.net_capex_after_itc_cad:,.0f} | C${econ_htpem.net_capex_after_itc_cad:,.0f} |
| Annual maintenance | C${econ_ltpem.annual_opex_cad:,.0f} | C${econ_htpem.annual_opex_cad:,.0f} |
| Annual power bill | C${econ_ltpem.annual_electricity_cost_cad:,.0f} | C${econ_htpem.annual_electricity_cost_cad:,.0f} |
| H₂ output rate | {econ_ltpem.effective_h2_efficiency*100:.1f}% | {econ_htpem.effective_h2_efficiency*100:.1f}% |
| **Fuel cost per kg** | **C${econ_ltpem.lcoh_cad_per_kg:.4f}** | **C${econ_htpem.lcoh_cad_per_kg:.4f}** |
        """)
        st.divider()
        st.metric(
            "High-Temp Cost Advantage",
            f"C${lcoh_delta:.4f} cheaper per kg",
            f"{lcoh_delta / econ_ltpem.lcoh_cad_per_kg * 100:.1f}% lower fuel cost than Low-Temp",
            help=HELP_LCOH,
        )


# TAB 3 · WINTER HEATING (Thermal)

with tab3:
    trip_dur = thermal["h2_htpem"].trip_duration_hr
    with st.container():
        st.subheader("Winter Heating Cost — The Annual Bill for Keeping Passengers Warm")
        st.caption(
            f"At {winter_temp} °C · {trips_per_year:,} trips/yr · "
            f"{trip_dur:.2f} hr average trip · electricity C${electricity_rate:.4f}/kWh"
        )
        profile_legend()

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        net_impacts = [thermal[p.energy_type].net_annual_impact_cad for p in ALL_PROFILES]
        bar_colors  = [
            BRAND_COLORS[p.energy_type] if thermal[p.energy_type].net_annual_impact_cad >= 0 else C_RED
            for p in ALL_PROFILES
        ]
        fig_net = go.Figure(go.Bar(
            x=PROFILE_NAMES, y=net_impacts,
            marker_color=bar_colors, marker_line_width=0,
            text=[f"C${v:+,.0f}" for v in net_impacts],
            textposition="outside", textfont=dict(size=12, color=C_TEXT, family="Inter, system-ui, sans-serif"),
            width=0.5, cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Net Annual Heating Impact: <b>C$%{y:+,.0f}</b><extra></extra>",
        ))
        fig_net.add_hline(y=0, line_width=2, line_color=C_BORDER)
        fig_net.update_layout(
            **PLOTLY_BASE,
            title=dict(text=f"Annual Heating Savings (+) or Cost (−) per Technology — {corridor_km} km", font_size=13, font_color=C_TEXT),
            yaxis_title=dict(text="C$ per Year", font_size=12, font_color=C_MUTED),
            xaxis_title=None,
            height=400, margin=dict(t=50, b=80, l=60, r=20), showlegend=False,
        )
        fig_net.update_xaxes(
            tickfont=dict(color=C_MUTED, size=11), linewidth=2, linecolor=C_BORDER,
            gridwidth=1, gridcolor="rgba(24,67,90,0.25)",
        )
        fig_net.update_yaxes(
            tickfont=dict(color=C_MUTED, size=11), gridcolor="rgba(24,67,90,0.25)",
            gridwidth=1, linewidth=2, linecolor=C_BORDER,
        )
        st.plotly_chart(fig_net, use_container_width=True, config={"displayModeBar": False})

        fig_stack = go.Figure()
        fig_stack.add_bar(
            x=PROFILE_NAMES,
            y=[thermal[p.energy_type].annual_savings_cad for p in ALL_PROFILES],
            name="Free Heat Recovered", marker_color=C_HTPEM, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Heat Recovered: C$%{y:,.0f}<extra></extra>",
        )
        fig_stack.add_bar(
            x=PROFILE_NAMES,
            y=[-thermal[p.energy_type].hvac_annual_cost_cad for p in ALL_PROFILES],
            name="Electric Heater Cost", marker_color=C_RED, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Heater Cost: C$%{y:,.0f}<extra></extra>",
        )
        fig_stack.add_hline(y=0, line_width=2, line_color=C_BORDER)
        fig_stack.update_layout(
            **PLOTLY_BASE,
            barmode="relative",
            title=dict(text="Free Heat Recovered vs Electric Heater Cost (C$/yr)", font_size=13, font_color=C_TEXT),
            yaxis_title=dict(text="C$ per Year", font_size=12, font_color=C_MUTED),
            xaxis_title=None,
            height=360, margin=dict(t=50, b=100, l=60, r=20),
        )
        fig_stack.update_xaxes(
            tickfont=dict(color=C_MUTED, size=11), linewidth=2, linecolor=C_BORDER,
            gridwidth=1, gridcolor="rgba(24,67,90,0.25)",
        )
        fig_stack.update_yaxes(
            tickfont=dict(color=C_MUTED, size=11), gridcolor="rgba(24,67,90,0.25)",
            gridwidth=1, linewidth=2, linecolor=C_BORDER,
        )
        st.plotly_chart(fig_stack, use_container_width=True, config={"displayModeBar": False})

    with col_panel:
        st.markdown(
            f'<div class="section-accent"><h3>Heating Scorecard</h3>'
            f'<p>Annual C$ impact per technology</p></div>',
            unsafe_allow_html=True,
        )
        rows = []
        for p in ALL_PROFILES:
            r = thermal[p.energy_type]
            rows.append({
                "Technology": PROFILE_LABELS[p.energy_type],
                "Engine Temp": "—" if p.energy_type in ("diesel", "battery")
                               else f"{p.operating_temp_c:.0f} °C",
                "Heating": "Free (combustion)" if p.energy_type == "diesel"
                           else ("Free (waste heat)" if p.hvac_power_draw_kw == 0
                                 else f"{p.hvac_power_draw_kw:.0f} kW electric"),
                "Net/yr": f"C${r.net_annual_impact_cad:+,.0f}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Technology"), use_container_width=True)
        st.divider()
        htpem_net   = thermal["h2_htpem"].net_annual_impact_cad
        battery_net = thermal["battery"].net_annual_impact_cad
        st.metric("HTPEM vs Battery EV",
                  f"C${htpem_net - battery_net:,.0f} /yr",
                  "annual heating advantage",
                  help=HELP_HTPEM)
        st.metric("HTPEM vs Low-Temp H₂",
                  f"C${htpem_net - ltpem_thermal.net_annual_impact_cad:,.0f} /yr",
                  "no electric heater needed at 160 °C",
                  help=HELP_HTPEM)
        if system_age_years > 0:
            st.markdown(
                f'<div class="warn-callout">'
                f'<strong>Engine Ageing Active</strong><br>'
                f'Efficiency = {thermal["h2_htpem"].effective_fc_efficiency*100:.1f}% '
                f'(−{system_age_years * 1.5:.0f}% from new). '
                f'Slightly less waste heat is available; the figures above reflect this.'
                f'</div>',
                unsafe_allow_html=True,
            )


# TAB 4 · CARBON IMPACT

with tab4:
    with st.container():
        st.subheader("Environmental Impact — How Much Pollution Does This Eliminate?")
        st.caption(
            f"Compared to keeping the diesel train · {corridor_km} km · "
            f"Carbon price C${carbon.annual_results[0].carbon_price_cad_per_tonne:.0f}–"
            f"C${carbon.annual_results[-1].carbon_price_cad_per_tonne:.0f}/t · "
            f"Diesel at C${diesel_price:.2f}/L"
        )

    df_carbon = pd.DataFrame([
        {
            "Year":                r.year,
            "CO₂ Removed (t)":     r.co2_abated_tonnes,
            "Carbon Credits (C$)": r.carbon_credit_value_cad,
            "Fuel Savings (C$)":   r.avoided_fuel_cost_cad,
            "Social Benefit (C$)": r.social_benefit_cad,
            "Carbon Price (C$/t)": r.carbon_price_cad_per_tonne,
        }
        for r in carbon.annual_results
    ])

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        fig_carbon = go.Figure()
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Carbon Credits (C$)"],
            name="Carbon Credits Earned", marker_color=C_HTPEM, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Carbon Credits: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Fuel Savings (C$)"],
            name="Diesel Fuel Savings", marker_color=C_BATT, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Fuel Savings: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Social Benefit (C$)"],
            name="Social Cost of Carbon", marker_color=C_LTPEM, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Social Benefit: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.update_layout(
            **PLOTLY_BASE,
            barmode="group",
            title=dict(text="Annual Financial Value of Switching Away from Diesel (C$)", font_size=13, font_color=C_TEXT),
            yaxis_title=dict(text="C$ per Year", font_size=12, font_color=C_MUTED),
            xaxis_title=None,
            height=480, margin=dict(t=50, b=100, l=60, r=20),
        )
        fig_carbon.update_xaxes(
            tickfont=dict(color=C_MUTED, size=11), linewidth=2, linecolor=C_BORDER,
            gridwidth=1, gridcolor="rgba(24,67,90,0.25)",
        )
        fig_carbon.update_yaxes(
            tickfont=dict(color=C_MUTED, size=11), gridcolor="rgba(24,67,90,0.25)",
            gridwidth=1, linewidth=2, linecolor=C_BORDER,
        )
        st.plotly_chart(fig_carbon, use_container_width=True, config={"displayModeBar": False})

    with col_panel:
        st.markdown(
            f'<div class="section-accent"><h3>5-Year Totals</h3>'
            f'<p>Cumulative impact vs keeping the diesel train</p></div>',
            unsafe_allow_html=True,
        )
        _lcoa = carbon.lcoa_cad_per_tonne
        _lcoa_cell = (
            f"**Saves C${abs(_lcoa):,.0f}/t**" if _lcoa <= 0
            else f"**C${_lcoa:,.0f}/t**"
        )
        st.markdown(f"""
| What We Gain | Amount |
|--------|------:|
| CO₂ Removed | **{carbon.total_co2_abated_tonnes:,.0f} tonnes** |
| NOx Removed | **{carbon.total_nox_abated_kg:,.0f} kg** |
| Carbon Credits | **C${carbon.total_carbon_credit_value_cad:,.0f}** |
| Diesel Fuel Saved | **C${carbon.total_avoided_fuel_cost_cad:,.0f}** |
| Social Value | **C${carbon.total_social_benefit_cad:,.0f}** |
| Net cost per tonne | {_lcoa_cell} |
| Equivalent cars off road | **{carbon.equivalent_cars_removed:,} /yr** |
        """)
        st.divider()

        if _lcoa <= 0:
            _lcoa_label  = "Net Savings per Tonne of CO₂ Removed"
            _lcoa_value  = f"Saves C${abs(_lcoa):,.0f} / tonne"
            _lcoa_delta  = "Net operational cost is below diesel — switch is self-financing."
            _lcoa_dcolor = "normal"   # green: saving
        else:
            _lcoa_label  = "Net Cost per Tonne of CO₂ Removed"
            _lcoa_value  = f"C${_lcoa:,.0f} / tonne"
            _lcoa_delta  = f"{carbon.total_co2_abated_tonnes:,.0f} t removed over 5 years"
            _lcoa_dcolor = "inverse"  # red: paying to abate

        st.metric(
            _lcoa_label,
            _lcoa_value,
            _lcoa_delta,
            delta_color=_lcoa_dcolor,
            help=HELP_LCOA,
        )
        st.metric(
            "Cars Taken Off the Road",
            f"{carbon.equivalent_cars_removed:,} / yr",
            "equivalent annual impact vs keeping diesel",
            help="Each tonne of CO₂ avoided equals the annual emissions of one average passenger car.",
        )
        st.dataframe(
            df_carbon[["Year", "CO₂ Removed (t)", "Carbon Price (C$/t)"]].set_index("Year"),
            use_container_width=True,
        )
        _callout_body = (
            f'<strong>How LCOA is calculated:</strong> '
            f'Full H₂ cost (equipment + maintenance + electricity) minus avoided diesel purchases, '
            f'divided by CO₂ abated. '
            f'At current settings the H₂ system costs <strong>C${carbon.lcoa_cad_per_tonne:+,.0f}/t</strong> '
            f'net of diesel savings — a {"saving" if _lcoa <= 0 else "premium"}. '
            f'Adjust the Electricity or Diesel Price sliders to explore.'
        )
        st.markdown(
            f'<div class="info-callout">{_callout_body}</div>',
            unsafe_allow_html=True,
        )


# TAB 5 · SENSITIVITY

with tab5:
    with st.container():
        st.subheader("Sensitivity Analysis — Best and Worst Case Fuel Cost Scenarios")
        st.markdown(
            f'<div class="info-callout">'
            f'<strong>How to read this:</strong> The colour map shows the hydrogen fuel '
            f'cost at every combination of electricity price and plant construction cost. '
            f'The <strong>X marker</strong> represents your current scenario. '
            f'<strong>Dark blue</strong> = lower fuel cost · <strong>Light blue</strong> = higher fuel cost. '
            f'Plant size: {electrolyzer_kw:,} kW · Utilisation: {capacity_factor}%.'
            f'</div>',
            unsafe_allow_html=True,
        )

    rates, capexes, z_grid, deg_curve = run_sensitivity(
        electrolyzer_kw, capacity_factor, system_age_years,
        profile=cfg.INNOVATION_HTPEM,
    )

    col_heat, col_curve = st.columns([1.3, 0.7])

    with col_heat:
        colorscale = [
            [0.00, C_BG],
            [0.25, C_ACCENT2],
            [0.55, C_BORDER],
            [0.80, C_MUTED],
            [1.00, C_LTPEM],
        ]
        fig_heat = go.Figure()
        fig_heat.add_heatmap(
            x=rates, y=capexes, z=z_grid,
            colorscale=colorscale, zsmooth="best",
            hovertemplate=(
                "Electricity: <b>C$%{x:.3f}/kWh</b><br>"
                "Plant Cost: <b>C$%{y:,.0f}/kW</b><br>"
                "Fuel Cost: <b>C$%{z:.2f}/kg</b><extra></extra>"
            ),
            colorbar=dict(
                title=dict(text="Fuel Cost<br>(C$/kg)", font=dict(color=C_MUTED, size=12)),
                tickfont=dict(color=C_MUTED, size=11),
                outlinecolor=C_BORDER, outlinewidth=2,
                thickness=16, len=0.85, x=1.02,
            ),
        )
        fig_heat.add_scatter(
            x=[electricity_rate],
            y=[cfg.ELECTROLYZER_CAPEX_PER_KW],
            mode="markers+text",
            marker=dict(symbol="x", size=16, color=C_TEXT, line_width=3),
            text=["Current scenario"],
            textposition="top center",
            textfont=dict(color=C_TEXT, size=12, family="Inter, system-ui, sans-serif"),
            hovertemplate=(
                f"<b>Current scenario</b><br>"
                f"Electricity: C${electricity_rate:.4f}/kWh<br>"
                f"Plant Cost: C${cfg.ELECTROLYZER_CAPEX_PER_KW:,.0f}/kW<br>"
                f"Fuel Cost: C${econ_htpem.lcoh_cad_per_kg:.4f}/kg"
                "<extra></extra>"
            ),
            showlegend=False,
        )
        fig_heat.update_layout(
            **PLOTLY_BASE,
            title=dict(text="High-Temp H₂ Fuel Cost Grid (C$ per kg)", font_size=15, font_color=C_TEXT),
            xaxis_title=dict(text="Electricity Price (C$/kWh)", font_size=13, font_color=C_MUTED),
            yaxis_title=dict(text="Plant Construction Cost (C$/kW)", font_size=13, font_color=C_MUTED),
            height=480, margin=dict(t=60, b=80, l=100, r=80),
        )
        fig_heat.update_xaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(24,67,90,0.25)", zeroline=False,
            linecolor=C_BORDER, linewidth=2, tickcolor=C_BORDER, tickfont=dict(color=C_MUTED, size=11),
            tickformat=".3f", ticklen=6,
        )
        fig_heat.update_yaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(24,67,90,0.25)", zeroline=False,
            linecolor=C_BORDER, linewidth=2, tickcolor=C_BORDER, tickfont=dict(color=C_MUTED, size=11),
            tickformat=",.0f", ticklen=6,
        )
        st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})

    with col_curve:
        deg_years   = [d["year"]              for d in deg_curve]
        deg_lcoh    = [d["lcoh"]              for d in deg_curve]
        deg_pct     = [d["lcoh_increase_pct"] for d in deg_curve]

        # Defensive: use fc_efficiency_pct if present, otherwise compute FC degradation inline.
        _base_fc = cfg.FC_SYSTEM_EFFICIENCY * 100.0
        deg_fc_eff = [
            d.get(
                "fc_efficiency_pct",
                max(_base_fc * (1.0 - 0.015 * d["year"]), _base_fc * 0.50),
            )
            for d in deg_curve
        ]

        # Demand scaled inversely with per-year efficiency relative to year-0 baseline.
        base_h2_demand_kg = (
            cfg.AVG_CONSUMPTION_KG_KM * corridor_km * trips_per_year
        )
        base_eff = deg_fc_eff[0] / 100.0 if deg_fc_eff[0] > 0 else cfg.FC_SYSTEM_EFFICIENCY
        annual_h2_demand = [
            round(base_h2_demand_kg * (base_eff / (eff / 100.0)), 1)
            for eff in deg_fc_eff
        ]

        fig_deg = go.Figure()
        # solid line + circle markers: primary series
        fig_deg.add_scatter(
            x=deg_years, y=deg_lcoh,
            name="Fuel Cost (C$/kg)",
            mode="lines+markers",
            line=dict(color=C_HTPEM, width=3, dash="solid"),
            marker=dict(size=8, symbol="circle", color=C_HTPEM, line_width=1, line_color=C_BG),
            hovertemplate="Year %{x}<br>Fuel Cost: <b>C$%{y:.4f}/kg</b><extra></extra>",
        )
        if system_age_years <= 10:
            cur_lcoh = deg_lcoh[system_age_years]
            fig_deg.add_scatter(
                x=[system_age_years], y=[cur_lcoh],
                mode="markers",
                marker=dict(size=14, color=C_TEXT, symbol="circle",
                            line_color=C_HTPEM, line_width=3),
                hovertemplate=f"<b>Current year</b><br>C${cur_lcoh:.4f}/kg<extra></extra>",
                showlegend=False,
            )
        # dotted line + square markers on y2: distinct from primary by both dash and shape
        fig_deg.add_scatter(
            x=deg_years, y=annual_h2_demand,
            name="Annual H₂ Demand (kg)",
            mode="lines+markers",
            line=dict(color=C_BATT, width=2.5, dash="dot"),
            marker=dict(size=6, symbol="square", color=C_BATT),
            yaxis="y2",
            hovertemplate="Year %{x}<br>H₂ Demand: <b>%{y:,.0f} kg/yr</b><extra></extra>",
        )
        demand_min = min(annual_h2_demand)
        demand_max = max(annual_h2_demand)
        demand_pad = (demand_max - demand_min) * 0.30
        fig_deg.update_layout(
            **PLOTLY_BASE,
            title=dict(text="Fuel Cost & H₂ Demand as the Engine Ages (0–10 yrs)", font_size=15, font_color=C_TEXT),
            xaxis=dict(
                title=dict(text="Engine Age (years)", font_size=13, font_color=C_MUTED),
                zerolinecolor=C_BORDER, zerolinewidth=1,
                tickfont=dict(color=C_MUTED, size=11), ticklen=6,
                showgrid=True, gridcolor="rgba(24,67,90,0.25)", gridwidth=1,
            ),
            yaxis=dict(
                title=dict(text="Fuel Cost (C$/kg)", font_size=13, font_color=C_HTPEM),
                tickfont=dict(color=C_MUTED, size=11), ticklen=6,
                gridcolor="rgba(24,67,90,0.40)", showgrid=True, gridwidth=1,
                automargin=True,
                zeroline=False,
            ),
            yaxis2=dict(
                title=dict(text="Annual H₂ Demand (kg)", font_size=13, font_color=C_BATT),
                tickfont=dict(color=C_BATT, size=11), ticklen=6,
                overlaying="y", side="right",
                showgrid=False,
                range=[demand_min - demand_pad, demand_max + demand_pad],
                tickformat=",",
                automargin=True,
                zeroline=False,
            ),
            # local override: extra bottom margin to clear the dual-axis legend
            height=480, margin=dict(t=60, b=100, l=80, r=80),
        )
        fig_deg.update_xaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(24,67,90,0.25)", zeroline=False,
            automargin=True,
            linecolor=C_BORDER, linewidth=2, tickcolor=C_BORDER,
            tickmode="linear", tick0=0, dtick=1,
        )
        fig_deg.update_yaxes(
            linecolor=C_BORDER, linewidth=2, zeroline=False,
        )
        st.plotly_chart(fig_deg, use_container_width=True, config={"displayModeBar": False})

    st.divider()
    z_flat   = [v for row in z_grid for v in row]
    lcoh_min = min(z_flat)
    lcoh_max = max(z_flat)

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Best-Case Fuel Cost",
               f"C${lcoh_min:.2f} /kg",
               f"at C${rates[0]:.3f}/kWh · C${capexes[0]:,.0f}/kW plant",
               help=HELP_LCOH)
    sc2.metric("Worst-Case Fuel Cost",
               f"C${lcoh_max:.2f} /kg",
               f"+C${lcoh_max - lcoh_min:.2f} above best case",
               delta_color="inverse", help=HELP_LCOH)
    sc3.metric("Current Scenario",
               f"C${econ_htpem.lcoh_cad_per_kg:.4f} /kg",
               f"H₂ output rate {econ_htpem.effective_h2_efficiency*100:.1f}%",
               delta_color="off",
               help="Based on your current sidebar settings.")
    sc4.metric("Fuel Cost Rise Over 10 yrs",
               f"+{deg_pct[-1]:.1f}%",
               f"C${deg_lcoh[0]:.4f} → C${deg_lcoh[-1]:.4f}/kg as plant ages",
               delta_color="inverse",
               help="As the plant ages, efficiency slowly falls — consistent with observed PEM degradation rates.")