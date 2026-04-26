"""Tests for portfolio simulation with monthly contributions."""
from __future__ import annotations

import numpy as np
import pytest

from config import (
    BenchmarkParams,
    PortfolioParams,
    RealEstateParams,
)
from models import (
    simulate_benchmark,
    simulate_portfolio,
    simulate_real_estate,
)


def _make_simple_portfolio(capital=100_000, monthly_contribution=0.0,
                           indexed=True):
    """Single-asset portfolio with deterministic 10% net yield, no capital gain."""
    from config import AssetClass
    pf = PortfolioParams(
        capital=capital,
        monthly_contribution=monthly_contribution,
        contribution_inflation_indexed=indexed,
    )
    pf.assets = [
        AssetClass("Test", weight=1.0, expected_yield=0.10,
                   capital_gain=0.0, tax_rate=0.0),
    ]
    return pf


def test_zero_contribution_matches_pre_refactor_behavior():
    """monthly_contribution=0 must produce same result as old simulate_portfolio."""
    pf = _make_simple_portfolio(capital=100_000, monthly_contribution=0.0)
    result = simulate_portfolio(pf, horizon_years=10, reinvest_income=True)

    expected_final = 100_000 * (1.10 ** 10)
    assert result.patrimony[-1] == pytest.approx(expected_final, rel=1e-6)


def test_zero_contribution_with_indexing_flag_does_not_change_result():
    """Toggling indexing on a zero-contribution portfolio must be a no-op."""
    pf_off = _make_simple_portfolio(monthly_contribution=0.0, indexed=False)
    pf_on = _make_simple_portfolio(monthly_contribution=0.0, indexed=True)
    r_off = simulate_portfolio(pf_off, horizon_years=10)
    r_on = simulate_portfolio(pf_on, horizon_years=10)
    np.testing.assert_allclose(r_off.patrimony, r_on.patrimony)


def test_nominal_contribution_no_inflation():
    """Aporte nominal R$ 1000/mes, IPCA=0, horizon=5, capital=0, rate=10%.

    Year-by-year (begin-of-year, R$ 12_000 each Jan 1):
      end y1 = 12000 * 1.10                     = 13_200
      end y2 = (13_200 + 12_000) * 1.10         = 27_720
      end y3 = (27_720 + 12_000) * 1.10         = 43_692
      end y4 = (43_692 + 12_000) * 1.10         = 61_261.20
      end y5 = (61_261.20 + 12_000) * 1.10      = 80_587.32
    """
    pf = _make_simple_portfolio(
        capital=0, monthly_contribution=1_000, indexed=False)
    # Force IPCA=0 by passing it explicitly via simulate_portfolio
    result = simulate_portfolio(pf, horizon_years=5, reinvest_income=True,
                                ipca=0.0)
    assert result.patrimony[-1] == pytest.approx(80_587.32, abs=0.01)


def test_indexed_contribution_zero_ipca_equals_nominal():
    pf_nominal = _make_simple_portfolio(
        capital=50_000, monthly_contribution=500, indexed=False)
    pf_indexed = _make_simple_portfolio(
        capital=50_000, monthly_contribution=500, indexed=True)
    r_nom = simulate_portfolio(pf_nominal, horizon_years=10, ipca=0.0)
    r_idx = simulate_portfolio(pf_indexed, horizon_years=10, ipca=0.0)
    np.testing.assert_allclose(r_nom.patrimony, r_idx.patrimony)


def test_indexed_contribution_with_ipca():
    """With IPCA=5%, indexed aporte at year t = base × 1.05**t."""
    pf = _make_simple_portfolio(
        capital=0, monthly_contribution=1_000, indexed=True)
    result = simulate_portfolio(pf, horizon_years=3, reinvest_income=True,
                                ipca=0.05)

    # Year 0 contribution = 12_000 (no inflation yet, t=0)
    # Year 1 contribution = 12_000 * 1.05 = 12_600
    # Year 2 contribution = 12_000 * 1.05^2 = 13_230
    # Each compounds for (horizon - t) years at 10%:
    #   y0: 12_000 * 1.10^3 = 15_972
    #   y1: 12_600 * 1.10^2 = 15_246
    #   y2: 13_230 * 1.10^1 = 14_553
    expected_final = 12_000 * (1.10 ** 3) + 12_600 * (1.10 ** 2) + 13_230 * 1.10
    assert result.patrimony[-1] == pytest.approx(expected_final, rel=1e-4)


def test_contribution_with_reinvest_false():
    """When reinvest=False, contributions still grow capital, yields are distributed."""
    pf = _make_simple_portfolio(
        capital=10_000, monthly_contribution=500, indexed=False)
    # capital_gain=0 here means rate=0 when reinvest=False, so contributions
    # accumulate at face value (no compounding within this test).
    result = simulate_portfolio(pf, horizon_years=3,
                                reinvest_income=False, ipca=0.0)

    # capital + 3 years × 12 × 500 = 10_000 + 18_000 = 28_000
    assert result.patrimony[-1] == pytest.approx(28_000, abs=1.0)


def test_simulate_real_estate_unchanged():
    """Regression: real estate simulation must be unaffected by Phase 1 changes."""
    re_params = RealEstateParams()
    result = simulate_real_estate(re_params, horizon_years=10)
    # Sanity check: positive patrimony, monotonic non-decreasing
    assert result.patrimony[-1] > re_params.property_value
    assert all(result.patrimony[i] <= result.patrimony[i+1]
               for i in range(len(result.patrimony) - 1))


def test_simulate_benchmark_unchanged():
    """Regression: benchmark simulation must be unaffected by Phase 1 changes."""
    bench = BenchmarkParams(capital=100_000)
    result = simulate_benchmark(bench, horizon_years=5)
    expected = 100_000 * (1 + bench.net_yield()) ** 5
    assert result.patrimony[-1] == pytest.approx(expected, rel=1e-6)


# ---------- Financed real-estate scenarios ----------

def _make_financed_params(
    property_value: float = 200_000.0,
    monthly_rent: float = 1_500.0,
    appreciation: float = 0.0,
    iptu_rate: float = 0.0,
    vacancy_months: float = 0.0,
    mgmt_fee: float = 0.0,
    income_tax: float = 0.0,
    maintenance: float = 0.0,
    insurance_annual: float = 0.0,
    term_years: int = 30,
    annual_rate: float = 0.10,
    entry_pct: float = 0.20,
    system: str = "SAC",
    monthly_insurance_rate: float = 0.0,
):
    """Helper: build a RealEstateParams with financing attached, costs zeroed by default."""
    from config import FinancingParams
    fin = FinancingParams(
        term_years=term_years,
        annual_rate=annual_rate,
        entry_pct=entry_pct,
        system=system,  # type: ignore[arg-type]
        monthly_insurance_rate=monthly_insurance_rate,
    )
    return RealEstateParams(
        property_value=property_value,
        monthly_rent=monthly_rent,
        annual_appreciation=appreciation,
        iptu_rate=iptu_rate,
        vacancy_months_per_year=vacancy_months,
        management_fee_pct=mgmt_fee,
        maintenance_annual=maintenance,
        insurance_annual=insurance_annual,
        income_tax_bracket=income_tax,
        financing=fin,
    )


def test_real_estate_no_financing_unchanged():
    """Regression: financing=None → identical patrimony to Phase 1 behavior."""
    re_params = RealEstateParams()
    result = simulate_real_estate(re_params, horizon_years=10)
    expected_property_y10 = re_params.property_value * (1 + re_params.annual_appreciation) ** 10
    assert result.debt_balance is None
    assert result.patrimony[-1] >= expected_property_y10


def test_real_estate_with_financing_returns_debt_balance():
    re_params = _make_financed_params()
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    assert result.debt_balance is not None
    assert len(result.debt_balance) == 11


def test_financed_horizon_equals_term_pays_off():
    re_params = _make_financed_params(term_years=10)
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    assert result.debt_balance[-1] == pytest.approx(0.0, abs=1e-6)


def test_financed_horizon_less_than_term_leaves_debt():
    re_params = _make_financed_params(term_years=30)
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    assert result.debt_balance[-1] > 0


def test_financed_horizon_greater_than_term_zero_after_term():
    re_params = _make_financed_params(term_years=10)
    result = simulate_real_estate(
        re_params, horizon_years=15, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    np.testing.assert_allclose(result.debt_balance[10:], 0.0, atol=1e-6)


def test_financed_internal_portfolio_can_go_negative():
    """Low rent + high payment → internal portfolio goes negative, no error raised."""
    re_params = _make_financed_params(
        property_value=500_000.0,
        monthly_rent=500.0,
        term_years=10, annual_rate=0.15, entry_pct=0.20,
    )
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=100_000.0,
        internal_portfolio_rate=0.0,
    )
    property_values = re_params.property_value * (1 + re_params.annual_appreciation) ** np.arange(11)
    internal = result.patrimony - property_values + result.debt_balance
    assert internal.min() < 0


def test_capital_initial_split_correctly():
    """capital=300k, entry_pct=20%, property=200k → buffer = 300k - 40k = 260k.

    With zero rent and zero portfolio rate over 1 year, year 0 patrimony equals
    property_value - loan_principal + buffer = 200k - 160k + 260k = 300k.
    """
    re_params = _make_financed_params(
        property_value=200_000.0, monthly_rent=0.0, entry_pct=0.20,
        term_years=10, annual_rate=0.10,
    )
    result = simulate_real_estate(
        re_params, horizon_years=1, capital_initial=300_000.0,
        internal_portfolio_rate=0.0,
    )
    assert result.patrimony[0] == pytest.approx(300_000.0, abs=1e-6)


def test_sac_vs_price_final_patrimony():
    """Same inputs except system → both viable, Price has more interest paid (smaller portfolio)."""
    re_sac = _make_financed_params(term_years=10, system="SAC")
    re_price = _make_financed_params(term_years=10, system="Price")
    r_sac = simulate_real_estate(
        re_sac, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    r_price = simulate_real_estate(
        re_price, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    assert r_sac.debt_balance[-1] == pytest.approx(0.0, abs=1e-6)
    assert r_price.debt_balance[-1] == pytest.approx(0.0, abs=1e-6)
    assert r_sac.patrimony[-1] > r_price.patrimony[-1]
