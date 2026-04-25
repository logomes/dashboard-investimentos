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
    # capital_gain=0 in this test setup, so patrimony grows only via contributions
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
