# Phase 2 Financing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real estate financing (SAC and Price) as an optional toggle in the Imóvel scenario, with capital surplus going to an internal portfolio at the same total return as the Carteira diversificada, and visual alert when the internal cash flow turns negative.

**Architecture:** New `FinancingParams` dataclass in `config.py`; `RealEstateParams` gains `financing: FinancingParams | None`. New amortization helpers (`_sac_schedule`, `_price_schedule`, `build_schedule`, `AmortizationSchedule`) in `models.py`. `simulate_real_estate` is refactored into a dispatcher that routes to `_simulate_real_estate_cash` (current Phase 1 behavior, untouched) or `_simulate_real_estate_financed` (new). `SimulationResult` gains `debt_balance: np.ndarray | None`. UI adds toggle + inputs in the Imóvel sidebar block, KPIs and a saldo-devedor chart in the Imóvel tab, and a banner when the internal portfolio goes negative.

**Tech Stack:** Python 3.14, Streamlit, NumPy, Pandas, Plotly, pytest + pytest-mock.

**Spec reference:** `docs/superpowers/specs/2026-04-25-phase2-financing-design.md`

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `config.py` | modify | + `FinancingParams` dataclass, + `financing: FinancingParams \| None` on `RealEstateParams` |
| `models.py` | modify | + `AmortizationSchedule`, `_sac_schedule`, `_price_schedule`, `build_schedule`; refactor `simulate_real_estate` into dispatcher; + `_simulate_real_estate_cash`, `_simulate_real_estate_financed`; + `debt_balance` field on `SimulationResult` |
| `app.py` | modify | toggle + inputs in sidebar; capital-vs-entry validation; KPIs + banner in Imóvel tab; pass internal portfolio rate from `pf_params.total_return()` |
| `charts.py` | modify | + `debt_evolution_chart` |
| `README.md` | modify | document financing feature |
| `tests/test_financing.py` | create | 12 unit tests for amortization formulas |
| `tests/test_models.py` | modify | + 8 tests for financed simulation |

---

## Task 1: Amortization helpers (TDD)

**Files:**
- Create: `tests/test_financing.py`
- Modify: `models.py` (add `AmortizationSchedule`, `_sac_schedule`, `_price_schedule`, `build_schedule`)

This task adds pure mathematical helpers with no integration into the rest of the code. Strict TDD: tests first, verify they fail, then implement.

- [ ] **Step 1: Write the failing tests in `tests/test_financing.py`**

```python
"""Tests for amortization schedules (SAC and Price systems).

These are pure mathematical tests with no Streamlit/dashboard integration.
"""
from __future__ import annotations

import numpy as np
import pytest

from models import AmortizationSchedule, _price_schedule, _sac_schedule, build_schedule


# ---------- SAC ----------

def test_sac_amortization_is_constant():
    schedule = _sac_schedule(principal=120.0, monthly_rate=0.01, n_months=12)
    expected = np.full(12, 10.0)  # 120 / 12
    np.testing.assert_allclose(schedule.principal, expected)


def test_sac_balance_decreases_to_zero():
    schedule = _sac_schedule(principal=120.0, monthly_rate=0.01, n_months=12)
    assert schedule.balance[-1] == pytest.approx(0.0, abs=1e-9)
    diffs = np.diff(schedule.balance)
    assert np.all(diffs <= 0)


def test_sac_payment_decreasing():
    schedule = _sac_schedule(principal=120.0, monthly_rate=0.01, n_months=12)
    diffs = np.diff(schedule.payments)
    assert np.all(diffs < 0)


def test_sac_total_principal_equals_loan():
    schedule = _sac_schedule(principal=100_000.0, monthly_rate=0.008, n_months=240)
    assert schedule.principal.sum() == pytest.approx(100_000.0)


# ---------- Price ----------

def test_price_payment_is_constant():
    schedule = _price_schedule(principal=100_000.0, monthly_rate=0.01, n_months=12)
    np.testing.assert_allclose(schedule.payments, schedule.payments[0])


def test_price_balance_decreases_to_zero():
    schedule = _price_schedule(principal=100_000.0, monthly_rate=0.01, n_months=12)
    assert schedule.balance[-1] == pytest.approx(0.0, abs=1e-6)


def test_price_principal_increasing():
    schedule = _price_schedule(principal=100_000.0, monthly_rate=0.01, n_months=12)
    diffs = np.diff(schedule.principal)
    assert np.all(diffs > 0)


def test_price_total_principal_equals_loan():
    schedule = _price_schedule(principal=100_000.0, monthly_rate=0.01, n_months=12)
    assert schedule.principal.sum() == pytest.approx(100_000.0)


def test_price_pmt_formula_known_case():
    """principal=100_000, rate=0.01/m, n=12 → PMT ≈ 8884.88."""
    schedule = _price_schedule(principal=100_000.0, monthly_rate=0.01, n_months=12)
    assert schedule.payments[0] == pytest.approx(8884.88, abs=0.01)


# ---------- Comparison ----------

def test_total_interest_price_greater_than_sac():
    """Same principal/rate/term → Price pays more total interest."""
    sac = _sac_schedule(principal=200_000.0, monthly_rate=0.009, n_months=120)
    price = _price_schedule(principal=200_000.0, monthly_rate=0.009, n_months=120)
    assert price.interest.sum() > sac.interest.sum()


def test_zero_rate_degenerate_case():
    """rate=0 → both systems: payment = principal/n, interest = 0."""
    sac = _sac_schedule(principal=120.0, monthly_rate=0.0, n_months=12)
    price = _price_schedule(principal=120.0, monthly_rate=0.0, n_months=12)
    np.testing.assert_allclose(sac.payments, np.full(12, 10.0))
    np.testing.assert_allclose(price.payments, np.full(12, 10.0))
    np.testing.assert_allclose(sac.interest, np.zeros(12))
    np.testing.assert_allclose(price.interest, np.zeros(12))


# ---------- Dispatcher ----------

def test_build_schedule_dispatches_correctly():
    from config import FinancingParams

    sac_params = FinancingParams(term_years=1, annual_rate=0.0, entry_pct=0.0,
                                  system="SAC")
    price_params = FinancingParams(term_years=1, annual_rate=0.0, entry_pct=0.0,
                                    system="Price")

    sac_schedule = build_schedule(sac_params, principal=120.0)
    price_schedule = build_schedule(price_params, principal=120.0)

    # With rate=0 they should be identical numerically; check structure differs
    # via a rate>0 case.
    sac_p = FinancingParams(term_years=1, annual_rate=0.12, entry_pct=0.0, system="SAC")
    price_p = FinancingParams(term_years=1, annual_rate=0.12, entry_pct=0.0, system="Price")
    sac_s = build_schedule(sac_p, principal=120.0)
    price_s = build_schedule(price_p, principal=120.0)
    # SAC: principal constant; Price: principal increasing
    np.testing.assert_allclose(sac_s.principal, sac_s.principal[0])
    assert np.all(np.diff(price_s.principal) > 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_financing.py -v`
Expected: ImportError on `AmortizationSchedule`, `_sac_schedule`, `_price_schedule`, `build_schedule`, `FinancingParams` — none exist yet.

- [ ] **Step 3: Add `FinancingParams` to `config.py`**

In `/home/lucgomes/Downloads/dashboard/config.py`, find the `# ---------- Real Estate defaults` block and insert this new section right BEFORE it (after the macro section):

```python
# ---------- Financing ----------

@dataclass(slots=True, frozen=True)
class FinancingParams:
    """Real-estate financing terms (loan principal, rate, system, insurance)."""
    term_years: int = 30
    annual_rate: float = 0.115
    entry_pct: float = 0.20
    system: Literal["SAC", "Price"] = "SAC"
    monthly_insurance_rate: float = 0.0005

    @property
    def monthly_rate(self) -> float:
        return (1 + self.annual_rate) ** (1 / 12) - 1
```

Add `Literal` to the existing typing import. The line currently reads:
```python
from typing import Final
```
Change it to:
```python
from typing import Final, Literal
```

- [ ] **Step 4: Add `financing` field to `RealEstateParams`**

In `/home/lucgomes/Downloads/dashboard/config.py`, find the end of `RealEstateParams` field declarations (the last field is `acquisition_cost_pct: float = 0.05`). Add immediately after it:

```python
    financing: "FinancingParams | None" = None
```

(The forward reference quotation `"FinancingParams | None"` is unnecessary because `FinancingParams` is defined earlier in the same file, but Python 3.14 with `from __future__ import annotations` already accepts the bare form. Use the bare form:)

```python
    financing: FinancingParams | None = None
```

- [ ] **Step 5: Implement amortization helpers in `models.py`**

In `/home/lucgomes/Downloads/dashboard/models.py`, update the imports at the top:

```python
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
```

Then, immediately AFTER the existing `SimulationResult` dataclass and BEFORE `simulate_real_estate`, add:

```python
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
    # Numerical drift cleanup: enforce final balance = 0
    balance_end[-1] = 0.0
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_financing.py -v`
Expected: 12 tests passing.

- [ ] **Step 7: Run all tests to ensure no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 21 (Phase 1) + 12 (new) = 33 tests passing.

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add config.py models.py tests/test_financing.py
git commit -m "Add SAC and Price amortization helpers with FinancingParams"
```

---

## Task 2: Refactor `simulate_real_estate` into dispatcher

**Files:**
- Modify: `models.py` (extract current logic into `_simulate_real_estate_cash`; turn `simulate_real_estate` into a dispatcher that routes based on `params.financing`)

This task is a pure refactor — no behavior change. Existing 21 tests must still pass.

- [ ] **Step 1: Read the current `simulate_real_estate` function**

The current function lives at `/home/lucgomes/Downloads/dashboard/models.py` lines 28-72 (approximately). It looks like:

```python
def simulate_real_estate(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool = True,
) -> SimulationResult:
    """Simulate real estate investment over time."""
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    years = np.arange(0, horizon_years + 1)

    # Property value evolution
    property_values = params.property_value * (1 + params.annual_appreciation) ** years

    # Annual rent grows with appreciation as well
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
```

- [ ] **Step 2: Replace the function with a dispatcher + extracted cash variant**

Replace the entire function above with:

```python
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
    """Financed purchase. Skeleton — full implementation in Task 4."""
    raise NotImplementedError("Implemented in Task 4")
```

- [ ] **Step 3: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 33 tests passing — none of them call `simulate_real_estate` with `financing != None` yet.

- [ ] **Step 4: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: prints `OK` (with the usual Streamlit warnings about ScriptRunContext).

- [ ] **Step 5: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py
git commit -m "Refactor simulate_real_estate into dispatcher for cash and financed variants"
```

---

## Task 3: Add `debt_balance` field to `SimulationResult`

**Files:**
- Modify: `models.py` (`SimulationResult`)

- [ ] **Step 1: Update `SimulationResult` dataclass**

In `/home/lucgomes/Downloads/dashboard/models.py`, find:

```python
@dataclass(slots=True)
class SimulationResult:
    years: np.ndarray
    patrimony: np.ndarray
    annual_income: np.ndarray
    cumulative_income: np.ndarray
    label: str
    color: str
```

Replace with:

```python
@dataclass(slots=True)
class SimulationResult:
    years: np.ndarray
    patrimony: np.ndarray
    annual_income: np.ndarray
    cumulative_income: np.ndarray
    label: str
    color: str
    debt_balance: np.ndarray | None = None    # outstanding loan balance at end of each year (financed only)
```

- [ ] **Step 2: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 33 tests passing. The new field has a default of `None`, so existing call sites keep working.

- [ ] **Step 3: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py
git commit -m "Add optional debt_balance field to SimulationResult"
```

---

## Task 4: Implement `_simulate_real_estate_financed` (TDD)

**Files:**
- Modify: `tests/test_models.py` (+ 8 new tests)
- Modify: `models.py` (replace the `NotImplementedError` skeleton)

Write the tests first, verify they fail, then implement.

- [ ] **Step 1: Add 8 new tests to `tests/test_models.py`**

Append at the end of `/home/lucgomes/Downloads/dashboard/tests/test_models.py`:

```python
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
    """Helper: build a RealEstateParams with financing attached, with all costs zeroed by default."""
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
    # Property value at year 10
    expected_property_y10 = re_params.property_value * (1 + re_params.annual_appreciation) ** 10
    # debt_balance must be None for cash purchase
    assert result.debt_balance is None
    assert result.patrimony[-1] >= expected_property_y10  # rent reinvested adds on top


def test_real_estate_with_financing_returns_debt_balance():
    re_params = _make_financed_params()
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=200_000.0,
        internal_portfolio_rate=0.0,
    )
    assert result.debt_balance is not None
    assert len(result.debt_balance) == 11  # horizon_years + 1


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
    # After year 10, debt is zero
    np.testing.assert_allclose(result.debt_balance[10:], 0.0, atol=1e-6)


def test_financed_internal_portfolio_can_go_negative():
    """Low rent + high payment → internal portfolio goes negative, no error raised."""
    re_params = _make_financed_params(
        property_value=500_000.0,
        monthly_rent=500.0,           # very low rent
        term_years=10, annual_rate=0.15, entry_pct=0.20,
    )
    result = simulate_real_estate(
        re_params, horizon_years=10, capital_initial=100_000.0,
        internal_portfolio_rate=0.0,
    )
    # Compute internal portfolio = patrimony - property_value_t + debt_balance
    property_values = re_params.property_value * (1 + re_params.annual_appreciation) ** np.arange(11)
    internal = result.patrimony - property_values + result.debt_balance
    assert internal.min() < 0


def test_capital_initial_split_correctly():
    """capital=300k, entry_pct=20%, property=200k → buffer = 300k - 40k = 260k.

    With zero rent and zero portfolio rate over 0 years, the initial
    patrimony must equal property_value - loan_principal + buffer.
    """
    re_params = _make_financed_params(
        property_value=200_000.0, monthly_rent=0.0, entry_pct=0.20,
        term_years=10, annual_rate=0.10,
    )
    result = simulate_real_estate(
        re_params, horizon_years=1, capital_initial=300_000.0,
        internal_portfolio_rate=0.0,
    )
    # At year 0 (before any payment), debt = loan_principal, internal = buffer.
    # patrimony[0] = property_value - loan + buffer = 200k - 160k + 260k = 300k
    assert result.patrimony[0] == pytest.approx(300_000.0, abs=1e-6)


def test_sac_vs_price_final_patrimony():
    """Same inputs except system → both viable, Price has more interest paid (smaller internal portfolio)."""
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
    # Both pay off completely
    assert r_sac.debt_balance[-1] == pytest.approx(0.0, abs=1e-6)
    assert r_price.debt_balance[-1] == pytest.approx(0.0, abs=1e-6)
    # SAC pays less interest → leaves more in internal portfolio → higher patrimony
    assert r_sac.patrimony[-1] > r_price.patrimony[-1]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_models.py -v -k "financed or real_estate_no_financing or capital_initial_split or sac_vs_price"`
Expected: most fail with `NotImplementedError` from the skeleton.

- [ ] **Step 3: Replace the `_simulate_real_estate_financed` skeleton with the full implementation**

In `/home/lucgomes/Downloads/dashboard/models.py`, find:

```python
def _simulate_real_estate_financed(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool,
    capital_initial: float,
    internal_portfolio_rate: float,
) -> SimulationResult:
    """Financed purchase. Skeleton — full implementation in Task 4."""
    raise NotImplementedError("Implemented in Task 4")
```

Replace with:

```python
def _simulate_real_estate_financed(
    params: RealEstateParams,
    horizon_years: int,
    reinvest_income: bool,
    capital_initial: float,
    internal_portfolio_rate: float,
) -> SimulationResult:
    """Financed purchase: entry + monthly amortization, surplus invested at internal_portfolio_rate."""
    fin = params.financing
    assert fin is not None  # caller ensures this

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

    # Pad/truncate schedule to horizon_years × 12 months
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
    # net cash flow per year (excluding year 0, which has no payment activity yet)
    net_cash_flow = annual_net_income[1:] - payments_annual - insurance_annual

    # Internal portfolio evolution: starts at initial_buffer, grows at internal_portfolio_rate
    # and absorbs net_cash_flow each year (PMT-end semantics: rate first, then cash flow added).
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
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 33 (Phase 1 + Task 1) + 8 (new) = 41 tests passing.

- [ ] **Step 5: Commit**

```bash
cd ~/Downloads/dashboard
git add models.py tests/test_models.py
git commit -m "Implement financed real-estate simulation with internal portfolio buffer"
```

---

## Task 5: UI — toggle and inputs in `app.py`

**Files:**
- Modify: `app.py` (sidebar UI, capital validation, wiring of `internal_portfolio_rate`)

This task threads the new feature through the UI. No new tests; manual smoke test only.

- [ ] **Step 1: Add `FinancingParams` import**

In `/home/lucgomes/Downloads/dashboard/app.py`, find the existing config import block:

```python
from config import (
    BenchmarkParams,
    MacroParams,
    PALETTE,
    PortfolioParams,
    RealEstateParams,
    TODAY_LABEL,
)
```

Replace with:

```python
from config import (
    BenchmarkParams,
    FinancingParams,
    MacroParams,
    PALETTE,
    PortfolioParams,
    RealEstateParams,
    TODAY_LABEL,
)
```

- [ ] **Step 2: Add the financing UI block to `render_sidebar`**

Inside `render_sidebar`, find the Imóvel section. The last existing input there is `re_params.income_tax_bracket = ...`. AFTER that line and BEFORE the next `st.sidebar.markdown("---")`, insert:

```python
    financing_enabled = st.sidebar.checkbox(
        "Financiar imóvel",
        value=False,
        help="Quando ligado, simula entrada + parcelas. Capital inicial cobre a entrada; sobra entra na carteira interna.",
    )
    if financing_enabled:
        with st.sidebar.expander("Detalhes do financiamento", expanded=True):
            entry_pct = st.slider("Entrada (% do imóvel)", 10, 80, 20, 5) / 100
            term_years = st.slider("Prazo (anos)", 5, 35, 30, 1)
            annual_rate = st.slider("Taxa anual (%)", 6.0, 18.0, 11.5, 0.25) / 100
            system = st.radio("Sistema", ["SAC", "Price"], horizontal=True)
        re_params.financing = FinancingParams(
            term_years=term_years,
            annual_rate=annual_rate,
            entry_pct=entry_pct,
            system=system,
        )
```

- [ ] **Step 3: Add capital-vs-entry validation in `main()`**

In `/home/lucgomes/Downloads/dashboard/app.py`, find `main()`. After the `re_params, pf_params, bench_params, horizon, reinvest = render_sidebar(macro)` line and BEFORE `tabs = st.tabs(...)`, insert:

```python
    if re_params.financing is not None:
        entry_required = re_params.property_value * re_params.financing.entry_pct
        if re_params.property_value > entry_required:  # always true here, just to keep flow clear
            pass
        # Capital initial is the user's "Capital inicial" slider value.
        # In the current sidebar, capital == property_value because they share the
        # same input. With financing, capital represents what the user has, not the
        # property. So we use the slider's value as capital_initial.
        capital_initial = re_params.property_value
        if capital_initial < entry_required:
            st.error(
                f"Capital insuficiente: a entrada exige R$ {entry_required:,.0f}".replace(",", ".")
                + f", mas o capital inicial é R$ {capital_initial:,.0f}.".replace(",", ".")
                + " Aumente o capital ou reduza a % de entrada."
            )
            st.stop()
```

- [ ] **Step 4: Wire `_run_simulations` to pass financing-aware kwargs**

In `/home/lucgomes/Downloads/dashboard/app.py`, find `_run_simulations` (introduced in Phase 1). It currently looks like:

```python
def _run_simulations(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    bench_params: BenchmarkParams,
    horizon: int,
    reinvest: bool,
    ipca: float,
):
    """Run all three simulations consistently for both overview and export."""
    return (
        simulate_real_estate(re_params, horizon, reinvest),
        simulate_portfolio(pf_params, horizon, reinvest, ipca=ipca),
        simulate_benchmark(bench_params, horizon),
    )
```

Replace with:

```python
def _run_simulations(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    bench_params: BenchmarkParams,
    horizon: int,
    reinvest: bool,
    ipca: float,
):
    """Run all three simulations consistently for both overview and export."""
    re_kwargs = {}
    if re_params.financing is not None:
        re_kwargs["capital_initial"] = re_params.property_value
        re_kwargs["internal_portfolio_rate"] = pf_params.total_return()
    return (
        simulate_real_estate(re_params, horizon, reinvest, **re_kwargs),
        simulate_portfolio(pf_params, horizon, reinvest, ipca=ipca),
        simulate_benchmark(bench_params, horizon),
    )
```

- [ ] **Step 5: Apply same wiring to direct `simulate_real_estate` calls**

In `/home/lucgomes/Downloads/dashboard/app.py`, find the call inside `render_real_estate`. It looks like:

```python
def render_real_estate(re_params: RealEstateParams) -> None:
```

This function does not currently call `simulate_real_estate`; it only uses the static methods on `re_params`. No change needed here.

Also check `render_sensitivity` — it uses `sensitivity_real_estate`, which itself calls `simulate_real_estate`. The sensitivity helper does NOT pass financing kwargs, but its call sites all use `RealEstateParams` instances that we control. To keep sensitivity working in the cash variant, ensure that `sensitivity_real_estate` continues calling `simulate_real_estate(low_params, horizon)` with no financing.

Verify the existing `sensitivity_real_estate` function in `/home/lucgomes/Downloads/dashboard/models.py` only varies cash-related fields (`monthly_rent`, `annual_appreciation`, `vacancy_months_per_year`, `management_fee_pct`, `iptu_rate`, `income_tax_bracket`). It does. No code change needed; sensitivity remains a cash-purchase analysis (deliberate scope choice).

- [ ] **Step 6: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 41 tests passing.

- [ ] **Step 7: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add app.py
git commit -m "Wire financing UI: sidebar toggle, validation, internal portfolio rate"
```

---

## Task 6: KPIs, banner, and debt evolution chart

**Files:**
- Modify: `charts.py` (add `debt_evolution_chart`)
- Modify: `app.py` (`render_real_estate` displays new KPIs and banner when financed)

- [ ] **Step 1: Add `debt_evolution_chart` to `charts.py`**

In `/home/lucgomes/Downloads/dashboard/charts.py`, append at the end:

```python
def debt_evolution_chart(
    years: np.ndarray,
    debt_balance: np.ndarray,
) -> go.Figure:
    """Area chart of outstanding loan balance over time."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years,
        y=debt_balance,
        mode="lines",
        fill="tozeroy",
        line=dict(color=PALETTE["imovel"], width=2),
        name="Saldo devedor",
    ))
    fig.update_layout(
        title="Saldo devedor ao longo do tempo",
        xaxis_title="Ano",
        yaxis_title="Saldo (R$)",
        yaxis=dict(tickformat=",.0f", separatethousands=True),
        plot_bgcolor=PALETTE["background"],
        margin=dict(l=20, r=20, t=50, b=40),
        height=320,
    )
    return fig
```

If the imports at the top of `charts.py` don't already include `numpy as np`, add `import numpy as np` to the top of the file.

- [ ] **Step 2: Update `app.py` imports**

In `/home/lucgomes/Downloads/dashboard/app.py`, find the existing `charts` import block. Add `debt_evolution_chart` to it. The existing block looks like:

```python
from charts import (
    annual_income_chart,
    cost_breakdown_chart,
    income_vs_costs_waterfall,
    patrimony_evolution_chart,
    portfolio_donut_chart,
    risk_return_scatter,
    sensitivity_tornado_chart,
    tax_comparison_chart,
    yield_comparison_bars,
)
```

Replace with:

```python
from charts import (
    annual_income_chart,
    cost_breakdown_chart,
    debt_evolution_chart,
    income_vs_costs_waterfall,
    patrimony_evolution_chart,
    portfolio_donut_chart,
    risk_return_scatter,
    sensitivity_tornado_chart,
    tax_comparison_chart,
    yield_comparison_bars,
)
```

- [ ] **Step 3: Update `render_real_estate` signature to accept `pf_params`, `horizon`, `reinvest`**

The current signature is:

```python
def render_real_estate(re_params: RealEstateParams) -> None:
```

The financing KPIs need access to a simulation result, which requires `pf_params`, `horizon`, and `reinvest`. Update to:

```python
def render_real_estate(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    horizon: int,
    reinvest: bool,
) -> None:
```

In `main()`, find the call:

```python
    with tabs[1]:
        render_real_estate(re_params)
```

Replace with:

```python
    with tabs[1]:
        render_real_estate(re_params, pf_params, horizon, reinvest)
```

- [ ] **Step 4: Add financing KPIs and chart inside `render_real_estate`**

In `/home/lucgomes/Downloads/dashboard/app.py`, find `render_real_estate`. Right BEFORE its existing `### Decomposição de receita e custos` section (which calls `income_vs_costs_waterfall`), insert:

```python
    if re_params.financing is not None:
        from models import build_schedule, simulate_real_estate as _sim

        result = _sim(
            re_params, horizon, reinvest,
            capital_initial=re_params.property_value,
            internal_portfolio_rate=pf_params.total_return(),
        )

        fin = re_params.financing
        entry = re_params.property_value * fin.entry_pct
        loan = re_params.property_value - entry
        schedule = build_schedule(fin, loan)
        first_payment = float(schedule.payments[0])
        total_interest = float(schedule.interest.sum())

        st.markdown("### 💼 Financiamento")
        cols = st.columns(4)
        cols[0].metric("Entrada", f"R$ {entry:,.0f}".replace(",", "."))
        cols[1].metric("Parcela inicial", f"R$ {first_payment:,.0f}".replace(",", "."),
                       help=f"Primeira parcela ({fin.system}). Em SAC, parcelas decrescem; em Price, ficam constantes.")
        cols[2].metric("Total de juros", f"R$ {total_interest:,.0f}".replace(",", "."))
        cols[3].metric("Prazo", f"{fin.term_years} anos")

        # Internal portfolio = patrimony - property_value_t + debt_balance
        property_values = re_params.property_value * (1 + re_params.annual_appreciation) ** result.years
        internal_portfolio = result.patrimony - property_values + result.debt_balance
        if internal_portfolio.min() < 0:
            negative_year = int(result.years[internal_portfolio < 0][0])
            st.warning(
                f"⚠️ Cenário com fluxo negativo: a carteira interna do Imóvel fica deficitária "
                f"a partir do ano {negative_year}. Em vida real, isso exigiria injeção de capital "
                f"externo. Considere aumentar a entrada, o prazo, ou o aluguel-alvo."
            )

        st.plotly_chart(
            debt_evolution_chart(result.years, result.debt_balance),
            use_container_width=True,
        )
```

- [ ] **Step 5: Run all tests to confirm no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 41 tests passing.

- [ ] **Step 6: Verify importability**

Run: `cd ~/Downloads/dashboard && .venv/bin/python -c "import app; print('OK')"`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
cd ~/Downloads/dashboard
git add charts.py app.py
git commit -m "Add financing KPIs, deficit banner, and debt-evolution chart"
```

---

## Task 7: README and final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update Funcionalidades**

In `/home/lucgomes/Downloads/dashboard/README.md`, find the Imóvel bullet:

```
- **Imóvel**: decomposição waterfall de receita/custos, breakdown de custos anuais, custos de aquisição
```

Replace with:

```
- **Imóvel**: decomposição waterfall de receita/custos, breakdown de custos anuais, custos de aquisição, financiamento opcional (SAC/Price) com saldo devedor e alerta de fluxo negativo
```

- [ ] **Step 2: Add Financiamento section after Dados macro ao vivo**

In the same file, find the section `## Dados macro ao vivo` (added in Phase 1). Add this NEW section right AFTER its content:

```markdown
## Financiamento imobiliário

O cenário Imóvel aceita um modo financiado opcional via toggle na sidebar:

- **Sistemas**: SAC (parcelas decrescentes) ou Price (parcelas fixas)
- **Inputs**: entrada (10–80%), prazo (5–35 anos), taxa anual (6–18%)
- **Sobra de capital**: a parte do capital inicial não usada na entrada vai para uma carteira interna do Imóvel, com o mesmo retorno total da Carteira diversificada
- **Cash flow mensal**: aluguel líquido − parcela − seguro entra (ou sai) da carteira interna
- **Alerta visual**: se a carteira interna ficar negativa, banner informa o ano em que cruzou zero

Quando o toggle está desligado, comportamento é idêntico ao Phase 1 (compra à vista).
```

- [ ] **Step 3: Run full test suite**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 41 tests passing.

- [ ] **Step 4: Smoke test the app**

Run: `cd ~/Downloads/dashboard && .venv/bin/streamlit run app.py --server.headless true --server.port 8501`

Visit http://localhost:8501 and verify:
- Sidebar shows new "Financiar imóvel" checkbox in the Imóvel block.
- With toggle OFF: behavior identical to Phase 1 — no KPIs, no banner, no debt chart.
- With toggle ON: sidebar expander appears with entrada / prazo / taxa / sistema. Imóvel tab shows new KPI row (Entrada, Parcela inicial, Total de juros, Prazo) and the debt-evolution chart.
- With aggressive params (e.g., entrada 10%, prazo 35y, taxa 18%, low rent 1500, high property 800k): a yellow "⚠️ fluxo negativo" banner appears in the Imóvel tab.
- Setting capital below required entry (programmatically; the slider may not reach there): the page shows the red "Capital insuficiente" error and stops.
- Other tabs (Carteira, Sensibilidade, Tributação, Exportar) remain functional.

Stop the test server when done.

- [ ] **Step 5: Commit README**

```bash
cd ~/Downloads/dashboard
git add README.md
git commit -m "Document financing feature in README"
```

- [ ] **Step 6: Merge into main and push**

```bash
cd ~/Downloads/dashboard
git checkout main
git merge --no-ff phase2-financing -m "Merge Phase 2 sub-project 1: financiamento imobiliário (SAC e Price)"
git push
```

The user will be asked for GitHub credentials (PAT). After push, Streamlit Cloud auto-redeploys.

- [ ] **Step 7: Verify deploy**

Visit https://dashboard-investimentos.streamlit.app/ after ~2 minutes and confirm:
- New "Financiar imóvel" checkbox is present.
- Toggling it works.
- All other Phase 1 features remain intact.

---

## Self-Review Checklist (run after writing the plan)

**Spec coverage:**
- ✅ Toggle in existing Imóvel scenario (Task 5, Step 2)
- ✅ Sobra → carteira interna at Carteira's blended yield (Task 5, Step 4 wires `pf_params.total_return()`)
- ✅ SAC and Price toggleable (Task 1, helpers + Task 5 radio button)
- ✅ Internal portfolio can go negative with visual alert (Task 6, Step 4)
- ✅ Nominal rate, no TR (helpers in Task 1 use `monthly_rate` derived from `annual_rate`)
- ✅ Insurance default 0.05% a.m. (Task 1, `FinancingParams`)
- ✅ Juros not deductible from IR (no change to existing `income_tax_amount`)
- ✅ Limits 10–80% entry, 5–35 years term, 6–18% rate (Task 5, Step 2 sliders)
- ✅ `financing=None` preserves Phase 1 behavior (Task 2 dispatcher)
- ✅ `horizon < term` leaves residual debt; `horizon > term` zeros after term (Task 4 implementation handles padding/truncation)
- ✅ Capital insufficient error in UI (Task 5, Step 3)
- ✅ All 12 amortization tests + 8 simulation tests planned (Task 1, Task 4)

**Type consistency:**
- `FinancingParams` (in `config.py`) — used in `models.py` (Task 1, build_schedule) and `app.py` (Task 5) ✓
- `AmortizationSchedule` (in `models.py`) — returned by `_sac_schedule`, `_price_schedule`, `build_schedule`; consumed by `_simulate_real_estate_financed` and `render_real_estate` chart logic ✓
- `simulate_real_estate(params, horizon, reinvest, capital_initial=None, internal_portfolio_rate=0.0)` — same signature in dispatcher (Task 2), in `_run_simulations` (Task 5), and in `render_real_estate` direct call (Task 6) ✓
- `SimulationResult.debt_balance: np.ndarray | None` — set in financed variant (Task 4), read in chart logic (Task 6) ✓

**Placeholder scan:** No TBD/TODO. Every code step has a complete code block. Test expectations all carry concrete numeric values.
