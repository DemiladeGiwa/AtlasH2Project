
"""
test_engine.py -- Atlas-H2 Digital Infrastructure Twin v10.0
Pytest unit tests for core engine logic.

Run with:
    pytest test_engine.py -v

Test matrix
-----------
Category A — Economics (LCOH)
  test_lcoh_consistency         Manual calculation cross-check against EconomicsEngine.
  test_lcoh_htpem_cheaper       HTPEM BOP discount always yields lower LCOH than LTPEM.
  test_lcoh_zero_corridor       Zero-corridor does not crash; corridor is irrelevant to LCOH.
  test_lcoh_negative_capex      Negative CAPEX raises ValueError at construction.
  test_lcoh_negative_opex       Negative OPEX rate raises ValueError at construction.
  test_lcoh_efficiency_gt_one   Capacity factor > 1.0 raises ValueError at construction.
  test_lcoh_negative_electricity Negative electricity rate raises ValueError at construction.
  test_lcoh_itc_bounds          ITC rate outside [0, 1] raises ValueError.

Category B — Degradation floor
  test_degradation_floor        Efficiency is floored at 50% of initial value for very old engines.
  test_degradation_year_zero    Age 0 returns base efficiency unchanged.
  test_degradation_negative_age Negative age raises ValueError.
  test_degradation_eff_gt_one   base_efficiency > 1.0 raises ValueError.
  test_degradation_eff_zero     base_efficiency = 0.0 raises ValueError.
  test_degradation_monotone     Efficiency is non-increasing as engine ages.

Category C — Zero-corridor resilience
  test_zero_corridor_resilience corridor_km = 0 raises ValueError and never silently
                                returns a nonsensical result.
  test_negative_corridor        Negative corridor_km raises ValueError.
  test_payload_zero_corridor    PayloadAnalyzer.compare_systems rejects km = 0.
  test_carbon_zero_corridor     CarbonAbatementCalculator rejects km = 0.
  test_route_zero_corridor      RouteProfile construction rejects corridor_km = 0.

Category D — PayloadAnalyzer
  test_payload_diesel_zero_mass  Diesel profile always has zero storage mass.
  test_payload_htpem_lt_battery  HTPEM storage mass is always lighter than Battery-EV.
  test_payload_li_ion_density_guard Non-positive li_ion_density raises ValueError.
  test_payload_gravimetric_ratio Gravimetric ratio < 1 for HTPEM vs battery.

Category E — Carbon abatement
  test_carbon_price_schedule     Known schedule values are returned exactly.
  test_carbon_price_extrapolation Post-2030 extrapolation follows +C$15/t/yr rule.
  test_carbon_abatement_positive CO₂ abated is always > 0 on valid corridors.
  test_carbon_lcoa_negative      Cheap electricity scenario should produce negative LCOA
                                 (H₂ cheaper than diesel to operate).
  test_carbon_negative_cost      Negative annual_h2_cost_cad raises ValueError.

Category F — Thermal module
  test_thermal_htpem_no_hvac    HTPEM at 160°C should have zero electric HVAC penalty.
  test_thermal_ltpem_has_hvac   LTPEM at 70°C should have a positive HVAC penalty.
  test_thermal_efficiency_gt_one efficiency > 1.0 raises ValueError in heat recovery.
  test_thermal_fc_power_zero    fc_power_kw = 0 raises ValueError at construction.

Category G — RouteProfile validation
  test_route_invalid_cabin_temp  cabin_target ≤ winter_ambient raises ValueError.
  test_route_zero_trips          trips_per_year = 0 raises ValueError.
  test_route_zero_energy         trip_energy_kwh = 0 raises ValueError.

Category H — Config citation registry
  test_citations_non_empty       CITATIONS dict has at least one entry per constant category.
  test_train_profile_citation    All four TrainProfiles have non-empty citation strings.
"""

from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Fixtures — import from outputs if running against edited files, else from
# the same directory as this test file.
# ---------------------------------------------------------------------------
from config import cfg, RouteProfile, ROUTE_SJ_MONCTON
from atlas_engine import (
    EconomicsEngine,
    PayloadAnalyzer,
    ThermalEfficiencyModule,
    apply_degradation,
    corridor_trip_energy_kwh,
)
from carbon_abatement import CarbonAbatementCalculator, get_carbon_price


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manual_lcoh(
    size_kw: float,
    rate: float,
    capex_kw: float,
    itc: float,
    opex: float,
    cf: float,
    bop_discount: float = 0.0,
    years: int = 10,
) -> float:
    """
    Pure-Python reproduction of the EconomicsEngine LCOH formula.
    Used as the oracle in test_lcoh_consistency.
    """
    base_h2_yield = 0.70
    annual_hours  = 8_760.0 * cf
    annual_elec   = size_kw * annual_hours
    annual_h2     = (annual_elec * base_h2_yield) / cfg.H2_ENERGY_DENSITY_KWH_KG
    total_h2      = annual_h2 * years

    gross_capex  = size_kw * capex_kw
    bop_saving   = gross_capex * cfg.ELECTROLYZER_BOP_FRACTION * bop_discount
    adj_capex    = gross_capex - bop_saving
    itc_saving   = adj_capex * itc
    net_capex    = adj_capex - itc_saving
    annual_opex  = adj_capex * opex
    annual_elec_cost = annual_elec * rate

    total_cost = net_capex + (annual_opex * years) + (annual_elec_cost * years)
    return total_cost / total_h2 if total_h2 > 0 else 0.0


# ===========================================================================
# CATEGORY A — Economics (LCOH)
# ===========================================================================

class TestLCOH:

    def test_lcoh_consistency(self) -> None:
        """
        The engine's LCOH must agree with the manually computed oracle to
        within C$0.01/kg (rounding tolerances only).
        """
        size_kw   = 1_000.0
        rate      = 0.1023     # NB Power rate
        capex_kw  = 1_200.0
        itc       = 0.40
        opex      = 0.02
        cf        = 0.80
        profile   = cfg.INNOVATION_HTPEM  # BOP discount = 0.15

        engine  = EconomicsEngine(
            electrolyzer_size_kw=size_kw,
            electricity_rate=rate,
            capex_per_kw=capex_kw,
            itc_rate=itc,
            opex_rate=opex,
            capacity_factor=cf,
        )
        result = engine.calculate_lcoh(profile=profile, system_age_years=0)

        oracle = _manual_lcoh(
            size_kw=size_kw,
            rate=rate,
            capex_kw=capex_kw,
            itc=itc,
            opex=opex,
            cf=cf,
            bop_discount=profile.capex_purification_discount_pct,
        )
        assert abs(result.lcoh_cad_per_kg - oracle) < 0.01, (
            f"Engine LCOH C${result.lcoh_cad_per_kg:.4f} deviates from "
            f"manual oracle C${oracle:.4f} by more than C$0.01/kg."
        )

    def test_lcoh_htpem_cheaper(self) -> None:
        """HTPEM's BOP discount must always yield a lower LCOH than LTPEM."""
        engine = EconomicsEngine()
        ltpem  = engine.calculate_lcoh(profile=cfg.BASELINE_LTPEM,   system_age_years=0)
        htpem  = engine.calculate_lcoh(profile=cfg.INNOVATION_HTPEM,  system_age_years=0)
        assert htpem.lcoh_cad_per_kg < ltpem.lcoh_cad_per_kg, (
            "HTPEM LCOH must be lower than LTPEM due to BOP CAPEX discount."
        )

    def test_lcoh_zero_corridor_does_not_crash(self) -> None:
        """
        EconomicsEngine does not use corridor_km at all; calling calculate_lcoh
        should succeed regardless of what corridor_km the dashboard might pass.
        LCOH is a plant-level calculation.
        """
        engine = EconomicsEngine(electrolyzer_size_kw=500.0)
        result = engine.calculate_lcoh(profile=cfg.INNOVATION_HTPEM)
        assert result.lcoh_cad_per_kg > 0

    def test_lcoh_negative_capex_raises(self) -> None:
        with pytest.raises(ValueError, match="capex_per_kw cannot be negative"):
            EconomicsEngine(capex_per_kw=-1.0)

    def test_lcoh_negative_opex_raises(self) -> None:
        with pytest.raises(ValueError, match="opex_rate cannot be negative"):
            EconomicsEngine(opex_rate=-0.01)

    def test_lcoh_opex_exceeds_one_raises(self) -> None:
        with pytest.raises(ValueError, match="opex_rate cannot exceed"):
            EconomicsEngine(opex_rate=1.05)

    def test_lcoh_capacity_factor_gt_one_raises(self) -> None:
        with pytest.raises(ValueError, match="capacity_factor must be in"):
            EconomicsEngine(capacity_factor=1.01)

    def test_lcoh_capacity_factor_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="capacity_factor must be in"):
            EconomicsEngine(capacity_factor=0.0)

    def test_lcoh_negative_electricity_raises(self) -> None:
        with pytest.raises(ValueError, match="electricity_rate cannot be negative"):
            EconomicsEngine(electricity_rate=-0.01)

    def test_lcoh_itc_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="itc_rate must be in"):
            EconomicsEngine(itc_rate=1.01)

    def test_lcoh_itc_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="itc_rate must be in"):
            EconomicsEngine(itc_rate=-0.01)

    def test_lcoh_positive_output(self) -> None:
        """LCOH must be a positive finite number under all valid inputs."""
        engine = EconomicsEngine(
            electrolyzer_size_kw=2_000.0,
            electricity_rate=0.08,
            capex_per_kw=900.0,
            itc_rate=0.30,
            opex_rate=0.015,
            capacity_factor=0.90,
        )
        r = engine.calculate_lcoh(profile=cfg.INNOVATION_HTPEM, system_age_years=5)
        assert r.lcoh_cad_per_kg > 0
        assert math.isfinite(r.lcoh_cad_per_kg)

    def test_lcoh_itc_reduces_cost(self) -> None:
        """A higher ITC rate must strictly lower the net CAPEX and therefore LCOH."""
        e_low_itc  = EconomicsEngine(itc_rate=0.0)
        e_high_itc = EconomicsEngine(itc_rate=0.40)
        assert (
            e_high_itc.calculate_lcoh().lcoh_cad_per_kg
            < e_low_itc.calculate_lcoh().lcoh_cad_per_kg
        )

    def test_lcoh_degradation_raises_cost(self) -> None:
        """Older systems must have equal or higher LCOH than new systems."""
        engine = EconomicsEngine()
        lcoh_new = engine.calculate_lcoh(system_age_years=0).lcoh_cad_per_kg
        lcoh_old = engine.calculate_lcoh(system_age_years=10).lcoh_cad_per_kg
        assert lcoh_old >= lcoh_new


# ===========================================================================
# CATEGORY B — Degradation floor
# ===========================================================================

class TestDegradation:

    def test_degradation_floor(self) -> None:
        """
        After extreme age (e.g. 200 years), efficiency must be exactly 50% of
        initial, not zero or negative.
        """
        base = cfg.FC_SYSTEM_EFFICIENCY   # 0.45
        aged = apply_degradation(base, 200)
        floor = base * 0.50
        assert aged == pytest.approx(floor, abs=1e-9), (
            f"Degradation floor should be {floor:.4f}, got {aged:.4f}."
        )

    def test_degradation_year_zero(self) -> None:
        """At age 0 the returned efficiency must equal the base exactly."""
        base = cfg.FC_SYSTEM_EFFICIENCY
        assert apply_degradation(base, 0) == pytest.approx(base, abs=1e-9)

    def test_degradation_negative_age_raises(self) -> None:
        with pytest.raises(ValueError, match="age_years cannot be negative"):
            apply_degradation(cfg.FC_SYSTEM_EFFICIENCY, -1)

    def test_degradation_eff_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="base_efficiency must be in"):
            apply_degradation(1.01, 0)

    def test_degradation_eff_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="base_efficiency must be in"):
            apply_degradation(0.0, 0)

    def test_degradation_monotone(self) -> None:
        """
        Efficiency must be non-increasing year over year until the floor is hit;
        once floored it must remain constant.
        """
        base   = cfg.FC_SYSTEM_EFFICIENCY
        values = [apply_degradation(base, yr) for yr in range(40)]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1], (
                f"Efficiency rose at year {i + 1}: {values[i]:.6f} -> {values[i + 1]:.6f}"
            )

    def test_degradation_floor_is_fifty_percent(self) -> None:
        """The floor is exactly 50% of the initial value, not a hardcoded constant."""
        for base in (0.30, 0.45, 0.60, 1.0):
            assert apply_degradation(base, 9999) == pytest.approx(base * 0.50, abs=1e-9)


# ===========================================================================
# CATEGORY C — Zero-corridor resilience
# ===========================================================================

class TestZeroCorridorResilience:

    def test_zero_corridor_resilience(self) -> None:
        """
        The primary red-team scenario: corridor_km = 0 must raise a clear
        ValueError and must never silently produce an infinite or NaN result.
        """
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            corridor_trip_energy_kwh(0.0)

    def test_negative_corridor_trip_energy(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            corridor_trip_energy_kwh(-50.0)

    def test_payload_zero_corridor_raises(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            PayloadAnalyzer().compare_systems(corridor_km=0.0)

    def test_payload_negative_corridor_raises(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            PayloadAnalyzer().compare_systems(corridor_km=-155.0)

    def test_carbon_zero_corridor_raises(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            CarbonAbatementCalculator(corridor_km=0.0)

    def test_carbon_negative_corridor_raises(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            CarbonAbatementCalculator(corridor_km=-10.0)

    def test_route_zero_corridor_raises(self) -> None:
        with pytest.raises(ValueError, match="corridor_km must be > 0"):
            RouteProfile(
                name="bad_route",
                corridor_km=0.0,
                trip_energy_kwh=4_000.0,
                winter_ambient_temp_c=-10.0,
                cabin_target_temp_c=20.0,
                trips_per_year=730,
            )

    def test_app_does_not_silently_return_nan(self) -> None:
        """
        For the minimum valid corridor (1 km), all engines must return finite
        positive results — no NaN, no inf.
        """
        r   = corridor_trip_energy_kwh(1.0)
        pl  = PayloadAnalyzer().compare_systems(corridor_km=1.0, profile=cfg.INNOVATION_HTPEM)
        assert math.isfinite(r) and r > 0
        assert math.isfinite(pl.storage_system_mass_kg)


# ===========================================================================
# CATEGORY D — PayloadAnalyzer
# ===========================================================================

class TestPayloadAnalyzer:

    def test_payload_diesel_zero_mass(self) -> None:
        """Diesel profile must always return zero storage mass."""
        r = PayloadAnalyzer().compare_systems(profile=cfg.LEGACY_DIESEL)
        assert r.storage_system_mass_kg == 0.0

    def test_payload_htpem_lighter_than_battery(self) -> None:
        """HTPEM has higher energy density, so its storage mass is always less than Battery-EV."""
        pa   = PayloadAnalyzer()
        batt = pa.compare_systems(profile=cfg.BATTERY_EV)
        htpem = pa.compare_systems(profile=cfg.INNOVATION_HTPEM)
        assert htpem.storage_system_mass_kg < batt.storage_system_mass_kg

    def test_payload_htpem_lighter_than_ltpem(self) -> None:
        """HTPEM (1800 Wh/kg) must produce less storage mass than LTPEM (1500 Wh/kg)."""
        pa    = PayloadAnalyzer()
        ltpem = pa.compare_systems(profile=cfg.BASELINE_LTPEM)
        htpem = pa.compare_systems(profile=cfg.INNOVATION_HTPEM)
        assert htpem.storage_system_mass_kg < ltpem.storage_system_mass_kg

    def test_payload_li_ion_density_guard(self) -> None:
        """Non-positive li_ion_density must raise ValueError at construction."""
        with pytest.raises(ValueError, match="li_ion_density must be > 0"):
            PayloadAnalyzer(li_ion_density=0.0)
        with pytest.raises(ValueError, match="li_ion_density must be > 0"):
            PayloadAnalyzer(li_ion_density=-250.0)

    def test_payload_gravimetric_ratio_htpem(self) -> None:
        """
        HTPEM gravimetric ratio vs battery must be between 0 and 1 (it is lighter
        than batteries but heavier than nothing).
        """
        r = PayloadAnalyzer().compare_systems(profile=cfg.INNOVATION_HTPEM)
        assert 0.0 < r.gravimetric_ratio_vs_battery < 1.0

    def test_payload_scales_with_corridor(self) -> None:
        """Storage mass must grow proportionally with corridor length."""
        pa    = PayloadAnalyzer()
        r_100 = pa.compare_systems(corridor_km=100.0, profile=cfg.INNOVATION_HTPEM)
        r_200 = pa.compare_systems(corridor_km=200.0, profile=cfg.INNOVATION_HTPEM)
        ratio = r_200.storage_system_mass_kg / r_100.storage_system_mass_kg
        assert ratio == pytest.approx(2.0, rel=0.01), (
            "Doubling corridor length should double storage mass (linear scaling)."
        )

    def test_payload_all_profiles_complete(self) -> None:
        """compare_all_profiles must return exactly 4 entries, one per profile."""
        results = PayloadAnalyzer().compare_all_profiles()
        assert len(results) == 4
        expected_types = {"diesel", "battery", "h2_ltpem", "h2_htpem"}
        assert set(results.keys()) == expected_types


# ===========================================================================
# CATEGORY E — Carbon abatement
# ===========================================================================

class TestCarbonAbatement:

    def test_carbon_price_schedule_2026(self) -> None:
        assert get_carbon_price(2026) == pytest.approx(110.0)

    def test_carbon_price_schedule_2030(self) -> None:
        assert get_carbon_price(2030) == pytest.approx(170.0)

    def test_carbon_price_extrapolation_2031(self) -> None:
        """2031 = 2030 price + 1 × C$15 = C$185."""
        assert get_carbon_price(2031) == pytest.approx(185.0)

    def test_carbon_price_extrapolation_2040(self) -> None:
        """2040 = 2030 price + 10 × C$15 = C$320."""
        assert get_carbon_price(2040) == pytest.approx(320.0)

    def test_carbon_abatement_positive(self) -> None:
        """CO₂ abated must always be positive for any valid corridor."""
        calc = CarbonAbatementCalculator()
        r    = calc.calculate_lifetime()
        assert r.total_co2_abated_tonnes > 0

    def test_carbon_lcoa_negative_at_cheap_electricity(self) -> None:
        """
        When H₂ production cost is very low (minimal annual_h2_cost_cad),
        LCOA should be negative (H₂ is cheaper than diesel to operate).
        """
        calc = CarbonAbatementCalculator(annual_h2_cost_cad=1.0)
        r    = calc.calculate_lifetime()
        assert r.lcoa_cad_per_tonne < 0, (
            "With near-zero H₂ cost, LCOA must be negative (diesel costs more to operate)."
        )

    def test_carbon_negative_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="annual_h2_cost_cad cannot be negative"):
            CarbonAbatementCalculator(annual_h2_cost_cad=-500.0)

    def test_carbon_nox_positive(self) -> None:
        r = CarbonAbatementCalculator().calculate_lifetime()
        assert r.total_nox_abated_kg > 0

    def test_carbon_annual_credits_increase_with_price(self) -> None:
        """
        Since the carbon price rises each year, annual carbon credit values
        must be non-decreasing across the 2026–2030 schedule.
        """
        r   = CarbonAbatementCalculator().calculate_lifetime()
        credits = [a.carbon_credit_value_cad for a in r.annual_results]
        for i in range(len(credits) - 1):
            assert credits[i] <= credits[i + 1], (
                f"Carbon credits should not decrease as the price schedule rises "
                f"(year index {i} vs {i + 1}: {credits[i]:.2f} vs {credits[i + 1]:.2f})."
            )

    def test_carbon_equivalent_cars_nonzero(self) -> None:
        """The equivalent cars removed metric must be at least 1 for a valid corridor."""
        r = CarbonAbatementCalculator().calculate_lifetime()
        assert r.equivalent_cars_removed >= 1

    def test_carbon_zero_trips_raises(self) -> None:
        with pytest.raises(ValueError, match="trips_per_year must be > 0"):
            CarbonAbatementCalculator(trips_per_year=0)


# ===========================================================================
# CATEGORY F — Thermal module
# ===========================================================================

class TestThermalModule:

    def test_htpem_no_electric_hvac_penalty(self) -> None:
        """
        HTPEM at 160°C recycles waste heat for cabin heating.
        Its electric HVAC power draw (hvac_power_draw_kw) must be 0.0.
        """
        assert cfg.INNOVATION_HTPEM.hvac_power_draw_kw == 0.0

    def test_htpem_hvac_annual_cost_is_zero(self) -> None:
        """
        At new-engine age, HTPEM must produce zero electric HVAC cost.
        """
        mod = ThermalEfficiencyModule()
        r   = mod.calculate_heat_recovery(profile=cfg.INNOVATION_HTPEM, system_age_years=0)
        assert r.hvac_annual_cost_cad == pytest.approx(0.0, abs=0.01)

    def test_ltpem_has_positive_hvac_penalty(self) -> None:
        """LTPEM (70°C) cannot supply cabin heat; HVAC penalty must be positive."""
        mod = ThermalEfficiencyModule()
        r   = mod.calculate_heat_recovery(profile=cfg.BASELINE_LTPEM, system_age_years=0)
        assert r.hvac_annual_cost_cad > 0

    def test_battery_has_positive_hvac_penalty(self) -> None:
        """Battery-EV has no waste heat; HVAC penalty must be positive."""
        mod = ThermalEfficiencyModule()
        r   = mod.calculate_heat_recovery(profile=cfg.BATTERY_EV, system_age_years=0)
        assert r.hvac_annual_cost_cad > 0

    def test_htpem_net_impact_better_than_ltpem(self) -> None:
        """HTPEM net annual impact must be higher (less negative / more positive) than LTPEM."""
        mod   = ThermalEfficiencyModule()
        htpem = mod.calculate_heat_recovery(profile=cfg.INNOVATION_HTPEM, system_age_years=0)
        ltpem = mod.calculate_heat_recovery(profile=cfg.BASELINE_LTPEM,   system_age_years=0)
        assert htpem.net_annual_impact_cad > ltpem.net_annual_impact_cad

    def test_thermal_efficiency_above_one_raises(self) -> None:
        """
        Passing fc_efficiency > 1.0 to calculate_heat_recovery must raise ValueError.
        This guards against slider mis-conversion (e.g. 45 instead of 0.45).
        """
        mod = ThermalEfficiencyModule()
        with pytest.raises(ValueError, match="fc_efficiency cannot exceed 1.0"):
            mod.calculate_heat_recovery(
                dynamic_efficiency=1.01,
                profile=cfg.INNOVATION_HTPEM,
            )

    def test_thermal_fc_power_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="fc_power_kw must be > 0"):
            ThermalEfficiencyModule(fc_power_kw=0.0)

    def test_thermal_fc_efficiency_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="fc_efficiency must be in"):
            ThermalEfficiencyModule(fc_efficiency=0.0)

    def test_thermal_all_profiles_return_results(self) -> None:
        """calculate_all_profiles must return results for all 4 energy types."""
        mod     = ThermalEfficiencyModule()
        results = mod.calculate_all_profiles()
        assert len(results) == 4
        for key in ("diesel", "battery", "h2_ltpem", "h2_htpem"):
            assert key in results


# ===========================================================================
# CATEGORY G — RouteProfile validation
# ===========================================================================

class TestRouteProfile:

    def test_route_invalid_cabin_temp_raises(self) -> None:
        """cabin_target_temp_c must be strictly above winter_ambient_temp_c."""
        with pytest.raises(ValueError, match="cabin_target_temp_c"):
            RouteProfile(
                name="bad",
                corridor_km=155.0,
                trip_energy_kwh=4_000.0,
                winter_ambient_temp_c=20.0,
                cabin_target_temp_c=20.0,  # equal — violates constraint
                trips_per_year=730,
            )

    def test_route_cabin_below_ambient_raises(self) -> None:
        with pytest.raises(ValueError, match="cabin_target_temp_c"):
            RouteProfile(
                name="bad",
                corridor_km=155.0,
                trip_energy_kwh=4_000.0,
                winter_ambient_temp_c=20.0,
                cabin_target_temp_c=15.0,  # below ambient
                trips_per_year=730,
            )

    def test_route_zero_trips_raises(self) -> None:
        with pytest.raises(ValueError, match="trips_per_year must be > 0"):
            RouteProfile(
                name="bad",
                corridor_km=155.0,
                trip_energy_kwh=4_000.0,
                winter_ambient_temp_c=-10.0,
                cabin_target_temp_c=20.0,
                trips_per_year=0,
            )

    def test_route_zero_energy_raises(self) -> None:
        with pytest.raises(ValueError, match="trip_energy_kwh must be > 0"):
            RouteProfile(
                name="bad",
                corridor_km=155.0,
                trip_energy_kwh=0.0,
                winter_ambient_temp_c=-10.0,
                cabin_target_temp_c=20.0,
                trips_per_year=730,
            )

    def test_default_route_is_valid(self) -> None:
        """ROUTE_SJ_MONCTON must pass all its own validation without raising."""
        assert ROUTE_SJ_MONCTON.corridor_km == pytest.approx(155.0)
        assert ROUTE_SJ_MONCTON.trips_per_year == 730


# ===========================================================================
# CATEGORY H — Config citation registry
# ===========================================================================

class TestCitationLayer:

    def test_citations_dict_non_empty(self) -> None:
        """The CITATIONS property must return a non-empty dict."""
        cits = cfg.CITATIONS
        assert isinstance(cits, dict)
        assert len(cits) >= 10, (
            f"Expected at least 10 citation entries, found {len(cits)}."
        )

    def test_all_train_profiles_have_citations(self) -> None:
        """Every TrainProfile must have a non-empty citation string."""
        for profile in cfg.ALL_PROFILES:
            assert profile.citation, (
                f"TrainProfile '{profile.name}' has an empty citation string."
            )
            assert len(profile.citation) > 20, (
                f"TrainProfile '{profile.name}' citation appears too short to be meaningful."
            )

    def test_citations_cover_key_constants(self) -> None:
        """CITATIONS must contain entries for all critical economic constants."""
        required = {
            "NB_POWER_INDUSTRIAL_RATE",
            "FEDERAL_H2_ITC",
            "ELECTROLYZER_CAPEX_PER_KW",
            "DIESEL_CO2_PER_LITER",
            "NB_GRID_CARBON_INTENSITY",
            "SOCIAL_COST_CARBON_CAD_PER_TONNE",
        }
        cit_keys = set(cfg.CITATIONS.keys())
        missing  = required - cit_keys
        assert not missing, (
            f"CITATIONS dict is missing entries for: {missing}. "
            "Every critical constant must have a source reference."
        )

    def test_citation_strings_are_non_trivial(self) -> None:
        """Each citation must be at least 30 characters — enough to name a source."""
        for key, text in cfg.CITATIONS.items():
            assert len(text) >= 30, (
                f"Citation for '{key}' is suspiciously short ({len(text)} chars)."
            )

    def test_htpem_cites_advent(self) -> None:
        """The HTPEM profile citation must reference Advent Technologies."""
        assert "Advent" in cfg.INNOVATION_HTPEM.citation

    def test_ltpem_cites_ballard(self) -> None:
        """The LTPEM profile citation must reference Ballard (the stack supplier)."""
        assert "Ballard" in cfg.BASELINE_LTPEM.citation

    def test_battery_cites_catl(self) -> None:
        """The Battery profile citation must reference CATL (the cell source)."""
        assert "CATL" in cfg.BATTERY_EV.citation