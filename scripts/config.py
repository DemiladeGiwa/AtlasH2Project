"""
config.py -- Atlas-H2 Digital Infrastructure Twin v10.0
Single source of truth for all physical, economic, and environmental constants.
All modules import from here. Do not hard-code constants elsewhere.

Citation policy: every constant whose value is non-trivial carries a `citation`
key in `cfg.CITATIONS` and, where applicable, inline in the TrainProfile.
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
    name: str                    # route label
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
    corridor_km=155.0,           # source: NB Southern Railway network map; GeoNB geospatial data
    trip_energy_kwh=4_000.0,     # source: Stadler FLIRT H2 traction model scaled to 155 km
    winter_ambient_temp_c=-10.0, # source: Environment Canada Climate Normals 1991–2020, Saint John A
    cabin_target_temp_c=20.0,    # source: EN 13129 Railway Heating Standard
    trips_per_year=730,          # 2 round trips/day x 365 days
)


@dataclass(frozen=True)
class TrainProfile:
    """
    Immutable descriptor for one propulsion variant. frozen=True required for @st.cache_data.

    The `citation` field identifies the primary data source(s) for the profile's
    key technical parameters (energy density, stack temperature, BOP discount).
    """

    name: str                              # chart legend label
    energy_type: str                       # 'diesel' | 'battery' | 'h2_ltpem' | 'h2_htpem'
    operating_temp_c: float                # FC stack temp [C]; 0.0 for diesel/battery
    capex_purification_discount_pct: float # BOP CAPEX reduction fraction; HTPEM = 0.15
    system_energy_density_wh_kg: float     # traction storage density [Wh/kg]; 0.0 for diesel
    hvac_power_draw_kw: float              # electric HVAC draw when waste heat unavailable [kW]
    bar_color: str                         # Plotly hex color
    citation: str = ""                     # primary source reference for key profile parameters


@dataclass(frozen=True)
class AtlasConfig:
    """Immutable config singleton. Access via the module-level cfg instance."""

    # ---------------------------------------------------------------------------
    # train profiles
    # ---------------------------------------------------------------------------
    LEGACY_DIESEL: TrainProfile = TrainProfile(
        name="Legacy Diesel",
        energy_type="diesel",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=0.0,
        hvac_power_draw_kw=0.0,
        bar_color="#4b5563",
        citation=(
            "Railway Association of Canada, Locomotive Emission Monitoring Programme "
            "(LEM) Report 2019. Transport Canada GHG Reference Values 2024."
        ),
    )

    BATTERY_EV: TrainProfile = TrainProfile(
        name="Battery Electric (Li-ion)",
        energy_type="battery",
        operating_temp_c=0.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=250.0,   # Li-ion NMC system-level
        hvac_power_draw_kw=50.0,
        bar_color="#3b82f6",
        citation=(
            "CATL Qilin (NMC) battery system datasheet (2024), system-level 250 Wh/kg. "
            "HVAC demand: EN 13129 UA·ΔT model; NB design winter at −10 °C."
        ),
    )

    BASELINE_LTPEM: TrainProfile = TrainProfile(
        name="Stadler FLIRT H2 (LTPEM)",
        energy_type="h2_ltpem",
        operating_temp_c=70.0,
        capex_purification_discount_pct=0.0,
        system_energy_density_wh_kg=1_500.0,  # Ballard + 700-bar tanks + BOP
        hvac_power_draw_kw=50.0,              # 70°C stack insufficient for cabin heat
        bar_color="#10b981",
        citation=(
            "Stadler FLIRT H2 technical specification (2024); Ballard FCmove-HD "
            "datasheet (2023). System density: Hexagon Purus 700-bar Type IV tanks "
            "combined with Ballard BOP. HVAC: 70 °C exhaust insufficient per EN 13129."
        ),
    )

    INNOVATION_HTPEM: TrainProfile = TrainProfile(
        name="Atlas Custom (HTPEM)",
        energy_type="h2_htpem",
        operating_temp_c=160.0,
        capex_purification_discount_pct=0.15,  # PSA unit eliminated
        system_energy_density_wh_kg=1_800.0,   # Advent + simplified BOP
        hvac_power_draw_kw=0.0,                # 160°C waste heat covers cabin load
        bar_color="#059669",
        citation=(
            "Advent Technologies HT-PEM stack (2023); IRENA Green Hydrogen Cost "
            "Reduction Roadmap (2022). BOP saving: PSA purification unit elimination "
            "(15% of total BOP CAPEX) per IRENA 2020. Waste-heat HVAC: 160 °C exhaust "
            "satisfies EN 13129 cabin setpoint without supplemental electric heating."
        ),
    )

    @property
    def ALL_PROFILES(self) -> List[TrainProfile]:
        """Ordered profile list: diesel -> battery -> LTPEM -> HTPEM."""
        return [self.LEGACY_DIESEL, self.BATTERY_EV, self.BASELINE_LTPEM, self.INNOVATION_HTPEM]

    # ---------------------------------------------------------------------------
    # economic constants
    # ---------------------------------------------------------------------------
    NB_POWER_INDUSTRIAL_RATE: float  = 0.1023   # CAD/kWh
    FEDERAL_H2_ITC: float            = 0.40     # Canada Budget 2023 / Bill C-59
    CLEAN_TECH_ITC: float            = 0.30     # cannot stack with H2 ITC
    DIESEL_PRICE_LITER: float        = 1.75     # CAD/L NB average 2025/26
    ELECTROLYZER_CAPEX_PER_KW: float = 1_200.0  # CAD/kW installed
    ELECTROLYZER_OPEX_RATE: float    = 0.02     # fraction of gross CAPEX/yr
    ELECTROLYZER_BOP_FRACTION: float = 0.25     # BOP share of total CAPEX
    FC_PARASITIC_FRACTION: float     = 0.10     # parasitic load fraction of gross FC input
    WACC: float                      = 0.08     # pre-positioned for NPV-LCOH upgrade

    # technical / physical constants
    H2_ENERGY_DENSITY_KWH_KG: float    = 33.3    # LHV
    BATTERY_SYSTEM_DENSITY_WH_KG: float = 250.0  # CATL 2024
    FC_SYSTEM_EFFICIENCY: float         = 0.45   # net efficiency LHV basis; dashboard default
    TRAIN_POWER_KW: float               = 600.0  # FLIRT H2 FC output
    TRAIN_PASSENGER_CAPACITY: int       = 108    # 3-car regional seating
    AVG_CONSUMPTION_KG_KM: float        = 0.25   # H2 consumption [kg/km] on SJ-Moncton
    TRAIN_H2_TANK_CAPACITY_KG: float    = 56.0   # 700-bar Type IV tanks
    TRAIN_MAX_SPEED_KPH: float          = 127.0
    TRAIN_BASE_MASS_TONNES: float       = 114.3  # 3-car consist, empty
    # Maximum practical onboard storage mass before structural feasibility is exceeded.
    # Derived from track loading limit (~155 t) minus base mass (114.3 t) minus
    # passenger payload (108 pax × 90 kg ≈ 9.7 t), leaving ≈ 31 t for storage.
    # A 25 t hard ceiling preserves a modest margin for ancillary equipment.
    STORAGE_MASS_LIMIT_KG: float        = 25_000.0

    # environmental constants
    DIESEL_CO2_PER_LITER: float             = 2.68   # kg CO2/L TTW
    DIESEL_CONSUMPTION_L_PER_KM: float      = 4.5    # L/km regional passenger
    DIESEL_NOX_G_PER_LITER: float           = 35.0   # g NOx/L
    NB_GRID_CARBON_INTENSITY: float         = 0.22   # kg CO2/kWh
    SOCIAL_COST_CARBON_CAD_PER_TONNE: float = 210.0  # CAD/tonne CO2e

    # ---------------------------------------------------------------------------
    # citation registry
    # Full academic/regulatory source for every non-trivial constant.
    # Access via cfg.CITATIONS["CONSTANT_NAME"].
    # ---------------------------------------------------------------------------
    @property
    def CITATIONS(self) -> dict[str, str]:
        """
        Returns a mapping from constant name to its primary source reference.
        Intended for display in UI tooltips, audit logs, and exported reports.
        """
        return {
            # economic
            "NB_POWER_INDUSTRIAL_RATE": (
                "NB Power General Rate Application 2025/26, Schedule 2-B "
                "(Industrial Service IS-91). C$0.1023/kWh effective April 2025."
            ),
            "FEDERAL_H2_ITC": (
                "Government of Canada Budget 2023; Income Tax Act s. 127.48 "
                "(enacted via Bill C-59, 2024). 40% refundable ITC on eligible "
                "clean hydrogen production equipment."
            ),
            "CLEAN_TECH_ITC": (
                "Government of Canada Budget 2023; Income Tax Act s. 127.45. "
                "30% refundable ITC; cannot be stacked with the H2 ITC (s. 127.48)."
            ),
            "DIESEL_PRICE_LITER": (
                "Natural Resources Canada Fuel Price Monitor, New Brunswick weekly "
                "average (Q1 2025). C$1.75/L represents mid-range ultra-low-sulphur "
                "diesel for rail operations."
            ),
            "ELECTROLYZER_CAPEX_PER_KW": (
                "IRENA (2022) Green Hydrogen Cost Reduction: Scaling Up Electrolysers, "
                "Table 3.1 (alkaline/PEM central estimate); BNEF Hydrogen Market "
                "Outlook 2024, Figure 4 (PEM installed CAPEX range C$900–C$1,500/kW)."
            ),
            "ELECTROLYZER_OPEX_RATE": (
                "NREL H2A Production Analysis, PEM Central Case v3.0 (2023). "
                "Fixed O&M assumed at 2% of uninstalled CAPEX per annum."
            ),
            "ELECTROLYZER_BOP_FRACTION": (
                "IRENA (2020) Green Hydrogen: A Guide to Policy Making, Annex I. "
                "Balance-of-plant typically represents 20–30% of total installed CAPEX; "
                "25% used as central estimate."
            ),
            "FC_PARASITIC_FRACTION": (
                "U.S. DOE Fuel Cell Technologies Office, Multi-Year R&D Plan 2022, "
                "Section 3.4. Parasitic loads (compressor, pumps, controls) assumed "
                "at 10% of gross FC input."
            ),
            "WACC": (
                "Infrastructure project finance benchmark for Canadian green energy "
                "projects; consistent with NREL ATB 2023 utility-scale assumptions "
                "and NRCan Clean Fuels Fund criteria."
            ),
            # technical / physical
            "H2_ENERGY_DENSITY_KWH_KG": (
                "NIST WebBook, Hydrogen (CAS 1333-74-0), Lower Heating Value. "
                "IEA Hydrogen 2023, Annex Table A.3. LHV = 33.33 kWh/kg."
            ),
            "FC_SYSTEM_EFFICIENCY": (
                "Ballard FCmove-HD 200 kW datasheet (2023), net system efficiency "
                "43–47% LHV basis. DOE 2025 target: 50%. Central case 45% used."
            ),
            "TRAIN_POWER_KW": (
                "Stadler FLIRT H2 (RABe 523) technical specification, Fuel Cell "
                "traction power 600 kW (2024). Source: Stadler Rail AG press release "
                "and SBB/SNCF procurement documentation."
            ),
            "TRAIN_PASSENGER_CAPACITY": (
                "Stadler FLIRT H2 3-car consist, standard seating layout (2024). "
                "108 seats in 2+2 configuration; accessible spaces included."
            ),
            "AVG_CONSUMPTION_KG_KM": (
                "Alstom Coradia iLint baseline consumption 0.24–0.26 kg H₂/km "
                "(Alstom, 2023); calibrated to SJ–Moncton corridor profile "
                "including grade and stop pattern."
            ),
            "TRAIN_H2_TANK_CAPACITY_KG": (
                "Hexagon Purus 700-bar Type IV composite tanks as fitted to Stadler "
                "FLIRT H2; total usable capacity 56 kg (2022). "
                "Source: Stadler Rail AG FLIRT H2 factsheet."
            ),
            "TRAIN_BASE_MASS_TONNES": (
                "Stadler FLIRT H2 3-car consist tare mass 114.3 t (2024). "
                "Source: Stadler Rail AG technical specification."
            ),
            # environmental
            "DIESEL_CO2_PER_LITER": (
                "Transport Canada, Greenhouse Gas Emission Factors for the "
                "Transportation Sector (2024 edition). Diesel combustion: "
                "2.68 kg CO₂/L tank-to-wheel (TTW), excluding upstream."
            ),
            "DIESEL_CONSUMPTION_L_PER_KM": (
                "Railway Association of Canada, Locomotive Emission Monitoring "
                "Programme (LEM) Report 2019. Regional passenger locomotive "
                "diesel consumption 4.0–5.0 L/km; 4.5 L/km central estimate."
            ),
            "DIESEL_NOX_G_PER_LITER": (
                "Railway Association of Canada LEM Report 2019, Table B-4. "
                "NOx emission factor 35 g/L for Tier 0–2 road-switcher locomotives "
                "in Canadian regional service."
            ),
            "NB_GRID_CARBON_INTENSITY": (
                "Environment and Climate Change Canada, National Inventory Report "
                "2023 (NIR), Annex 8, NB provincial grid average. "
                "0.22 kg CO₂/kWh reflects NB Power's mixed hydro/gas/wind fleet."
            ),
            "SOCIAL_COST_CARBON_CAD_PER_TONNE": (
                "Environment and Climate Change Canada, Technical Update to the "
                "Social Cost of Greenhouse Gases (2023). Central estimate C$210/t "
                "CO₂e in 2025 Canadian dollars at 2% discount rate."
            ),
            # route
            "ROUTE_SJ_MONCTON.corridor_km": (
                "NB Southern Railway network map; New Brunswick Geographic "
                "Information Corporation (GeoNB) geospatial dataset. "
                "One-way rail distance Saint John Union Station to Moncton "
                "Intermodal Terminal: 155 km."
            ),
            "ROUTE_SJ_MONCTON.winter_ambient_temp_c": (
                "Environment Canada, Canadian Climate Normals 1991–2020, "
                "Station: Saint John A (Climate ID 8105000). Mean January "
                "daily minimum: −10.0 °C (design ambient for HVAC sizing)."
            ),
            "ROUTE_SJ_MONCTON.trip_energy_kwh": (
                "Stadler FLIRT H2 traction energy model; scaled linearly from "
                "published figures to the 155 km SJ–Moncton corridor. "
                "4,000 kWh per one-way trip at standard load."
            ),
        }


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
        print(f"    Bar Color            : {p.bar_color}")
        print(f"    Citation             : {p.citation[:80]}...\n")
    print("  GLOBAL CONSTANTS:")
    skip = {"LEGACY_DIESEL", "BATTERY_EV", "BASELINE_LTPEM", "INNOVATION_HTPEM"}
    for f in cfg.__dataclass_fields__:
        if f not in skip:
            print(f"  {f:<42} = {getattr(cfg, f)}")
    print("\n  CITATION REGISTRY:")
    for k, v in cfg.CITATIONS.items():
        print(f"  [{k}]")
        print(f"    {v[:100]}...")
    print("=" * 68)
    print(f"  Profiles  : {len(cfg.ALL_PROFILES)} | Constants : {len(cfg.__dataclass_fields__)}")
    print(f"  Citations : {len(cfg.CITATIONS)}")
    print("=" * 68)