# Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add monthly inflation-indexed contributions to the portfolio simulation and integrate live macro indicators (Selic, IPCA, CDI, USD/BRL) from the Banco Central SGS API with cache and fallback.

**Architecture:** Two new layers introduced — `data_sources/bcb.py` (pure HTTP client) and `services/macro.py` (cache + fallback orchestration). `config.py` gains `MacroParams` + `MACRO_FALLBACK`. `PortfolioParams` gains `monthly_contribution` + `contribution_inflation_indexed`. `simulate_portfolio` is extended with PMT-begin contribution logic. `app.py` consumes `MacroParams` for slider defaults and shows a stale-data banner when the API fails.

**Tech Stack:** Python 3.14, Streamlit, NumPy, Pandas, requests (new), pytest + pytest-mock (new, dev only).

**Spec reference:** `docs/superpowers/specs/2026-04-25-phase1-design.md`

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `requirements.txt` | modify | + `requests>=2.31.0` |
| `requirements-dev.txt` | create | pytest + pytest-mock |
| `tests/__init__.py` | create | empty marker |
| `tests/conftest.py` | create | pytest config (sys.path) |
| `tests/test_bcb.py` | create | tests for BCB HTTP client |
| `tests/test_macro.py` | create | tests for cache+fallback service |
| `tests/test_models.py` | create | tests for portfolio simulation w/ contributions |
| `data_sources/__init__.py` | create | empty marker |
| `data_sources/bcb.py` | create | HTTP client for BCB SGS API |
| `services/__init__.py` | create | empty marker |
| `services/macro.py` | create | cached macro params with fallback |
| `config.py` | modify | + `MacroParams` dataclass, `MACRO_FALLBACK`, 2 fields on `PortfolioParams` |
| `models.py` | modify | extend `simulate_portfolio` with contributions + IPCA indexing |
| `app.py` | modify | sidebar aporte input, banner, consume `MacroParams` |
| `README.md` | modify | document live macro + aporte feature |

---

## Task 1: Test Infrastructure

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 2: Install dev dependencies**

Run: `cd ~/Downloads/dashboard && .venv/bin/pip install -r requirements-dev.txt`
Expected: pytest and pytest-mock installed.

- [ ] **Step 3: Create `tests/__init__.py`**

Empty file (just `touch tests/__init__.py`).

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Pytest config: ensure project root is on sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 5: Verify pytest discovers no tests**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: `no tests ran in 0.0Xs` (exit code 5, which means "no tests collected" — that's fine).

- [ ] **Step 6: Commit**

```bash
cd ~/Downloads/dashboard
git add requirements-dev.txt tests/__init__.py tests/conftest.py
git commit -m "Add pytest infrastructure for Phase 1 tests"
```

---

## Task 2: BCB SGS API Client (`data_sources/bcb.py`)

**Files:**
- Create: `tests/test_bcb.py`
- Create: `data_sources/__init__.py`
- Create: `data_sources/bcb.py`
- Modify: `requirements.txt`

**Series IDs (BCB SGS):**
- 432 = Selic Meta (% a.a., already annualized)
- 433 = IPCA mensal (%, must accumulate 12 months via product `Π(1 + r_i/100) − 1`)
- 12 = CDI (% a.a., already annualized)
- 1 = USD/BRL compra (PTAX, R$/USD)

Endpoint: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados/ultimos/{n}?formato=json`

Each item in the JSON list has shape: `{"data": "DD/MM/YYYY", "valor": "X.XX"}`.

- [ ] **Step 1: Add `requests` to `requirements.txt`**

```
streamlit>=1.32.0
plotly>=5.18.0
pandas>=2.1.0
numpy>=1.26.0
requests>=2.31.0
```

- [ ] **Step 2: Install requests**

Run: `cd ~/Downloads/dashboard && .venv/bin/pip install -r requirements.txt`
Expected: `requests` installed.

- [ ] **Step 3: Create `data_sources/__init__.py`**

Empty file.

- [ ] **Step 4: Write the failing tests in `tests/test_bcb.py`**

```python
"""Tests for BCB SGS API client."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests

from data_sources.bcb import BcbApiError, BcbReading, fetch_macro


def _mock_response(json_data, status_code=200):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    return resp


def _ipca_payload_12m():
    """12 months of IPCA at 0.4% each: cumulative ≈ 4.91%."""
    return [{"data": f"01/{m:02d}/2025", "valor": "0.4"} for m in range(1, 13)]


def test_fetch_macro_success(mocker):
    def fake_get(url, timeout):
        if "bcdata.sgs.432" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.75"}])
        if "bcdata.sgs.433" in url:
            return _mock_response(_ipca_payload_12m())
        if "bcdata.sgs.12" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.65"}])
        if "bcdata.sgs.1" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "5.30"}])
        raise AssertionError(f"unexpected url: {url}")

    mocker.patch("data_sources.bcb.requests.get", side_effect=fake_get)
    reading = fetch_macro()

    assert isinstance(reading, BcbReading)
    assert reading.selic == pytest.approx(0.1475)
    assert reading.cdi == pytest.approx(0.1465)
    assert reading.usd_brl == pytest.approx(5.30)
    # 1.004^12 - 1 ≈ 0.04907
    assert reading.ipca_12m == pytest.approx(0.04907, abs=1e-4)
    assert isinstance(reading.fetched_at, datetime)


def test_fetch_macro_timeout(mocker):
    mocker.patch("data_sources.bcb.requests.get",
                 side_effect=requests.Timeout("timeout"))
    with pytest.raises(BcbApiError) as exc:
        fetch_macro()
    assert "timeout" in str(exc.value).lower()


def test_fetch_macro_http_500(mocker):
    mocker.patch("data_sources.bcb.requests.get",
                 return_value=_mock_response([], status_code=500))
    with pytest.raises(BcbApiError) as exc:
        fetch_macro()
    assert "500" in str(exc.value)


def test_fetch_macro_invalid_json(mocker):
    bad_resp = MagicMock(spec=requests.Response)
    bad_resp.status_code = 200
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.side_effect = ValueError("not json")
    mocker.patch("data_sources.bcb.requests.get", return_value=bad_resp)
    with pytest.raises(BcbApiError):
        fetch_macro()


def test_fetch_macro_empty_list(mocker):
    mocker.patch("data_sources.bcb.requests.get",
                 return_value=_mock_response([]))
    with pytest.raises(BcbApiError):
        fetch_macro()


def test_fetch_macro_partial_failure_is_total_failure(mocker):
    """If any single series fails, fall back entirely (all-or-nothing)."""
    def fake_get(url, timeout):
        if "bcdata.sgs.432" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.75"}])
        if "bcdata.sgs.433" in url:
            return _mock_response(_ipca_payload_12m())
        if "bcdata.sgs.12" in url:
            return _mock_response([], status_code=500)
        return _mock_response([{"data": "01/04/2026", "valor": "5.30"}])

    mocker.patch("data_sources.bcb.requests.get", side_effect=fake_get)
    with pytest.raises(BcbApiError):
        fetch_macro()


def test_fetch_macro_connection_error(mocker):
    mocker.patch("data_sources.bcb.requests.get",
                 side_effect=requests.ConnectionError("network"))
    with pytest.raises(BcbApiError):
        fetch_macro()
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_bcb.py -v`
Expected: ImportError / ModuleNotFoundError on `data_sources.bcb` (file doesn't exist yet).

- [ ] **Step 6: Implement `data_sources/bcb.py`**

```python
"""HTTP client for the Banco Central SGS API.

Pure data layer: no Streamlit dependencies, no caching. Raises BcbApiError
on any failure; service layer (services/macro.py) handles fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

SGS_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados/ultimos/{n}?formato=json"

SERIES_SELIC_META = 432       # % a.a.
SERIES_IPCA_MONTHLY = 433     # % mensal — accumulate 12 months
SERIES_CDI_ANNUAL = 12        # % a.a.
SERIES_USD_BRL = 1            # R$/USD (PTAX compra)

DEFAULT_TIMEOUT = 5.0


class BcbApiError(Exception):
    """Raised on any failure while fetching from the BCB SGS API."""


@dataclass(slots=True)
class BcbReading:
    selic: float          # decimal annual (0.1475 == 14.75% a.a.)
    ipca_12m: float       # decimal, accumulated 12 months
    cdi: float            # decimal annual
    usd_brl: float        # R$/USD
    fetched_at: datetime


def _fetch_series(series_id: int, n: int, timeout: float) -> list[dict]:
    url = SGS_BASE_URL.format(series_id=series_id, n=n)
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.Timeout as e:
        raise BcbApiError(f"timeout fetching series {series_id}") from e
    except requests.ConnectionError as e:
        raise BcbApiError(f"connection error: {e}") from e

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise BcbApiError(f"http_{resp.status_code}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise BcbApiError("invalid_payload: not json") from e

    if not isinstance(data, list) or len(data) == 0:
        raise BcbApiError(f"invalid_payload: empty series {series_id}")

    return data


def _last_value(payload: list[dict]) -> float:
    try:
        return float(payload[-1]["valor"])
    except (KeyError, ValueError, TypeError) as e:
        raise BcbApiError(f"invalid_payload: bad valor field") from e


def _accumulate_monthly(payload: list[dict]) -> float:
    """Accumulate monthly percentages into an annual decimal."""
    factor = 1.0
    for item in payload:
        try:
            r = float(item["valor"]) / 100.0
        except (KeyError, ValueError, TypeError) as e:
            raise BcbApiError("invalid_payload: bad valor field") from e
        factor *= (1.0 + r)
    return factor - 1.0


def fetch_macro(timeout: float = DEFAULT_TIMEOUT) -> BcbReading:
    """Fetch the 4 macro indicators. All-or-nothing: any failure raises BcbApiError."""
    selic_payload = _fetch_series(SERIES_SELIC_META, 1, timeout)
    ipca_payload = _fetch_series(SERIES_IPCA_MONTHLY, 12, timeout)
    cdi_payload = _fetch_series(SERIES_CDI_ANNUAL, 1, timeout)
    usd_payload = _fetch_series(SERIES_USD_BRL, 1, timeout)

    return BcbReading(
        selic=_last_value(selic_payload) / 100.0,
        ipca_12m=_accumulate_monthly(ipca_payload),
        cdi=_last_value(cdi_payload) / 100.0,
        usd_brl=_last_value(usd_payload),
        fetched_at=datetime.now(),
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_bcb.py -v`
Expected: 7 tests passing.

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add requirements.txt data_sources/ tests/test_bcb.py
git commit -m "Add BCB SGS API client with all-or-nothing fetch semantics"
```

---

## Task 3: Macro Service (cache + fallback)

**Files:**
- Modify: `config.py` (add `MacroParams` + `MACRO_FALLBACK`)
- Create: `tests/test_macro.py`
- Create: `services/__init__.py`
- Create: `services/macro.py`

- [ ] **Step 1: Add `MacroParams` and `MACRO_FALLBACK` to `config.py`**

Insert after the existing macro constants block (after `TODAY_LABEL`, line 19), keeping the constants for backward-compat reference:

```python
@dataclass(slots=True)
class MacroParams:
    """Macro indicators consumed by the app. May come from BCB live or fallback."""
    selic: float
    ipca: float
    cdi: float
    usd_brl: float
    is_stale: bool                       # True when fallback values are used
    source_label: str                    # "BCB SGS (live)" or "Fallback (Abr/2026)"


MACRO_FALLBACK: Final[MacroParams] = MacroParams(
    selic=SELIC_RATE,
    ipca=IPCA_EXPECTED,
    cdi=CDI_RATE,
    usd_brl=USD_BRL,
    is_stale=True,
    source_label=f"Fallback ({TODAY_LABEL})",
)
```

- [ ] **Step 2: Create `services/__init__.py`**

Empty file.

- [ ] **Step 3: Write the failing tests in `tests/test_macro.py`**

```python
"""Tests for macro params service (cache + fallback orchestration)."""
from __future__ import annotations

from datetime import datetime

import pytest

from data_sources.bcb import BcbApiError, BcbReading
from services.macro import build_macro_params


def test_build_macro_params_success(mocker):
    """Live fetch succeeds → is_stale=False, values from API."""
    reading = BcbReading(
        selic=0.1500,
        ipca_12m=0.0500,
        cdi=0.1490,
        usd_brl=5.40,
        fetched_at=datetime.now(),
    )
    mocker.patch("services.macro.fetch_macro", return_value=reading)

    params = build_macro_params()

    assert params.selic == 0.1500
    assert params.ipca == 0.0500
    assert params.cdi == 0.1490
    assert params.usd_brl == 5.40
    assert params.is_stale is False
    assert "live" in params.source_label.lower()


def test_build_macro_params_fallback_on_api_error(mocker):
    """fetch_macro raises → returns MACRO_FALLBACK."""
    mocker.patch("services.macro.fetch_macro",
                 side_effect=BcbApiError("timeout"))

    params = build_macro_params()

    assert params.is_stale is True
    assert "fallback" in params.source_label.lower()
    # Fallback values match config constants
    from config import SELIC_RATE, IPCA_EXPECTED, CDI_RATE, USD_BRL
    assert params.selic == SELIC_RATE
    assert params.ipca == IPCA_EXPECTED
    assert params.cdi == CDI_RATE
    assert params.usd_brl == USD_BRL


def test_macro_fallback_constant_is_complete():
    """Smoke test: MACRO_FALLBACK has all 4 indicators populated."""
    from config import MACRO_FALLBACK

    assert MACRO_FALLBACK.selic > 0
    assert MACRO_FALLBACK.ipca > 0
    assert MACRO_FALLBACK.cdi > 0
    assert MACRO_FALLBACK.usd_brl > 0
    assert MACRO_FALLBACK.is_stale is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_macro.py -v`
Expected: ImportError on `services.macro` and possibly on `MACRO_FALLBACK` if config edit hasn't been picked up yet.

- [ ] **Step 5: Implement `services/macro.py`**

```python
"""Macro indicators service: cached fetch with fallback.

Wraps `data_sources.bcb.fetch_macro` with Streamlit caching (24h TTL) and
falls back to MACRO_FALLBACK on any error. Exposes a hashable, dataclass-
based result that the rest of the app consumes.
"""
from __future__ import annotations

import streamlit as st

from config import MACRO_FALLBACK, MacroParams
from data_sources.bcb import BcbApiError, fetch_macro


def build_macro_params() -> MacroParams:
    """Single attempt to fetch live; fall back on any BcbApiError."""
    try:
        reading = fetch_macro()
    except BcbApiError:
        return MACRO_FALLBACK

    return MacroParams(
        selic=reading.selic,
        ipca=reading.ipca_12m,
        cdi=reading.cdi,
        usd_brl=reading.usd_brl,
        is_stale=False,
        source_label="BCB SGS (live)",
    )


@st.cache_data(ttl=86400, show_spinner=False)
def get_macro_params() -> MacroParams:
    """Cached entrypoint for app.py. Refreshes every 24h."""
    return build_macro_params()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_macro.py -v`
Expected: 3 tests passing.

- [ ] **Step 7: Run all tests so far**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 10 tests total passing (7 from test_bcb + 3 from test_macro).

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add config.py services/ tests/test_macro.py
git commit -m "Add macro service with 24h cache and fallback to hardcoded values"
```

---

## Task 4: Integrate Macro into `app.py`

**Files:**
- Modify: `app.py` (~30 lines)

This task has no automated tests — it's pure UI integration. Manual verification via Streamlit run.

- [ ] **Step 1: Update imports in `app.py`**

Replace the existing `from config import (...)` block (lines 17-27) with:

```python
from config import (
    BenchmarkParams,
    PALETTE,
    PortfolioParams,
    RealEstateParams,
    TODAY_LABEL,
)
from services.macro import get_macro_params
```

(Removed direct imports of `SELIC_RATE`, `IPCA_EXPECTED`, `CDI_RATE`, `USD_BRL` — those now come from `MacroParams`.)

- [ ] **Step 2: Replace `render_sidebar` signature and pass `MacroParams` in**

Modify `render_sidebar` declaration (line 97):

```python
def render_sidebar(macro) -> tuple[RealEstateParams, PortfolioParams, BenchmarkParams, int, bool]:
    """Build sidebar inputs and return parameter objects."""
    st.sidebar.title("⚙️ Parâmetros")
    st.sidebar.caption(f"Cenário macroeconômico: {TODAY_LABEL} — {macro.source_label}")
```

(`macro` parameter type is `MacroParams` — kept dynamic to avoid extra import in signature.)

- [ ] **Step 3: Update Selic slider to use `macro.selic` as default**

Find lines 142-145:

```python
    bench_params.selic_rate = st.sidebar.slider(
        "Taxa Selic (%)", 5.0, 20.0, SELIC_RATE * 100, 0.25) / 100
```

Replace with:

```python
    bench_params.selic_rate = st.sidebar.slider(
        "Taxa Selic (%)", 5.0, 20.0, macro.selic * 100, 0.25) / 100
```

- [ ] **Step 4: Add reload button at the bottom of the sidebar**

Add right before `return re_params, pf_params, bench_params, horizon, reinvest` (line 147):

```python
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Recarregar dados macro", use_container_width=True):
        get_macro_params.clear()
        st.rerun()
```

- [ ] **Step 5: Update `render_portfolio` reference to `SELIC_RATE`**

Find the `yields` dict in `render_portfolio` (around line 326-332). Replace `SELIC_RATE` references:

```python
    yields = {
        "Imóvel bruto": 0.0783,
        "Imóvel líquido": 0.0415,
        "FIIs (IFIX)": 0.118,
        "Ações BR": 0.09,
        "Tesouro Selic líq.": macro.selic * (1 - 0.175),
        "Carteira blended": pf_params.blended_yield(),
    }
    st.plotly_chart(
        yield_comparison_bars(yields, {"Selic": macro.selic, "IPCA": macro.ipca}),
        use_container_width=True,
    )
```

This requires passing `macro` to `render_portfolio`. Update its signature:

```python
def render_portfolio(pf_params: PortfolioParams, macro) -> None:
```

And update the call site in `main()` (was line 459):

```python
    with tabs[2]:
        render_portfolio(pf_params, macro)
```

- [ ] **Step 6: Update `main()` to fetch macro and pass it through**

Replace the body of `main()` (lines 435-472):

```python
def main() -> None:
    macro = get_macro_params()

    st.title("📊 Imóvel vs. Carteira Diversificada")
    st.caption(
        f"**Análise Buy & Hold** — Macro: Selic {macro.selic:.2%} | "
        f"IPCA esp. {macro.ipca:.2%} | CDI {macro.cdi:.2%} | "
        f"USD/BRL {macro.usd_brl:.2f} ({macro.source_label})"
    )

    if macro.is_stale:
        st.warning(
            "⚠️ Indicadores macro indisponíveis ao vivo. Usando referências de "
            f"{TODAY_LABEL}. Tente recarregar em alguns minutos."
        )

    re_params, pf_params, bench_params, horizon, reinvest = render_sidebar(macro)

    tabs = st.tabs([
        "📌 Visão Geral",
        "🏠 Imóvel",
        "📈 Carteira",
        "🎯 Sensibilidade",
        "💸 Tributação",
        "📥 Exportar",
    ])

    with tabs[0]:
        render_overview(re_params, pf_params, bench_params, horizon, reinvest)
    with tabs[1]:
        render_real_estate(re_params)
    with tabs[2]:
        render_portfolio(pf_params, macro)
    with tabs[3]:
        render_sensitivity(re_params, horizon)
    with tabs[4]:
        render_taxes(re_params, pf_params)
    with tabs[5]:
        render_export(re_params, pf_params, bench_params, horizon, reinvest)

    st.markdown("---")
    st.caption(
        "💡 Dashboard técnico para análise de cenário. "
        "Não constitui recomendação formal de investimento. "
        f"Premissas baseadas em {macro.source_label}."
    )
```

- [ ] **Step 7: Run tests to ensure no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 10 tests still passing (no models.py changes yet).

- [ ] **Step 8: Manually verify the app**

Stop the existing Streamlit server (if running). Then start fresh:

Run: `cd ~/Downloads/dashboard && .venv/bin/streamlit run app.py --server.headless true --server.port 8501`

Visit http://localhost:8501 and verify:
- Page header shows current Selic/IPCA/CDI/USD with label "BCB SGS (live)" (assuming network OK).
- No yellow warning banner.
- Sidebar caption ends with the source label.
- "🔄 Recarregar dados macro" button visible at the bottom of the sidebar.
- Selic slider default reflects live value.

To simulate fallback: temporarily edit `services/macro.py` to raise `BcbApiError("test")` unconditionally, restart Streamlit, verify yellow banner appears and label says "Fallback". Revert after test.

Stop the test server before continuing.

- [ ] **Step 9: Commit**

```bash
cd ~/Downloads/dashboard
git add app.py
git commit -m "Integrate live BCB macro data into app with stale-data banner"
```

---

## Task 5: Extend `simulate_portfolio` with Contributions

**Files:**
- Modify: `config.py` (extend `PortfolioParams`)
- Create: `tests/test_models.py`
- Modify: `models.py`

**Math reminder (from spec):** For each year `t ∈ [0, horizon-1]`, annual contribution at the start of year `t` is:
- `aporte_t = 12 × monthly_contribution × (1 + ipca) ** t` if indexed
- `aporte_t = 12 × monthly_contribution` otherwise

Each annual contribution then compounds for `(horizon - t)` more years at the appropriate rate.

- [ ] **Step 1: Extend `PortfolioParams` in `config.py`**

Add 2 fields to the `PortfolioParams` dataclass (after the `assets: list[AssetClass]` field, before the methods):

```python
    monthly_contribution: float = 0.0           # R$/month, in today's value
    contribution_inflation_indexed: bool = True
```

- [ ] **Step 2: Write the failing tests in `tests/test_models.py`**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_models.py -v`
Expected:
- `test_zero_contribution_*` and `test_simulate_*_unchanged` may pass already (regression tests).
- New behavior tests fail with `TypeError: simulate_portfolio() got an unexpected keyword argument 'ipca'`.

- [ ] **Step 4: Extend `simulate_portfolio` in `models.py`**

Replace the entire `simulate_portfolio` function (lines 75-112) with:

```python
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
    if reinvest_income:
        patrimony = params.capital * (1 + rate) ** years
    else:
        patrimony = params.capital * (1 + params.blended_capital_gain()) ** years

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/test_models.py -v`
Expected: 8 tests passing.

- [ ] **Step 6: Run all tests**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 18 tests total passing (7 + 3 + 8).

- [ ] **Step 7: Commit**

```bash
cd ~/Downloads/dashboard
git add config.py models.py tests/test_models.py
git commit -m "Add monthly contributions with optional IPCA indexing to portfolio simulation"
```

---

## Task 6: Aporte UI in Sidebar + Plumbing

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add aporte UI block to `render_sidebar`**

Insert new block right before `st.sidebar.markdown("---")` that precedes "📈 Carteira Diversificada" (around line 126):

```python
    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 Aporte mensal (Carteira)")
    monthly_contribution = st.sidebar.number_input(
        "Valor mensal (R$, em valor de hoje)",
        min_value=0.0, max_value=100_000.0, value=0.0, step=100.0,
        format="%.0f",
        help="Valor adicionado mensalmente à carteira. Imóvel não recebe aportes.",
    )
    indexed = st.sidebar.checkbox(
        "Indexar pelo IPCA",
        value=True,
        help="Quando ligado, o aporte cresce ano a ano pela inflação esperada (mantém poder de compra).",
    )
```

- [ ] **Step 2: Wire up the new params to `PortfolioParams`**

In `render_sidebar`, find where `pf_params` is created (around line 128):

```python
    pf_params = PortfolioParams(capital=capital)
```

Replace with:

```python
    pf_params = PortfolioParams(
        capital=capital,
        monthly_contribution=monthly_contribution,
        contribution_inflation_indexed=indexed,
    )
```

- [ ] **Step 3: Pass `macro.ipca` to `simulate_portfolio` in `render_overview`**

In `render_overview` (around line 159):

```python
    pf_result = simulate_portfolio(pf_params, horizon, reinvest)
```

Replace with:

```python
    pf_result = simulate_portfolio(pf_params, horizon, reinvest, ipca=macro.ipca)
```

This requires passing `macro` to `render_overview`. Update its signature:

```python
def render_overview(re_params: RealEstateParams,
                    pf_params: PortfolioParams,
                    bench_params: BenchmarkParams,
                    horizon: int,
                    reinvest: bool,
                    macro) -> None:
```

And update its call in `main()` (was line 455):

```python
    with tabs[0]:
        render_overview(re_params, pf_params, bench_params, horizon, reinvest, macro)
```

- [ ] **Step 4: Apply same change to `render_export`**

In `render_export`, find line `pf_result = simulate_portfolio(pf_params, horizon, reinvest)` and update similarly:

```python
    pf_result = simulate_portfolio(pf_params, horizon, reinvest, ipca=macro.ipca)
```

Update signature:

```python
def render_export(re_params: RealEstateParams,
                  pf_params: PortfolioParams,
                  bench_params: BenchmarkParams,
                  horizon: int,
                  reinvest: bool,
                  macro) -> None:
```

And the call in `main()`:

```python
    with tabs[5]:
        render_export(re_params, pf_params, bench_params, horizon, reinvest, macro)
```

- [ ] **Step 5: Run tests to ensure no regression**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: all 18 tests still passing.

- [ ] **Step 6: Manual verification**

Run: `cd ~/Downloads/dashboard && .venv/bin/streamlit run app.py --server.headless true --server.port 8501`

Visit http://localhost:8501 and verify:
- Sidebar shows "💰 Aporte mensal (Carteira)" section between Real Estate and Portfolio sections.
- Setting aporte to 0 → patrimony chart unchanged from previous task's snapshot.
- Setting aporte to R$ 2.000/mês with default 10-year horizon → portfolio's final patrimony in the "Visão Geral" KPI card should increase noticeably (~R$ 380k+ in addition to capital growth).
- Toggle "Indexar pelo IPCA" → final patrimony with checkbox ON should be slightly higher than OFF (over 10y at IPCA 4.8%).

Stop the test server.

- [ ] **Step 7: Update `README.md`**

Edit `README.md`. Replace the "Funcionalidades" section to add the new aporte feature, and add a new "Dados ao vivo" subsection after "Premissas macro":

In the Funcionalidades list, change:

```
- **Carteira**: alocação por classe (donut), yields comparados
```

To:

```
- **Carteira**: alocação por classe (donut), yields comparados, aporte mensal opcional indexado pelo IPCA
```

Add new section after "## Premissas macro (Abril/2026)":

```markdown
## Dados macro ao vivo

Os indicadores Selic, IPCA, CDI e USD/BRL são buscados ao vivo da API SGS do Banco Central, com cache de 24h. Em caso de falha (timeout, indisponibilidade), o app usa valores de referência hardcoded e exibe banner de aviso. Os sliders de macro permanecem editáveis para simulação de cenários.
```

- [ ] **Step 8: Commit**

```bash
cd ~/Downloads/dashboard
git add app.py README.md
git commit -m "Add aporte mensal UI and wire IPCA indexing through render layers"
```

---

## Task 7: Final Verification and Push

- [ ] **Step 1: Run full test suite**

Run: `cd ~/Downloads/dashboard && .venv/bin/pytest tests/ -v`
Expected: 18 tests passing.

- [ ] **Step 2: Smoke test the app end-to-end**

Run: `cd ~/Downloads/dashboard && .venv/bin/streamlit run app.py --server.headless true --server.port 8501`

Click through every tab and verify:
- Visão Geral: KPIs render, charts update with aporte changes.
- Imóvel: unchanged behavior.
- Carteira: yields_comparison chart still renders with `macro.selic` and `macro.ipca`.
- Sensibilidade: tornado chart works (uses real estate only — should be untouched).
- Tributação: unchanged.
- Exportar: CSV download works; if aporte > 0, portfolio patrimony column reflects contributions.

Stop the server.

- [ ] **Step 3: Push everything**

Run:

```bash
cd ~/Downloads/dashboard
git push
```

- [ ] **Step 4: Verify Streamlit Cloud auto-deploys**

Visit https://share.streamlit.io and look at the app's "Manage app" panel — should show new build picking up the latest commit. Wait ~2 min.

Then visit https://dashboard-investimentos.streamlit.app/ and:
- Confirm the page header shows live macro data ("BCB SGS (live)").
- Try the aporte input — patrimony chart should respond.
- Click the reload button — page reruns.

If build fails: check logs in Manage app panel; most common issue is `requirements.txt` typo.

---

## Self-Review Checklist (run after writing the plan)

**Spec coverage:**
- ✅ Aporte mensal com indexação IPCA (Task 5, 6)
- ✅ API BCB SGS com fallback (Task 2, 3)
- ✅ Cache 24h (Task 3)
- ✅ Banner stale (Task 4)
- ✅ Sliders editáveis ainda (Task 4 — defaults vêm de `MacroParams`, não força)
- ✅ Botão recarregar (Task 4)
- ✅ Tudo-ou-nada na falha (Task 2 test_fetch_macro_partial_failure_is_total_failure)
- ✅ Tests for bcb, macro, models (Tasks 2, 3, 5)
- ✅ requirements-dev.txt separado (Task 1)
- ✅ README atualizado (Task 6)

**Type consistency:**
- `MacroParams` defined in config.py (Task 3 step 1) — used in services/macro.py and app.py ✓
- `BcbReading` from data_sources/bcb.py — used in test_bcb.py and services/macro.py ✓
- `BcbApiError` from data_sources/bcb.py — caught in services/macro.py ✓
- `PortfolioParams.monthly_contribution` and `contribution_inflation_indexed` — added Task 5, used Task 5/6 ✓
- `simulate_portfolio(params, horizon, reinvest, ipca=)` — signature consistent across tests, model, app ✓

**Placeholder scan:** No TBD/TODO. All code blocks complete.
