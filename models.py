"""Financial simulation engine for scenario comparison.

Computes patrimony evolution, monthly income progression, and sensitivity
analysis for real estate vs portfolio scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from config import RealEstateParams, PortfolioParams, BenchmarkParams


@dataclass(slots=True)
class SimulationResult:
    years: np.ndarray
    patrimony: np.ndarray            # Patrimony at end of each year
    annual_income: np.ndarray        # Income generated in that year
    cumulative_income: np.ndarray    # Total income accumulated
    label: str
    color: str


def simulate_real_estate(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool = True,
) -> SimulationResult:
    """Simulate real estate investment over time.

    Patrimony grows by appreciation. Income from rent compounds only if
    reinvested at the same blended yield as a generic portfolio (assumed to
    match `params.total_return()` — net yield + appreciation).
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    years = np.arange(0, horizon_years + 1)

    # Property value evolution
    property_values = params.property_value * (1 + params.annual_appreciation) ** years

    # Annual rent grows with appreciation as well (typical IGP-M / IPCA reajuste)
    annual_net_income = np.array([
        params.net_annual_income() * (1 + params.annual_appreciation) ** y
        for y in years
    ])

    if reinvest_income:
        # Reinvested at the same blended return rate
        rate = params.total_return()
        accumulated = np.zeros_like(years, dtype=float)
        for i in range(1, len(years)):
            accumulated[i] = accumulated[i - 1] * (1 + rate) + annual_net_income[i]
        patrimony = property_values + accumulated
    else:
        patrimony = property_values

    cumulative_income = np.cumsum(annual_net_income)

    return SimulationResult(
        years=years,
        patrimony=patrimony,
        annual_income=annual_net_income,
        cumulative_income=cumulative_income,
        label="Imóvel",
        color="#C0392B",
    )


def simulate_portfolio(
    params: PortfolioParams,
    horizon_years: int,
    reinvest_income: bool = True,
) -> SimulationResult:
    """Simulate a diversified portfolio with full reinvestment.

    Total return is composed of (net yield) + (capital gain). When reinvesting,
    everything compounds at the total return rate.
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    years = np.arange(0, horizon_years + 1)
    rate = params.total_return() if reinvest_income else params.blended_capital_gain()
    yield_only = params.blended_yield()

    if reinvest_income:
        patrimony = params.capital * (1 + rate) ** years
        # Income generated = patrimony at start of year × yield
        annual_income = np.array([
            params.capital * (1 + rate) ** max(y - 1, 0) * yield_only
            for y in years
        ])
    else:
        patrimony = params.capital * (1 + params.blended_capital_gain()) ** years
        annual_income = np.full_like(years, params.capital * yield_only, dtype=float)

    cumulative_income = np.cumsum(annual_income)

    return SimulationResult(
        years=years,
        patrimony=patrimony,
        annual_income=annual_income,
        cumulative_income=cumulative_income,
        label="Carteira Diversificada",
        color="#27AE60",
    )


def simulate_benchmark(
    params: BenchmarkParams,
    horizon_years: int,
) -> SimulationResult:
    """Tesouro Selic with full reinvestment (reference benchmark)."""
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    years = np.arange(0, horizon_years + 1)
    rate = params.net_yield()
    patrimony = params.capital * (1 + rate) ** years
    annual_income = np.array([
        params.capital * (1 + rate) ** max(y - 1, 0) * rate
        for y in years
    ])
    cumulative_income = np.cumsum(annual_income)

    return SimulationResult(
        years=years,
        patrimony=patrimony,
        annual_income=annual_income,
        cumulative_income=cumulative_income,
        label="Tesouro Selic (líquido)",
        color="#F39C12",
    )


def build_comparison_dataframe(
    results: Iterable[SimulationResult],
) -> pd.DataFrame:
    """Combine multiple simulation results into a single long-format dataframe."""
    frames = []
    for r in results:
        frames.append(pd.DataFrame({
            "Ano": r.years,
            "Patrimônio": r.patrimony,
            "Renda Anual": r.annual_income,
            "Renda Acumulada": r.cumulative_income,
            "Cenário": r.label,
        }))
    return pd.concat(frames, ignore_index=True)


# ---------- Sensitivity analysis ----------

def sensitivity_real_estate(
    base_params: RealEstateParams,
    horizon_years: int,
    deltas: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    """Tornado-style sensitivity: vary one parameter at a time.

    Args:
        base_params: baseline scenario
        horizon_years: simulation horizon
        deltas: dict mapping parameter name to (low, high) values

    Returns:
        DataFrame with columns [parameter, low_patrimony, high_patrimony, base_patrimony]
    """
    base_result = simulate_real_estate(base_params, horizon_years)
    base_patrimony = float(base_result.patrimony[-1])

    rows = []
    for param_name, (low, high) in deltas.items():
        low_params = _replace_field(base_params, param_name, low)
        high_params = _replace_field(base_params, param_name, high)

        low_result = simulate_real_estate(low_params, horizon_years)
        high_result = simulate_real_estate(high_params, horizon_years)

        rows.append({
            "Parâmetro": param_name,
            "Cenário Pessimista": float(low_result.patrimony[-1]),
            "Cenário Base": base_patrimony,
            "Cenário Otimista": float(high_result.patrimony[-1]),
        })

    return pd.DataFrame(rows)


def _replace_field(obj: object, field_name: str, value: float) -> object:
    """Create a copy of a dataclass with a single field replaced."""
    from copy import copy
    new_obj = copy(obj)
    setattr(new_obj, field_name, value)
    return new_obj


# ---------- Tax impact analysis ----------

def compute_irpf_carne_leao(monthly_income: float) -> float:
    """Compute IRPF using current 2026 progressive table (R$).

    From Jan/2026 (Lei 15.270/2025): redutor effectively isenta até R$ 5.000.
    Above R$ 7.350, full progressive table applies up to 27,5%.
    """
    if monthly_income <= 5_000:
        return 0.0
    if monthly_income <= 7_350:
        # Reductor decreases linearly in this range — approximation
        # Effective rate ramps from 0% to ~12%
        progress = (monthly_income - 5_000) / (7_350 - 5_000)
        effective_rate = 0.075 * progress
        return monthly_income * effective_rate

    # Standard progressive table for > R$ 7.350
    if monthly_income <= 4_664.68:
        return 0.0
    elif monthly_income <= 9_338.92:
        return monthly_income * 0.225 - 950.94
    return monthly_income * 0.275 - 1_417.89


def annual_tax_comparison(
    real_estate: RealEstateParams,
    portfolio: PortfolioParams,
) -> pd.DataFrame:
    """Compare annual tax burden between scenarios."""
    re_tax = real_estate.income_tax_amount()
    re_gross_income = real_estate.gross_annual_rent()

    # Portfolio tax (computed inside blended yield)
    pf_gross_income = sum(
        portfolio.capital * a.weight * a.expected_yield
        for a in portfolio.assets
    )
    pf_tax = sum(
        portfolio.capital * a.weight * a.expected_yield * a.tax_rate
        for a in portfolio.assets
    )

    return pd.DataFrame([
        {
            "Cenário": "Imóvel",
            "Receita Bruta": re_gross_income,
            "Imposto Anual": re_tax,
            "Receita Líquida": re_gross_income - re_tax,
            "Carga Tributária Efetiva": re_tax / re_gross_income if re_gross_income else 0.0,
        },
        {
            "Cenário": "Carteira Diversificada",
            "Receita Bruta": pf_gross_income,
            "Imposto Anual": pf_tax,
            "Receita Líquida": pf_gross_income - pf_tax,
            "Carga Tributária Efetiva": pf_tax / pf_gross_income if pf_gross_income else 0.0,
        },
    ])
