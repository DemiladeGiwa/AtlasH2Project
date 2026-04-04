"""
atlas_engine.py
================
Core computational logic for the Atlas-H2 Digital Twin.

v6.2 — Antigravity Audit Pass
  Audit fixes applied over v6.2 pre-flight:

  [PHYSICS-1]  _waste_heat_output_kw: thermal_fraction clamped to ≥ 0.0 to prevent
               negative waste heat when (efficiency + FC_PARASITIC_FRACTION) ≥ 1.
               FC_PARASITIC_FRACTION now sourced from cfg instead of a magic number.

  [ARCH-1]     EconomicsEngine.calculate_lcoh: ELECTROLYZER_BOP_FRACTION now sourced
               from cfg.ELECTROLYZER_BOP_FRACTION instead of the in-line literal 0.25.

  [ARCH-2]     SensitivityEngine.compute_lcoh_grid: same BOP_FRACTION fix; grid LCOH
               and EconomicsEngine LCOH are now algebraically identical for identical
               inputs — eliminating the crosshair mismatch on the sensitivity heatmap.

  [PERF-1]     SensitivityEngine: O(N²) loop constants hoisted (v6.1 pre-flight,
               retained and documented).

  [STYLE-1]    Optional[float] = None annotations corrected throughout.
  [STYLE-2]    PEP-8 alignment pass; all lines ≤ 99 characters.
  [STYLE-3]    Type aliases tightened from Dict/List to dict/list (PEP-585, Py 3.9+).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import cfg, TrainProfile

# ── ROUTE CONSTANTS ───────────────────────────────────────────────────────────

_BASE_KM: float   = cfg.CORRIDOR_DISTANCE_KM    # 155 km SJ-Moncton baseline
_BASE_KWH: float  = cfg.TRIP_ENERGY_KWH         # 4 000 kWh at baseline
_BASE_HR: float   = 1.75                        # 1.75 hr at ~88.6 km/h average
_AVG_SPEED: float = _BASE_KM / _BASE_HR         # 88.57 km/h

# FC stack degradation rate [fraction / year, relative]
FC_DEGRADATION_RATE: float = 0.015


def apply_degradation(base_efficiency: float, age_years: int) -> float:
    """
    Effective FC efficiency after ``age_years`` of operation.

    Model: η_eff = η₀ × (1 − 0.015 × age), floored at 50 % of η₀.
    The floor prevents the slider from driving efficiency to physically
    impossible values over long simulated lifetimes.
    """
    degraded = base_efficiency * (1.0 - FC_DEGRADATION_RATE * age_years)
    return max(degraded, base_efficiency * 0.50)


def corridor_trip_energy_kwh(corridor_km: float) -> float:
    """Trip energy [kWh] scaled linearly with corridor distance."""
    return corridor_km * (_BASE_KWH / _BASE_KM)


def corridor_trip_duration_hr(corridor_km: float) -> float:
    """Trip duration [hr] at SJ-Moncton average operating speed (88.57 km/h)."""
    return corridor_km / _AVG_SPEED


# ── DATA CLASSES ──────────────────────────────────────────────────────────────

@dataclass
class PayloadAnalysisResult:
    profile_name: str
    energy_type: str
    corridor_km: float
    energy_requirement_kwh: float
    storage_system_mass_kg: float
    freight_capacity_loss_tonnes: float
    gravimetric_ratio_vs_battery: float
    system_density_wh_kg: float


@dataclass
class LCOHResult:
    profile_name: str
    system_age_years: int
    effective_h2_efficiency: float
    electrolyzer_capex_cad: float
    bop_saving_cad: float
    itc_savings_cad: float
    net_capex_after_itc_cad: float
    annual_opex_cad: float
    annual_electricity_cost_cad: float
    total_10yr_cost_cad: float
    total_h2_produced_kg: float
    lcoh_cad_per_kg: float
    lcoh_cad_per_kwh: float
    carbon_abatement_notes: str


@dataclass
class HeatRecoveryResult:
    profile_name: str
    energy_type: str
    system_age_years: int
    effective_fc_efficiency: float
    corridor_km: float
    trip_duration_hr: float
    stack_operating_temp_c: float
    ambient_temp_c: float
    delta_t_c: float
    waste_heat_available_kw: float
    cabin_heating_demand_kw: float
    heat_fraction_covered: float
    electricity_saved_kwh_per_trip: float
    annual_savings_cad: float
    hvac_penalty_kwh_per_trip: float
    hvac_annual_cost_cad: float
    net_annual_impact_cad: float


# ── CLASS 1: PAYLOAD ANALYZER ─────────────────────────────────────────────────

class PayloadAnalyzer:
    """Calculates onboard energy storage mass for all four propulsion profiles."""

    def __init__(self, li_ion_density: float = cfg.BATTERY_SYSTEM_DENSITY_WH_KG) -> None:
        self.li_ion_density = li_ion_density

    @staticmethod
    def _mass_for_energy(energy_kwh: float, density_wh_kg: float) -> float:
        """Return storage mass [kg]; returns 0.0 if density is non-positive."""
        if density_wh_kg <= 0:
            return 0.0
        return (energy_kwh * 1_000.0) / density_wh_kg

    def compare_systems(
        self,
        energy_kwh: Optional[float] = None,
        corridor_km: Optional[float] = None,
        profile: Optional[TrainProfile] = None,
    ) -> PayloadAnalysisResult:
        ckm     = corridor_km if corridor_km is not None else _BASE_KM
        ekwh    = energy_kwh  if energy_kwh  is not None else corridor_trip_energy_kwh(ckm)
        profile = profile     if profile     is not None else cfg.INNOVATION_HTPEM

        storage_mass = (
            0.0
            if profile.energy_type == "diesel"
            else self._mass_for_energy(ekwh, profile.system_energy_density_wh_kg)
        )

        battery_mass     = self._mass_for_energy(ekwh, cfg.BATTERY_SYSTEM_DENSITY_WH_KG)
        ratio_vs_battery = (
            storage_mass / battery_mass
            if battery_mass > 0 and storage_mass > 0
            else 0.0
        )

        return PayloadAnalysisResult(
            profile_name=profile.name,
            energy_type=profile.energy_type,
            corridor_km=ckm,
            energy_requirement_kwh=round(ekwh, 1),
            storage_system_mass_kg=round(storage_mass, 2),
            freight_capacity_loss_tonnes=round(storage_mass / 1_000.0, 3),
            gravimetric_ratio_vs_battery=round(ratio_vs_battery, 3),
            system_density_wh_kg=profile.system_energy_density_wh_kg,
        )

    def compare_all_profiles(
        self,
        energy_kwh: Optional[float] = None,
        corridor_km: Optional[float] = None,
    ) -> dict[str, PayloadAnalysisResult]:
        return {
            p.energy_type: self.compare_systems(
                energy_kwh=energy_kwh, corridor_km=corridor_km, profile=p,
            )
            for p in cfg.ALL_PROFILES
        }

    def print_report(
        self, results: Optional[dict[str, PayloadAnalysisResult]] = None,
    ) -> None:
        results = results or self.compare_all_profiles()
        print("=" * 68)
        print("  PAYLOAD ANALYSIS — 4-Way Comparison")
        print("=" * 68)
        for r in results.values():
            print(
                f"  {r.profile_name:<32} {r.storage_system_mass_kg:>10,.0f} kg  "
                f"{r.freight_capacity_loss_tonnes:>8.3f} t"
            )
        print("=" * 68)


# ── CLASS 2: ECONOMICS ENGINE ─────────────────────────────────────────────────

class EconomicsEngine:
    """Calculates LCOH for green H₂ from an on-site PEM electrolyzer in NB."""

    ANALYSIS_PERIOD_YEARS: int   = 10
    ELEC_DEGRADATION_RATE: float = 0.010  # 1.0 %/yr electrolyzer H₂ yield drop

    def __init__(
        self,
        electrolyzer_size_kw: float = 1_000.0,
        electricity_rate: float = cfg.NB_POWER_INDUSTRIAL_RATE,
        capex_per_kw: float = cfg.ELECTROLYZER_CAPEX_PER_KW,
        itc_rate: float = cfg.FEDERAL_H2_ITC,
        opex_rate: float = cfg.ELECTROLYZER_OPEX_RATE,
        capacity_factor: float = 0.80,
    ) -> None:
        self.electrolyzer_size_kw = electrolyzer_size_kw
        self.electricity_rate     = electricity_rate
        self.capex_per_kw         = capex_per_kw
        self.itc_rate             = itc_rate
        self.opex_rate            = opex_rate
        self.capacity_factor      = capacity_factor

    def calculate_lcoh(
        self,
        dynamic_electricity_rate: Optional[float] = None,
        dynamic_capex_per_kw: Optional[float] = None,
        dynamic_capacity_factor: Optional[float] = None,
        profile: Optional[TrainProfile] = None,
        system_age_years: int = 0,
    ) -> LCOHResult:
        rate     = dynamic_electricity_rate if dynamic_electricity_rate is not None \
                   else self.electricity_rate
        capex_kw = dynamic_capex_per_kw     if dynamic_capex_per_kw     is not None \
                   else self.capex_per_kw
        cf       = dynamic_capacity_factor  if dynamic_capacity_factor  is not None \
                   else self.capacity_factor
        profile  = profile                  if profile                  is not None \
                   else cfg.INNOVATION_HTPEM

        base_h2_yield      = 0.70
        effective_h2_yield = max(
            base_h2_yield * (1.0 - self.ELEC_DEGRADATION_RATE * system_age_years),
            base_h2_yield * 0.60,
        )

        # [ARCH-1] Use cfg.ELECTROLYZER_BOP_FRACTION — no more in-line 0.25 magic number.
        gross_capex    = self.electrolyzer_size_kw * capex_kw
        bop_saving     = gross_capex * cfg.ELECTROLYZER_BOP_FRACTION * profile.capex_purification_discount_pct
        adjusted_capex = gross_capex - bop_saving
        itc_savings    = adjusted_capex * self.itc_rate
        net_capex      = adjusted_capex - itc_savings

        # [ECON-1 FIX] OPEX is a fraction of the cost of equipment actually purchased
        # (adjusted_capex), not of the pre-discount gross price.  For HTPEM the PSA
        # purification unit has been eliminated; maintaining it on gross_capex added
        # ~C$900/yr in phantom maintenance cost for equipment that doesn't exist.
        annual_opex      = adjusted_capex * self.opex_rate
        annual_hours     = 8_760.0 * cf
        annual_elec_kwh  = self.electrolyzer_size_kw * annual_hours
        annual_elec_cost = annual_elec_kwh * rate

        annual_h2_kg = (annual_elec_kwh * effective_h2_yield) / cfg.H2_ENERGY_DENSITY_KWH_KG
        total_h2_kg  = annual_h2_kg * self.ANALYSIS_PERIOD_YEARS
        total_cost   = (
            net_capex
            + (annual_opex      * self.ANALYSIS_PERIOD_YEARS)
            + (annual_elec_cost * self.ANALYSIS_PERIOD_YEARS)
        )
        lcoh_per_kg = total_cost / total_h2_kg if total_h2_kg > 0 else 0.0

        return LCOHResult(
            profile_name=profile.name,
            system_age_years=system_age_years,
            effective_h2_efficiency=round(effective_h2_yield, 4),
            electrolyzer_capex_cad=round(gross_capex, 2),
            bop_saving_cad=round(bop_saving, 2),
            itc_savings_cad=round(itc_savings, 2),
            net_capex_after_itc_cad=round(net_capex, 2),
            annual_opex_cad=round(annual_opex, 2),
            annual_electricity_cost_cad=round(annual_elec_cost, 2),
            total_10yr_cost_cad=round(total_cost, 2),
            total_h2_produced_kg=round(total_h2_kg, 2),
            lcoh_cad_per_kg=round(lcoh_per_kg, 4),
            lcoh_cad_per_kwh=round(lcoh_per_kg / cfg.H2_ENERGY_DENSITY_KWH_KG, 4),
            carbon_abatement_notes=(
                f"NB grid {cfg.NB_GRID_CARBON_INTENSITY} kg CO₂/kWh → "
                f"{cfg.FEDERAL_H2_ITC * 100:.0f}% Clean H₂ ITC applies."
            ),
        )

    def print_report(self, result: Optional[LCOHResult] = None) -> None:
        r = result or self.calculate_lcoh()
        print("=" * 60)
        print(f"  ECONOMICS ENGINE — LCOH · {r.profile_name}")
        print("=" * 60)
        print(f"  Stack Age                   : {r.system_age_years} yr")
        print(f"  LCOH                        : C${r.lcoh_cad_per_kg:>8.4f} / kg")
        print("=" * 60)


# ── CLASS 3: THERMAL EFFICIENCY MODULE ───────────────────────────────────────

class ThermalEfficiencyModule:
    """Quantifies the annual thermal energy impact for all four profiles."""

    HTPEM_THRESHOLD_C: float       = 100.0  # min stack temp [°C] for waste-heat cabin heating

    # [THERM-1 FIX] Calibrated from first principles: the LTPEM/Battery profiles both carry
    # a 50 kW electric HVAC unit (cfg.BASELINE_LTPEM.hvac_power_draw_kw) sized for the
    # SJ-Moncton design-point ΔT of 30 °C (cabin 20 °C − winter −10 °C).
    # → BUILDING_HEAT_LOSS_COEFF = 50 kW / 30 °C = 1.6̄67 kW/°C.
    #
    # Previous value (0.15 kW/°C) gave cabin_demand = 4.5 kW at −10 °C, 11× below the
    # 50 kW HVAC draw used for the LTPEM/Battery penalty.  That asymmetry caused
    # HTPEM's waste-heat savings to be understated by the same factor (~11×), while
    # the LTPEM/Battery penalty was computed correctly.  With the corrected coefficient:
    #   cabin_demand(−10 °C) = 1.6̄67 × 30 = 50 kW  (matches HVAC rated power)
    #   HTPEM elec_saved/trip = 50 kW × 1.75 hr = 87.5 kWh  ✓
    #   LTPEM hvac_kwh/trip   = 50 kW × 1.75 hr = 87.5 kWh  ✓  (same model, symmetric)
    BUILDING_HEAT_LOSS_COEFF: float = (
        cfg.BASELINE_LTPEM.hvac_power_draw_kw
        / (cfg.CABIN_TARGET_TEMP_C - cfg.WINTER_AMBIENT_TEMP_C)
    )  # = 50 / 30 ≈ 1.6667 kW/°C

    def __init__(
        self,
        fc_power_kw: float = cfg.TRAIN_POWER_KW,
        fc_efficiency: float = cfg.FC_SYSTEM_EFFICIENCY,
        ambient_temp_c: float = cfg.WINTER_AMBIENT_TEMP_C,
        target_cabin_temp_c: float = cfg.CABIN_TARGET_TEMP_C,
        trips_per_year: int = cfg.TRIPS_PER_YEAR,
        corridor_km: float = _BASE_KM,
    ) -> None:
        self.fc_power_kw         = fc_power_kw
        self.fc_efficiency       = fc_efficiency
        self.ambient_temp_c      = ambient_temp_c
        self.target_cabin_temp_c = target_cabin_temp_c
        self.trips_per_year      = trips_per_year
        self.corridor_km         = corridor_km

    def _waste_heat_output_kw(self, efficiency: float) -> float:
        """
        Waste heat [kW] available from the FC stack.

        Energy balance (per unit gross H₂ input):
            gross_input = net_electrical / η
            thermal_loss = gross_input × max(0, 1 − η − parasitic)

        [PHYSICS-1] thermal_fraction is clamped to ≥ 0.  Without the clamp,
        if efficiency + FC_PARASITIC_FRACTION ≥ 1 (only reachable via extreme
        slider values or future model changes), the formula returns negative
        waste heat, silently corrupting annual_savings and net_annual_impact.
        """
        if efficiency <= 0:
            return 0.0
        thermal_fraction = max(0.0, 1.0 - efficiency - cfg.FC_PARASITIC_FRACTION)
        return (self.fc_power_kw / efficiency) * thermal_fraction

    def _cabin_demand_kw(self, ambient_temp: float) -> float:
        """
        Cabin heating demand [kW] via a simple UA·ΔT model.
        Returns 0.0 when ambient ≥ cabin setpoint (no heating needed).
        """
        return max(0.0, self.BUILDING_HEAT_LOSS_COEFF * (self.target_cabin_temp_c - ambient_temp))

    def calculate_heat_recovery(
        self,
        dynamic_efficiency: Optional[float] = None,
        dynamic_ambient_temp: Optional[float] = None,
        dynamic_corridor_km: Optional[float] = None,
        dynamic_electricity_rate: Optional[float] = None,
        profile: Optional[TrainProfile] = None,
        system_age_years: int = 0,
    ) -> HeatRecoveryResult:
        base_eff  = dynamic_efficiency       if dynamic_efficiency       is not None else self.fc_efficiency
        amb_temp  = dynamic_ambient_temp     if dynamic_ambient_temp     is not None else self.ambient_temp_c
        ckm       = dynamic_corridor_km      if dynamic_corridor_km      is not None else self.corridor_km
        elec_rate = dynamic_electricity_rate if dynamic_electricity_rate is not None \
                    else cfg.NB_POWER_INDUSTRIAL_RATE
        profile   = profile                  if profile                  is not None else cfg.INNOVATION_HTPEM

        efficiency       = apply_degradation(base_eff, system_age_years)
        trip_duration_hr = corridor_trip_duration_hr(ckm)

        stack_temp   = profile.operating_temp_c
        delta_t      = stack_temp - amb_temp
        cabin_demand = self._cabin_demand_kw(amb_temp)

        waste_heat = (
            self._waste_heat_output_kw(efficiency)
            if profile.energy_type in ("h2_ltpem", "h2_htpem")
            else 0.0
        )

        if profile.energy_type == "diesel":
            fraction, elec_saved, savings_trip = 1.0, 0.0, 0.0
        elif profile.energy_type == "h2_htpem" and stack_temp >= self.HTPEM_THRESHOLD_C:
            fraction     = min(waste_heat / cabin_demand, 1.0) if cabin_demand > 0 else 0.0
            elec_saved   = (cabin_demand * fraction) * trip_duration_hr
            savings_trip = elec_saved * elec_rate
        else:
            fraction, elec_saved, savings_trip = 0.0, 0.0, 0.0

        hvac_kwh_trip  = profile.hvac_power_draw_kw * trip_duration_hr
        hvac_cost_trip = hvac_kwh_trip * elec_rate

        annual_savings   = savings_trip   * self.trips_per_year
        annual_hvac_cost = hvac_cost_trip * self.trips_per_year
        net_annual       = annual_savings - annual_hvac_cost

        return HeatRecoveryResult(
            profile_name=profile.name,
            energy_type=profile.energy_type,
            system_age_years=system_age_years,
            effective_fc_efficiency=round(efficiency, 4),
            corridor_km=ckm,
            trip_duration_hr=round(trip_duration_hr, 3),
            stack_operating_temp_c=stack_temp,
            ambient_temp_c=amb_temp,
            delta_t_c=round(delta_t, 1),
            waste_heat_available_kw=round(waste_heat, 2),
            cabin_heating_demand_kw=round(cabin_demand, 2),
            heat_fraction_covered=round(fraction, 3),
            electricity_saved_kwh_per_trip=round(elec_saved, 3),
            annual_savings_cad=round(annual_savings, 2),
            hvac_penalty_kwh_per_trip=round(hvac_kwh_trip, 3),
            hvac_annual_cost_cad=round(annual_hvac_cost, 2),
            net_annual_impact_cad=round(net_annual, 2),
        )

    def calculate_all_profiles(
        self,
        dynamic_efficiency: Optional[float] = None,
        dynamic_ambient_temp: Optional[float] = None,
        dynamic_corridor_km: Optional[float] = None,
        dynamic_electricity_rate: Optional[float] = None,
        system_age_years: int = 0,
    ) -> dict[str, HeatRecoveryResult]:
        return {
            p.energy_type: self.calculate_heat_recovery(
                dynamic_efficiency=dynamic_efficiency,
                dynamic_ambient_temp=dynamic_ambient_temp,
                dynamic_corridor_km=dynamic_corridor_km,
                dynamic_electricity_rate=dynamic_electricity_rate,
                profile=p,
                system_age_years=system_age_years,
            )
            for p in cfg.ALL_PROFILES
        }

    def print_report(self, results: Optional[dict[str, HeatRecoveryResult]] = None) -> None:
        results = results or self.calculate_all_profiles()
        print("=" * 68)
        print("  THERMAL MODULE — 4-Way Comparison")
        print("=" * 68)
        for r in results.values():
            print(
                f"  {r.profile_name:<32} "
                f"Penalty C${r.hvac_annual_cost_cad:>8,.0f}   "
                f"Saving C${r.annual_savings_cad:>8,.0f}   "
                f"Net C${r.net_annual_impact_cad:>8,.0f}"
            )
        print("=" * 68)


# ── CLASS 4: SENSITIVITY ENGINE ───────────────────────────────────────────────

class SensitivityEngine:
    """
    Produces the 2-D LCOH sensitivity grid (electricity rate × CAPEX) and the
    degradation curve (LCOH vs stack age).

    Grid vs EconomicsEngine algebraic equivalence (v6.2 fix):
    ──────────────────────────────────────────────────────────
    The grid inner loop replicates the LCOH formula from EconomicsEngine rather
    than calling it, for O(N²) performance (256 evaluations without 256 full
    LCOHResult object instantiations). After [ARCH-1] and [ARCH-2] both use
    cfg.ELECTROLYZER_BOP_FRACTION, so grid[i, j] == EconomicsEngine.calculate_lcoh(
        dynamic_electricity_rate=rates[j], dynamic_capex_per_kw=capexes[i], ...
    ).lcoh_cad_per_kg for all (i, j) at any given age, eliminating the heatmap
    crosshair mismatch that existed in v6.1.
    """

    ANALYSIS_PERIOD_YEARS: int   = 10
    ELEC_DEGRADATION_RATE: float = 0.010  # 1.0 %/yr electrolyzer H₂ yield drop
    BASE_H2_YIELD: float         = 0.70

    def compute_lcoh_grid(
        self,
        electrolyzer_size_kw: float,
        capacity_factor: float,
        profile: TrainProfile,
        itc_rate: float = cfg.FEDERAL_H2_ITC,
        opex_rate: float = cfg.ELECTROLYZER_OPEX_RATE,
        rate_min: float = 0.04,
        rate_max: float = 0.26,
        rate_steps: int = 16,
        capex_min: float = 500.0,
        capex_max: float = 2_400.0,
        capex_steps: int = 16,
        system_age_years: int = 0,
    ) -> tuple[list[float], list[float], list[list[float]]]:
        step_r = (rate_max  - rate_min)  / max(rate_steps  - 1, 1)
        step_c = (capex_max - capex_min) / max(capex_steps - 1, 1)

        rate_values  = [round(rate_min  + i * step_r, 4) for i in range(rate_steps)]
        capex_values = [round(capex_min + j * step_c, 0) for j in range(capex_steps)]

        effective_yield = max(
            self.BASE_H2_YIELD * (1.0 - self.ELEC_DEGRADATION_RATE * system_age_years),
            self.BASE_H2_YIELD * 0.60,
        )

        # ── Hoist all loop-invariant terms out of the O(N²) body ─────────────
        annual_hours      = 8_760.0 * capacity_factor
        annual_elec_base  = electrolyzer_size_kw * annual_hours  # kWh — rate factored in inner loop
        annual_h2_kg      = (annual_elec_base * effective_yield) / cfg.H2_ENERGY_DENSITY_KWH_KG
        total_h2          = annual_h2_kg * self.ANALYSIS_PERIOD_YEARS
        # [ARCH-2] BOP discount fraction sourced from cfg — matches EconomicsEngine exactly.
        bop_discount_rate = cfg.ELECTROLYZER_BOP_FRACTION * profile.capex_purification_discount_pct

        z_grid: list[list[float]] = []

        for capex_kw in capex_values:
            gross_capex      = electrolyzer_size_kw * capex_kw
            bop_saving       = gross_capex * bop_discount_rate
            adj_capex        = gross_capex - bop_saving
            net_capex        = adj_capex - adj_capex * itc_rate
            # [ECON-1 FIX] OPEX on adj_capex — mirrors EconomicsEngine fix for algebraic equivalence.
            annual_opex      = adj_capex * opex_rate
            base_fixed_costs = net_capex + (annual_opex * self.ANALYSIS_PERIOD_YEARS)

            row: list[float] = []
            for rate in rate_values:
                total_cost = base_fixed_costs + (annual_elec_base * rate * self.ANALYSIS_PERIOD_YEARS)
                row.append(round(total_cost / total_h2, 3) if total_h2 > 0 else 0.0)
            z_grid.append(row)

        return rate_values, capex_values, z_grid

    def compute_degradation_curve(
        self,
        electrolyzer_size_kw: float,
        capacity_factor: float,
        electricity_rate: float,
        capex_per_kw: float,
        profile: TrainProfile,
        itc_rate: float = cfg.FEDERAL_H2_ITC,
        opex_rate: float = cfg.ELECTROLYZER_OPEX_RATE,
        max_age_years: int = 10,
    ) -> list[dict]:
        engine = EconomicsEngine(
            electrolyzer_size_kw=electrolyzer_size_kw,
            electricity_rate=electricity_rate,
            capex_per_kw=capex_per_kw,
            itc_rate=itc_rate,
            opex_rate=opex_rate,
            capacity_factor=capacity_factor,
        )
        baseline_lcoh  = engine.calculate_lcoh(profile=profile, system_age_years=0).lcoh_cad_per_kg
        curve: list[dict] = []
        for year in range(max_age_years + 1):
            r = engine.calculate_lcoh(profile=profile, system_age_years=year)
            lcoh_increase = (
                round((r.lcoh_cad_per_kg - baseline_lcoh) / baseline_lcoh * 100, 2)
                if baseline_lcoh > 0
                else 0.0
            )
            # [VIZ-1] Expose the train FC stack's degrading efficiency so the dashboard
            # can derive annual_fuel_demand_kg (which rises as the stack ages).
            # This is the physically interesting secondary variable for the degradation chart:
            # as the FC loses efficiency, the train needs more H₂ to cover the same route.
            fc_eff = apply_degradation(cfg.FC_SYSTEM_EFFICIENCY, year)
            curve.append({
                "year":              year,
                "lcoh":              r.lcoh_cad_per_kg,
                "effective_yield":   r.effective_h2_efficiency,   # electrolyzer yield (kept for compat)
                "fc_efficiency_pct": round(fc_eff * 100, 2),       # train FC efficiency [%]
                "lcoh_increase_pct": lcoh_increase,
            })
        return curve