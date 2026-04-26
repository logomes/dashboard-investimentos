"""Financial simulation engine for scenario comparison.

Computes patrimony evolution, monthly income progression, and sensitivity
analysis for real estate vs portfolio scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from config import (
    BenchmarkParams,
    FinancingParams,
    PortfolioParams,
    RealEstateParams,
)


@dataclass(slots=True)
class SimulationResult:
    years: np.ndarray
    patrimony: np.ndarray            # Patrimony at end of each year
    annual_income: np.ndarray        # Income generated in that year
    cumulative_income: np.ndarray    # Total income accumulated
    label: str
    color: str
    debt_balance: np.ndarray | None = None    # outstanding loan balance at end of each year (financed only)


@dataclass(slots=True, frozen=True)
class AmortizationSchedule:
    """Monthly amortization schedule for a fixed-rate loan."""
    payments: np.ndarray   # total payment (interest + principal) per month
    interest: np.ndarray   # interest portion per month
    principal: np.ndarray  # principal amortization per month
    balance: np.ndarray    # outstanding balance at END of each month


def _sac_schedule(principal: float, monthly_rate: float, n_months: int) -> AmortizationSchedule:
    """Sistema de Amortização Constante: principal constant per month."""
    amortization = principal / n_months
    principal_arr = np.full(n_months, amortization)
    # Balance at the START of month k (0-indexed): principal - k * amortization
    balance_start = principal - np.arange(n_months) * amortization
    interest = balance_start * monthly_rate
    payments = principal_arr + interest
    balance_end = balance_start - principal_arr
    # SAC final balance is algebraically zero; no drift cleanup needed.
    return AmortizationSchedule(
        payments=payments,
        interest=interest,
        principal=principal_arr,
        balance=balance_end,
    )


def _price_schedule(principal: float, monthly_rate: float, n_months: int) -> AmortizationSchedule:
    """Price (French) system: constant payment per month."""
    if monthly_rate == 0:
        amortization = principal / n_months
        return AmortizationSchedule(
            payments=np.full(n_months, amortization),
            interest=np.zeros(n_months),
            principal=np.full(n_months, amortization),
            balance=principal - np.arange(1, n_months + 1) * amortization,
        )

    factor = (1 + monthly_rate) ** n_months
    pmt = principal * monthly_rate * factor / (factor - 1)

    payments = np.full(n_months, pmt)
    interest = np.zeros(n_months)
    principal_arr = np.zeros(n_months)
    balance = np.zeros(n_months)

    saldo = principal
    for k in range(n_months):
        interest[k] = saldo * monthly_rate
        principal_arr[k] = pmt - interest[k]
        saldo -= principal_arr[k]
        balance[k] = saldo
    # Numerical drift cleanup
    balance[-1] = 0.0
    return AmortizationSchedule(
        payments=payments,
        interest=interest,
        principal=principal_arr,
        balance=balance,
    )


def build_schedule(financing: FinancingParams, principal: float) -> AmortizationSchedule:
    """Dispatch to SAC or Price based on financing.system."""
    n_months = financing.term_years * 12
    if financing.system == "SAC":
        return _sac_schedule(principal, financing.monthly_rate, n_months)
    if financing.system == "Price":
        return _price_schedule(principal, financing.monthly_rate, n_months)
    raise ValueError(f"unknown amortization system: {financing.system}")


def simulate_real_estate(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool = True,
    capital_initial: float | None = None,
    internal_portfolio_rate: float = 0.0,
) -> SimulationResult:
    """Top-level dispatcher for real estate scenario.

    Routes to the cash variant (Phase 1, no financing) or the financed
    variant based on `params.financing`.
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")
    if params.financing is None:
        return _simulate_real_estate_cash(params, horizon_years, reinvest_income)
    if capital_initial is None:
        capital_initial = params.property_value
    return _simulate_real_estate_financed(
        params, horizon_years, reinvest_income, capital_initial, internal_portfolio_rate,
    )


def _simulate_real_estate_cash(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool,
) -> SimulationResult:
    """Cash purchase: original Phase 1 behavior, untouched."""
    years = np.arange(0, horizon_years + 1)

    property_values = params.property_value * (1 + params.annual_appreciation) ** years

    annual_net_income = np.array([
        params.net_annual_income() * (1 + params.annual_appreciation) ** y
        for y in years
    ])

    if reinvest_income:
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


def _simulate_real_estate_financed(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool,
    capital_initial: float,
    internal_portfolio_rate: float,
) -> SimulationResult:
    """Financed purchase: entry + monthly amortization, surplus invested at internal_portfolio_rate."""
    fin = params.financing
    if fin is None:
        raise ValueError(
            "_simulate_real_estate_financed requires params.financing to be set; "
            "use simulate_real_estate() dispatcher instead."
        )

    entry = params.property_value * fin.entry_pct
    if capital_initial < entry:
        raise ValueError(
            f"capital_initial ({capital_initial:.2f}) is below the required "
            f"entry ({entry:.2f}) at entry_pct={fin.entry_pct:.0%}."
        )

    loan_principal = params.property_value - entry
    initial_buffer = capital_initial - entry

    # Build full schedule for term_years × 12 months
    schedule = build_schedule(fin, loan_principal)

    # Pad/truncate to horizon_years × 12 months
    n_months_horizon = horizon_years * 12
    n_months_term = fin.term_years * 12
    if n_months_horizon > n_months_term:
        pad = n_months_horizon - n_months_term
        payments_full = np.concatenate([schedule.payments, np.zeros(pad)])
        balance_full = np.concatenate([schedule.balance, np.zeros(pad)])
    elif n_months_horizon < n_months_term:
        payments_full = schedule.payments[:n_months_horizon]
        balance_full = schedule.balance[:n_months_horizon]
    else:
        payments_full = schedule.payments
        balance_full = schedule.balance

    # Aggregate monthly → annual
    payments_annual = payments_full.reshape(horizon_years, 12).sum(axis=1)

    # Insurance: applied on balance at START of each month (before that month's amortization)
    balance_at_month_start = np.concatenate([[loan_principal], balance_full[:-1]])
    insurance_monthly = balance_at_month_start * fin.monthly_insurance_rate
    insurance_annual = insurance_monthly.reshape(horizon_years, 12).sum(axis=1)

    # Annual rent net (Phase 1 logic, grows with appreciation)
    annual_net_income = np.array([
        params.net_annual_income() * (1 + params.annual_appreciation) ** y
        for y in range(horizon_years + 1)
    ])
    # net cash flow per year (year 0 has no payment activity; index 1.. of net_income aligns)
    net_cash_flow = annual_net_income[1:] - payments_annual - insurance_annual

    # Internal portfolio: starts at initial_buffer; PMT-end semantics (rate first, then cash flow)
    rate = internal_portfolio_rate if reinvest_income else 0.0
    internal_portfolio = np.zeros(horizon_years + 1)
    internal_portfolio[0] = initial_buffer
    for y in range(1, horizon_years + 1):
        internal_portfolio[y] = internal_portfolio[y - 1] * (1 + rate) + net_cash_flow[y - 1]

    # Property value evolution
    years = np.arange(0, horizon_years + 1)
    property_values = params.property_value * (1 + params.annual_appreciation) ** years

    # Debt balance at end of each year
    debt_balance = np.zeros(horizon_years + 1)
    debt_balance[0] = loan_principal
    for y in range(1, horizon_years + 1):
        idx = 12 * y - 1
        if idx < len(balance_full):
            debt_balance[y] = balance_full[idx]
        else:
            debt_balance[y] = 0.0

    patrimony = property_values - debt_balance + internal_portfolio
    cumulative_income = np.cumsum(annual_net_income)

    return SimulationResult(
        years=years,
        patrimony=patrimony,
        annual_income=annual_net_income,
        cumulative_income=cumulative_income,
        label="Imóvel (financiado)",
        color="#C0392B",
        debt_balance=debt_balance,
    )


def simulate_portfolio(
    params: PortfolioParams,
    horizon_years: int,
    reinvest_income: bool = True,
    ipca: float = 0.0,
) -> SimulationResult:
    """Simulate a diversified portfolio with full reinvestment and optional aporte.

    `ipca` is only used when `params.contribution_inflation_indexed` is True.
    Contributions enter at the beginning of each year (PMT begin) and compound
    at the same rate as `reinvest_income` mode.
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    years = np.arange(0, horizon_years + 1)
    rate = params.total_return() if reinvest_income else params.blended_capital_gain()
    yield_only = params.blended_yield()

    # Vectorized base patrimony (no contributions)
    patrimony = params.capital * (1 + rate) ** years

    # Add contributions (begin-of-year), compounded at `rate` until end-of-year y
    monthly = params.monthly_contribution
    indexed = params.contribution_inflation_indexed
    if monthly > 0:
        annual_base = 12.0 * monthly
        contribution_pv = np.zeros_like(patrimony, dtype=float)
        for y in range(1, horizon_years + 1):
            total = 0.0
            for t in range(y):
                aporte_t = annual_base * ((1 + ipca) ** t if indexed else 1.0)
                total += aporte_t * (1 + rate) ** (y - t)
            contribution_pv[y] = total
        patrimony = patrimony + contribution_pv

    # Annual income generated (yield on patrimony at start of year)
    if reinvest_income:
        annual_income = np.array([
            patrimony[max(y - 1, 0)] * yield_only
            for y in years
        ])
    else:
        # Without reinvest, income is on principal + accumulated contributions
        annual_income = patrimony * yield_only

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
