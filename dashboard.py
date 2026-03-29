"""
dashboard.py v6.1 — Red-Team Audit Fixes
==========================================
Atlas-H2 | Dynamic Rail Corridor Simulation

Fixes over v6.0:
  • run_all now passes dynamic_electricity_rate to thermal_engine so HVAC
    penalty and heat-recovery savings update when the electricity slider moves
  • age_note formula corrected (was a mathematical identity, now shows real yield)
  • Dead variables removed: C_DIM, current_x_idx, current_y_idx
  • Session-state reads hardened with .get() + DEFAULTS fallback
  • Repetitive "Stack age X yr" text trimmed; age badge on header carries that info

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

from config import cfg, TrainProfile
from atlas_engine import (
    PayloadAnalyzer, PayloadAnalysisResult,
    EconomicsEngine, LCOHResult,
    ThermalEfficiencyModule, HeatRecoveryResult,
    SensitivityEngine,
    corridor_trip_energy_kwh,
)
from carbon_abatement import CarbonAbatementCalculator

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Atlas-H2 | Digital Twin v6.1",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── PALETTE ───────────────────────────────────────────────────────────────────

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

# ── GLOBAL CSS ────────────────────────────────────────────────────────────────

st.markdown(f"""
<style>
/* ═══════════════════════════════════════════════════════════
   1. RESET & CHROME
══════════════════════════════════════════════════════════════ */
header[data-testid="stHeader"] {{
    background-color: {C_BG};
    border-bottom: 1px solid {C_BORDER};
}}
[data-testid="stToolbar"] {{ background-color: {C_BG}; }}
.stApp {{ background-color: {C_BG}; }}
.main .block-container {{
    background-color: {C_BG};
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 100%;
}}
html, body, [class*="css"] {{
    font-family: "Inter", system-ui, sans-serif;
    color: {C_TEXT};
    line-height: 1.6;
}}
h1, h2, h3 {{
    color: {C_TEXT};
    letter-spacing: 0.02rem;
    font-weight: 700;
}}
h1 {{ font-size: 1.7rem;  }}
h2 {{ font-size: 1.15rem; }}
h3 {{ font-size: 0.95rem; }}

/* ═══════════════════════════════════════════════════════════
   2. ANIMATIONS
══════════════════════════════════════════════════════════════ */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to   {{ opacity: 1; transform: translateY(0);    }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}
@keyframes slideInLeft {{
    from {{ opacity: 0; transform: translateX(-18px); }}
    to   {{ opacity: 1; transform: translateX(0);     }}
}}
@keyframes slideInRight {{
    from {{ opacity: 0; transform: translateX(18px); }}
    to   {{ opacity: 1; transform: translateX(0);    }}
}}
@keyframes scaleIn {{
    from {{ opacity: 0; transform: scale(0.97); }}
    to   {{ opacity: 1; transform: scale(1);    }}
}}
@keyframes pulse {{
    0%   {{ box-shadow: 0 0 0 0   {C_GREEN}99; }}
    70%  {{ box-shadow: 0 0 0 6px {C_GREEN}00; }}
    100% {{ box-shadow: 0 0 0 0   {C_GREEN}00; }}
}}
@keyframes accentPulse {{
    0%   {{ box-shadow: 0 0 0 0   {C_ACCENT}66; }}
    70%  {{ box-shadow: 0 0 0 8px {C_ACCENT}00; }}
    100% {{ box-shadow: 0 0 0 0   {C_ACCENT}00; }}
}}
@keyframes borderGlow {{
    0%, 100% {{ border-color: {C_BORDER}; }}
    50%       {{ border-color: {C_ACCENT}88; }}
}}

/* Staggered KPI entrance */
.kpi-card {{ animation: fadeInUp 0.45s ease both; }}
.kpi-card:nth-child(1) {{ animation-delay: 0.05s; }}
.kpi-card:nth-child(2) {{ animation-delay: 0.10s; }}
.kpi-card:nth-child(3) {{ animation-delay: 0.15s; }}
.kpi-card:nth-child(4) {{ animation-delay: 0.20s; }}
.kpi-card:nth-child(5) {{ animation-delay: 0.25s; }}

[data-baseweb="tab-panel"] > div {{ animation: fadeIn 0.35s ease; }}

[data-testid="stPlotlyChart"] {{
    animation: slideInLeft 0.45s ease both;
    border-radius: 10px;
    overflow: hidden;
}}
[data-testid="stPlotlyChart"] iframe {{ animation: scaleIn 0.5s ease both; }}

[data-testid="stVerticalBlock"] > div:last-child [data-testid="stMetric"],
[data-testid="stVerticalBlock"] > div:last-child [data-testid="stDataFrame"] {{
    animation: slideInRight 0.4s ease both;
}}
[data-testid="stDataFrame"]            {{ animation: fadeInUp 0.4s ease both; }}
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {{ animation: fadeIn 0.4s ease both; }}

.stTabs [aria-selected="true"] {{
    background: {C_BG} !important;
    color: {C_ACCENT} !important;
    font-weight: 700;
    border-color: {C_BORDER} {C_BORDER} {C_BG} !important;
    animation: accentPulse 1.2s ease 1;
}}

.legend-pill:nth-child(1) {{ animation-delay: 0.05s; }}
.legend-pill:nth-child(2) {{ animation-delay: 0.10s; }}
.legend-pill:nth-child(3) {{ animation-delay: 0.15s; }}
.legend-pill:nth-child(4) {{ animation-delay: 0.20s; }}

/* ═══════════════════════════════════════════════════════════
   3. KPI ROW
══════════════════════════════════════════════════════════════ */
.kpi-row {{
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 6px;
    scrollbar-width: thin;
    scrollbar-color: {C_BORDER} transparent;
}}
.kpi-row::-webkit-scrollbar       {{ height: 4px; }}
.kpi-row::-webkit-scrollbar-track {{ background: transparent; }}
.kpi-row::-webkit-scrollbar-thumb {{ background: {C_BORDER}; border-radius: 4px; }}

.kpi-card {{
    flex: 1 0 180px;
    min-width: 180px;
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 18px 16px 14px;
    transition: border-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
    cursor: default;
}}
.kpi-card:hover {{
    border-color: {C_ACCENT};
    box-shadow: 0 0 16px {C_ACCENT}44;
    transform: translateY(-2px);
}}
.kpi-label {{
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {C_MUTED};
    margin-bottom: 6px;
    white-space: nowrap;
}}
.kpi-value {{
    font-size: 1.35rem;
    font-weight: 700;
    color: {C_TEXT};
    letter-spacing: -0.01em;
    margin-bottom: 4px;
    white-space: nowrap;
}}
.kpi-delta {{
    font-size: 0.74rem;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.kpi-delta.pos  {{ color: {C_GREEN};  }}
.kpi-delta.neg  {{ color: {C_RED};    }}
.kpi-delta.neu  {{ color: {C_MUTED};  }}
.kpi-delta.warn {{ color: {C_ORANGE}; }}

/* ═══════════════════════════════════════════════════════════
   4. STREAMLIT METRICS (inside tabs)
══════════════════════════════════════════════════════════════ */
[data-testid="stMetric"] {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 16px 14px;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
    animation: fadeInUp 0.4s ease both;
}}
[data-testid="stMetric"]:hover {{
    border-color: {C_ACCENT};
    box-shadow: 0 0 14px {C_ACCENT}44;
}}
[data-testid="stMetricLabel"] {{
    color: {C_MUTED};
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-weight: 700;
}}
[data-testid="stMetricValue"] {{ color: {C_TEXT}; font-weight: 700; font-size: 1.25rem; }}
[data-testid="stMetricDelta"] {{ font-size: 0.73rem; }}

/* ═══════════════════════════════════════════════════════════
   5. TABS
══════════════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {{
    background: {C_SURFACE};
    border-radius: 8px 8px 0 0;
    border-bottom: 1px solid {C_BORDER};
    gap: 2px;
    padding: 4px 6px 0;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 6px 6px 0 0;
    color: {C_MUTED};
    padding: 8px 18px;
    font-size: 0.83rem;
    font-weight: 500;
    transition: all 0.2s ease;
    letter-spacing: 0.02em;
    border: 1px solid transparent;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: {C_TEXT}; background: {C_ACCENT2}33; }}

/* ═══════════════════════════════════════════════════════════
   6. SIDEBAR
══════════════════════════════════════════════════════════════ */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] .block-container {{
    background: {C_SURFACE};
    border-right: 1px solid {C_BORDER};
}}
.stExpander {{
    background: {C_BG} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 8px !important;
}}
.stExpander summary {{
    color: {C_MUTED};
    font-size: 0.83rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}}

/* ═══════════════════════════════════════════════════════════
   7. BUTTONS & DOWNLOAD
══════════════════════════════════════════════════════════════ */
div[data-testid="stButton"] button,
div[data-testid="stDownloadButton"] button {{
    width: 100%;
    background: transparent;
    border: 1px solid {C_BORDER};
    color: {C_MUTED};
    border-radius: 6px;
    font-weight: 600;
    font-size: 0.81rem;
    letter-spacing: 0.04em;
    transition: all 0.3s ease;
}}
div[data-testid="stButton"] button:hover {{
    border-color: {C_ACCENT};
    color: {C_ACCENT};
    box-shadow: 0 0 10px {C_ACCENT}44;
}}
div[data-testid="stDownloadButton"] button {{
    border-color: {C_GREEN}88;
    color: {C_GREEN};
}}
div[data-testid="stDownloadButton"] button:hover {{
    border-color: {C_GREEN};
    box-shadow: 0 0 10px {C_GREEN}44;
    background: {C_GREEN}11;
}}

/* ═══════════════════════════════════════════════════════════
   8. MISC
══════════════════════════════════════════════════════════════ */
hr {{ border-color: {C_BORDER} !important; opacity: 1 !important; }}
[data-testid="stDataFrame"] {{
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    overflow: hidden;
}}
.stCaption, small {{ color: {C_MUTED} !important; font-size: 0.77rem !important; }}

/* ═══════════════════════════════════════════════════════════
   9. EYEBROW / LEGEND / BADGES
══════════════════════════════════════════════════════════════ */
.eyebrow {{
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {C_ACCENT};
    margin-bottom: 4px;
    animation: fadeIn 0.5s ease;
}}
.legend-row {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
}}
.legend-pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 11px;
    border-radius: 20px;
    font-size: 0.73rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    animation: fadeIn 0.4s ease both;
}}
.route-badge {{
    display: inline-block;
    background: {C_ACCENT}18;
    border: 1px solid {C_ACCENT}55;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.73rem;
    font-weight: 700;
    color: {C_ACCENT};
    letter-spacing: 0.04em;
    animation: fadeIn 0.5s ease;
    margin-left: 8px;
}}
.age-badge {{
    display: inline-block;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.73rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    animation: fadeIn 0.5s ease;
    margin-left: 8px;
}}

/* ═══════════════════════════════════════════════════════════
   10. SIDEBAR STATUS
══════════════════════════════════════════════════════════════ */
.status-dot {{
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: {C_GREEN};
    animation: pulse 2s infinite;
    margin-right: 8px;
    vertical-align: middle;
    flex-shrink: 0;
}}
.status-bar {{
    display: flex;
    align-items: center;
    background: {C_BG};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 0.72rem;
    font-weight: 700;
    color: {C_GREEN};
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-bottom: 10px;
    animation: borderGlow 3s ease infinite;
}}
</style>
""", unsafe_allow_html=True)


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

ALL_PROFILES   = cfg.ALL_PROFILES
PROFILE_NAMES  = [p.name for p in ALL_PROFILES]
PROFILE_COLORS = [p.bar_color for p in ALL_PROFILES]  # DO NOT change — MECE palette

PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", size=12, color=C_MUTED),
    title_font=dict(size=13, color=C_TEXT, family="Inter, system-ui, sans-serif"),
    hoverlabel=dict(
        bgcolor=C_SURFACE, bordercolor=C_BORDER,
        font_size=12, font_family="Inter, system-ui, sans-serif", font_color=C_TEXT,
    ),
    transition=dict(duration=500, easing="cubic-in-out"),
)


# ── SESSION STATE — initialised before ANY widget or engine call ──────────────

DEFAULTS: dict = {
    "corridor_km":      int(cfg.CORRIDOR_DISTANCE_KM),
    "system_age_years": 0,
    "electrolyzer_kw":  1000,
    "capacity_factor":  80,
    "fc_power":         int(cfg.TRAIN_POWER_KW),
    "trips_per_year":   cfg.TRIPS_PER_YEAR,
    "electricity_rate": cfg.NB_POWER_INDUSTRIAL_RATE,
    "diesel_price":     cfg.DIESEL_PRICE_LITER,
    "fc_efficiency":    int(cfg.FC_SYSTEM_EFFICIENCY * 100),
    "winter_temp":      int(cfg.WINTER_AMBIENT_TEMP_C),
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_to_defaults() -> None:
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


# ── ROUTE LABEL ───────────────────────────────────────────────────────────────

def route_label(km: int) -> str:
    if 140 <= km <= 170: return f"Saint John ↔ Moncton ({km} km)"
    if  95 <= km <= 115: return f"Saint John ↔ Fredericton ({km} km)"
    if 185 <= km <= 215: return f"Moncton ↔ Charlottetown ({km} km)"
    if km < 95:          return f"Short Regional ({km} km)"
    if km > 400:         return f"Long Haul Corridor ({km} km)"
    return f"Custom Route ({km} km)"


# ── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="eyebrow" style="margin-bottom:8px;">Atlas-H2 · Digital Twin v6.1</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="status-bar"><span class="status-dot"></span>System Status · Active</div>',
        unsafe_allow_html=True,
    )
    st.button("↺  Reset Parameters", on_click=reset_to_defaults, use_container_width=True)
    st.divider()

    with st.expander("🗺️  Route Configuration", expanded=True):
        st.slider("Corridor Distance (km)", 50, 500, step=5, key="corridor_km",
                  help="Scales trip energy and HVAC trip duration automatically.")
        st.slider("Annual Trips (one-way)", 200, 1460, step=10, key="trips_per_year")
        st.slider("FC Stack Age (years)", 0, 10, step=1, key="system_age_years",
                  help="1.5%/yr FC efficiency degradation; 1%/yr electrolyzer H₂ yield drop.")

    with st.expander("🚂  Train Parameters", expanded=False):
        st.slider("FC Stack Output (kW)", 200, 1200, step=50, key="fc_power")
        st.slider("FC Efficiency (%)",     30,   60, step=1,  key="fc_efficiency")
        st.slider("Winter Ambient (°C)",  -30,   10, step=1,  key="winter_temp")

    with st.expander("⚡  Electrolyzer", expanded=False):
        st.slider("Capacity (kW)",       250, 5000, step=250, key="electrolyzer_kw")
        st.slider("Capacity Factor (%)",  40,   95, step=5,   key="capacity_factor")

    with st.expander("💰  Economics", expanded=False):
        st.slider("Electricity (C$/kWh)", 0.05, 0.25, step=0.005,
                  format="C$%.4f", key="electricity_rate")
        st.slider("Diesel (C$/L)", 1.00, 5.00, step=0.05,
                  format="C$%.2f", key="diesel_price")

    st.divider()
    st.caption(
        f"ITC **{cfg.FEDERAL_H2_ITC*100:.0f}%** · "
        f"Grid **{cfg.NB_GRID_CARBON_INTENSITY} kg CO₂/kWh**"
    )
    st.caption("**Atlas-H2** · TKS · NB Rail Corridor")


# ── READ SLIDERS (hardened with .get() + DEFAULTS fallback) ──────────────────

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

trip_energy_kwh = int(corridor_trip_energy_kwh(corridor_km))


# ── SIMULATION (cached) ───────────────────────────────────────────────────────

@st.cache_data
def run_all(
    corridor_km: int,
    system_age_years: int,
    electrolyzer_kw: int,
    capacity_factor_pct: int,
    fc_power: int,
    trips_yr: int,
    electricity_rate: float,
    diesel_price: float,
    fc_eff_pct: int,
    winter_temp: int,
) -> dict:
    payload_engine = PayloadAnalyzer()
    thermal_engine = ThermalEfficiencyModule(fc_power_kw=fc_power, trips_per_year=trips_yr)
    econ_engine    = EconomicsEngine(
        electrolyzer_size_kw=electrolyzer_kw,
        capacity_factor=capacity_factor_pct / 100.0,
    )

    payload: Dict[str, PayloadAnalysisResult] = payload_engine.compare_all_profiles(
        corridor_km=float(corridor_km),
    )
    thermal: Dict[str, HeatRecoveryResult] = thermal_engine.calculate_all_profiles(
        dynamic_efficiency=fc_eff_pct / 100.0,
        dynamic_ambient_temp=float(winter_temp),
        dynamic_corridor_km=float(corridor_km),
        dynamic_electricity_rate=electricity_rate,   # ← FIX: was missing; thermal C$ now reactive
        system_age_years=system_age_years,
    )
    econ_ltpem: LCOHResult = econ_engine.calculate_lcoh(
        dynamic_electricity_rate=electricity_rate,
        dynamic_capacity_factor=capacity_factor_pct / 100.0,
        profile=cfg.BASELINE_LTPEM,
        system_age_years=system_age_years,
    )
    econ_htpem: LCOHResult = econ_engine.calculate_lcoh(
        dynamic_electricity_rate=electricity_rate,
        dynamic_capacity_factor=capacity_factor_pct / 100.0,
        profile=cfg.INNOVATION_HTPEM,
        system_age_years=system_age_years,
    )
    carbon = CarbonAbatementCalculator(
        trips_per_year=trips_yr,
        corridor_km=float(corridor_km),
    ).calculate_lifetime(dynamic_diesel_price=diesel_price)

    return dict(
        payload=payload, thermal=thermal,
        econ_ltpem=econ_ltpem, econ_htpem=econ_htpem,
        carbon=carbon,
    )


@st.cache_data
def run_sensitivity(
    electrolyzer_kw: int,
    capacity_factor_pct: int,
    system_age_years: int,
) -> tuple:
    se = SensitivityEngine()
    rates, capexes, grid = se.compute_lcoh_grid(
        electrolyzer_size_kw=float(electrolyzer_kw),
        capacity_factor=capacity_factor_pct / 100.0,
        profile=cfg.INNOVATION_HTPEM,
        system_age_years=system_age_years,
    )
    curve = se.compute_degradation_curve(
        electrolyzer_size_kw=float(electrolyzer_kw),
        capacity_factor=capacity_factor_pct / 100.0,
        electricity_rate=cfg.NB_POWER_INDUSTRIAL_RATE,
        capex_per_kw=cfg.ELECTROLYZER_CAPEX_PER_KW,
        profile=cfg.INNOVATION_HTPEM,
    )
    return rates, capexes, grid, curve


results    = run_all(
    corridor_km, system_age_years,
    electrolyzer_kw, capacity_factor, fc_power, trips_per_year,
    electricity_rate, diesel_price, fc_efficiency, winter_temp,
)
payload:    Dict[str, PayloadAnalysisResult] = results["payload"]
thermal:    Dict[str, HeatRecoveryResult]    = results["thermal"]
econ_ltpem: LCOHResult                       = results["econ_ltpem"]
econ_htpem: LCOHResult                       = results["econ_htpem"]
carbon                                        = results["carbon"]


# ── CSV EXPORT ────────────────────────────────────────────────────────────────

def build_export_csv() -> bytes:
    rows = []
    for p in ALL_PROFILES:
        pl = payload[p.energy_type]
        th = thermal[p.energy_type]
        row: dict = {
            "Profile":                 p.name,
            "Energy Type":             p.energy_type,
            "Corridor (km)":           corridor_km,
            "Trip Energy (kWh)":       trip_energy_kwh,
            "Stack Age (yr)":          system_age_years,
            "Storage Mass (kg)":       pl.storage_system_mass_kg,
            "Freight Loss (t)":        pl.freight_capacity_loss_tonnes,
            "Stack Temp (°C)":         p.operating_temp_c,
            "FC Efficiency (degraded)":th.effective_fc_efficiency,
            "Trip Duration (hr)":      th.trip_duration_hr,
            "HVAC Penalty kWh/trip":   th.hvac_penalty_kwh_per_trip,
            "Heat Recovery kWh/trip":  th.electricity_saved_kwh_per_trip,
            "Net Thermal C$/yr":       th.net_annual_impact_cad,
            "CO₂ Abated 5yr (t)":      carbon.total_co2_abated_tonnes,
            "Carbon Credits 5yr (C$)": carbon.total_carbon_credit_value_cad,
            "Avoided Fuel 5yr (C$)":   carbon.total_avoided_fuel_cost_cad,
        }
        if p.energy_type in ("h2_ltpem", "h2_htpem"):
            econ = econ_ltpem if p.energy_type == "h2_ltpem" else econ_htpem
            row.update({
                "LCOH (C$/kg)":            econ.lcoh_cad_per_kg,
                "Gross CAPEX (C$)":        econ.electrolyzer_capex_cad,
                "BOP Saving (C$)":         econ.bop_saving_cad,
                "ITC Saving (C$)":         econ.itc_savings_cad,
                "Net CAPEX (C$)":          econ.net_capex_after_itc_cad,
                "Annual Electricity (C$)": econ.annual_electricity_cost_cad,
                "H₂ Yield (degraded)":     econ.effective_h2_efficiency,
            })
        else:
            row.update({k: "N/A" for k in (
                "LCOH (C$/kg)", "Gross CAPEX (C$)", "BOP Saving (C$)",
                "ITC Saving (C$)", "Net CAPEX (C$)",
                "Annual Electricity (C$)", "H₂ Yield (degraded)",
            )})
        rows.append(row)

    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


with st.sidebar:
    st.divider()
    st.download_button(
        label="⬇  Export Report CSV",
        data=build_export_csv(),
        file_name=f"Atlas_Feasibility_{corridor_km}km_age{system_age_years}yr.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ── HELPERS ───────────────────────────────────────────────────────────────────

def kpi_row(cards: list[dict]) -> None:
    html = '<div class="kpi-row">'
    for c in cards:
        dc = c.get("delta_class", "pos")
        html += (
            f'<div class="kpi-card">'
            f'  <div class="kpi-label">{c["label"]}</div>'
            f'  <div class="kpi-value">{c["value"]}</div>'
            f'  <div class="kpi-delta {dc}">↑ {c["delta"]}</div>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def profile_legend() -> None:
    pills = "".join(
        f'<span class="legend-pill" '
        f'style="background:{p.bar_color}1a;border:1px solid {p.bar_color};color:{p.bar_color}">'
        f'● {p.name}</span>'
        for p in ALL_PROFILES
    )
    st.markdown(f'<div class="legend-row">{pills}</div>', unsafe_allow_html=True)


def _axis(fig: go.Figure, x_grid: bool = False, y_grid: bool = True) -> None:
    fig.update_xaxes(
        showgrid=x_grid, zeroline=False,
        linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
    )
    fig.update_yaxes(
        showgrid=y_grid, gridcolor=C_BORDER,
        zeroline=False, tickfont_color=C_MUTED,
    )


# ── PAGE HEADER ───────────────────────────────────────────────────────────────

age_color      = C_GREEN if system_age_years == 0 else (C_ORANGE if system_age_years < 6 else C_RED)
age_badge_text = (
    "New Stack"
    if system_age_years == 0
    else f"Yr {system_age_years} · H₂ yield {econ_htpem.effective_h2_efficiency*100:.1f}%"
)

st.markdown('<p class="eyebrow">Atlas-H2 · Enterprise Intelligence v6.1</p>', unsafe_allow_html=True)
st.title("4-Way Propulsion Feasibility Study")
st.markdown(
    f"<span style='color:{C_MUTED}'>Legacy Diesel &nbsp;·&nbsp; Battery EV "
    f"&nbsp;·&nbsp; LTPEM H₂ &nbsp;·&nbsp; </span>"
    f"<span style='color:{C_ACCENT};font-weight:700;'>HTPEM H₂ — Recommended</span>"
    f'<span class="route-badge">📍 {route_label(corridor_km)}</span>'
    f'<span class="age-badge" style="background:{age_color}18;border:1px solid {age_color}55;'
    f'color:{age_color}">⚡ {age_badge_text}</span>',
    unsafe_allow_html=True,
)
st.divider()


# ── KPI ROW ───────────────────────────────────────────────────────────────────

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
        "delta": f"−C${lcoh_delta:.2f} vs LTPEM",
    },
    {
        "label": "Gravimetric Advantage",
        "value": f"{freight_saved_t:.2f} t / trip",
        "delta": f"vs Battery · {corridor_km} km route",
    },
    {
        "label": "CO₂ Abated · 5yr",
        "value": f"{carbon.total_co2_abated_tonnes:,.0f} t",
        "delta": f"{carbon.equivalent_cars_removed:,} cars / yr",
    },
    {
        "label": "Gov't Incentives",
        "value": f"C${econ_htpem.itc_savings_cad + econ_htpem.bop_saving_cad:,.0f}",
        "delta": f"40% ITC + C${econ_htpem.bop_saving_cad:,.0f} BOP",
    },
    {
        "label": "Thermal Swing · HTPEM",
        "value": f"C${thermal_swing:,.0f} /yr",
        "delta": "vs LTPEM · no HVAC draw",
        "delta_class": "pos" if system_age_years == 0 else "warn",
    },
])

st.divider()


# ── TABS ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📦  Payload",
    "💰  LCOH",
    "🌡️  Thermal",
    "🌿  Carbon",
    "🎯  Sensitivity",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 · PAYLOAD
# ════════════════════════════════════════════════════════════════════════════

with tab1:
    with st.container():
        st.subheader("Gravimetric Delta — Storage Mass Penalty vs Diesel")
        st.caption(
            f"{trip_energy_kwh:,} kWh auto-derived from {corridor_km} km corridor · "
            "Diesel = zero reference"
        )
        profile_legend()

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        loss_values = [payload[p.energy_type].freight_capacity_loss_tonnes for p in ALL_PROFILES]
        fig_payload = go.Figure(go.Bar(
            x=PROFILE_NAMES, y=loss_values,
            marker_color=PROFILE_COLORS, marker_line_width=0,
            text=[f"{v:.2f} t" if v > 0 else "Baseline" for v in loss_values],
            textposition="outside", textfont=dict(size=11, color=C_TEXT),
            width=0.5, cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Freight Lost: <b>%{y:.3f} t</b><extra></extra>",
        ))
        fig_payload.update_layout(
            **PLOTLY_BASE,
            title=f"Storage Mass Loss — {corridor_km} km Corridor",
            height=420, margin=dict(t=44, b=56, l=8, r=8),
            yaxis_title="Tonnes Lost vs Diesel", xaxis_title=None, showlegend=False,
        )
        _axis(fig_payload)
        fig_payload.update_yaxes(zeroline=True, zerolinecolor=C_BORDER, zerolinewidth=1)
        st.plotly_chart(fig_payload, use_container_width=True)

    with col_panel:
        st.markdown("#### Storage Breakdown")
        rows = []
        for p in ALL_PROFILES:
            r = payload[p.energy_type]
            rows.append({
                "Profile": p.name,
                "Density": "— fuel" if p.energy_type == "diesel"
                           else f"{p.system_energy_density_wh_kg:,.0f} Wh/kg",
                "Mass":    "0 kg"   if p.energy_type == "diesel"
                           else f"{r.storage_system_mass_kg:,.0f} kg",
                "Δ Loss":  "Ref" if p.energy_type == "diesel"
                           else f"{r.freight_capacity_loss_tonnes:.3f} t",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Profile"), use_container_width=True)
        st.divider()
        htpem_vs_ltpem = payload["h2_ltpem"].freight_capacity_loss_tonnes - htpem_loss_t
        st.metric("HTPEM vs Battery", f"−{freight_saved_t:.2f} t", "lighter storage")
        st.metric("HTPEM vs LTPEM",   f"−{htpem_vs_ltpem:.3f} t", "lighter storage")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 · LCOH
# ════════════════════════════════════════════════════════════════════════════

with tab2:
    # Show degraded H₂ yield when stack is aged — no broken formula
    age_note = (
        f" · H₂ yield {econ_htpem.effective_h2_efficiency*100:.1f}% (degraded)"
        if system_age_years > 0 else ""
    )
    with st.container():
        st.subheader("LCOH — 10-Year H₂ Production Cost")
        st.caption(
            f"{electrolyzer_kw:,} kW · CF {capacity_factor}% · "
            f"C${electricity_rate:.4f}/kWh{age_note}"
        )

    col_lt, col_ht, col_panel = st.columns([1.0, 1.0, 0.85])

    with col_lt:
        fig_lt = go.Figure(go.Pie(
            labels=["Net CAPEX", "10-yr OPEX", "10-yr Electricity"],
            values=[
                econ_ltpem.net_capex_after_itc_cad,
                econ_ltpem.annual_opex_cad * 10,
                econ_ltpem.annual_electricity_cost_cad * 10,
            ],
            hole=0.54,
            marker_colors=["#1d4ed8", "#3b82f6", "#93c5fd"],
            marker_line=dict(color=C_BG, width=2),
            textinfo="percent", textfont_size=11,
            hovertemplate="<b>%{label}</b><br>C$%{value:,.0f} · %{percent}<extra></extra>",
        ))
        fig_lt.update_layout(
            **PLOTLY_BASE,
            title=f"LTPEM · C${econ_ltpem.lcoh_cad_per_kg:.2f}/kg",
            height=320, margin=dict(t=48, b=16, l=8, r=8), showlegend=False,
            annotations=[dict(
                text=f"<b>C${econ_ltpem.total_10yr_cost_cad/1e6:.2f}M</b>",
                x=0.5, y=0.5, font_size=14, showarrow=False,
                font_color=C_TEXT, font_family="Inter, system-ui, sans-serif",
            )],
        )
        st.plotly_chart(fig_lt, use_container_width=True)

    with col_ht:
        fig_ht = go.Figure(go.Pie(
            labels=["Net CAPEX", "10-yr OPEX", "10-yr Electricity"],
            values=[
                econ_htpem.net_capex_after_itc_cad,
                econ_htpem.annual_opex_cad * 10,
                econ_htpem.annual_electricity_cost_cad * 10,
            ],
            hole=0.54,
            marker_colors=["#065f46", "#059669", "#6ee7b7"],
            marker_line=dict(color=C_BG, width=2),
            textinfo="percent", textfont_size=11,
            hovertemplate="<b>%{label}</b><br>C$%{value:,.0f} · %{percent}<extra></extra>",
        ))
        fig_ht.update_layout(
            **PLOTLY_BASE,
            title=f"HTPEM · C${econ_htpem.lcoh_cad_per_kg:.2f}/kg",
            height=320, margin=dict(t=48, b=16, l=8, r=8), showlegend=False,
            annotations=[dict(
                text=f"<b>C${econ_htpem.total_10yr_cost_cad/1e6:.2f}M</b>",
                x=0.5, y=0.5, font_size=14, showarrow=False,
                font_color=C_TEXT, font_family="Inter, system-ui, sans-serif",
            )],
        )
        st.plotly_chart(fig_ht, use_container_width=True)

    with col_panel:
        st.markdown("#### LTPEM vs HTPEM")
        st.markdown(f"""
| | LTPEM | HTPEM |
|--|--:|--:|
| Gross CAPEX | C${econ_ltpem.electrolyzer_capex_cad:,.0f} | C${econ_htpem.electrolyzer_capex_cad:,.0f} |
| BOP Saving | — | **C${econ_htpem.bop_saving_cad:,.0f}** |
| ITC (40%) | C${econ_ltpem.itc_savings_cad:,.0f} | C${econ_htpem.itc_savings_cad:,.0f} |
| Net CAPEX | C${econ_ltpem.net_capex_after_itc_cad:,.0f} | C${econ_htpem.net_capex_after_itc_cad:,.0f} |
| Annual OPEX | C${econ_ltpem.annual_opex_cad:,.0f} | C${econ_htpem.annual_opex_cad:,.0f} |
| Annual Elec. | C${econ_ltpem.annual_electricity_cost_cad:,.0f} | C${econ_htpem.annual_electricity_cost_cad:,.0f} |
| H₂ Yield | {econ_ltpem.effective_h2_efficiency*100:.1f}% | {econ_htpem.effective_h2_efficiency*100:.1f}% |
| **LCOH** | **C${econ_ltpem.lcoh_cad_per_kg:.4f}/kg** | **C${econ_htpem.lcoh_cad_per_kg:.4f}/kg** |
        """)
        st.divider()
        st.metric(
            "HTPEM Cost Advantage",
            f"C${lcoh_delta:.4f} /kg",
            f"{lcoh_delta / econ_ltpem.lcoh_cad_per_kg * 100:.1f}% lower LCOH",
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 · THERMAL
# ════════════════════════════════════════════════════════════════════════════

with tab3:
    trip_dur = thermal["h2_htpem"].trip_duration_hr
    with st.container():
        st.subheader("HVAC Energy Balance — Net Annual Thermal Impact")
        st.caption(
            f"{winter_temp}°C NB winter · {trips_per_year:,} trips/yr · "
            f"{trip_dur:.2f} hr/trip · C${electricity_rate:.4f}/kWh"
        )
        profile_legend()

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        net_impacts = [thermal[p.energy_type].net_annual_impact_cad for p in ALL_PROFILES]
        bar_colors  = [
            p.bar_color if thermal[p.energy_type].net_annual_impact_cad >= 0 else C_RED
            for p in ALL_PROFILES
        ]
        fig_net = go.Figure(go.Bar(
            x=PROFILE_NAMES, y=net_impacts,
            marker_color=bar_colors, marker_line_width=0,
            text=[f"C${v:+,.0f}" for v in net_impacts],
            textposition="outside", textfont=dict(size=11, color=C_TEXT),
            width=0.5, cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Net Impact: <b>C$%{y:+,.0f}/yr</b><extra></extra>",
        ))
        fig_net.add_hline(y=0, line_width=1, line_color=C_BORDER)
        fig_net.update_layout(
            **PLOTLY_BASE,
            title=f"Net Annual Thermal Impact (C$/yr) · {corridor_km} km",
            yaxis_title="C$ / Year", xaxis_title=None,
            height=360, margin=dict(t=44, b=56, l=8, r=8), showlegend=False,
        )
        _axis(fig_net)
        st.plotly_chart(fig_net, use_container_width=True)

        fig_stack = go.Figure()
        fig_stack.add_bar(
            x=PROFILE_NAMES,
            y=[thermal[p.energy_type].annual_savings_cad for p in ALL_PROFILES],
            name="Heat Recovery", marker_color="#059669", marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Saving: C$%{y:,.0f}<extra></extra>",
        )
        fig_stack.add_bar(
            x=PROFILE_NAMES,
            y=[-thermal[p.energy_type].hvac_annual_cost_cad for p in ALL_PROFILES],
            name="HVAC Penalty", marker_color=C_RED, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Penalty: C$%{y:,.0f}<extra></extra>",
        )
        fig_stack.add_hline(y=0, line_width=1, line_color=C_BORDER)
        fig_stack.update_layout(
            **PLOTLY_BASE,
            barmode="relative",
            title="Savings vs Penalties (C$/yr)",
            yaxis_title="C$ / Year", xaxis_title=None,
            height=300, margin=dict(t=44, b=72, l=8, r=8),
            legend=dict(
                orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center",
                font_size=11, bgcolor="rgba(0,0,0,0)", font_color=C_MUTED,
            ),
        )
        _axis(fig_stack)
        st.plotly_chart(fig_stack, use_container_width=True)

    with col_panel:
        st.markdown("#### Thermal Scorecard")
        rows = []
        for p in ALL_PROFILES:
            r = thermal[p.energy_type]
            rows.append({
                "Profile":  p.name,
                "Stack °C": "—" if p.energy_type in ("diesel", "battery")
                            else f"{p.operating_temp_c:.0f}",
                "HVAC":     "Free" if p.energy_type == "diesel"
                            else ("Waste heat" if p.hvac_power_draw_kw == 0
                                  else f"{p.hvac_power_draw_kw:.0f} kW"),
                "Net /yr":  f"C${r.net_annual_impact_cad:+,.0f}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Profile"), use_container_width=True)
        st.divider()
        htpem_net   = thermal["h2_htpem"].net_annual_impact_cad
        battery_net = thermal["battery"].net_annual_impact_cad
        st.metric("HTPEM vs Battery",
                  f"C${htpem_net - battery_net:,.0f} /yr", "thermal swing")
        st.metric("HTPEM vs LTPEM",
                  f"C${htpem_net - ltpem_thermal.net_annual_impact_cad:,.0f} /yr",
                  "HVAC penalty eliminated")
        if system_age_years > 0:
            st.caption(
                f"FC η = {thermal['h2_htpem'].effective_fc_efficiency*100:.1f}% "
                f"(−{system_age_years * 1.5:.0f}% from new)"
            )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 · CARBON
# ════════════════════════════════════════════════════════════════════════════

with tab4:
    with st.container():
        st.subheader("Decarbonisation Value — 2026–2030")
        st.caption(
            f"vs diesel baseline · {corridor_km} km corridor · "
            f"Carbon C${carbon.annual_results[0].carbon_price_cad_per_tonne:.0f}–"
            f"C${carbon.annual_results[-1].carbon_price_cad_per_tonne:.0f}/t · "
            f"Diesel C${diesel_price:.2f}/L"
        )

    df_carbon = pd.DataFrame([
        {
            "Year":               r.year,
            "CO₂ Abated (t)":     r.co2_abated_tonnes,
            "Carbon Credit (C$)": r.carbon_credit_value_cad,
            "Avoided Fuel (C$)":  r.avoided_fuel_cost_cad,
            "Social Benefit (C$)":r.social_benefit_cad,
            "Carbon Price (C$/t)":r.carbon_price_cad_per_tonne,
        }
        for r in carbon.annual_results
    ])

    col_chart, col_panel = st.columns([1.5, 0.5])

    with col_chart:
        fig_carbon = go.Figure()
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Carbon Credit (C$)"],
            name="Carbon Credits", marker_color=cfg.INNOVATION_HTPEM.bar_color,
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Carbon Credits: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Avoided Fuel (C$)"],
            name="Avoided Fuel", marker_color="#f59e0b", marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Avoided Fuel: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.add_bar(
            x=df_carbon["Year"], y=df_carbon["Social Benefit (C$)"],
            name="Social Cost of Carbon", marker_color=C_ACCENT2, marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Social Benefit: C$%{y:,.0f}<extra></extra>",
        )
        fig_carbon.update_layout(
            **PLOTLY_BASE,
            barmode="group",
            title="Annual Value of Decarbonisation (C$)",
            yaxis_title="C$", xaxis_title=None,
            height=430, margin=dict(t=44, b=80, l=8, r=8),
            legend=dict(
                orientation="h", yanchor="top", y=-0.18, x=0.5, xanchor="center",
                font_size=11, bgcolor="rgba(0,0,0,0)", font_color=C_MUTED,
            ),
        )
        _axis(fig_carbon)
        st.plotly_chart(fig_carbon, use_container_width=True)

    with col_panel:
        st.markdown("#### 5-Year Totals")
        st.markdown(f"""
| Metric | Value |
|--------|------:|
| CO₂ Abated | **{carbon.total_co2_abated_tonnes:,.0f} t** |
| NOx Abated | **{carbon.total_nox_abated_kg:,.0f} kg** |
| Carbon Credits | **C${carbon.total_carbon_credit_value_cad:,.0f}** |
| Avoided Fuel | **C${carbon.total_avoided_fuel_cost_cad:,.0f}** |
| Social Benefit | **C${carbon.total_social_benefit_cad:,.0f}** |
| LCOA | **C${carbon.lcoa_cad_per_tonne:,.0f}/t** |
| Cars Off Road | **{carbon.equivalent_cars_removed:,}/yr** |
        """)
        st.divider()
        st.metric(
            "Equivalent Cars Removed",
            f"{carbon.equivalent_cars_removed:,} / yr",
            f"{carbon.total_co2_abated_tonnes:,.0f} t CO₂ over 5 yrs",
        )
        st.dataframe(
            df_carbon[["Year", "CO₂ Abated (t)", "Carbon Price (C$/t)"]].set_index("Year"),
            use_container_width=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 · SENSITIVITY
# ════════════════════════════════════════════════════════════════════════════

with tab5:
    with st.container():
        st.subheader("HTPEM LCOH Sensitivity — Electricity Rate × Electrolyzer CAPEX")
        st.caption(
            f"{electrolyzer_kw:,} kW · CF {capacity_factor}% · "
            f"Current scenario marked ✕ · "
            f"Blue Bell = high-cost zone · Deep Space Blue = target zone"
        )

    rates, capexes, z_grid, deg_curve = run_sensitivity(
        electrolyzer_kw, capacity_factor, system_age_years,
    )

    col_heat, col_curve = st.columns([1.3, 0.7])

    with col_heat:
        colorscale = [
            [0.00, C_BG],
            [0.25, C_ACCENT2],
            [0.55, C_BORDER],
            [0.80, C_MUTED],
            [1.00, C_ACCENT],
        ]
        fig_heat = go.Figure()
        fig_heat.add_heatmap(
            x=rates, y=capexes, z=z_grid,
            colorscale=colorscale, zsmooth="best",
            hovertemplate=(
                "Electricity: <b>C$%{x:.3f}/kWh</b><br>"
                "CAPEX: <b>C$%{y:,.0f}/kW</b><br>"
                "LCOH: <b>C$%{z:.2f}/kg</b><extra></extra>"
            ),
            colorbar=dict(
                title=dict(text="LCOH (C$/kg)", font_color=C_MUTED, font_size=11),
                tickfont=dict(color=C_MUTED, size=10),
                outlinecolor=C_BORDER, outlinewidth=1,
                thickness=14, len=0.85,
            ),
        )
        fig_heat.add_scatter(
            x=[electricity_rate],
            y=[cfg.ELECTROLYZER_CAPEX_PER_KW],
            mode="markers+text",
            marker=dict(symbol="x", size=14, color=C_TEXT, line_width=2.5),
            text=["  Current"],
            textfont=dict(color=C_TEXT, size=11),
            hovertemplate=(
                f"Current scenario<br>"
                f"Rate: C${electricity_rate:.4f}/kWh<br>"
                f"CAPEX: C${cfg.ELECTROLYZER_CAPEX_PER_KW:,.0f}/kW<br>"
                f"LCOH: C${econ_htpem.lcoh_cad_per_kg:.4f}/kg"
                "<extra></extra>"
            ),
            showlegend=False,
        )
        fig_heat.update_layout(
            **PLOTLY_BASE,
            title="HTPEM LCOH Grid",
            xaxis_title="Electricity Rate (C$/kWh)",
            yaxis_title="Electrolyzer CAPEX (C$/kW)",
            height=440, margin=dict(t=44, b=48, l=60, r=20),
        )
        fig_heat.update_xaxes(
            showgrid=False, zeroline=False,
            linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
            tickformat=".3f",
        )
        fig_heat.update_yaxes(
            showgrid=False, zeroline=False,
            linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
            tickformat=",.0f",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    with col_curve:
        deg_years = [d["year"]                   for d in deg_curve]
        deg_lcoh  = [d["lcoh"]                   for d in deg_curve]
        deg_yield = [d["effective_yield"] * 100  for d in deg_curve]
        deg_pct   = [d["lcoh_increase_pct"]      for d in deg_curve]

        fig_deg = go.Figure()
        fig_deg.add_scatter(
            x=deg_years, y=deg_lcoh,
            name="LCOH (C$/kg)",
            mode="lines+markers",
            line=dict(color=C_ACCENT, width=2.5),
            marker=dict(size=6, color=C_ACCENT),
            hovertemplate="Year %{x}<br>LCOH: C$%{y:.4f}/kg<extra></extra>",
        )
        if system_age_years <= 10:
            cur_lcoh = deg_lcoh[system_age_years]
            fig_deg.add_scatter(
                x=[system_age_years], y=[cur_lcoh],
                mode="markers",
                marker=dict(size=12, color=C_TEXT, symbol="circle",
                            line_color=C_ACCENT, line_width=2),
                hovertemplate=f"C${cur_lcoh:.4f}/kg<extra></extra>",
                showlegend=False,
            )
        fig_deg.add_scatter(
            x=deg_years, y=deg_yield,
            name="H₂ Yield (%)",
            mode="lines",
            line=dict(color=C_MUTED, width=1.5, dash="dot"),
            yaxis="y2",
            hovertemplate="Year %{x}<br>H₂ Yield: %{y:.1f}%<extra></extra>",
        )
        fig_deg.update_layout(
            **PLOTLY_BASE,
            title="LCOH Degradation Curve (0–10 yr)",
            xaxis_title="Stack Age (years)",
            yaxis=dict(
                title="LCOH (C$/kg)", title_font_color=C_ACCENT,
                tickfont_color=C_MUTED, gridcolor=C_BORDER, showgrid=True,
            ),
            yaxis2=dict(
                title="H₂ Yield (%)", title_font_color=C_MUTED,
                tickfont_color=C_MUTED, overlaying="y", side="right",
                showgrid=False, range=[55, 75],
            ),
            height=440, margin=dict(t=44, b=48, l=8, r=52),
            legend=dict(
                orientation="h", yanchor="top", y=-0.15, x=0.5, xanchor="center",
                font_size=11, bgcolor="rgba(0,0,0,0)", font_color=C_MUTED,
            ),
        )
        fig_deg.update_xaxes(
            showgrid=False, zeroline=False,
            linecolor=C_BORDER, tickcolor=C_BORDER, tickfont_color=C_MUTED,
            tickmode="linear", tick0=0, dtick=1,
        )
        st.plotly_chart(fig_deg, use_container_width=True)

    st.divider()
    z_flat   = [v for row in z_grid for v in row]
    lcoh_min = min(z_flat)
    lcoh_max = max(z_flat)

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Best-Case LCOH",   f"C${lcoh_min:.2f}/kg",  f"C${rates[0]:.3f}/kWh · C${capexes[0]:,.0f}/kW")
    sc2.metric("Worst-Case LCOH",  f"C${lcoh_max:.2f}/kg",  "Danger zone ceiling")
    sc3.metric("Current Scenario", f"C${econ_htpem.lcoh_cad_per_kg:.4f}/kg",
               f"H₂ yield {econ_htpem.effective_h2_efficiency*100:.1f}%")
    sc4.metric("10-yr LCOH Drift", f"+{deg_pct[-1]:.1f}%",
               f"C${deg_lcoh[0]:.4f} → C${deg_lcoh[-1]:.4f}/kg")