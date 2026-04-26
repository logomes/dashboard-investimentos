# Phase 2 Monte Carlo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Monte Carlo stochastic analysis to the dashboard — Carteira (per-asset volatility) and Imóvel (appreciation volatility) produce N=10.000 trajectories with seed-fixed reproducibility, displayed via p10/p50/p90 bands and a new "Risco" tab.

**Architecture:** New helpers and `MonteCarloResult` (frozen) live in `models.py`. New `MonteCarloParams` (frozen) and `volatility` fields on `AssetClass` and `RealEstateParams` go in `config.py`. Two new functions `simulate_portfolio_mc` and `simulate_real_estate_mc` mirror the deterministic pair and return `MonteCarloResult`. UI gains a sidebar block (target + volatility sliders) and a new tab "🎲 Risco". The existing `patrimony_evolution_chart` in `render_overview` is replaced with `patrimony_band_chart` that combines deterministic lines and stochastic bands.

**Tech Stack:** Python 3.14, Streamlit, NumPy (default_rng for reproducible draws), pandas, Plotly, pytest + pytest-mock.

**Spec reference:** `docs/superpowers/specs/2026-04-26-phase2-monte-carlo-design.md`

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `config.py` | modify | + `MonteCarloParams` (frozen), + `volatility: float` on `AssetClass`, + `appreciation_volatility: float` on `RealEstateParams`, update default volatilities per asset class |
| `models.py` | modify | + `MonteCarloResult` (frozen), + helpers (`_draw_normal_returns`, `_compute_percentiles`, `_compute_max_drawdowns`), + `simulate_portfolio_mc`, + `simulate_real_estate_mc` (cash + financed) |
| `charts.py` | modify | + `patrimony_band_chart` (with optional deterministic overlay), + `distribution_histogram_chart` |
| `app.py` | modify | sidebar: target + volatility sliders, returns `MonteCarloParams`; new "🎲 Risco" tab; replace patrimony chart in overview with band chart; risk banner |
| `README.md` | modify | document Monte Carlo feature |
| `tests/test_monte_carlo.py` | create | 15 tests covering helpers, portfolio MC, real-estate cash MC, real-estate financed MC |

---

## Task 1: Helpers and `MonteCarloResult` (TDD)

**Files:**
- Create: `tests/test_monte_carlo.py` (initial 4 tests for helpers/result)
- Modify: `models.py` (add `MonteCarloResult` and helpers)

- [ ] **Step 1: Create `tests/test_monte_carlo.py` with the first 4 tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: ImportError on `MonteCarloResult`, `_compute_max_drawdowns`, `_compute_percentiles`, `_draw_normal_returns`.

- [ ] **Step 3: Add `MonteCarloResult` and helpers to `models.py`**

In `/home/lucgomes/Downloads/dashboard/models.py`, find the existing `SimulationResult` dataclass. AFTER `SimulationResult` and BEFORE `AmortizationSchedule` (Phase 2 financing), insert:

```python
@dataclass(slots=True, frozen=True)
class MonteCarloResult:
    """Outcome of a Monte Carlo simulation: trajectories + summary stats."""
    trajectories: np.ndarray         # shape (N, horizon+1) — patrimônio ano a ano
    percentiles: dict                # {"p10","p50","p90"} — cada um shape (horizon+1,)
    final_distribution: np.ndarray   # shape (N,) — patrimônio no ano final
    max_drawdowns: np.ndarray        # shape (N,) — peak-to-trough drop por trajetória
    label: str
    color: str

    def prob_target(self, target: float) -> float:
        """Fração de trajetórias onde patrimônio final >= target."""
        return float((self.final_distribution >= target).mean())


def _draw_normal_returns(
    rng: np.random.Generator,
    mean: float,
    sigma: float,
    shape: tuple,
) -> np.ndarray:
    """Generate normal random returns with given shape, mean, and sigma."""
    return rng.normal(loc=mean, scale=sigma, size=shape)


def _compute_percentiles(trajectories: np.ndarray) -> dict:
    """Compute p10/p50/p90 across trajectories (axis=0) for each year."""
    return {
        "p10": np.percentile(trajectories, 10, axis=0),
        "p50": np.percentile(trajectories, 50, axis=0),
        "p90": np.percentile(trajectories, 90, axis=0),
    }


def _compute_max_drawdowns(trajectories: np.ndarray) -> np.ndarray:
    """Peak-to-trough relative drop per trajectory.

    Returns positive fractions in [0, 1]. A trajectory that only grows has drawdown 0.
    """
    running_max = np.maximum.accumulate(trajectories, axis=1)
    # Avoid divide-by-zero: where running_max == 0, drawdown is 0
    safe_max = np.where(running_max == 0, 1.0, running_max)
    drawdowns = (running_max - trajectories) / safe_max
    return drawdowns.max(axis=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: 4 tests passing.

- [ ] **Step 5: Run all tests for regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 41 + 4 = 45 tests passing.

- [ ] **Step 6: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py tests/test_monte_carlo.py
git commit -m "Add MonteCarloResult dataclass and pure stochastic helpers"
```

---

## Task 2: `MonteCarloParams` and volatility fields

**Files:**
- Modify: `config.py`

This task adds the configuration types. No new tests — the fields are exercised in subsequent task tests.

- [ ] **Step 1: Add `volatility` field to `AssetClass`**

In `/home/lucgomes/Downloads/dashboard/config.py`, find the `AssetClass` dataclass:

```python
@dataclass(slots=True)
class AssetClass:
    name: str
    weight: float
    expected_yield: float
    capital_gain: float = 0.0
    tax_rate: float = 0.0
    note: str = ""
```

Replace with (add `volatility` field at the end):

```python
@dataclass(slots=True)
class AssetClass:
    name: str
    weight: float
    expected_yield: float
    capital_gain: float = 0.0
    tax_rate: float = 0.0
    note: str = ""
    volatility: float = 0.15   # σ anual do retorno total (yield + capital gain)
```

- [ ] **Step 2: Update default volatilities in `PortfolioParams.assets`**

In the same file, find `PortfolioParams.assets` default factory. The current list looks like:

```python
    assets: list[AssetClass] = field(default_factory=lambda: [
        AssetClass("FIIs de Papel",         0.25, 0.130, 0.00, 0.00,
                   "HGCR11, KNCR11, RBRR11 — isento PF"),
        AssetClass("FIIs de Tijolo",        0.25, 0.090, 0.02, 0.00,
                   "HGLG11, XPML11, KNRI11 — isento PF"),
        AssetClass("Ações BR Dividendos",   0.20, 0.090, 0.03, 0.00,
                   "ITSA4, BBAS3, TAEE11, EGIE3"),
        AssetClass("Dividend Aristocrats US", 0.15, 0.040, 0.06, 0.30,
                   "JNJ, ABBV, O, MSFT (via Avenue)"),
        AssetClass("Tesouro IPCA+ / LCI",   0.15, 0.115, 0.00, 0.10,
                   "NTN-B 2035, LCI 100% CDI"),
    ])
```

Replace with (add `volatility` as keyword arg per asset, historical defaults):

```python
    assets: list[AssetClass] = field(default_factory=lambda: [
        AssetClass("FIIs de Papel",         0.25, 0.130, 0.00, 0.00,
                   "HGCR11, KNCR11, RBRR11 — isento PF",
                   volatility=0.14),
        AssetClass("FIIs de Tijolo",        0.25, 0.090, 0.02, 0.00,
                   "HGLG11, XPML11, KNRI11 — isento PF",
                   volatility=0.16),
        AssetClass("Ações BR Dividendos",   0.20, 0.090, 0.03, 0.00,
                   "ITSA4, BBAS3, TAEE11, EGIE3",
                   volatility=0.27),
        AssetClass("Dividend Aristocrats US", 0.15, 0.040, 0.06, 0.30,
                   "JNJ, ABBV, O, MSFT (via Avenue)",
                   volatility=0.18),
        AssetClass("Tesouro IPCA+ / LCI",   0.15, 0.115, 0.00, 0.10,
                   "NTN-B 2035, LCI 100% CDI",
                   volatility=0.05),
    ])
```

- [ ] **Step 3: Add `appreciation_volatility` to `RealEstateParams`**

In the same file, find `RealEstateParams`. The current fields end with `acquisition_cost_pct` and then `financing` (Phase 2). Add `appreciation_volatility` IMMEDIATELY AFTER `acquisition_cost_pct` and BEFORE `financing`:

```python
    acquisition_cost_pct: float = 0.05        # ITBI + cartório
    appreciation_volatility: float = 0.10     # σ anual da valorização
    financing: FinancingParams | None = None
```

- [ ] **Step 4: Add `MonteCarloParams`**

In the same file, find the `# ---------- Reference benchmark` section header. Add a NEW section IMMEDIATELY BEFORE it:

```python
# ---------- Monte Carlo ----------

@dataclass(slots=True, frozen=True)
class MonteCarloParams:
    """Parameters for Monte Carlo stochastic simulation."""
    n_trajectories: int = 10_000
    seed: int = 42
    target_patrimony: float = 0.0   # 0 desativa cálculo de prob de bater meta


```

(Two blank lines before the `# ---------- Reference benchmark` header that follows, matching project style.)

- [ ] **Step 5: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 45 tests passing. Existing tests don't reference `volatility` or `appreciation_volatility` directly — defaults apply silently.

- [ ] **Step 6: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "from config import MonteCarloParams, AssetClass, RealEstateParams; mc = MonteCarloParams(); print(mc); print(AssetClass('x', 1.0, 0.1).volatility); print(RealEstateParams().appreciation_volatility)"`
Expected: prints `MonteCarloParams(n_trajectories=10000, seed=42, target_patrimony=0.0)` and `0.15` and `0.1`.

- [ ] **Step 7: Commit**

```bash
cd ~/Downloads/dashboard
git add config.py
git commit -m "Add MonteCarloParams and per-asset volatility defaults"
```

---

## Task 3: `simulate_portfolio_mc` (TDD)

**Files:**
- Modify: `tests/test_monte_carlo.py` (append 4 tests)
- Modify: `models.py` (add `simulate_portfolio_mc`)

- [ ] **Step 1: Append 4 new tests to `tests/test_monte_carlo.py`**

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v -k "portfolio_mc"`
Expected: ImportError on `simulate_portfolio_mc`.

- [ ] **Step 3: Add `simulate_portfolio_mc` to `models.py`**

In `/home/lucgomes/Downloads/dashboard/models.py`, find `simulate_portfolio` (the existing deterministic function). AFTER it ends and BEFORE the next function (`simulate_benchmark`), insert:

```python
def simulate_portfolio_mc(
    params: PortfolioParams,
    horizon_years: int,
    mc_params: "MonteCarloParams",
    ipca: float = 0.0,
) -> MonteCarloResult:
    """Monte Carlo simulation of the diversified portfolio.

    Each year, each asset's net return is drawn from N(mean, volatility^2)
    independently. Portfolio return = weighted sum across assets. Aporte
    mensal is deterministic (PMT-begin: added at the start of the year,
    compounded with that year's return).
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    rng = np.random.default_rng(mc_params.seed)
    N, T = mc_params.n_trajectories, horizon_years
    K = len(params.assets)

    weights = np.array([a.weight for a in params.assets])
    means = np.array([
        a.expected_yield * (1 - a.tax_rate) + a.capital_gain
        for a in params.assets
    ])
    sigmas = np.array([a.volatility for a in params.assets])

    # Per-trajectory per-year per-asset draws: shape (N, T, K)
    draws = rng.normal(loc=means, scale=sigmas, size=(N, T, K))
    # Portfolio return = weighted sum across assets: shape (N, T)
    portfolio_returns = (draws * weights).sum(axis=2)

    monthly = params.monthly_contribution
    indexed = params.contribution_inflation_indexed
    annual_base = 12.0 * monthly

    trajectories = np.zeros((N, T + 1))
    trajectories[:, 0] = params.capital
    for t in range(T):
        if monthly > 0:
            aporte_t = annual_base * ((1 + ipca) ** t if indexed else 1.0)
        else:
            aporte_t = 0.0
        # PMT-begin: add aporte first, then compound with year's return
        trajectories[:, t + 1] = (trajectories[:, t] + aporte_t) * (1 + portfolio_returns[:, t])

    return MonteCarloResult(
        trajectories=trajectories,
        percentiles=_compute_percentiles(trajectories),
        final_distribution=trajectories[:, -1],
        max_drawdowns=_compute_max_drawdowns(trajectories),
        label="Carteira (MC)",
        color="#27AE60",
    )
```

Note the type annotation `"MonteCarloParams"` is a forward-reference string because `MonteCarloParams` lives in `config.py` and we don't want a runtime cyclic import. With `from __future__ import annotations` at the top of `models.py`, all annotations are strings anyway, but the explicit quoting makes intent clear.

Also add the import: at the top of `models.py`, find:

```python
from config import (
    BenchmarkParams,
    FinancingParams,
    PortfolioParams,
    RealEstateParams,
)
```

Replace with:

```python
from config import (
    BenchmarkParams,
    FinancingParams,
    MonteCarloParams,
    PortfolioParams,
    RealEstateParams,
)
```

(Now the forward reference can be a real reference, but keeping the string form is harmless.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: 8 tests passing (4 from Task 1 + 4 from Task 3).

- [ ] **Step 5: Run all tests for regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 49 tests passing.

- [ ] **Step 6: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py tests/test_monte_carlo.py
git commit -m "Add simulate_portfolio_mc with per-asset volatility"
```

---

## Task 4: `simulate_real_estate_mc` (cash variant) (TDD)

**Files:**
- Modify: `tests/test_monte_carlo.py` (append 2 tests)
- Modify: `models.py` (add `simulate_real_estate_mc` cash branch)

The math, year-by-year per trajectory:
- `appreciation_t ~ N(annual_appreciation, appreciation_volatility²)`
- `property_value_t = property_value × prod(1 + appreciation_i)` for `i=0..t-1`
- `annual_net_income_t = net_annual_income() × prod(1 + appreciation_i)` for `i=0..t-1`
- `rate_t = net_yield() + appreciation_t` (stochastic per-year rate)
- `accumulated_t+1 = accumulated_t × (1 + rate_t) + annual_net_income_t+1`
- `patrimony_t = property_value_t + accumulated_t`

- [ ] **Step 1: Append 2 tests to `tests/test_monte_carlo.py`**

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v -k "real_estate_mc"`
Expected: ImportError on `simulate_real_estate_mc`.

- [ ] **Step 3: Add `simulate_real_estate_mc` skeleton (cash branch only) to `models.py`**

In `/home/lucgomes/Downloads/dashboard/models.py`, find the existing `simulate_real_estate` dispatcher (which routes to `_simulate_real_estate_cash` or `_simulate_real_estate_financed`). AFTER `_simulate_real_estate_financed` ends, insert:

```python
def simulate_real_estate_mc(
    params: RealEstateParams,
    horizon_years: int,
    mc_params: "MonteCarloParams",
    capital_initial: float | None = None,
    portfolio_for_internal: PortfolioParams | None = None,
) -> MonteCarloResult:
    """Monte Carlo simulation of the real estate scenario.

    Appreciation is stochastic per trajectory per year. For the cash variant,
    rent grows with each trajectory's own appreciation and is reinvested at
    a stochastic rate. For the financed variant, the schedule is deterministic
    (contract rate is fixed) but the internal portfolio uses a Carteira-blended
    stochastic return drawn from `portfolio_for_internal`.
    """
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    rng = np.random.default_rng(mc_params.seed + 1)  # offset: independent stream from Carteira
    N, T = mc_params.n_trajectories, horizon_years

    # Stochastic appreciation per trajectory per year (N, T)
    appreciation = rng.normal(
        loc=params.annual_appreciation,
        scale=params.appreciation_volatility,
        size=(N, T),
    )

    if params.financing is None:
        return _real_estate_mc_cash(params, horizon_years, appreciation)

    if portfolio_for_internal is None:
        raise ValueError(
            "simulate_real_estate_mc with financing requires portfolio_for_internal"
        )
    if capital_initial is None:
        capital_initial = params.property_value
    return _real_estate_mc_financed(
        params, horizon_years, appreciation, capital_initial,
        portfolio_for_internal, rng,
    )


def _real_estate_mc_cash(
    params: RealEstateParams,
    horizon_years: int,
    appreciation: np.ndarray,
) -> MonteCarloResult:
    """Cash purchase MC: appreciation is the only stochastic input."""
    N, T = appreciation.shape
    # Property values: shape (N, T+1). Year 0 = initial value.
    appreciation_factors = np.concatenate(
        [np.ones((N, 1)), np.cumprod(1 + appreciation, axis=1)], axis=1,
    )
    property_values = params.property_value * appreciation_factors

    # Annual rent net per trajectory: grows with same appreciation factors
    annual_net_income = params.net_annual_income() * appreciation_factors

    # Reinvest accumulated rent at stochastic rate (net_yield + appreciation_t)
    rate = params.net_yield() + appreciation  # (N, T)
    accumulated = np.zeros((N, T + 1))
    for t in range(T):
        accumulated[:, t + 1] = accumulated[:, t] * (1 + rate[:, t]) + annual_net_income[:, t + 1]

    trajectories = property_values + accumulated

    return MonteCarloResult(
        trajectories=trajectories,
        percentiles=_compute_percentiles(trajectories),
        final_distribution=trajectories[:, -1],
        max_drawdowns=_compute_max_drawdowns(trajectories),
        label="Imóvel (MC)",
        color="#C0392B",
    )


def _real_estate_mc_financed(
    params: RealEstateParams,
    horizon_years: int,
    appreciation: np.ndarray,
    capital_initial: float,
    portfolio_for_internal: PortfolioParams,
    rng: np.random.Generator,
) -> MonteCarloResult:
    """Financed MC. Skeleton — full implementation in Task 5."""
    raise NotImplementedError("Implemented in Task 5")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: 10 tests passing.

- [ ] **Step 5: Run all tests for regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 51 tests passing.

- [ ] **Step 6: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py tests/test_monte_carlo.py
git commit -m "Add simulate_real_estate_mc cash variant with stochastic appreciation"
```

---

## Task 5: `simulate_real_estate_mc` (financed variant) (TDD)

**Files:**
- Modify: `tests/test_monte_carlo.py` (append 2 tests)
- Modify: `models.py` (replace `_real_estate_mc_financed` skeleton)

The financed MC is more complex. Key insight: the amortization schedule is **deterministic** (contract rate is fixed). What's stochastic is:
- Property value (via appreciation)
- Rent net (grows with appreciation)
- Internal portfolio rate (drawn from `portfolio_for_internal` per trajectory per year)

- [ ] **Step 1: Append 2 tests to `tests/test_monte_carlo.py`**

```python
# ---------- simulate_real_estate_mc (financed) ----------

def test_real_estate_mc_financed_requires_portfolio_for_internal():
    from config import FinancingParams, MonteCarloParams, RealEstateParams
    from models import simulate_real_estate_mc

    fin = FinancingParams(term_years=10, annual_rate=0.10, entry_pct=0.20, system="SAC")
    re_params = RealEstateParams()
    re_params.financing = fin
    mc_params = MonteCarloParams(n_trajectories=10, seed=42)

    with pytest.raises(ValueError) as exc:
        simulate_real_estate_mc(
            re_params, horizon_years=10, mc_params=mc_params,
            capital_initial=200_000.0, portfolio_for_internal=None,
        )
    assert "portfolio_for_internal" in str(exc.value)


def test_real_estate_mc_financed_zero_vol_matches_deterministic():
    """All volatilities = 0 → financed MC matches deterministic financed simulation."""
    from config import AssetClass, FinancingParams, MonteCarloParams, PortfolioParams, RealEstateParams
    from models import simulate_real_estate, simulate_real_estate_mc

    fin = FinancingParams(term_years=10, annual_rate=0.10, entry_pct=0.20, system="SAC")
    re_params = RealEstateParams(
        property_value=200_000.0, monthly_rent=1_500.0,
        annual_appreciation=0.05, appreciation_volatility=0.0,
        iptu_rate=0.0, vacancy_months_per_year=0.0,
        management_fee_pct=0.0, maintenance_annual=0.0,
        insurance_annual=0.0, income_tax_bracket=0.0,
    )
    re_params.financing = fin

    pf = PortfolioParams(capital=0.0)
    pf.assets = [
        AssetClass("Test", weight=1.0, expected_yield=0.10,
                   capital_gain=0.0, tax_rate=0.0, volatility=0.0),
    ]

    mc_params = MonteCarloParams(n_trajectories=20, seed=42)

    det = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=pf.total_return(),
    )
    mc = simulate_real_estate_mc(
        re_params, horizon_years=10, mc_params=mc_params,
        capital_initial=200_000.0, portfolio_for_internal=pf,
    )

    # All MC trajectories should match the deterministic patrimony
    for traj in mc.trajectories:
        np.testing.assert_allclose(traj, det.patrimony, rtol=1e-6, atol=1e-3)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v -k "financed"`
Expected: 1 test passes (the ValueError one — already raised by skeleton); the other fails with NotImplementedError.

- [ ] **Step 3: Implement `_real_estate_mc_financed` body**

In `/home/lucgomes/Downloads/dashboard/models.py`, find the skeleton:

```python
def _real_estate_mc_financed(
    params: RealEstateParams,
    horizon_years: int,
    appreciation: np.ndarray,
    capital_initial: float,
    portfolio_for_internal: PortfolioParams,
    rng: np.random.Generator,
) -> MonteCarloResult:
    """Financed MC. Skeleton — full implementation in Task 5."""
    raise NotImplementedError("Implemented in Task 5")
```

Replace with:

```python
def _real_estate_mc_financed(
    params: RealEstateParams,
    horizon_years: int,
    appreciation: np.ndarray,
    capital_initial: float,
    portfolio_for_internal: PortfolioParams,
    rng: np.random.Generator,
) -> MonteCarloResult:
    """Financed MC: stochastic appreciation + stochastic internal portfolio.

    Schedule (parcela, juros, saldo) is deterministic (contract rate fixed).
    Internal portfolio compounds with a Carteira-blended stochastic return.
    """
    fin = params.financing
    assert fin is not None  # caller ensures (raised earlier)
    N, T = appreciation.shape

    # Deterministic schedule (Phase 2 financing logic)
    entry = params.property_value * fin.entry_pct
    if capital_initial < entry:
        raise ValueError(
            f"capital_initial ({capital_initial:.2f}) is below the required "
            f"entry ({entry:.2f}) at entry_pct={fin.entry_pct:.0%}."
        )
    loan_principal = params.property_value - entry
    initial_buffer = capital_initial - entry

    schedule = build_schedule(fin, loan_principal)

    n_months_horizon = T * 12
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

    payments_annual = payments_full.reshape(T, 12).sum(axis=1)  # (T,)
    balance_at_month_start = np.concatenate([[loan_principal], balance_full[:-1]])
    insurance_monthly = balance_at_month_start * fin.monthly_insurance_rate
    insurance_annual = insurance_monthly.reshape(T, 12).sum(axis=1)  # (T,)

    # Property value per trajectory (N, T+1) using stochastic appreciation
    appreciation_factors = np.concatenate(
        [np.ones((N, 1)), np.cumprod(1 + appreciation, axis=1)], axis=1,
    )
    property_values = params.property_value * appreciation_factors  # (N, T+1)

    # Debt balance at end of each year (deterministic, broadcast to N)
    debt_balance_yearly = np.zeros(T + 1)
    debt_balance_yearly[0] = loan_principal
    for y in range(1, T + 1):
        idx = 12 * y - 1
        if idx < len(balance_full):
            debt_balance_yearly[y] = balance_full[idx]
        else:
            debt_balance_yearly[y] = 0.0
    debt_balance = np.broadcast_to(debt_balance_yearly, (N, T + 1))

    # Annual rent net per trajectory (grows with each trajectory's appreciation)
    annual_net_income = params.net_annual_income() * appreciation_factors  # (N, T+1)

    # Stochastic Carteira blended return per trajectory per year
    K = len(portfolio_for_internal.assets)
    weights = np.array([a.weight for a in portfolio_for_internal.assets])
    means = np.array([
        a.expected_yield * (1 - a.tax_rate) + a.capital_gain
        for a in portfolio_for_internal.assets
    ])
    sigmas = np.array([a.volatility for a in portfolio_for_internal.assets])
    carteira_draws = rng.normal(loc=means, scale=sigmas, size=(N, T, K))
    carteira_returns = (carteira_draws * weights).sum(axis=2)  # (N, T)

    # Net cash flow per trajectory per year:
    # rent (stochastic via appreciation) − payments (deterministic) − insurance (deterministic)
    net_cash_flow = annual_net_income[:, 1:] - payments_annual - insurance_annual  # (N, T)

    # Internal portfolio (PMT-end: compound previous, then add cash flow)
    internal_portfolio = np.zeros((N, T + 1))
    internal_portfolio[:, 0] = initial_buffer
    for t in range(T):
        internal_portfolio[:, t + 1] = (
            internal_portfolio[:, t] * (1 + carteira_returns[:, t])
            + net_cash_flow[:, t]
        )

    trajectories = property_values - debt_balance + internal_portfolio

    return MonteCarloResult(
        trajectories=trajectories,
        percentiles=_compute_percentiles(trajectories),
        final_distribution=trajectories[:, -1],
        max_drawdowns=_compute_max_drawdowns(trajectories),
        label="Imóvel financiado (MC)",
        color="#C0392B",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_monte_carlo.py -v`
Expected: 12 tests passing (10 from earlier + 2 new).

- [ ] **Step 5: Run all tests for regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 53 tests passing.

- [ ] **Step 6: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py tests/test_monte_carlo.py
git commit -m "Implement financed real-estate MC with stochastic carteira interna"
```

---

## Task 6: Charts (`patrimony_band_chart` + `distribution_histogram_chart`)

**Files:**
- Modify: `charts.py`

No automated tests — manual verification later.

- [ ] **Step 1: Inspect existing chart conventions**

Open `/home/lucgomes/Downloads/dashboard/charts.py` and read 2-3 chart functions (e.g., `patrimony_evolution_chart`, `cost_breakdown_chart`) to confirm: `_LAYOUT_DEFAULTS` exists at module level; `PALETTE` imported; conventions for `update_layout`, `update_yaxes`, `update_xaxes`. The new charts must follow the same conventions.

- [ ] **Step 2: Add `patrimony_band_chart` to `charts.py`**

Append at the end of `/home/lucgomes/Downloads/dashboard/charts.py`:

```python


def patrimony_band_chart(
    mc_results: list,
    deterministic_results: list | None = None,
) -> go.Figure:
    """Banda p10–p90 sombreada + linha p50 por cenário.

    When `deterministic_results` is provided, draws solid dashed lines on top
    using the same color per scenario (paired by list order).
    """
    fig = go.Figure()

    for i, mc in enumerate(mc_results):
        years = np.arange(len(mc.percentiles["p10"]))
        # Upper band edge (p90) — invisible marker (used as anchor for fill)
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p90"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
            name=f"{mc.label} p90",
        ))
        # Lower band edge (p10) with fill back up to p90
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p10"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=_band_fill(mc.color),
            showlegend=False,
            hoverinfo="skip",
            name=f"{mc.label} p10",
        ))
        # Median line
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p50"],
            mode="lines",
            line=dict(color=mc.color, width=2),
            name=f"{mc.label} p50",
        ))

    if deterministic_results is not None:
        for i, det in enumerate(deterministic_results):
            fig.add_trace(go.Scatter(
                x=det.years, y=det.patrimony,
                mode="lines",
                line=dict(color=det.color, width=2, dash="dash"),
                name=f"{det.label} (det)",
            ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title="Evolução do patrimônio — banda p10–p90 (Monte Carlo)",
        xaxis_title="Ano",
        yaxis_title="Patrimônio (R$)",
        height=420,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig


def _band_fill(hex_color: str) -> str:
    """Convert #RRGGBB to rgba(R,G,B,0.18) for soft band fill."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},0.18)"


def distribution_histogram_chart(mc_result, target: float = 0.0) -> go.Figure:
    """Histogram of the final-year patrimony distribution. Target line shown if > 0."""
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=mc_result.final_distribution,
        nbinsx=40,
        marker=dict(color=mc_result.color, opacity=0.7),
        name=mc_result.label,
    ))
    if target > 0:
        fig.add_vline(
            x=target, line=dict(color="#2C3E50", width=2, dash="dash"),
            annotation_text=f"Meta: R$ {target:,.0f}".replace(",", "."),
            annotation_position="top right",
        )
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title=f"Distribuição final — {mc_result.label}",
        xaxis_title="Patrimônio final (R$)",
        yaxis_title="Frequência",
        height=320,
        showlegend=False,
    )
    fig.update_xaxes(tickformat=",.0f", tickprefix="R$ ")
    return fig
```

If `numpy as np` is not imported at the top of `charts.py`, add `import numpy as np` to the existing imports.

- [ ] **Step 3: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "from charts import patrimony_band_chart, distribution_histogram_chart; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Run all tests for regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 53 tests passing.

- [ ] **Step 5: Commit**

```bash
cd ~/Downloads/dashboard
git add charts.py
git commit -m "Add patrimony band chart and distribution histogram for Monte Carlo"
```

---

## Task 7: Sidebar UI + `_run_monte_carlo` helper

**Files:**
- Modify: `app.py` (sidebar block; helper to run MC; update `render_sidebar` signature)

- [ ] **Step 1: Add `MonteCarloParams` to imports**

In `/home/lucgomes/Downloads/dashboard/app.py`, find the `from config import (...)` block. Add `MonteCarloParams` (alphabetical):

```python
from config import (
    BenchmarkParams,
    FinancingParams,
    MacroParams,
    MonteCarloParams,
    PALETTE,
    PortfolioParams,
    RealEstateParams,
    TODAY_LABEL,
)
```

- [ ] **Step 2: Add `MonteCarloResult`, `simulate_portfolio_mc`, `simulate_real_estate_mc` to model imports**

Find the `from models import (...)` block. Add the three new names (alphabetical):

```python
from models import (
    annual_tax_comparison,
    build_comparison_dataframe,
    build_schedule,
    MonteCarloResult,
    sensitivity_real_estate,
    simulate_benchmark,
    simulate_portfolio,
    simulate_portfolio_mc,
    simulate_real_estate,
    simulate_real_estate_mc,
    SimulationResult,
)
```

(Maintain whatever ordering convention the existing block uses; just add the three new names.)

- [ ] **Step 3: Add charts imports**

Find the `from charts import (...)` block. Add `distribution_histogram_chart` and `patrimony_band_chart` (alphabetical):

```python
from charts import (
    annual_income_chart,
    cost_breakdown_chart,
    debt_evolution_chart,
    distribution_histogram_chart,
    income_vs_costs_waterfall,
    patrimony_band_chart,
    patrimony_evolution_chart,
    portfolio_donut_chart,
    risk_return_scatter,
    sensitivity_tornado_chart,
    tax_comparison_chart,
    yield_comparison_bars,
)
```

- [ ] **Step 4: Update `render_sidebar` signature and add MC block**

Find `render_sidebar`. Change the return type annotation:

```python
def render_sidebar(macro: MacroParams) -> tuple[RealEstateParams, PortfolioParams, BenchmarkParams, int, bool, MonteCarloParams]:
```

Inside, find the existing reload button block at the bottom:

```python
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Recarregar dados macro", use_container_width=True):
        get_macro_params.clear()
        st.rerun()

    return re_params, pf_params, bench_params, horizon, reinvest
```

Replace with (insert MC block BEFORE the reload button, change return value):

```python
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎲 Análise estocástica")
    target_patrimony = st.sidebar.number_input(
        "Meta de patrimônio (R$)",
        min_value=0.0, max_value=100_000_000.0, value=0.0, step=50_000.0,
        format="%.0f",
        help="Patrimônio-alvo no horizonte. Mostra prob. de bater. 0 desativa.",
    )
    with st.sidebar.expander("Volatilidades (σ anual)", expanded=False):
        for asset in pf_params.assets:
            asset.volatility = st.slider(
                f"σ — {asset.name} (%)", 0.0, 50.0, asset.volatility * 100, 1.0,
                key=f"vol_{asset.name}",
            ) / 100
        re_params.appreciation_volatility = st.slider(
            "σ — Valorização imóvel (%)", 0.0, 30.0,
            re_params.appreciation_volatility * 100, 1.0,
        ) / 100
    mc_params = MonteCarloParams(target_patrimony=target_patrimony)

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Recarregar dados macro", use_container_width=True):
        get_macro_params.clear()
        st.rerun()

    return re_params, pf_params, bench_params, horizon, reinvest, mc_params
```

- [ ] **Step 5: Add `_run_monte_carlo` helper**

In `/home/lucgomes/Downloads/dashboard/app.py`, find `_run_simulations`. AFTER it, add:

```python
def _run_monte_carlo(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    horizon: int,
    mc_params: MonteCarloParams,
    ipca: float,
) -> tuple[MonteCarloResult, MonteCarloResult]:
    """Run Monte Carlo for both Carteira and Imóvel scenarios."""
    pf_mc = simulate_portfolio_mc(pf_params, horizon, mc_params, ipca=ipca)
    re_kwargs = {}
    if re_params.financing is not None:
        re_kwargs["capital_initial"] = re_params.property_value
        re_kwargs["portfolio_for_internal"] = pf_params
    re_mc = simulate_real_estate_mc(re_params, horizon, mc_params, **re_kwargs)
    return re_mc, pf_mc
```

- [ ] **Step 6: Update `main()` to unpack `mc_params` and run MC**

In `main()`, find the current sidebar call:

```python
    re_params, pf_params, bench_params, horizon, reinvest = render_sidebar(macro)
```

Replace with:

```python
    re_params, pf_params, bench_params, horizon, reinvest, mc_params = render_sidebar(macro)
```

Then find the existing single-simulation block:

```python
    re_result, pf_result, bench_result = _run_simulations(
        re_params, pf_params, bench_params, horizon, reinvest, macro.ipca,
    )
```

Add the MC call IMMEDIATELY AFTER it:

```python
    re_mc, pf_mc = _run_monte_carlo(re_params, pf_params, horizon, mc_params, macro.ipca)
```

- [ ] **Step 7: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 53 tests passing.

- [ ] **Step 8: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 9: Commit**

```bash
cd ~/Downloads/dashboard
git add app.py
git commit -m "Wire Monte Carlo: sidebar volatility/target inputs and parallel MC run"
```

---

## Task 8: "Risco" tab + band overlay in overview

**Files:**
- Modify: `app.py` (new tab, `render_risk`, replace patrimony chart in overview, risk banner)

- [ ] **Step 1: Add new tab to the tabs list**

In `main()`, find:

```python
    tabs = st.tabs([
        "📌 Visão Geral",
        "🏠 Imóvel",
        "📈 Carteira",
        "🎯 Sensibilidade",
        "💸 Tributação",
        "📥 Exportar",
    ])
```

Replace with (add "🎲 Risco" between "💸 Tributação" and "📥 Exportar"):

```python
    tabs = st.tabs([
        "📌 Visão Geral",
        "🏠 Imóvel",
        "📈 Carteira",
        "🎯 Sensibilidade",
        "💸 Tributação",
        "🎲 Risco",
        "📥 Exportar",
    ])
```

- [ ] **Step 2: Add the Risco tab dispatch in main()**

In `main()`, find the existing tabs dispatch block:

```python
    with tabs[0]:
        render_overview(re_params, pf_params, bench_params, horizon, reinvest, macro,
                        re_result, pf_result, bench_result)
    with tabs[1]:
        render_real_estate(re_params, re_result)
    with tabs[2]:
        render_portfolio(pf_params, macro)
    with tabs[3]:
        render_sensitivity(re_params, horizon)
    with tabs[4]:
        render_taxes(re_params, pf_params)
    with tabs[5]:
        render_export(re_params, pf_params, bench_params, horizon, reinvest, macro,
                      re_result, pf_result, bench_result)
```

Replace with (insert Risco at index 5, push Export to index 6, also pass MC results to overview):

```python
    with tabs[0]:
        render_overview(re_params, pf_params, bench_params, horizon, reinvest, macro,
                        re_result, pf_result, bench_result, re_mc, pf_mc)
    with tabs[1]:
        render_real_estate(re_params, re_result)
    with tabs[2]:
        render_portfolio(pf_params, macro)
    with tabs[3]:
        render_sensitivity(re_params, horizon)
    with tabs[4]:
        render_taxes(re_params, pf_params)
    with tabs[5]:
        render_risk(re_mc, pf_mc, mc_params, horizon, re_params.property_value)
    with tabs[6]:
        render_export(re_params, pf_params, bench_params, horizon, reinvest, macro,
                      re_result, pf_result, bench_result)
```

- [ ] **Step 3: Update `render_overview` signature to accept MC results**

Find `render_overview`:

```python
def render_overview(re_params: RealEstateParams,
                    pf_params: PortfolioParams,
                    bench_params: BenchmarkParams,
                    horizon: int,
                    reinvest: bool,
                    macro: MacroParams,
                    re_result: SimulationResult,
                    pf_result: SimulationResult,
                    bench_result: SimulationResult) -> None:
```

Replace with:

```python
def render_overview(re_params: RealEstateParams,
                    pf_params: PortfolioParams,
                    bench_params: BenchmarkParams,
                    horizon: int,
                    reinvest: bool,
                    macro: MacroParams,
                    re_result: SimulationResult,
                    pf_result: SimulationResult,
                    bench_result: SimulationResult,
                    re_mc: MonteCarloResult,
                    pf_mc: MonteCarloResult) -> None:
```

- [ ] **Step 4: Replace the existing patrimony chart in `render_overview` with band chart**

Inside `render_overview`, find the existing call to `patrimony_evolution_chart`:

```python
    st.markdown("### Evolução comparativa do patrimônio")
    st.plotly_chart(
        patrimony_evolution_chart([re_result, pf_result, bench_result]),
        use_container_width=True,
    )
```

Replace with:

```python
    st.markdown("### Evolução comparativa do patrimônio")
    st.plotly_chart(
        patrimony_band_chart(
            [re_mc, pf_mc],
            deterministic_results=[re_result, pf_result, bench_result],
        ),
        use_container_width=True,
    )
```

(The benchmark `bench_result` is shown as deterministic dashed line only — no MC for it. The chart handles that gracefully because we only pass two MC results.)

- [ ] **Step 5: Add `render_risk` function**

In `/home/lucgomes/Downloads/dashboard/app.py`, find `render_export` (the last render function before `main()`). AFTER `render_export` ends and BEFORE `main()`, insert:

```python
def render_risk(
    re_mc: MonteCarloResult,
    pf_mc: MonteCarloResult,
    mc_params: MonteCarloParams,
    horizon: int,
    capital_initial: float,
) -> None:
    """Risco tab: probability of meeting target, drawdowns, percentiles, distributions."""
    st.markdown("## 🎲 Análise de risco — Monte Carlo")
    st.caption(
        f"Baseado em {mc_params.n_trajectories:,} trajetórias com seed fixa. "
        "Distribuição normal por ativo; ativos independentes (limitação documentada)."
        .replace(",", ".")
    )

    target = mc_params.target_patrimony
    cols = st.columns(2)
    with cols[0]:
        st.markdown("### Carteira (MC)")
        st.metric("Drawdown médio máximo", f"{pf_mc.max_drawdowns.mean():.1%}")
        st.metric(f"Patrimônio p10 (ano {horizon})",
                  f"R$ {pf_mc.percentiles['p10'][-1]:,.0f}".replace(",", "."))
        st.metric(f"Patrimônio p50 (ano {horizon})",
                  f"R$ {pf_mc.percentiles['p50'][-1]:,.0f}".replace(",", "."))
        st.metric(f"Patrimônio p90 (ano {horizon})",
                  f"R$ {pf_mc.percentiles['p90'][-1]:,.0f}".replace(",", "."))
        if target > 0:
            st.metric("Prob. de bater meta", f"{pf_mc.prob_target(target):.1%}")
    with cols[1]:
        st.markdown("### Imóvel (MC)")
        st.metric("Drawdown médio máximo", f"{re_mc.max_drawdowns.mean():.1%}")
        st.metric(f"Patrimônio p10 (ano {horizon})",
                  f"R$ {re_mc.percentiles['p10'][-1]:,.0f}".replace(",", "."))
        st.metric(f"Patrimônio p50 (ano {horizon})",
                  f"R$ {re_mc.percentiles['p50'][-1]:,.0f}".replace(",", "."))
        st.metric(f"Patrimônio p90 (ano {horizon})",
                  f"R$ {re_mc.percentiles['p90'][-1]:,.0f}".replace(",", "."))
        if target > 0:
            st.metric("Prob. de bater meta", f"{re_mc.prob_target(target):.1%}")

    # Risk banner: any scenario with >5% trajectories ending below capital
    pf_loss_rate = float((pf_mc.final_distribution < capital_initial).mean())
    re_loss_rate = float((re_mc.final_distribution < capital_initial).mean())
    flagged = []
    if pf_loss_rate > 0.05:
        flagged.append(f"Carteira: {pf_loss_rate:.1%}")
    if re_loss_rate > 0.05:
        flagged.append(f"Imóvel: {re_loss_rate:.1%}")
    if flagged:
        st.warning(
            "⚠️ Trajetórias com perda nominal — "
            + " | ".join(flagged)
            + f" das trajetórias terminam abaixo de R$ {capital_initial:,.0f}".replace(",", ".")
            + " ao final do horizonte. Considere reduzir alocação em ativos de alta σ "
            + "ou ajustar o horizonte."
        )

    st.markdown("### Banda do patrimônio (p10–p90)")
    st.plotly_chart(
        patrimony_band_chart([re_mc, pf_mc]),
        use_container_width=True,
    )

    st.markdown("### Distribuição final do patrimônio")
    cols2 = st.columns(2)
    with cols2[0]:
        st.plotly_chart(
            distribution_histogram_chart(pf_mc, target=target),
            use_container_width=True,
        )
    with cols2[1]:
        st.plotly_chart(
            distribution_histogram_chart(re_mc, target=target),
            use_container_width=True,
        )
```

- [ ] **Step 6: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 53 tests passing.

- [ ] **Step 7: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add app.py
git commit -m "Add Risco tab, band overlay in overview, and risk banner"
```

---

## Task 9: README and final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update Funcionalidades**

In `/home/lucgomes/Downloads/dashboard/README.md`, find the existing line that mentions sensitivity (or similar). Add a new bullet for the risk analysis. The current Funcionalidades list ends with something like the Sensibilidade or Tributação bullet. Add this AFTER the Tributação bullet and BEFORE the Exportar bullet:

```
- **Risco (Monte Carlo)**: análise estocástica com 10.000 trajetórias, banda p10/p50/p90, drawdown máximo, probabilidade de bater meta de patrimônio
```

- [ ] **Step 2: Add Análise de risco section**

In the same file, find the section `## Financiamento imobiliário` (added in Phase 2 sub-projeto 1). Add this NEW section right AFTER it:

```markdown
## Análise de risco (Monte Carlo)

Camada estocástica paralela ao caminho determinístico:

- **N=10.000 trajetórias** com seed fixa (42) → resultado reproduzível.
- **Carteira**: cada classe de ativo tem σ próprio (FIIs ~14-16%, Ações BR ~27%, Aristocrats US ~18%, RF ~5%). Sliders na sidebar permitem sobrescrever.
- **Imóvel**: σ na valorização anual (default 10%). Aluguel cresce com a apreciação sorteada.
- **Imóvel financiado**: parcela continua determinística (taxa contratual fixa); carteira interna usa retorno blended estocástico da Carteira.
- **Aba "🎲 Risco"**: KPIs de probabilidade de bater meta, drawdown médio, percentis p10/p50/p90 do ano final, e histograma da distribuição final.
- **Visão Geral**: gráfico de patrimônio combina banda sombreada (estocástica) + linhas tracejadas (determinístico).

Limitações documentadas: distribuição normal (caudas finas) e ativos independentes (superestima diversificação). Migrações futuras (t-Student, matriz de correlação, VaR/CVaR) ficam para Phase 3.
```

- [ ] **Step 3: Run full test suite**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 53 tests passing.

- [ ] **Step 4: Smoke-import the app**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 5: Manual smoke test (optional)**

```bash
cd ~/Downloads/dashboard && .venv/bin/streamlit run app.py --server.headless true --server.port 8503 &
sleep 5
curl -sf http://localhost:8503/_stcore/health > /dev/null && echo "app responsive" || echo "app failed"
kill %1
```

Visit http://localhost:8503 manually to verify:
- Sidebar shows new "🎲 Análise estocástica" block with target input and volatility expander.
- Overview chart shows shaded band + dashed deterministic lines.
- New "🎲 Risco" tab is present with KPIs, band chart, and histograms.
- Setting target > 0 shows "Prob. de bater meta" KPI.
- Setting low capital + high σ triggers the yellow risk banner.
- Other tabs (Imóvel, Carteira, Sensibilidade, Tributação, Exportar) remain functional.

- [ ] **Step 6: Commit README**

```bash
cd ~/Downloads/dashboard
git add README.md
git commit -m "Document Monte Carlo risk analysis in README"
```

- [ ] **Step 7: Merge `phase2-monte-carlo` into `main`**

```bash
cd ~/Downloads/dashboard
git checkout main
git merge --no-ff phase2-monte-carlo -m "Merge Phase 2 sub-projeto 2: Monte Carlo (análise estocástica)

Implementa:
- MonteCarloParams + volatility per asset/imóvel em config.py
- MonteCarloResult dataclass com trajectories, percentiles, drawdowns
- simulate_portfolio_mc (per-asset volatility)
- simulate_real_estate_mc (cash + financiado, com carteira interna estocástica)
- patrimony_band_chart e distribution_histogram_chart
- Nova aba 🎲 Risco com KPIs de probabilidade e drawdown
- Banda p10/p50/p90 sobreposta no gráfico do overview
- 15 novos testes (test_monte_carlo.py) — 53 testes totais

Spec: docs/superpowers/specs/2026-04-26-phase2-monte-carlo-design.md
Plan: docs/superpowers/plans/2026-04-26-phase2-monte-carlo-implementation.md"
```

DO NOT push — user will run `git push` themselves (auth required).

---

## Self-Review Checklist (run after writing the plan)

**Spec coverage:**
- ✅ Carteira per-asset stochastic (Task 3)
- ✅ Imóvel valorização stochastic (Task 4)
- ✅ Imóvel financiado: parcela determinística + carteira interna estocástica (Task 5)
- ✅ Volatilidades hardcoded com sliders (Task 2 + Task 7)
- ✅ Nova aba "🎲 Risco" + banda nos gráficos (Task 8)
- ✅ N=10.000 fixo, seed=42 fixa, sem cache (Task 2 defaults + Task 7 instantiation)
- ✅ Distribuição normal por ativo, draws independentes (Task 3, Task 5)
- ✅ Trajetórias anuais (Task 3, Task 4, Task 5)
- ✅ `simulate_real_estate_mc(financed)` exige `portfolio_for_internal` (Task 4 dispatcher, Task 5 test #1)
- ✅ Banner de risco quando >5% trajetórias terminam abaixo do capital (Task 8 render_risk)
- ✅ Phase 1 aporte indexado integra (Task 3 implementation uses ipca arg, test #4)
- ✅ Phase 2 financiamento integra (Task 5)
- ✅ `MonteCarloResult.prob_target(target)` (Task 1)

**Type consistency:**
- `MonteCarloParams` (config.py) — used in models.py (Task 3, 4, 5) and app.py (Task 7) ✓
- `MonteCarloResult` (models.py) — returned by simulate_*_mc, consumed by app.py charts/render_risk ✓
- `simulate_portfolio_mc(params, horizon, mc_params, ipca=0.0)` — signature consistent in implementation, tests, app.py ✓
- `simulate_real_estate_mc(params, horizon, mc_params, capital_initial=None, portfolio_for_internal=None)` — signature consistent ✓
- `patrimony_band_chart(mc_results, deterministic_results=None)` — defined in Task 6, used in Task 8 ✓
- `_run_monte_carlo` returns `tuple[MonteCarloResult, MonteCarloResult]` — consumed in main() ✓

**Placeholder scan:** No TBD/TODO. Every code step has a complete code block. Test expectations carry concrete numeric values.
