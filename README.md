# Atlas-H2: Digital Infrastructure Twin
### Saint John ↔ Moncton Hydrogen Rail Corridor | New Brunswick, Canada

> *A Techno-Economic Analysis (TEA) engine simulating the replacement of diesel
> rolling stock with Stadler FLIRT H₂ hydrogen multiple units, with a focus on
> High-Temperature PEM (HTPEM) fuel cell technology.*

---

## Table of Contents
1. [Project Overview](#overview)
2. [Repository Structure](#structure)
3. [Methodology & Math Appendix](#appendix)
   - [Module 1: Payload Mass Penalty](#module-1)
   - [Module 2: Levelized Cost of Hydrogen (LCOH)](#module-2)
   - [Module 3: HTPEM Thermal Recovery](#module-3)
4. [Configuration Layer](#config)
5. [Running the Simulation](#running)

---

## Project Overview <a name="overview"></a>

Atlas-H2 is my Python-based Digital model of the
full techno-economic profile of a hydrogen rail transition on the
155 km Saint John–Moncton corridor as proof for hydrogen's viability. 

The simulation produces:
- **Payload Analysis** — gravimetric comparison of Li-ion vs. H₂+HTPEM systems
- **LCOH Calculation** — 10-year Levelized Cost of Hydrogen using NB-specific inputs
- **Thermal Recovery** — waste heat monetization for NB winter operations
- **Carbon Abatement** — CO₂, NOx, and carbon credit valuation (2026–2030)

All physical and economic constants are in `scripts/config.py`
(frozen dataclass), thit is the source used across all modules.

---

## Repository Structure <a name="structure"></a>
Atlas-H2/
├── scripts/                # The "Models" (Computational Engines)
│   ├── atlas_engine.py      # Core logic for Payload and Thermal Recovery
│   ├── carbon_abatement.py  # 5-year environmental & credit valuation
│   └── config.py            # Source of Truth: Frozen dataclass for all constants
├── dashboard.py            # The "View" (Streamlit Industrial OS UI)
├── requirements.txt        # Dependency manifest
└── README.md               # Documentation

