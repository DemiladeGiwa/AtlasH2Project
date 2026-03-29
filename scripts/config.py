"""
config.py
==========
Atlas-H2: Digital Infrastructure Twin  — v6.2
Single Source of Truth — All Physical, Economic & Environmental Constants

This file is the authoritative configuration layer for the entire simulation.
All other modules (atlas_engine.py, carbon_abatement.py, dashboard.py) import
from here. Never hard-code constants elsewhere.

Usage:
    from config import cfg, TrainProfile
    rate = cfg.NB_POWER_INDUSTRIAL_RATE
    profile = cfg.INNOVATION_HTPEM
    for p in cfg.ALL_PROFILES: ...
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


# ── TRAIN TECHNOLOGY PROFILE ──────────────────────────────────────────────────

@dataclass(frozen=True)
class TrainProfile:
    """
    Immutable descriptor for one train technology variant in the 4-way study.

    frozen=True makes instances hashable — required for @st.cache_data.
    All four profiles are instantiated inside AtlasConfig and exposed via
    cfg.ALL_PROFILES for ordered iteration.
    """

    name: str
    """Human-readable label for chart legends and report headers."""

    energy_type: str
    """
    Propulsion category — consumed by engine routing logic.
    Valid values:
        'diesel'    — combustion baseline; no traction storage; free cabin heat.
        'battery'   — Li-ion EV; storage mass from density; electric HVAC required.
        'h2_ltpem'  — LTPEM H₂; storage mass from density; HVAC required (70°C stack).
        'h2_htpem'  — HTPEM H₂; storage mass from density; 160°C heat replaces HVAC.
    """

    operating_temp_c: float
    """
    Fuel cell stack operating temperature [°C].
    Diesel / Battery: 0.0 (not applicable).
    LTPEM (Ballard FCmove): 70°C — insufficient for NB-winter cabin heating.
    HTPEM (Advent / Danish Power Systems): 160°C — fully replaces electric HVAC.
    """

    capex_purification_discount_pct: float
    """
    Electrolyzer BOP CAPEX reduction from fuel cell CO-tolerance [fraction 0–1].
    Non-H₂ profiles: 0.0. LTPEM: 0.0. HTPEM: 0.15 (PSA unit eliminated).
    """

    system_energy_density_wh_kg: float
    """
    Traction energy storage system gravimetric density [Wh/kg].
    Diesel: 0.0 (fuel tank mass negligible vs electrical storage systems).
    Battery (Li-ion NMC system-level): 250 Wh/kg.
    LTPEM H₂ system (Ballard + 700-bar tanks + BOP): 1,500 Wh/kg.
    HTPEM H₂ system (Advent + simplified BOP): 1,800 Wh/kg.
    """

    hvac_power_draw_kw: float
    """
    Electrical power consumed by cabin HVAC when waste heat is unavailable [kW].
    Diesel: 0.0 — combustion coolant loop heats cabin for free.
    Battery: 50.0 — no waste heat source; full electric resistance / heat pump.
    LTPEM: 50.0 — 70°C stack waste heat below usable HVAC threshold.
    HTPEM: 0.0 — 160°C waste heat covers the full 30°C ΔT cabin load.
    """

    bar_color: str
    """Plotly hex colour for this profile across all dashboard charts."""


# ── CONFIGURATION DATACLASS ───────────────────────────────────────────────────

@dataclass(frozen=True)
class AtlasConfig:
    """
    Immutable configuration singleton for the Atlas-H2 simulation.
    Access via the pre-instantiated `cfg` object at the bottom of this module.
    """

    # ── TRAIN TECHNOLOGY PROFILES ─────────────────────────────────────────────

    LEGACY_DIESEL: TrainProfile = TrainProfile(
        name="Legacy Diesel",
        energy_type="diesel",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=0.0,
        hvac_power_draw_kw=0.0,
        bar_color="#4b5563",
    )
    """
    Status-quo baseline: diesel-electric locomotive on SJ-Moncton.
    Combustion engine coolant loop provides cabin heat for free.
    Fuel tank mass is negligible vs the electrical storage of other profiles —
    sets the zero-reference for both payload-loss and thermal-impact charts.
    """

    BATTERY_EV: TrainProfile = TrainProfile(
        name="Battery Electric (Li-ion)",
        energy_type="battery",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=250.0,
        hvac_power_draw_kw=50.0,
        bar_color="#3b82f6",
    )
    """
    Battery-electric alternative: full Li-ion NMC traction pack.
    System-level 250 Wh/kg (BMS + thermal management + casing) produces
    the heaviest onboard storage of all electric profiles — worst freight loss.
    No waste heat: 50 kW electric HVAC required in NB winter.
    Represents the "EV narrative" common in infrastructure procurement.
    """

    BASELINE_LTPEM: TrainProfile = TrainProfile(
        name="Stadler FLIRT H₂ (LTPEM)",
        energy_type="h2_ltpem",
        operating_temp_c=70.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=1_500.0,
        hvac_power_draw_kw=50.0,
        bar_color="#10b981",
    )
    """
    Commercial baseline: real-world Stadler FLIRT H₂ (Ballard FCmove-HD+ LTPEM).
    High TRL, proven in revenue service. Key constraint: 70°C stack waste heat
    is below the NB-winter HVAC threshold — requires a separate 50 kW electric
    HVAC system, creating an ongoing energy cost over 730 annual trips.
    """

    INNOVATION_HTPEM: TrainProfile = TrainProfile(
        name="Atlas Custom (HTPEM)",
        energy_type="h2_htpem",
        operating_temp_c=160.0,
        capex_purification_discount_pct=0.15,
        system_energy_density_wh_kg=1_800.0,
        hvac_power_draw_kw=0.0,
        bar_color="#059669",
    )
    """
    Innovation proposal: Atlas-H2 HTPEM retrofit (Advent Technologies architecture).
    Dominant across all three comparison dimensions:
      • Lowest storage mass → smallest freight capacity loss vs Battery and LTPEM.
      • 160°C waste heat eliminates the 50 kW HVAC draw entirely.
      • 15% BOP CAPEX saving on the on-site electrolyzer (no PSA purification).
    """

    @property
    def ALL_PROFILES(self) -> List[TrainProfile]:
        """
        Ordered list of all four profiles for chart iteration.
        Sequence follows the stakeholder narrative arc:
        status quo → EV alternative → H₂ commercial → H₂ innovation.
        """
        return [self.LEGACY_DIESEL, self.BATTERY_EV, self.BASELINE_LTPEM, self.INNOVATION_HTPEM]

    # ── ECONOMIC CONSTANTS ────────────────────────────────────────────────────

    NB_POWER_INDUSTRIAL_RATE: float = 0.1023
    """NB Power LIS industrial electricity rate [CAD/kWh]. Source: NB Power GRA 2025/26."""

    FEDERAL_H2_ITC: float = 0.40
    """Federal Clean Hydrogen ITC [fraction]. Canada Budget 2023 / Bill C-59."""

    CLEAN_TECH_ITC: float = 0.30
    """Federal Clean Technology ITC [fraction]. Cannot be stacked with H₂ ITC."""

    DIESEL_PRICE_LITER: float = 1.75
    """Diesel price [CAD/L] NB regional average 2025/26. Source: NRCan."""

    ELECTROLYZER_CAPEX_PER_KW: float = 1_200.0
    """PEM electrolyzer installed CAPEX [CAD/kW]. Source: IRENA 2022 / BNEF 2024."""

    ELECTROLYZER_OPEX_RATE: float = 0.02
    """Annual electrolyzer OPEX as fraction of gross CAPEX. Source: NREL H2A 2023."""

    ELECTROLYZER_BOP_FRACTION: float = 0.25
    """
    Balance-of-Plant share of total electrolyzer CAPEX [fraction].
    Applied to gross_capex before multiplying by the profile's BOP discount.
    Source: IRENA Green Hydrogen Cost Reduction 2020 (25–35% range, 25% conservative).
    FIX v6.2: Previously a magic number (0.25) duplicated in EconomicsEngine and
    SensitivityEngine. Centralised here so a single edit propagates everywhere.
    """

    FC_PARASITIC_FRACTION: float = 0.10
    """
    Fraction of gross FC input power lost to parasitic loads (compressor, cooling
    pumps, power electronics) beyond the net electrical output [dimensionless].
    Energy balance: gross_input = net_electrical / η; losses = gross_input × (1 − η − parasitic).
    FIX v6.2: Previously hard-coded as 0.10 in _waste_heat_output_kw. Moving here
    prevents the thermal model from producing negative waste heat if η + parasitic > 1.
    """

    WACC: float = 0.08
    """
    Weighted Average Cost of Capital [fraction] for NPV-LCOH discounting.
    Represents a blended government/institutional financing rate for Canadian
    rail infrastructure. Source: Transport Canada Green Infrastructure 2024 guidance.
    NOTE: LCOH calculations in v6.2 still use a simple nominal sum (no discounting).
    This constant is pre-positioned for a v7.0 NPV-LCOH upgrade.
    """

    # ── TECHNICAL & PHYSICAL CONSTANTS ───────────────────────────────────────

    H2_ENERGY_DENSITY_KWH_KG: float = 33.3
    """Hydrogen LHV [kWh/kg]. Source: NIST / IEA Hydrogen Report 2023."""

    BATTERY_SYSTEM_DENSITY_WH_KG: float = 250.0
    """Li-ion NMC system-level density [Wh/kg]. Source: CATL 2024."""

    FC_SYSTEM_EFFICIENCY: float = 0.45
    """Default fuel cell net efficiency (LHV basis). Used as dashboard slider default."""

    TRAIN_POWER_KW: float = 600.0
    """FLIRT H₂ total fuel cell output [kW]. Source: Stadler 2024."""

    TRAIN_PASSENGER_CAPACITY: int = 108
    """FLIRT H₂ 3-car regional seating capacity [seats]."""

    AVG_CONSUMPTION_KG_KM: float = 0.25
    """FLIRT H₂ H₂ consumption [kg/km] on SJ-Moncton profile."""

    TRAIN_H2_TANK_CAPACITY_KG: float = 56.0
    """Onboard H₂ storage [kg]. 700-bar Type IV tanks. Source: Stadler 2022."""

    TRAIN_MAX_SPEED_KPH: float = 127.0
    """FLIRT H₂ maximum operating speed [km/h]."""

    TRAIN_BASE_MASS_TONNES: float = 114.3
    """FLIRT H₂ base vehicle mass [tonnes], 3-car consist, empty."""

    # ── ENVIRONMENTAL CONSTANTS ───────────────────────────────────────────────

    DIESEL_CO2_PER_LITER: float = 2.68
    """Diesel TTW CO₂ factor [kg CO₂/L]. Source: Transport Canada 2024."""

    DIESEL_CONSUMPTION_L_PER_KM: float = 4.5
    """Diesel regional passenger consumption [L/km]. Source: RAC 2019."""

    DIESEL_NOX_G_PER_LITER: float = 35.0
    """NOx emissions [g/L diesel]. Source: RAC LEM Report 2019."""

    NB_GRID_CARBON_INTENSITY: float = 0.22
    """NB Power grid carbon intensity [kg CO₂/kWh]. Source: ECCC NIR 2023."""

    SOCIAL_COST_CARBON_CAD_PER_TONNE: float = 210.0
    """Social Cost of Carbon [CAD/tonne CO₂e]. Source: ECCC 2023."""

    # ── CORRIDOR PARAMETERS ───────────────────────────────────────────────────

    CORRIDOR_DISTANCE_KM: float = 155.0
    """Saint John to Moncton rail corridor distance [km]."""

    TRIP_ENERGY_KWH: float = 4_000.0
    """Estimated traction energy per one-way SJ-Moncton trip [kWh]."""

    WINTER_AMBIENT_TEMP_C: float = -10.0
    """NB winter design ambient [°C]. Environment Canada normals 1991–2020."""

    CABIN_TARGET_TEMP_C: float = 20.0
    """Cabin HVAC setpoint [°C]. EN 13129 railway standard."""

    TRIPS_PER_YEAR: int = 730
    """Annual one-way trips: 2 round trips/day × 365 days."""


# ── CONVENIENCE ACCESSOR ──────────────────────────────────────────────────────

cfg = AtlasConfig()

if __name__ == "__main__":
    print("=" * 68)
    print("  ATLAS-H2 CONFIG — Source of Truth Verification")
    print("=" * 68)
    print("\n  TRAIN PROFILES:\n")
    for p in cfg.ALL_PROFILES:
        print(f"  [{p.name}]")
        print(f"    energy_type          : {p.energy_type}")
        print(f"    Stack Temp           : {p.operating_temp_c:.0f} °C")
        print(f"    BOP CAPEX Discount   : {p.capex_purification_discount_pct * 100:.0f} %")
        print(f"    System Density       : {p.system_energy_density_wh_kg:,.0f} Wh/kg")
        print(f"    HVAC Power Draw      : {p.hvac_power_draw_kw:.0f} kW")
        print(f"    Bar Color            : {p.bar_color}\n")
    print("  GLOBAL CONSTANTS:")
    skip = {"LEGACY_DIESEL", "BATTERY_EV", "BASELINE_LTPEM", "INNOVATION_HTPEM"}
    for f in cfg.__dataclass_fields__:
        if f not in skip:
            print(f"  {f:<42} = {getattr(cfg, f)}")
    print("=" * 68)
    print(f"  Profiles  : {len(cfg.ALL_PROFILES)} | Constants : {len(cfg.__dataclass_fields__)}")
    print("=" * 68)