"""Tests for Monte Carlo helpers and MonteCarloResult."""
from __future__ import annotations

import numpy as np
import pytest

from models import (
    MonteCarloResult,
    _compute_max_drawdowns,
    _compute_percentiles,
    _draw_normal_returns,
)


def test_draw_normal_returns_shape_and_seed_reproducibility():
    rng = np.random.default_rng(42)
    a = _draw_normal_returns(rng, mean=0.10, sigma=0.05, shape=(100, 30))
    rng2 = np.random.default_rng(42)
    b = _draw_normal_returns(rng2, mean=0.10, sigma=0.05, shape=(100, 30))
    assert a.shape == (100, 30)
    np.testing.assert_array_equal(a, b)


def test_compute_percentiles_monotonicity():
    # Synthetic trajectories (N=1000, T+1=11)
    rng = np.random.default_rng(0)
    trajectories = rng.normal(loc=100.0, scale=10.0, size=(1000, 11))
    pcts = _compute_percentiles(trajectories)
    for t in range(11):
        assert pcts["p10"][t] <= pcts["p50"][t] <= pcts["p90"][t]


def test_max_drawdown_known_case():
    """Trajectory [100, 120, 80, 90] → drawdown = (120-80)/120 = 33.33%."""
    trajectories = np.array([[100.0, 120.0, 80.0, 90.0]])
    drawdowns = _compute_max_drawdowns(trajectories)
    assert drawdowns.shape == (1,)
    assert drawdowns[0] == pytest.approx((120.0 - 80.0) / 120.0)


def test_monte_carlo_result_prob_target():
    final_dist = np.array([100.0, 200.0, 50.0, 300.0, 150.0])
    result = MonteCarloResult(
        trajectories=np.zeros((5, 2)),
        percentiles={"p10": np.zeros(2), "p50": np.zeros(2), "p90": np.zeros(2)},
        final_distribution=final_dist,
        max_drawdowns=np.zeros(5),
        label="Test",
        color="#000000",
    )
    # 3 of 5 trajectories ≥ 150
    assert result.prob_target(150.0) == pytest.approx(0.6)
    # 0 of 5 trajectories ≥ 1000
    assert result.prob_target(1000.0) == pytest.approx(0.0)
    # All trajectories ≥ 0
    assert result.prob_target(0.0) == pytest.approx(1.0)


# ---------- simulate_portfolio_mc ----------

def _make_mc_portfolio(volatility=0.0, monthly_contribution=0.0, indexed=True):
    """Single-asset deterministic portfolio for MC tests; volatility configurable."""
    from config import AssetClass, PortfolioParams
    pf = PortfolioParams(
        capital=100_000.0,
        monthly_contribution=monthly_contribution,
        contribution_inflation_indexed=indexed,
    )
    pf.assets = [
        AssetClass("Test", weight=1.0, expected_yield=0.10,
                   capital_gain=0.0, tax_rate=0.0, volatility=volatility),
    ]
    return pf


def test_portfolio_mc_zero_volatility_collapses_to_deterministic():
    """volatility=0 → all trajectories identical → p10=p50=p90."""
    from config import MonteCarloParams
    from models import simulate_portfolio_mc

    pf = _make_mc_portfolio(volatility=0.0)
    mc_params = MonteCarloParams(n_trajectories=100, seed=42)
    result = simulate_portfolio_mc(pf, horizon_years=5, mc_params=mc_params)

    np.testing.assert_allclose(result.percentiles["p10"], result.percentiles["p50"])
    np.testing.assert_allclose(result.percentiles["p50"], result.percentiles["p90"])
    # Final value matches deterministic compounding
    expected_final = 100_000.0 * (1.10 ** 5)
    assert result.percentiles["p50"][-1] == pytest.approx(expected_final, rel=1e-6)


def test_portfolio_mc_seed_reproducibility():
    from config import MonteCarloParams
    from models import simulate_portfolio_mc

    pf = _make_mc_portfolio(volatility=0.15)
    mc_params = MonteCarloParams(n_trajectories=500, seed=42)
    a = simulate_portfolio_mc(pf, horizon_years=10, mc_params=mc_params)
    b = simulate_portfolio_mc(pf, horizon_years=10, mc_params=mc_params)
    np.testing.assert_array_equal(a.trajectories, b.trajectories)


def test_portfolio_mc_shape():
    from config import MonteCarloParams
    from models import simulate_portfolio_mc

    pf = _make_mc_portfolio(volatility=0.10)
    mc_params = MonteCarloParams(n_trajectories=1000, seed=42)
    result = simulate_portfolio_mc(pf, horizon_years=20, mc_params=mc_params)

    assert result.trajectories.shape == (1000, 21)
    assert result.final_distribution.shape == (1000,)
    assert result.max_drawdowns.shape == (1000,)
    for key in ("p10", "p50", "p90"):
        assert result.percentiles[key].shape == (21,)


def test_portfolio_mc_indexed_contribution_grows_mean():
    """With monthly_contribution > 0 indexed, mean trajectory is monotonically increasing."""
    from config import MonteCarloParams
    from models import simulate_portfolio_mc

    pf = _make_mc_portfolio(volatility=0.0, monthly_contribution=1_000, indexed=True)
    mc_params = MonteCarloParams(n_trajectories=10, seed=42)
    result = simulate_portfolio_mc(pf, horizon_years=5, mc_params=mc_params, ipca=0.05)

    # With volatility=0, all trajectories identical; mean = single trajectory
    mean_traj = result.trajectories.mean(axis=0)
    assert np.all(np.diff(mean_traj) > 0)  # strictly increasing


# ---------- simulate_real_estate_mc (cash) ----------

def test_real_estate_mc_cash_zero_vol_matches_deterministic():
    """appreciation_volatility=0 → MC trajectories all match deterministic patrimony."""
    from config import MonteCarloParams, RealEstateParams
    from models import simulate_real_estate, simulate_real_estate_mc

    re_params = RealEstateParams()
    re_params.appreciation_volatility = 0.0
    mc_params = MonteCarloParams(n_trajectories=50, seed=42)

    det = simulate_real_estate(re_params, horizon_years=10)
    mc = simulate_real_estate_mc(re_params, horizon_years=10, mc_params=mc_params)

    # All MC trajectories should match the deterministic patrimony
    for traj in mc.trajectories:
        np.testing.assert_allclose(traj, det.patrimony, rtol=1e-6)


def test_real_estate_mc_cash_shape():
    from config import MonteCarloParams, RealEstateParams
    from models import simulate_real_estate_mc

    re_params = RealEstateParams()
    mc_params = MonteCarloParams(n_trajectories=200, seed=42)
    result = simulate_real_estate_mc(re_params, horizon_years=15, mc_params=mc_params)

    assert result.trajectories.shape == (200, 16)
    assert result.final_distribution.shape == (200,)
    assert result.label == "Imóvel (MC)"
