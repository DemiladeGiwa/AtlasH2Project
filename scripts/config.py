"""
config.py -- Atlas-H2 Digital Infrastructure Twin v10.0
Single source of truth for all physical, economic, and environmental constants.
All modules import from here. Do not hard-code constants elsewhere.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class RouteProfile:
    """
    All corridor-specific parameters for one rail route.
    frozen=True makes it hashable for @st.cache_data keying.
    Raise ValueError on construction if any parameter is physically invalid.
    """
    name: str                    # human-readable route label
    corridor_km: float           # one-way route distance [km]
    trip_energy_kwh: float       # traction energy per one-way trip [kWh]
    winter_ambient_temp_c: float # design ambient temperature [C]
    cabin_target_temp_c: float   # HVAC setpoint [C]; EN 13129
    trips_per_year: int          # annual one-way trips

    def __post_init__(self) -> None:
        if self.corridor_km <= 0:
            raise ValueError(f"corridor_km must be > 0, got {self.corridor_km}")
        if self.trip_energy_kwh <= 0:
            raise ValueError(f"trip_energy_kwh must be > 0, got {self.trip_energy_kwh}")
        if self.trips_per_year <= 0:
            raise ValueError(f"trips_per_year must be > 0, got {self.trips_per_year}")
        if self.cabin_target_temp_c <= self.winter_ambient_temp_c:
            raise ValueError(
                f"cabin_target_temp_c ({self.cabin_target_temp_c}) must be > "
                f"winter_ambient_temp_c ({self.winter_ambient_temp_c})"
            )


# default route used by all engines when no route is explicitly passed
ROUTE_SJ_MONCTON: RouteProfile = RouteProfile(
    name="Saint John to Moncton",
    corridor_km=155.0,           # source: NB rail network map
    trip_energy_kwh=4_000.0,     # traction energy at 155 km baseline
    winter_ambient_temp_c=-10.0, # Environment Canada normals 1991-2020
    cabin_target_temp_c=20.0,    # EN 13129
    trips_per_year=730,          # 2 round trips/day x 365 days
)


@dataclass(frozen=True)
class TrainProfile:
    """Immutable descriptor for one propulsion variant. frozen=True required for @st.cache_data."""

    name: str                              # chart legend label
    energy_type: str                       # 'diesel' | 'battery' | 'h2_ltpem' | 'h2_htpem'
    operating_temp_c: float                # FC stack temp [C]; 0.0 for diesel/battery
    capex_purification_discount_pct: float # BOP CAPEX reduction fraction; HTPEM = 0.15
    system_energy_density_wh_kg: float     # traction storage density [Wh/kg]; 0.0 for diesel
    hvac_power_draw_kw: float              # electric HVAC draw when waste heat unavailable [kW]
    bar_color: str                         # Plotly hex color


@dataclass(frozen=True)
class AtlasConfig:
    """Immutable config singleton. Access via the module-level cfg instance."""

    # train profiles
    LEGACY_DIESEL: TrainProfile = TrainProfile(
        name="Legacy Diesel",
        energy_type="diesel",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=0.0,
        hvac_power_draw_kw=0.0,
        bar_color="#4b5563",
    )

    BATTERY_EV: TrainProfile = TrainProfile(
        name="Battery Electric (Li-ion)",
        energy_type="battery",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=250.0,   # Li-ion NMC system-level; source: CATL 2024
        hvac_power_draw_kw=50.0,
        bar_color="#3b82f6",
    )

    BASELINE_LTPEM: TrainProfile = TrainProfile(
        name="Stadler FLIRT H2 (LTPEM)",
        energy_type="h2_ltpem",
        operating_temp_c=70.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=1_500.0,  # Ballard + 700-bar tanks + BOP
        hvac_power_draw_kw=50.0,              # 70C stack insufficient for cabin heat
        bar_color="#10b981",
    )

    INNOVATION_HTPEM: TrainProfile = TrainProfile(
        name="Atlas Custom (HTPEM)",
        energy_type="h2_htpem",
        operating_temp_c=160.0,
        capex_purification_discount_pct=0.15,  # PSA unit eliminated
        system_energy_density_wh_kg=1_800.0,   # Advent + simplified BOP
        hvac_power_draw_kw=0.0,                # 160C waste heat covers cabin load
        bar_color="#059669",
    )

    @property
    def ALL_PROFILES(self) -> List[TrainProfile]:
        """Ordered profile list: diesel -> battery -> LTPEM -> HTPEM."""
        return [self.LEGACY_DIESEL, self.BATTERY_EV, self.BASELINE_LTPEM, self.INNOVATION_HTPEM]

    # economic constants
    NB_POWER_INDUSTRIAL_RATE: float  = 0.1023   # CAD/kWh; source: NB Power GRA 2025/26
    FEDERAL_H2_ITC: float            = 0.40     # Canada Budget 2023 / Bill C-59
    CLEAN_TECH_ITC: float            = 0.30     # cannot stack with H2 ITC
    DIESEL_PRICE_LITER: float        = 1.75     # CAD/L NB average 2025/26; source: NRCan
    ELECTROLYZER_CAPEX_PER_KW: float = 1_200.0  # CAD/kW installed; source: IRENA 2022 / BNEF 2024
    ELECTROLYZER_OPEX_RATE: float    = 0.02     # fraction of gross CAPEX/yr; source: NREL H2A 2023
    ELECTROLYZER_BOP_FRACTION: float = 0.25     # BOP share of total CAPEX; source: IRENA 2020
    FC_PARASITIC_FRACTION: float     = 0.10     # parasitic load fraction of gross FC input
    WACC: float                      = 0.08     # pre-positioned for NPV-LCOH upgrade

    # technical / physical constants
    H2_ENERGY_DENSITY_KWH_KG: float    = 33.3    # LHV; source: NIST / IEA 2023
    BATTERY_SYSTEM_DENSITY_WH_KG: float = 250.0  # source: CATL 2024
    FC_SYSTEM_EFFICIENCY: float         = 0.45   # net efficiency LHV basis; dashboard default
    TRAIN_POWER_KW: float               = 600.0  # FLIRT H2 FC output; source: Stadler 2024
    TRAIN_PASSENGER_CAPACITY: int       = 108    # 3-car regional seating
    AVG_CONSUMPTION_KG_KM: float        = 0.25   # H2 consumption [kg/km] on SJ-Moncton
    TRAIN_H2_TANK_CAPACITY_KG: float    = 56.0   # 700-bar Type IV tanks; source: Stadler 2022
    TRAIN_MAX_SPEED_KPH: float          = 127.0
    TRAIN_BASE_MASS_TONNES: float       = 114.3  # 3-car consist, empty

    # environmental constants
    DIESEL_CO2_PER_LITER: float             = 2.68   # kg CO2/L TTW; source: Transport Canada 2024
    DIESEL_CONSUMPTION_L_PER_KM: float      = 4.5    # L/km regional passenger; source: RAC 2019
    DIESEL_NOX_G_PER_LITER: float           = 35.0   # g NOx/L; source: RAC LEM Report 2019
    NB_GRID_CARBON_INTENSITY: float         = 0.22   # kg CO2/kWh; source: ECCC NIR 2023
    SOCIAL_COST_CARBON_CAD_PER_TONNE: float = 210.0  # CAD/tonne CO2e; source: ECCC 2023


cfg = AtlasConfig()

if __name__ == "__main__":
    print("=" * 68)
    print("  ATLAS-H2 CONFIG -- Source of Truth Verification")
    print("=" * 68)
    print(f"\n  DEFAULT ROUTE: {ROUTE_SJ_MONCTON.name}")
    print(f"    corridor_km          : {ROUTE_SJ_MONCTON.corridor_km} km")
    print(f"    trip_energy_kwh      : {ROUTE_SJ_MONCTON.trip_energy_kwh:,.0f} kWh")
    print(f"    winter_ambient_temp  : {ROUTE_SJ_MONCTON.winter_ambient_temp_c} C")
    print(f"    cabin_target_temp    : {ROUTE_SJ_MONCTON.cabin_target_temp_c} C")
    print(f"    trips_per_year       : {ROUTE_SJ_MONCTON.trips_per_year}")
    print("\n  TRAIN PROFILES:\n")
    for p in cfg.ALL_PROFILES:
        print(f"  [{p.name}]")
        print(f"    energy_type          : {p.energy_type}")
        print(f"    Stack Temp           : {p.operating_temp_c:.0f} C")
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