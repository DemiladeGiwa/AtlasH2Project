"""
carbon_abatement.py — v2.2 Antigravity Audit Pass
====================================================
Atlas-H2 — Carbon Abatement Calculator

Changes over v2.1:
  [MATH-1]   equivalent_cars_removed: int(floor) → round(), so short corridors
              don't silently report 0 cars when the true value is e.g. 0.6.
  [ARCH-1]   h2_system_annual_cost_cad renamed to annual_h2_cost_cad and
              documented clearly; dynamically injected from dashboard so LCOA
              actually reacts to slider changes (was hard-coded C$1.2 M).
  [STYLE-1]  `float = None` → `Optional[float] = None` (PEP-484 compliance).
  [STYLE-2]  dict/list type hints (PEP-585, Python 3.9+).
  [STYLE-3]  n_years added as an explicit local variable (was implicit len(years)).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config import cfg

CARBON_PRICE_SCHEDULE: dict[int, float] = {
    2026: 110.0,
    2027: 125.0,
    2028: 140.0,
    2029: 155.0,
    2030: 170.0,
}


@dataclass
class AnnualAbatementResult:
    year: int
    diesel_co2_tonnes: float
    h2_co2_tonnes: float
    co2_abated_tonnes: float
    nox_abated_kg: float
    carbon_price_cad_per_tonne: float
    carbon_credit_value_cad: float
    social_benefit_cad: float
    avoided_fuel_cost_cad: float


@dataclass
class LifetimeAbatementResult:
    analysis_years: List[int]
    annual_results: List[AnnualAbatementResult]
    total_co2_abated_tonnes: float
    total_nox_abated_kg: float
    total_carbon_credit_value_cad: float
    total_social_benefit_cad: float
    total_avoided_fuel_cost_cad: float
    lcoa_cad_per_tonne: float
    equivalent_cars_removed: int


class CarbonAbatementCalculator:
    """
    Calculates CO₂ and NOx abatement from switching the SJ–Moncton corridor
    from diesel to Stadler FLIRT H₂. All defaults sourced from cfg singleton.

    Parameters
    ----------
    annual_h2_cost_cad:
        Total annualised H₂ system cost [CAD/yr] used for LCOA calculation.
        Pass ``econ_htpem.annual_electricity_cost_cad + econ_htpem.annual_opex_cad``
        from the dashboard for a fully reactive LCOA figure.
        [ARCH-1] Previously hard-coded as C$1,200,000 regardless of slider state.
    """

    def __init__(
        self,
        corridor_km: float = cfg.CORRIDOR_DISTANCE_KM,
        trips_per_year: int = cfg.TRIPS_PER_YEAR,
        diesel_l_per_km: float = cfg.DIESEL_CONSUMPTION_L_PER_KM,
        h2_co2_kg_per_km: float = 0.012,
        annual_h2_cost_cad: float = 1_200_000.0,  # [ARCH-1] override via dashboard
    ) -> None:
        self.corridor_km        = corridor_km
        self.trips_per_year     = trips_per_year
        self.diesel_l_per_km    = diesel_l_per_km
        self.h2_co2_kg_per_km   = h2_co2_kg_per_km
        self.annual_h2_cost_cad = annual_h2_cost_cad

    # ── private helpers ───────────────────────────────────────────────────────

    def _annual_diesel_fuel_l(self) -> float:
        return self.diesel_l_per_km * self.corridor_km * self.trips_per_year

    def _annual_diesel_co2_tonnes(self) -> float:
        return (self._annual_diesel_fuel_l() * cfg.DIESEL_CO2_PER_LITER) / 1_000.0

    def _annual_h2_co2_tonnes(self) -> float:
        return (self.h2_co2_kg_per_km * self.corridor_km * self.trips_per_year) / 1_000.0

    # ── public API ────────────────────────────────────────────────────────────

    def calculate_annual(
        self,
        year: int,
        dynamic_diesel_price: Optional[float] = None,  # [STYLE-1] was `float = None`
    ) -> AnnualAbatementResult:
        """Calculate abatement metrics for a single calendar year."""
        diesel_price = (
            dynamic_diesel_price if dynamic_diesel_price is not None
            else cfg.DIESEL_PRICE_LITER
        )
        carbon_price = CARBON_PRICE_SCHEDULE.get(year, 170.0)
        diesel_co2   = self._annual_diesel_co2_tonnes()
        h2_co2       = self._annual_h2_co2_tonnes()
        co2_abated   = diesel_co2 - h2_co2
        nox_kg       = (self._annual_diesel_fuel_l() * cfg.DIESEL_NOX_G_PER_LITER) / 1_000.0
        avoided_fuel = self._annual_diesel_fuel_l() * diesel_price

        return AnnualAbatementResult(
            year=year,
            diesel_co2_tonnes=round(diesel_co2, 2),
            h2_co2_tonnes=round(h2_co2, 2),
            co2_abated_tonnes=round(co2_abated, 2),
            nox_abated_kg=round(nox_kg, 2),
            carbon_price_cad_per_tonne=carbon_price,
            carbon_credit_value_cad=round(co2_abated * carbon_price, 2),
            social_benefit_cad=round(co2_abated * cfg.SOCIAL_COST_CARBON_CAD_PER_TONNE, 2),
            avoided_fuel_cost_cad=round(avoided_fuel, 2),
        )

    def calculate_lifetime(
        self,
        start_year: int = 2026,
        end_year: int = 2030,
        dynamic_diesel_price: Optional[float] = None,  # [STYLE-1] was `float = None`
    ) -> LifetimeAbatementResult:
        """Calculate aggregated abatement metrics over the analysis horizon."""
        years   = list(range(start_year, end_year + 1))
        results = [
            self.calculate_annual(y, dynamic_diesel_price=dynamic_diesel_price)
            for y in years
        ]
        n_years = len(years)  # [STYLE-3] named for clarity in the cars-removed formula

        total_co2     = sum(r.co2_abated_tonnes        for r in results)
        total_nox     = sum(r.nox_abated_kg            for r in results)
        total_credits = sum(r.carbon_credit_value_cad  for r in results)
        total_social  = sum(r.social_benefit_cad       for r in results)
        total_fuel    = sum(r.avoided_fuel_cost_cad    for r in results)

        # LCOA = total system cost / total CO₂ abated [ARCH-1]
        lcoa = (self.annual_h2_cost_cad * n_years) / total_co2 if total_co2 > 0 else 0.0

        # Average annual CO₂ abated ÷ EPA car benchmark (4.6 t/yr/car).
        # [MATH-1] round() instead of int() — prevents 0 result on short corridors
        # where total_co2 / n_years yields a sub-0.5 figure.
        cars_per_year = round(total_co2 / (4.6 * n_years))

        return LifetimeAbatementResult(
            analysis_years=years,
            annual_results=results,
            total_co2_abated_tonnes=round(total_co2, 2),
            total_nox_abated_kg=round(total_nox, 2),
            total_carbon_credit_value_cad=round(total_credits, 2),
            total_social_benefit_cad=round(total_social, 2),
            total_avoided_fuel_cost_cad=round(total_fuel, 2),
            lcoa_cad_per_tonne=round(lcoa, 2),
            equivalent_cars_removed=cars_per_year,
        )

    def print_report(self) -> None:
        r = self.calculate_lifetime()
        print("=" * 65)
        print("  CARBON ABATEMENT — SJ <-> Moncton (2026-2030)")
        print("=" * 65)
        print(f"  {'Year':<8} {'CO2 Abated':>12} {'Credit Value':>16} {'Avoided Fuel':>16}")
        print(f"  {'-'*7} {'-'*12} {'-'*16} {'-'*16}")
        for a in r.annual_results:
            print(
                f"  {a.year:<8} "
                f"{a.co2_abated_tonnes:>9,.1f} t  "
                f"C${a.carbon_credit_value_cad:>12,.0f}  "
                f"C${a.avoided_fuel_cost_cad:>12,.0f}"
            )
        print("=" * 65)
        print(f"  Total CO2 Abated         : {r.total_co2_abated_tonnes:>10,.2f} t")
        print(f"  Total Carbon Credits     : C${r.total_carbon_credit_value_cad:>10,.0f}")
        print(f"  Total Avoided Fuel Cost  : C${r.total_avoided_fuel_cost_cad:>10,.0f}")
        print(f"  Total Social Benefit     : C${r.total_social_benefit_cad:>10,.0f}")
        print(f"  LCOA                     : C${r.lcoa_cad_per_tonne:>10,.2f} / tonne")
        print(f"  Equiv. Cars Off Road/yr  : {r.equivalent_cars_removed:>10,}")
        print("=" * 65)


if __name__ == "__main__":
    CarbonAbatementCalculator().print_report()