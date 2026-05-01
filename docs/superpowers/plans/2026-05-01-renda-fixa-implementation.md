# Renda Fixa — Tracker de Posições — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "📊 Renda Fixa" tab to the dashboard that lets users register fixed-income positions (Tesouro, CDB, LCI, etc.) with indexer-aware modeling, automatic regressive IR, optional maturity, and CSV import/export.

**Architecture:** Distributed across the existing project layers: dataclass in `config.py`, simulation engine in `models.py`, chart in `charts.py`, UI in `app.py`. Tests in a new `tests/test_fixed_income.py`. CSV serialization via classmethods on the dataclass (no pandas in `config.py`).

**Tech Stack:** Python 3.10+, dataclasses, numpy, pandas, plotly, streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-05-01-renda-fixa-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `config.py` | Modify | Add `IndexerKind`, `FixedIncomePosition` dataclass with `effective_annual_rate`, `holding_days`, `applicable_ir_rate`, `to_record`, `from_record` |
| `models.py` | Modify | Add `FixedIncomeProjection`, `FixedIncomePortfolio` dataclasses + `simulate_fixed_income()` function |
| `charts.py` | Modify | Add `fixed_income_evolution_chart()` |
| `app.py` | Modify | Add `render_fixed_income(macro, horizon)` + register 8th tab |
| `tests/test_fixed_income.py` | Create | All 16 unit tests |

---

## Task 1: Add `IndexerKind` and `FixedIncomePosition` dataclass

**Files:**
- Modify: `config.py` (append after `BenchmarkParams` block, before `# ---------- Visual palette ----------` line)
- Create: `tests/test_fixed_income.py`

- [ ] **Step 1.1: Write failing tests for dataclass instantiation**

Create `tests/test_fixed_income.py`:

```python
"""Tests for FixedIncomePosition dataclass and simulation."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from config import (
    FixedIncomePosition,
    IndexerKind,
    MacroParams,
)


@pytest.fixture
def macro():
    """Macro fixture with stable values for tests."""
    return MacroParams(
        selic=0.1475,
        ipca=0.048,
        cdi=0.1465,
        usd_brl=5.30,
        is_stale=False,
        source_label="test",
    )


def test_position_creation_with_defaults():
    pos = FixedIncomePosition(
        name="LCI Banco X",
        initial_amount=10_000.0,
        purchase_date=date(2025, 1, 1),
        indexer="cdi",
        rate=0.95,
    )
    assert pos.name == "LCI Banco X"
    assert pos.initial_amount == 10_000.0
    assert pos.indexer == "cdi"
    assert pos.rate == 0.95
    assert pos.maturity_date is None
    assert pos.is_tax_exempt is False
    assert pos.color == "#3498DB"


def test_position_creation_with_all_fields():
    pos = FixedIncomePosition(
        name="Tesouro IPCA+ 2035",
        initial_amount=50_000.0,
        purchase_date=date(2024, 8, 1),
        indexer="ipca",
        rate=0.06,
        maturity_date=date(2035, 8, 1),
        is_tax_exempt=False,
        color="#E74C3C",
    )
    assert pos.maturity_date == date(2035, 8, 1)
    assert pos.color == "#E74C3C"
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: FAIL — `ImportError: cannot import name 'FixedIncomePosition' from 'config'`

- [ ] **Step 1.3: Add `IndexerKind` Literal and `FixedIncomePosition` dataclass to `config.py`**

In `config.py`, locate the imports at the top — they already include `from datetime import date` is missing, add it. Then locate the `# ---------- Visual palette ----------` section near the bottom and insert the new code immediately before it.

Imports to add at top of `config.py` (after `from typing import Final, Literal`):
```python
from datetime import date
```

Insert this block just before the `# ---------- Visual palette ----------` line:

```python
# ---------- Renda Fixa (fixed-income positions) ----------

IndexerKind = Literal["prefixado", "cdi", "selic", "ipca"]


@dataclass(slots=True)
class FixedIncomePosition:
    """One fixed-income holding (CDB, LCI, Tesouro, debênture, etc.)."""
    name: str
    initial_amount: float
    purchase_date: date
    indexer: IndexerKind
    rate: float
    maturity_date: date | None = None
    is_tax_exempt: bool = False
    color: str = "#3498DB"
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 2 passed

- [ ] **Step 1.5: Commit**

```bash
git add config.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): add FixedIncomePosition dataclass

Adds IndexerKind Literal and FixedIncomePosition dataclass to config.py
as the foundational data model for the Renda Fixa tracker feature.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Implement `effective_annual_rate()` method

**Files:**
- Modify: `config.py` (add method to `FixedIncomePosition`)
- Modify: `tests/test_fixed_income.py` (append tests)

- [ ] **Step 2.1: Append failing tests for the 4 indexer conversions**

Add to `tests/test_fixed_income.py`:

```python
def test_effective_rate_prefixado(macro):
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.12,
    )
    assert pos.effective_annual_rate(macro) == pytest.approx(0.12)


def test_effective_rate_cdi_percentual(macro):
    # 100% CDI with cdi=0.1465 → 0.1465
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="cdi", rate=1.00,
    )
    assert pos.effective_annual_rate(macro) == pytest.approx(0.1465)


def test_effective_rate_selic_com_spread(macro):
    # Selic + 0.1% with selic=0.1475 → 0.1485
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="selic", rate=0.001,
    )
    assert pos.effective_annual_rate(macro) == pytest.approx(0.1485)


def test_effective_rate_ipca_compoe_corretamente(macro):
    # IPCA+6% with ipca=0.048 → (1.048)(1.06) - 1 = 0.11088
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="ipca", rate=0.06,
    )
    assert pos.effective_annual_rate(macro) == pytest.approx(0.11088)
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v -k effective_rate`
Expected: 4 FAIL — `AttributeError: 'FixedIncomePosition' object has no attribute 'effective_annual_rate'`

- [ ] **Step 2.3: Implement the method**

Add inside the `FixedIncomePosition` class in `config.py`:

```python
    def effective_annual_rate(self, macro: "MacroParams") -> float:
        """Convert the position's indexer + rate into a nominal annual rate."""
        match self.indexer:
            case "prefixado":
                return self.rate
            case "cdi":
                return macro.cdi * self.rate
            case "selic":
                return macro.selic + self.rate
            case "ipca":
                return (1 + macro.ipca) * (1 + self.rate) - 1
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 6 passed (2 from Task 1 + 4 new)

- [ ] **Step 2.5: Commit**

```bash
git add config.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): convert indexer+rate to effective annual rate

Adds FixedIncomePosition.effective_annual_rate() that handles the four
supported indexers (prefixado, CDI%, Selic+, IPCA+) using current macro
values. IPCA composes (1+IPCA)(1+spread)-1 instead of summing, which is
the correct convention for indexed bonds.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Implement `holding_days()` and `applicable_ir_rate()`

**Files:**
- Modify: `config.py` (add methods)
- Modify: `tests/test_fixed_income.py` (append tests)

- [ ] **Step 3.1: Append failing tests**

Add to `tests/test_fixed_income.py`:

```python
def test_holding_days_simple():
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    assert pos.holding_days(date(2025, 1, 1)) == 0
    assert pos.holding_days(date(2025, 7, 1)) == 181
    assert pos.holding_days(date(2026, 1, 1)) == 365


def test_ir_regressivo_22_5_ate_180_dias():
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    # day 0
    assert pos.applicable_ir_rate(date(2025, 1, 1)) == pytest.approx(0.225)
    # day 180 (still in first bracket)
    assert pos.applicable_ir_rate(date(2025, 6, 30)) == pytest.approx(0.225)


def test_ir_regressivo_20_entre_181_e_360():
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    # day 181 (boundary)
    assert pos.applicable_ir_rate(date(2025, 7, 1)) == pytest.approx(0.20)
    # day 360
    assert pos.applicable_ir_rate(date(2025, 12, 27)) == pytest.approx(0.20)


def test_ir_regressivo_17_5_entre_361_e_720():
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    # day 365
    assert pos.applicable_ir_rate(date(2026, 1, 1)) == pytest.approx(0.175)
    # day 720
    assert pos.applicable_ir_rate(date(2026, 12, 22)) == pytest.approx(0.175)


def test_ir_regressivo_15_acima_de_720():
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    # day 721
    assert pos.applicable_ir_rate(date(2026, 12, 23)) == pytest.approx(0.15)
    # day 1095 (3 years)
    assert pos.applicable_ir_rate(date(2028, 1, 1)) == pytest.approx(0.15)


def test_ir_isento_zero_independente_do_holding():
    pos = FixedIncomePosition(
        name="LCI", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="cdi", rate=0.95, is_tax_exempt=True,
    )
    assert pos.applicable_ir_rate(date(2025, 1, 1)) == 0.0
    assert pos.applicable_ir_rate(date(2025, 6, 1)) == 0.0
    assert pos.applicable_ir_rate(date(2030, 1, 1)) == 0.0
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v -k "holding_days or ir_"`
Expected: 6 FAIL — `AttributeError: ... 'holding_days'` / `'applicable_ir_rate'`

- [ ] **Step 3.3: Implement both methods**

Add to `FixedIncomePosition` class in `config.py`:

```python
    def holding_days(self, at_date: date) -> int:
        """Days elapsed between purchase_date and at_date (clamped at 0)."""
        delta = (at_date - self.purchase_date).days
        return max(0, delta)

    def applicable_ir_rate(self, at_date: date) -> float:
        """Brazilian regressive IR for fixed-income (0 if tax-exempt)."""
        if self.is_tax_exempt:
            return 0.0
        days = self.holding_days(at_date)
        if days <= 180:
            return 0.225
        if days <= 360:
            return 0.20
        if days <= 720:
            return 0.175
        return 0.15
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 12 passed

- [ ] **Step 3.5: Commit**

```bash
git add config.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): regressive IR + holding-day helpers

Adds FixedIncomePosition.holding_days() and applicable_ir_rate(). The IR
function applies Brazilian regressive brackets (22.5%/20%/17.5%/15% at
180/360/720-day boundaries) and short-circuits to 0 for tax-exempt
positions (LCI/LCA/CRA/CRI).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Add `FixedIncomeProjection` and `FixedIncomePortfolio` dataclasses

**Files:**
- Modify: `models.py` (append after existing Monte Carlo dataclasses, near top)
- Modify: `tests/test_fixed_income.py` (append smoke test)

- [ ] **Step 4.1: Append a smoke test for the dataclasses**

Add to `tests/test_fixed_income.py`:

```python
def test_projection_and_portfolio_dataclasses_construct():
    from models import FixedIncomeProjection, FixedIncomePortfolio
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    proj = FixedIncomeProjection(
        position=pos,
        years=np.arange(4),
        gross_values=np.array([1000, 1100, 1210, 1331], dtype=float),
        net_values=np.array([1000, 1082.5, 1178.5, 1281.35]),
        matured=np.zeros(4, dtype=bool),
    )
    portfolio = FixedIncomePortfolio(
        projections=[proj],
        total_gross=proj.gross_values.copy(),
        total_net=proj.net_values.copy(),
        total_initial=1000.0,
    )
    assert portfolio.total_initial == 1000.0
    assert len(portfolio.projections) == 1
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_fixed_income.py::test_projection_and_portfolio_dataclasses_construct -v`
Expected: FAIL — `ImportError: cannot import name 'FixedIncomeProjection'`

- [ ] **Step 4.3: Add dataclasses to `models.py`**

In `models.py`, locate the import block at the top and add `FixedIncomePosition` to the import from config:

```python
from config import (
    BenchmarkParams,
    FinancingParams,
    FixedIncomePosition,
    MonteCarloParams,
    PortfolioParams,
    RealEstateParams,
)
```

Add `from datetime import date` to the date imports (or new `from datetime import date` if not present).

Insert the new dataclasses immediately after the `MonteCarloResult` dataclass (around line 60-70 in models.py — find the `def prob_target` method end and insert after the blank line):

```python
@dataclass(slots=True, frozen=True)
class FixedIncomeProjection:
    """Year-by-year projection for a single fixed-income position."""
    position: FixedIncomePosition
    years: np.ndarray              # 0, 1, ..., horizon
    gross_values: np.ndarray       # nominal value at end of each year
    net_values: np.ndarray         # value after IR (== gross if isento)
    matured: np.ndarray            # bool — True from the maturity year onward


@dataclass(slots=True, frozen=True)
class FixedIncomePortfolio:
    """Aggregate of all fixed-income projections plus per-year totals."""
    projections: list[FixedIncomeProjection]
    total_gross: np.ndarray
    total_net: np.ndarray
    total_initial: float
```

- [ ] **Step 4.4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 13 passed

- [ ] **Step 4.5: Commit**

```bash
git add config.py models.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): add projection and portfolio result dataclasses

Adds FixedIncomeProjection (per-position year-by-year arrays) and
FixedIncomePortfolio (aggregated totals across positions) to models.py.
These are the result types returned by the upcoming simulate_fixed_income()
function.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Implement `simulate_fixed_income()`

**Files:**
- Modify: `models.py` (add function)
- Modify: `tests/test_fixed_income.py` (append simulation tests)

- [ ] **Step 5.1: Append failing tests**

Add to `tests/test_fixed_income.py`:

```python
def test_simulate_prefixado_3_anos_golden_numbers(macro):
    """Closed-form check: 1k @ 10% prefixado, 3-year horizon starting at purchase."""
    from models import simulate_fixed_income
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    portfolio = simulate_fixed_income(
        positions=[pos],
        macro=macro,
        horizon_years=3,
        start_date=date(2025, 1, 1),
    )
    proj = portfolio.projections[0]
    # Year 0: just principal, no growth, no IR
    np.testing.assert_allclose(proj.gross_values[0], 1000.0)
    np.testing.assert_allclose(proj.net_values[0], 1000.0)
    # Year 1: 1100 gross. holding=365 → IR=17.5%. Net = 1000 + 100*0.825 = 1082.5
    np.testing.assert_allclose(proj.gross_values[1], 1100.0, rtol=1e-6)
    np.testing.assert_allclose(proj.net_values[1], 1082.5, rtol=1e-6)
    # Year 2: 1210 gross. holding=730 → IR=15%. Net = 1000 + 210*0.85 = 1178.5
    np.testing.assert_allclose(proj.gross_values[2], 1210.0, rtol=1e-6)
    np.testing.assert_allclose(proj.net_values[2], 1178.5, rtol=1e-6)
    # Year 3: 1331 gross. holding=1095 → IR=15%. Net = 1000 + 331*0.85 = 1281.35
    np.testing.assert_allclose(proj.gross_values[3], 1331.0, rtol=1e-6)
    np.testing.assert_allclose(proj.net_values[3], 1281.35, rtol=1e-6)


def test_simulate_isento_net_igual_gross(macro):
    from models import simulate_fixed_income
    pos = FixedIncomePosition(
        name="LCI", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10, is_tax_exempt=True,
    )
    portfolio = simulate_fixed_income(
        positions=[pos], macro=macro, horizon_years=3,
        start_date=date(2025, 1, 1),
    )
    np.testing.assert_allclose(
        portfolio.projections[0].net_values,
        portfolio.projections[0].gross_values,
    )


def test_simulate_vencimento_congela_valor_apos_maturity(macro):
    """Position with maturity at year 2: years 3+ should equal year-2 value."""
    from models import simulate_fixed_income
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10,
        maturity_date=date(2027, 1, 1),  # 2 years after purchase
    )
    portfolio = simulate_fixed_income(
        positions=[pos], macro=macro, horizon_years=5,
        start_date=date(2025, 1, 1),
    )
    proj = portfolio.projections[0]
    # Year 2: matured. gross=1210 (1000*1.1^2)
    np.testing.assert_allclose(proj.gross_values[2], 1210.0, rtol=1e-6)
    # Years 3-5: frozen at year-2 value (gross AND net)
    for t in (3, 4, 5):
        np.testing.assert_allclose(proj.gross_values[t], proj.gross_values[2])
        np.testing.assert_allclose(proj.net_values[t], proj.net_values[2])
        assert proj.matured[t]
    # Year 1: not matured
    assert not proj.matured[1]


def test_simulate_posicao_comprada_no_passado_ja_inicia_acumulada(macro):
    """Position bought 2 years ago should show accumulated value at year 0."""
    from models import simulate_fixed_income
    pos = FixedIncomePosition(
        name="X", initial_amount=1000, purchase_date=date(2023, 1, 1),
        indexer="prefixado", rate=0.10,
    )
    portfolio = simulate_fixed_income(
        positions=[pos], macro=macro, horizon_years=2,
        start_date=date(2025, 1, 1),
    )
    proj = portfolio.projections[0]
    # Year 0 (today, 2025-01-01): holding=730 days → gross=1210, IR=15%, net=1178.5
    np.testing.assert_allclose(proj.gross_values[0], 1210.0, rtol=1e-6)
    np.testing.assert_allclose(proj.net_values[0], 1178.5, rtol=1e-6)


def test_portfolio_totals_somam_corretamente_multiplas_posicoes(macro):
    from models import simulate_fixed_income
    a = FixedIncomePosition(
        name="A", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.10, is_tax_exempt=True,
    )
    b = FixedIncomePosition(
        name="B", initial_amount=2000, purchase_date=date(2025, 1, 1),
        indexer="prefixado", rate=0.05, is_tax_exempt=True,
    )
    portfolio = simulate_fixed_income(
        positions=[a, b], macro=macro, horizon_years=2,
        start_date=date(2025, 1, 1),
    )
    assert portfolio.total_initial == 3000.0
    # Year 1: A = 1000*1.1 = 1100, B = 2000*1.05 = 2100, total = 3200
    np.testing.assert_allclose(portfolio.total_gross[1], 3200.0, rtol=1e-6)
    np.testing.assert_allclose(portfolio.total_net[1], 3200.0, rtol=1e-6)  # both isentas
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v -k "simulate or totals"`
Expected: 5 FAIL — `ImportError: cannot import name 'simulate_fixed_income'`

- [ ] **Step 5.3: Implement `simulate_fixed_income`**

Add to `models.py`, after the `FixedIncomePortfolio` dataclass:

```python
def simulate_fixed_income(
    positions: list[FixedIncomePosition],
    macro: MacroParams,
    horizon_years: int,
    start_date: date | None = None,
) -> FixedIncomePortfolio:
    """Project each position year-by-year, applying regressive IR and maturity.

    Year 0 corresponds to start_date. Position values at year 0 already reflect
    accumulated growth from purchase_date to start_date. Macro values are held
    constant for the entire horizon.
    """
    if start_date is None:
        start_date = date.today()
    n_points = horizon_years + 1
    years = np.arange(n_points)

    projections: list[FixedIncomeProjection] = []
    total_gross = np.zeros(n_points)
    total_net = np.zeros(n_points)
    total_initial = 0.0

    for pos in positions:
        r = pos.effective_annual_rate(macro)
        gross = np.zeros(n_points)
        net = np.zeros(n_points)
        matured = np.zeros(n_points, dtype=bool)

        # Pre-compute frozen value at maturity if applicable.
        # applicable_ir_rate returns 0 when isento, so the same formula works for both.
        frozen_gross = None
        frozen_net = None
        if pos.maturity_date is not None:
            mat_holding = max(0, (pos.maturity_date - pos.purchase_date).days)
            frozen_gross = pos.initial_amount * (1 + r) ** (mat_holding / 365)
            ir_at_mat = pos.applicable_ir_rate(pos.maturity_date)
            frozen_net = pos.initial_amount + (frozen_gross - pos.initial_amount) * (1 - ir_at_mat)

        for t in range(n_points):
            current_date = _add_years(start_date, t)
            if pos.maturity_date is not None and current_date >= pos.maturity_date:
                gross[t] = frozen_gross
                net[t] = frozen_net
                matured[t] = True
            else:
                holding = pos.holding_days(current_date)
                gross[t] = pos.initial_amount * (1 + r) ** (holding / 365)
                ir = pos.applicable_ir_rate(current_date)
                net[t] = pos.initial_amount + (gross[t] - pos.initial_amount) * (1 - ir)

        projections.append(FixedIncomeProjection(
            position=pos,
            years=years.copy(),
            gross_values=gross,
            net_values=net,
            matured=matured,
        ))
        total_gross += gross
        total_net += net
        total_initial += pos.initial_amount

    return FixedIncomePortfolio(
        projections=projections,
        total_gross=total_gross,
        total_net=total_net,
        total_initial=total_initial,
    )


def _add_years(d: date, years: int) -> date:
    """Return d + N years, falling back to Feb 28 if Feb 29 is invalid in target year."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 in non-leap target year
        return d.replace(year=d.year + years, day=28)
```

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 18 passed

- [ ] **Step 5.5: Commit**

```bash
git add models.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): simulate_fixed_income with maturity and IR

Year-by-year projection of all positions: applies effective annual rate
based on indexer and macro, regressive IR on the gain only (not on
principal), and freezes value at maturity_date when set. Macro held
constant for the horizon, consistent with the rest of the dashboard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: CSV serialization (`to_record` / `from_record` on the dataclass)

**Files:**
- Modify: `config.py` (add classmethods)
- Modify: `tests/test_fixed_income.py` (append tests)

- [ ] **Step 6.1: Append failing tests**

Add to `tests/test_fixed_income.py`:

```python
def test_csv_roundtrip_preserva_todos_os_campos():
    """to_record → from_record should reconstruct the position exactly."""
    original = FixedIncomePosition(
        name="LCI Banco X 2027",
        initial_amount=30_000.0,
        purchase_date=date(2025, 3, 15),
        indexer="cdi",
        rate=0.95,
        maturity_date=date(2027, 3, 15),
        is_tax_exempt=True,
    )
    record = original.to_record()
    rebuilt = FixedIncomePosition.from_record(record)
    assert rebuilt.name == original.name
    assert rebuilt.initial_amount == original.initial_amount
    assert rebuilt.purchase_date == original.purchase_date
    assert rebuilt.indexer == original.indexer
    assert rebuilt.rate == original.rate
    assert rebuilt.maturity_date == original.maturity_date
    assert rebuilt.is_tax_exempt == original.is_tax_exempt


def test_csv_roundtrip_handles_optional_maturity():
    original = FixedIncomePosition(
        name="CDB Pós-fixado",
        initial_amount=5000.0,
        purchase_date=date(2025, 1, 1),
        indexer="cdi",
        rate=1.05,
        maturity_date=None,
    )
    record = original.to_record()
    rebuilt = FixedIncomePosition.from_record(record)
    assert rebuilt.maturity_date is None


def test_csv_indexador_invalido_levanta_validation_error():
    bad = {
        "name": "X",
        "initial_amount": 1000.0,
        "purchase_date": "2025-01-01",
        "indexer": "bitcoin",  # not a valid IndexerKind
        "rate": 0.1,
        "maturity_date": "",
        "is_tax_exempt": False,
    }
    with pytest.raises(ValueError, match="indexer"):
        FixedIncomePosition.from_record(bad)
```

- [ ] **Step 6.2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v -k csv`
Expected: 3 FAIL — `AttributeError: ... 'to_record'` / `'from_record'`

- [ ] **Step 6.3: Implement `to_record` / `from_record`**

Add to `FixedIncomePosition` class in `config.py`:

```python
    _VALID_INDEXERS = ("prefixado", "cdi", "selic", "ipca")

    def to_record(self) -> dict:
        """Serialize to a flat dict suitable for pandas.DataFrame / CSV."""
        return {
            "name": self.name,
            "initial_amount": self.initial_amount,
            "purchase_date": self.purchase_date.isoformat(),
            "indexer": self.indexer,
            "rate": self.rate,
            "maturity_date": self.maturity_date.isoformat() if self.maturity_date else "",
            "is_tax_exempt": self.is_tax_exempt,
        }

    @classmethod
    def from_record(cls, record: dict) -> "FixedIncomePosition":
        """Build from a flat dict (one CSV row).

        Raises ValueError if required fields are missing or `indexer` is invalid.
        """
        indexer = record.get("indexer", "")
        if indexer not in cls._VALID_INDEXERS:
            raise ValueError(
                f"invalid indexer {indexer!r} — must be one of {cls._VALID_INDEXERS}"
            )
        maturity_raw = record.get("maturity_date", "")
        maturity = (
            date.fromisoformat(maturity_raw)
            if isinstance(maturity_raw, str) and maturity_raw
            else None
        )
        return cls(
            name=str(record["name"]),
            initial_amount=float(record["initial_amount"]),
            purchase_date=date.fromisoformat(str(record["purchase_date"])),
            indexer=indexer,
            rate=float(record["rate"]),
            maturity_date=maturity,
            is_tax_exempt=bool(record.get("is_tax_exempt", False)),
        )
```

- [ ] **Step 6.4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 21 passed

- [ ] **Step 6.5: Commit**

```bash
git add config.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): CSV (de)serialization via to_record/from_record

Adds classmethod from_record() and instance method to_record() to
FixedIncomePosition for round-trip serialization. ISO dates, empty string
for null maturity, and explicit ValueError for invalid indexers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Add `fixed_income_evolution_chart()` to `charts.py`

**Files:**
- Modify: `charts.py` (append at end)
- Modify: `tests/test_fixed_income.py` (append smoke test)

- [ ] **Step 7.1: Append a smoke test that the chart builds without errors**

Add to `tests/test_fixed_income.py`:

```python
def test_fixed_income_chart_smoke(macro):
    """Chart builder produces a Plotly figure with one trace per position."""
    from models import simulate_fixed_income
    from charts import fixed_income_evolution_chart
    positions = [
        FixedIncomePosition(
            name="A", initial_amount=1000, purchase_date=date(2025, 1, 1),
            indexer="prefixado", rate=0.10,
        ),
        FixedIncomePosition(
            name="B", initial_amount=2000, purchase_date=date(2025, 1, 1),
            indexer="cdi", rate=1.00, is_tax_exempt=True,
        ),
    ]
    portfolio = simulate_fixed_income(
        positions=positions, macro=macro, horizon_years=3,
        start_date=date(2025, 1, 1),
    )
    fig = fixed_income_evolution_chart(portfolio)
    assert len(fig.data) == 2
    assert fig.data[0].name == "A"
    assert fig.data[1].name == "B"
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_fixed_income.py::test_fixed_income_chart_smoke -v`
Expected: FAIL — `ImportError: cannot import name 'fixed_income_evolution_chart'`

- [ ] **Step 7.3: Implement the chart**

Append to `charts.py` (at the very end):

```python
def fixed_income_evolution_chart(portfolio) -> go.Figure:
    """Line chart with net evolution per fixed-income position over time."""
    fig = go.Figure()
    for proj in portfolio.projections:
        fig.add_trace(go.Scatter(
            x=proj.years,
            y=proj.net_values,
            mode="lines+markers",
            name=proj.position.name,
            line=dict(color=proj.position.color, width=3),
            marker=dict(size=6),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Ano %{x}<br>"
                "Líquido: R$ %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title="Evolução líquida por posição",
        xaxis_title="Anos",
        yaxis_title="Valor líquido (R$)",
        hovermode="x unified",
        height=440,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig
```

> **Note:** This task uses `_LAYOUT_DEFAULTS` directly (the version on `main`, where the bottom-legend split has not yet been merged). When `fix/chart-layout-overlap` lands, this function may need to spread `**{**_LAYOUT_DEFAULTS, **_BOTTOM_LEGEND}` instead. Adjust at merge time, not now.

- [ ] **Step 7.4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_fixed_income.py -v`
Expected: 22 passed

- [ ] **Step 7.5: Commit**

```bash
git add charts.py tests/test_fixed_income.py
git commit -m "feat(renda-fixa): line chart with net evolution per position

Adds fixed_income_evolution_chart(): one trace per FixedIncomeProjection
plotting net_values over the years array. Hover format matches the rest
of the dashboard. Maturity is reflected naturally — net_values stays
flat after the maturity year.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Add `render_fixed_income()` to `app.py` and register the new tab

**Files:**
- Modify: `app.py` (add render function + tab entry + import updates)

> No automated test for this task — `streamlit.testing.v1` is flaky. Smoke test happens in Task 9.

- [ ] **Step 8.1: Update imports in `app.py`**

Three import edits in `app.py` — preserve all existing imports in each block, add only the new symbols:

1. **Add a new import** at the top (after `import streamlit as st`):
   ```python
   from datetime import date
   ```

2. **In the existing `from config import (...)` block**, add `FixedIncomePosition` (alphabetical position: between `FinancingParams` and `MacroParams`).

3. **In the existing `from models import (...)` block**, add `simulate_fixed_income` (any position; alphabetical preferred).

4. **In the existing `from charts import (...)` block**, add `fixed_income_evolution_chart` (alphabetical preferred).

To verify all four edits at once, after editing run:
```bash
.venv/bin/python -c "
from datetime import date
from config import FixedIncomePosition
from models import simulate_fixed_income
from charts import fixed_income_evolution_chart
print('imports OK')
"
```
Expected: `imports OK`

- [ ] **Step 8.2: Add the `render_fixed_income()` function**

Append this function near the other `render_*` functions in `app.py` (just before the `def main():` definition):

```python
_FI_PALETTE = [
    "#3498DB", "#E67E22", "#9B59B6", "#1ABC9C",
    "#E74C3C", "#16A085", "#F39C12", "#34495E",
]

_FI_INDEXER_LABELS = {
    "prefixado": "Prefixado",
    "cdi": "% CDI",
    "selic": "Selic +",
    "ipca": "IPCA +",
}


def _empty_fi_row() -> dict:
    """A blank row to seed the data_editor."""
    return {
        "name": "",
        "indexer": "cdi",
        "rate_pct": 100.0,           # display as percent
        "initial_amount": 0.0,
        "purchase_date": date.today(),
        "maturity_date": None,
        "is_tax_exempt": False,
    }


def _row_to_position(row: dict, color: str) -> FixedIncomePosition | None:
    """Coerce a data_editor row to FixedIncomePosition, or None if invalid.

    Validation rules (silent skip — st.warning displayed by render):
        - name must be non-empty
        - initial_amount > 0
        - rate_pct > 0
        - purchase_date <= today
        - if maturity_date set, must be > purchase_date
    """
    name = (row.get("name") or "").strip()
    if not name:
        return None
    initial = float(row.get("initial_amount") or 0)
    if initial <= 0:
        return None
    rate_pct = float(row.get("rate_pct") or 0)
    if rate_pct <= 0:
        return None
    purchase = row.get("purchase_date")
    if purchase is None or purchase > date.today():
        return None
    maturity = row.get("maturity_date")
    if maturity is not None and maturity <= purchase:
        return None
    return FixedIncomePosition(
        name=name,
        initial_amount=initial,
        purchase_date=purchase,
        indexer=row.get("indexer", "cdi"),
        rate=rate_pct / 100.0,
        maturity_date=maturity,
        is_tax_exempt=bool(row.get("is_tax_exempt", False)),
        color=color,
    )


def render_fixed_income(macro: MacroParams, horizon: int) -> None:
    st.markdown("## 📊 Renda Fixa")
    st.caption(
        "Cadastre suas posições. IR regressivo aplicado automaticamente "
        "(22,5% → 20% → 17,5% → 15% conforme tempo de aporte)."
    )

    # ----- Persisted state -----
    if "fi_positions" not in st.session_state:
        st.session_state["fi_positions"] = [_empty_fi_row()]

    # ----- CSV import / export row -----
    col_in, col_out = st.columns(2)
    with col_in:
        uploaded = st.file_uploader("Carregar CSV", type=["csv"], key="fi_csv_upload")
        if uploaded is not None:
            try:
                df_in = pd.read_csv(uploaded)
                positions = [
                    FixedIncomePosition.from_record(r) for r in df_in.to_dict("records")
                ]
                st.session_state["fi_positions"] = [
                    {
                        "name": p.name,
                        "indexer": p.indexer,
                        "rate_pct": p.rate * 100.0,
                        "initial_amount": p.initial_amount,
                        "purchase_date": p.purchase_date,
                        "maturity_date": p.maturity_date,
                        "is_tax_exempt": p.is_tax_exempt,
                    }
                    for p in positions
                ]
                st.success(f"{len(positions)} posições carregadas.")
            except Exception as e:  # noqa: BLE001 — we want to display any failure
                st.error(f"Falha ao ler CSV: {e}")

    # ----- Editable positions table -----
    st.markdown("### Posições")
    edited = st.data_editor(
        st.session_state["fi_positions"],
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn("Nome", required=True),
            "indexer": st.column_config.SelectboxColumn(
                "Indexador",
                options=list(_FI_INDEXER_LABELS.keys()),
                required=True,
            ),
            "rate_pct": st.column_config.NumberColumn(
                "Taxa (%)",
                help=(
                    "Prefixado: taxa anual (ex: 12.00). "
                    "CDI: % do CDI (ex: 100.00). "
                    "Selic/IPCA: spread anual em pp (ex: 6.00 para IPCA+6%)."
                ),
                min_value=0.0, step=0.01, format="%.2f",
            ),
            "initial_amount": st.column_config.NumberColumn(
                "Aporte (R$)", min_value=0.0, step=100.0, format="R$ %.2f",
            ),
            "purchase_date": st.column_config.DateColumn(
                "Data aporte", format="YYYY-MM-DD",
            ),
            "maturity_date": st.column_config.DateColumn(
                "Vencimento (opcional)", format="YYYY-MM-DD",
            ),
            "is_tax_exempt": st.column_config.CheckboxColumn(
                "Isento IR", help="LCI, LCA, CRA, CRI, debênture incentivada",
            ),
        },
        key="fi_editor",
    )
    st.session_state["fi_positions"] = edited

    # ----- Build positions list -----
    positions = []
    for i, row in enumerate(edited):
        color = _FI_PALETTE[i % len(_FI_PALETTE)]
        pos = _row_to_position(row, color)
        if pos is not None:
            positions.append(pos)

    # ----- CSV export (always available) -----
    if positions:
        export_df = pd.DataFrame([p.to_record() for p in positions])
        with col_out:
            st.download_button(
                "📤 Baixar CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name=f"renda-fixa-{date.today().isoformat()}.csv",
                mime="text/csv",
            )
    else:
        with col_out:
            st.info("Cadastre ao menos uma posição válida para exportar.")

    # ----- Simulation + chart + summary table -----
    if not positions:
        st.info("Cadastre ao menos uma posição válida para ver a projeção.")
        return

    portfolio = simulate_fixed_income(positions, macro, horizon)

    st.markdown("### Evolução líquida por posição")
    st.plotly_chart(fixed_income_evolution_chart(portfolio), use_container_width=True)

    # Summary table
    rows = []
    for proj in portfolio.projections:
        p = proj.position
        gross_end = float(proj.gross_values[-1])
        net_end = float(proj.net_values[-1])
        eff_rate = p.effective_annual_rate(macro)
        rows.append({
            "Nome": p.name,
            "Indexador": _FI_INDEXER_LABELS[p.indexer],
            "Taxa efetiva (%)": eff_rate * 100,
            "Aporte (R$)": p.initial_amount,
            "Bruto fim (R$)": gross_end,
            "Líquido fim (R$)": net_end,
            "Ganho líquido (R$)": net_end - p.initial_amount,
        })
    summary = pd.DataFrame(rows)
    total_row = pd.DataFrame([{
        "Nome": "Total",
        "Indexador": "—",
        "Taxa efetiva (%)": None,
        "Aporte (R$)": portfolio.total_initial,
        "Bruto fim (R$)": float(portfolio.total_gross[-1]),
        "Líquido fim (R$)": float(portfolio.total_net[-1]),
        "Ganho líquido (R$)": float(portfolio.total_net[-1]) - portfolio.total_initial,
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)
    st.markdown("### Resumo")
    st.dataframe(
        summary,
        column_config={
            "Taxa efetiva (%)": st.column_config.NumberColumn(format="%.2f"),
            "Aporte (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Bruto fim (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Líquido fim (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Ganho líquido (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        use_container_width=True, hide_index=True,
    )
```

- [ ] **Step 8.3: Register the new tab in `main()`**

In `app.py`, find the `tabs = st.tabs([...])` block (around line 695) and add the new entry as the last tab:

```python
    tabs = st.tabs([
        "📌 Visão Geral",
        "🏠 Imóvel",
        "📈 Carteira",
        "🎯 Sensibilidade",
        "💸 Tributação",
        "🎲 Risco",
        "📥 Exportar",
        "📊 Renda Fixa",
    ])
```

And add the corresponding `with tabs[7]:` block after the `with tabs[6]:` block:

```python
    with tabs[7]:
        render_fixed_income(macro, horizon)
```

- [ ] **Step 8.4: Verify imports and syntax**

Run: `.venv/bin/python -c "import app; print('imports OK')"`
Expected: `imports OK` (no syntax/import errors)

- [ ] **Step 8.5: Run the full test suite to verify no regressions**

Run: `.venv/bin/pytest tests/ -v`
Expected: all tests pass (existing + 22 new)

- [ ] **Step 8.6: Commit**

```bash
git add app.py
git commit -m "feat(renda-fixa): UI tab with editable positions + chart + summary

Registers the 8th tab '📊 Renda Fixa'. The render function uses
st.data_editor for the position list (persisted via session_state),
file_uploader/download_button for CSV import/export, and renders the
fixed-income evolution chart plus a summary table with a total row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Manual smoke test

**Files:** none — interactive verification only

- [ ] **Step 9.1: Start the streamlit server**

Run: `.venv/bin/streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false`

Open `http://localhost:8501` in a browser.

- [ ] **Step 9.2: Verify the new tab loads**

Click the "📊 Renda Fixa" tab. Expected:
- Header "📊 Renda Fixa" + caption visible
- File uploader on the left, info card on the right (no positions yet)
- Empty editable table with one blank row
- Below: `st.info("Cadastre ao menos uma posição válida...")`

- [ ] **Step 9.3: Cadastrar 3 posições e verificar gráfico/tabela**

In the data_editor, fill three rows:
1. `Tesouro Selic 2030` / Selic + / `0.10` / `R$ 50000` / today / 2030-01-01 / unchecked
2. `LCI Banco X` / % CDI / `95.00` / `R$ 30000` / today / blank / **checked**
3. `CDB Prefixado 2028` / Prefixado / `12.50` / `R$ 20000` / today / 2028-01-01 / unchecked

Expected:
- Chart appears with three lines (different colors from `_FI_PALETTE`)
- Hover on any year shows `<bold>name</bold> / Ano X / Líquido: R$ Y` for all three
- LCI line goes higher than equivalent taxable position because it's isenta
- Summary table shows all three rows + a Total row at the bottom; "Taxa efetiva" column on the Total row is empty

- [ ] **Step 9.4: Roundtrip CSV**

Click "📤 Baixar CSV" → save the file. Reload the browser tab (the session state resets to one empty row). Click "Carregar CSV" and upload the saved file. Expected:
- "3 posições carregadas." success message
- Editor table now shows the same three positions
- Chart and summary table reappear identical to before

- [ ] **Step 9.5: Verify other tabs unaffected**

Click through the other 7 tabs. Expected: each renders without errors and looks identical to before this feature was added.

- [ ] **Step 9.6: Commit nothing — this task is verification only**

If any step in 9.1-9.5 reveals a bug, **stop, debug, fix on top of the existing branch, and re-run from 9.1**.

---

## Done

- All 22 unit tests in `tests/test_fixed_income.py` pass
- Manual smoke (Task 9) passes
- No regressions in the other 7 tabs
- Branch `feat/renda-fixa` ready for PR review and merge to main
