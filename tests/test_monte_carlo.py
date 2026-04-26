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
