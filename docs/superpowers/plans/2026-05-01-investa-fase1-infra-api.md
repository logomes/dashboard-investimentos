# Investa — Fase 1 (Infra & API) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the new `logomes/investa` monorepo, migrate the simulation engine from `dashboard-investimentos`, expose 6 FastAPI endpoints, set up CI, and deploy `api/` to Render free tier. End state: `https://investa-api.onrender.com/api/macro` returns the current Selic from BCB.

**Architecture:** Monorepo with `api/` (FastAPI + Pydantic) and `web/` (placeholder; populated in Fase 2+). The `api/core/` directory mirrors the engine from the Streamlit project (config, models, data_sources) without modifying the math. The Streamlit-coupled `services/macro.py` is replaced by a `cachetools.TTLCache`-based version. Pydantic schemas in `api/schemas/` define the input/output contract; converters bridge the `numpy.ndarray` results to JSON-serializable lists.

**Tech Stack:** Python 3.12, FastAPI 0.110+, uvicorn, Pydantic v2, numpy, pandas, requests, cachetools, pytest, pytest-mock, httpx (for FastAPI TestClient), Render (free tier).

**Spec:** `docs/superpowers/specs/2026-05-01-investa-migration-design.md` (umbrella spec — this plan covers Phase 1 only)

---

## File Structure (end state of this phase)

```
investa/                                 # new repo at /home/lucgomes/workspace/investa
├── api/
│   ├── main.py                          # FastAPI app + middleware + routers
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── macro.py
│   │   ├── portfolio.py
│   │   ├── simulation.py
│   │   └── fixed_income.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── inputs.py
│   │   └── outputs.py
│   ├── converters.py                    # numpy → list helpers
│   ├── core/                            # migrated intact from dashboard-investimentos
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── data_sources/
│   │   │   ├── __init__.py
│   │   │   └── bcb.py
│   │   └── services/
│   │       ├── __init__.py
│   │       └── macro.py                 # rewritten: streamlit → cachetools
│   ├── tests/                           # migrated from dashboard-investimentos
│   │   ├── conftest.py
│   │   ├── __init__.py
│   │   ├── test_bcb.py
│   │   ├── test_financing.py
│   │   ├── test_fixed_income.py
│   │   ├── test_macro.py
│   │   ├── test_models.py
│   │   ├── test_monte_carlo.py
│   │   ├── test_endpoint_health.py      # NEW
│   │   ├── test_endpoint_macro.py       # NEW
│   │   ├── test_endpoint_portfolio.py   # NEW
│   │   ├── test_endpoint_simulate.py    # NEW
│   │   ├── test_endpoint_monte_carlo.py # NEW
│   │   └── test_endpoint_fixed_income.py# NEW
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml
│   └── render.yaml                      # Render IaC
├── web/
│   └── README.md                        # placeholder; populated in Fase 2
├── docs/
│   └── design-handoff/                  # README + 8 screenshots from /tmp/investimentos-design
├── .github/
│   └── workflows/
│       └── api-ci.yml
├── .gitignore
├── README.md
└── docker-compose.yml                   # optional; out of scope for Fase 1
```

---

## Working Environment

- **Existing source:** `/home/lucgomes/workspace/dashboard-investimentos` (current Streamlit project, contains the engine to migrate)
- **New target:** `/home/lucgomes/workspace/investa` (will be cloned in Task 2)
- **Python:** Use Python 3.12 in the new venv (`python3.12 -m venv .venv`). The Streamlit project used 3.14 locally but Render only supports up to 3.12 stable.
- **GitHub auth:** SSH (`git@github.com:logomes/...`) is configured and works (key at `~/.ssh/id_ed25519`).
- **`gh` CLI:** Not installed. Repo creation happens via GitHub web UI (Task 1).

---

## Task 1: Create empty repo on GitHub (manual)

**Files:** none (manual step on github.com)

This task is a manual handoff to the user. The agent cannot create the repo without `gh` CLI installed.

- [ ] **Step 1.1: Ask user to create the repo**

Tell the user:

> Open https://github.com/new and create a new repo with these settings:
> - **Owner:** `logomes`
> - **Repository name:** `investa`
> - **Description:** `Análise patrimonial — Imóvel vs Carteira (v2 React/Next.js)`
> - **Visibility:** Public
> - **Initialize:** leave UNCHECKED (no README, no .gitignore, no license — we'll bootstrap locally)
>
> Confirm here when done.

- [ ] **Step 1.2: Wait for user confirmation**

Do NOT proceed to Task 2 until the user confirms the repo exists at `https://github.com/logomes/investa`.

---

## Task 2: Bootstrap monorepo skeleton

**Files:**
- Create: `/home/lucgomes/workspace/investa/.gitignore`
- Create: `/home/lucgomes/workspace/investa/README.md`
- Create: `/home/lucgomes/workspace/investa/api/README.md`
- Create: `/home/lucgomes/workspace/investa/web/README.md`

- [ ] **Step 2.1: Clone the empty repo**

```bash
cd /home/lucgomes/workspace
git clone git@github.com:logomes/investa.git
cd investa
```

Expected: empty directory with `.git/` only.

- [ ] **Step 2.2: Create monorepo skeleton**

```bash
mkdir -p api/routers api/schemas api/core/data_sources api/core/services api/tests
mkdir -p web docs/design-handoff .github/workflows
```

- [ ] **Step 2.3: Write `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/

# Node / Next.js (Fase 2+)
node_modules/
.next/
out/
*.log

# OS / IDE
.DS_Store
.vscode/
.idea/

# Env
.env
.env.local
*.env
```

- [ ] **Step 2.4: Write root `README.md`**

```markdown
# investa

Análise patrimonial — Imóvel vs Carteira diversificada (v2).

Migração do dashboard `dashboard-investimentos` (Streamlit) para uma stack web moderna.

## Estrutura

- `api/` — Backend FastAPI com a engine de simulação
- `web/` — Frontend Next.js 14 (App Router) — _populado a partir da Fase 2_
- `docs/design-handoff/` — Mock e tokens de design
- `.github/workflows/` — CI

## URLs de produção

- **API:** https://investa-api.onrender.com (deploy: Render)
- **Web:** https://investa.vercel.app (deploy: Vercel — após Fase 2)

## Desenvolvimento local

Backend (a partir desta fase):
```bash
cd api
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

Health check:
```bash
curl http://localhost:8000/api/health
```

## Testes

```bash
cd api
.venv/bin/pytest -v
```
```

- [ ] **Step 2.5: Write `api/README.md` and `web/README.md`**

`api/README.md`:
```markdown
# investa — API

FastAPI backend wrapping the simulation engine.

## Endpoints

- `GET /api/health`
- `GET /api/macro`
- `GET /api/portfolio/defaults`
- `POST /api/simulate`
- `POST /api/simulate/monte-carlo`
- `POST /api/fixed-income/simulate`

See [openapi.json](http://localhost:8000/openapi.json) when running locally for the full schema.

## Local dev

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

## Tests

```bash
.venv/bin/pytest -v
```
```

`web/README.md`:
```markdown
# investa — Web

Frontend Next.js 14 (App Router). Populated starting in Fase 2 of the migration.
```

- [ ] **Step 2.6: Initial commit and push**

```bash
git add .
git commit -m "$(cat <<'EOF'
chore: bootstrap monorepo skeleton

Sets up api/ + web/ + docs/ + .github/ directory structure plus
.gitignore and README files. No code yet — subsequent tasks populate
api/ with FastAPI; web/ stays as placeholder until Fase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin main
```

Expected output: branch `main` created and pushed.

---

## Task 3: api/ — FastAPI app + health endpoint (TDD)

**Files:**
- Create: `api/requirements.txt`
- Create: `api/requirements-dev.txt`
- Create: `api/pyproject.toml`
- Create: `api/main.py`
- Create: `api/routers/__init__.py`
- Create: `api/routers/health.py`
- Create: `api/tests/__init__.py`
- Create: `api/tests/conftest.py`
- Create: `api/tests/test_endpoint_health.py`

- [ ] **Step 3.1: Write `api/requirements.txt`**

```
fastapi>=0.110.0,<0.120.0
uvicorn[standard]>=0.27.0,<0.40.0
pydantic>=2.6.0,<3.0.0
numpy>=1.26.0
pandas>=2.1.0
requests>=2.31.0
cachetools>=5.3.0
python-dateutil>=2.8.0
```

- [ ] **Step 3.2: Write `api/requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0.0
pytest-mock>=3.12.0
httpx>=0.27.0
```

- [ ] **Step 3.3: Write `api/pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3.4: Set up venv and install deps**

```bash
cd /home/lucgomes/workspace/investa/api
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
```

Expected: clean install, no errors. If `python3.12` is not found, use `python3 -m venv .venv` (the system Python 3.14 also works for tests; Render is the only place that needs 3.12 specifically).

- [ ] **Step 3.5: Write `api/tests/conftest.py`**

```python
"""Pytest config: ensure project root (api/) is on sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 3.6: Write `api/tests/__init__.py`** (empty file)

```bash
: > tests/__init__.py
```

- [ ] **Step 3.7: Write the failing test for /api/health**

`api/tests/test_endpoint_health.py`:

```python
"""Smoke tests for /api/health."""
from fastapi.testclient import TestClient

from main import app


def test_health_returns_200_and_payload():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 3.8: Run test — should FAIL with import error**

```bash
.venv/bin/pytest tests/test_endpoint_health.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'main'` or similar.

- [ ] **Step 3.9: Write `api/routers/__init__.py`** (empty file)

```bash
: > routers/__init__.py
```

- [ ] **Step 3.10: Write `api/routers/health.py`**

```python
"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check used by Render and external monitors."""
    return {"status": "ok", "version": "1.0.0"}
```

- [ ] **Step 3.11: Write `api/main.py`**

```python
"""FastAPI application entry point."""
from fastapi import FastAPI

from routers import health

app = FastAPI(
    title="investa API",
    description="Análise patrimonial — Imóvel vs Carteira",
    version="1.0.0",
)

app.include_router(health.router)
```

- [ ] **Step 3.12: Run test — should PASS**

```bash
.venv/bin/pytest tests/test_endpoint_health.py -v
```

Expected: 1 passed.

- [ ] **Step 3.13: Commit**

```bash
git add api/
git commit -m "$(cat <<'EOF'
feat(api): bootstrap FastAPI app with health endpoint

Sets up api/ skeleton: requirements (FastAPI, pydantic, uvicorn,
cachetools, numpy/pandas/requests for the engine), pyproject.toml
with pytest config, conftest.py for sys.path, the FastAPI app entry
in main.py, and a /api/health endpoint covered by a TestClient test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Migrate `core/` from `dashboard-investimentos` (math intact)

**Files:**
- Create: `api/core/__init__.py`
- Create: `api/core/config.py` (copy from `dashboard-investimentos/config.py`)
- Create: `api/core/models.py` (copy from `dashboard-investimentos/models.py`)
- Create: `api/core/data_sources/__init__.py` (copy)
- Create: `api/core/data_sources/bcb.py` (copy from `dashboard-investimentos/data_sources/bcb.py`)
- Create: `api/core/services/__init__.py`
- Create: `api/core/services/macro.py` (rewritten — replaces Streamlit caching with cachetools)
- Create: `api/tests/test_models.py` (copy + adjust imports)
- Create: `api/tests/test_monte_carlo.py` (copy + adjust imports)
- Create: `api/tests/test_financing.py` (copy + adjust imports)
- Create: `api/tests/test_fixed_income.py` (copy + adjust imports)
- Create: `api/tests/test_bcb.py` (copy + adjust imports)
- Create: `api/tests/test_macro.py` (copy + adjust imports)

The migration **must not change any math**. Only fix the import paths and replace `services/macro.py` (the only file with a Streamlit dep).

- [ ] **Step 4.1: Copy clean files (no edits needed)**

```bash
cd /home/lucgomes/workspace/investa
cp /home/lucgomes/workspace/dashboard-investimentos/config.py api/core/config.py
cp /home/lucgomes/workspace/dashboard-investimentos/models.py api/core/models.py
cp /home/lucgomes/workspace/dashboard-investimentos/data_sources/__init__.py api/core/data_sources/__init__.py
cp /home/lucgomes/workspace/dashboard-investimentos/data_sources/bcb.py api/core/data_sources/bcb.py
: > api/core/__init__.py
: > api/core/services/__init__.py
```

- [ ] **Step 4.2: Adjust import path in `api/core/models.py`**

The original `models.py` imports from `data_sources.bcb` would still work because we kept the relative module name. But it imports from `config`, which now lives at `core/config.py`. We need to convert these to **relative** imports inside the `core` package.

Edit `api/core/models.py`. Find the existing `from config import (...)` block (around line 16) and change it to:

```python
from .config import (
    BenchmarkParams,
    FinancingParams,
    FixedIncomePosition,
    MacroParams,
    MonteCarloParams,
    PortfolioParams,
    RealEstateParams,
)
```

(Note the leading `.` — relative import within the `core` package.)

- [ ] **Step 4.3: Write `api/core/services/macro.py` from scratch (no streamlit)**

```python
"""Macro indicators service: cached fetch with fallback.

Server-side TTL cache (1h) replacing the Streamlit caching used in the
original Streamlit project. Falls back to MACRO_FALLBACK on any BCB error.
"""
from __future__ import annotations

from cachetools import TTLCache, cached

from ..config import MACRO_FALLBACK, MacroParams
from ..data_sources.bcb import BcbApiError, fetch_macro


_CACHE: TTLCache = TTLCache(maxsize=1, ttl=3600)  # 1 hour


@cached(_CACHE)
def get_macro_params() -> MacroParams:
    """Single fetch attempt cached for 1h; fall back on any BcbApiError."""
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


def clear_cache() -> None:
    """For tests — clear the TTL cache."""
    _CACHE.clear()
```

- [ ] **Step 4.4: Copy and adjust the test files**

For each test file, copy from the source and adjust the imports. The original tests import from `config` and `models` directly (top-level). We need to change those to `from core.config import ...` and `from core.models import ...`.

```bash
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_models.py api/tests/test_models.py
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_monte_carlo.py api/tests/test_monte_carlo.py
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_financing.py api/tests/test_financing.py
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_fixed_income.py api/tests/test_fixed_income.py
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_bcb.py api/tests/test_bcb.py
cp /home/lucgomes/workspace/dashboard-investimentos/tests/test_macro.py api/tests/test_macro.py
```

Now batch-replace imports. Use sed for speed:

```bash
cd api/tests
sed -i 's/^from config import/from core.config import/g' test_models.py test_monte_carlo.py test_financing.py test_fixed_income.py
sed -i 's/^from models import/from core.models import/g' test_models.py test_monte_carlo.py test_financing.py test_fixed_income.py
sed -i 's/^from data_sources.bcb import/from core.data_sources.bcb import/g' test_bcb.py
sed -i 's/^from services.macro import/from core.services.macro import/g' test_macro.py
sed -i 's/^from config import/from core.config import/g' test_macro.py
```

Then look for any inline imports inside test bodies (the `simulate_fixed_income` test uses `from models import simulate_fixed_income`):

```bash
sed -i 's/from models import/from core.models import/g' test_fixed_income.py
```

- [ ] **Step 4.5: Run all migrated tests**

```bash
cd /home/lucgomes/workspace/investa/api
.venv/bin/pytest tests/ -v --ignore=tests/test_endpoint_health.py
```

Expected: roughly the same counts as the source project — 23 tests in `test_fixed_income.py` plus the existing `test_models.py`/`test_monte_carlo.py`/`test_financing.py` tests all pass. `test_bcb.py` and `test_macro.py` use `pytest-mock` (which we now have installed), so they should also pass — no skipped tests.

If any test file fails with `ModuleNotFoundError`, re-check the sed substitutions above.

- [ ] **Step 4.6: Verify the `services/macro.py` rewrite works end-to-end**

```bash
.venv/bin/python -c "
from core.services.macro import get_macro_params
m = get_macro_params()
print(f'selic={m.selic}, ipca={m.ipca}, cdi={m.cdi}, source={m.source_label}, stale={m.is_stale}')
"
```

Expected: prints actual numbers (or fallback values if BCB is down). Must NOT raise an `ImportError` for `streamlit`.

- [ ] **Step 4.7: Commit**

```bash
git add api/core/ api/tests/
git commit -m "$(cat <<'EOF'
feat(api): migrate simulation engine from dashboard-investimentos

Brings config, models, data_sources, and tests into api/core/ with
adjusted relative imports. The math is unchanged — same dataclasses,
same simulation functions, same test cases.

The only rewrite is api/core/services/macro.py: replaced Streamlit's
@st.cache_data with cachetools.TTLCache(ttl=3600) so the engine no
longer depends on Streamlit. Falls back to MACRO_FALLBACK on any
BcbApiError, matching the original behavior.

All 23+ existing tests pass; pytest-mock now available so test_bcb
and test_macro are no longer skipped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Pydantic input schemas

**Files:**
- Create: `api/schemas/__init__.py`
- Create: `api/schemas/inputs.py`
- Create: `api/tests/test_schemas_inputs.py`

The input schemas mirror the user-controlled parameters from the Streamlit sidebar. Field naming uses **camelCase** (matching the TS frontend convention) with Pydantic aliases mapping to the Python `snake_case` underlying.

- [ ] **Step 5.1: Write the failing test**

`api/tests/test_schemas_inputs.py`:

```python
"""Tests for Pydantic input schemas (camelCase API contract)."""
import pytest
from pydantic import ValidationError

from schemas.inputs import (
    BenchmarkInput,
    FinancingInput,
    FixedIncomePositionInput,
    FixedIncomeSimulateInput,
    MonteCarloInput,
    PortfolioAssetInput,
    PortfolioInput,
    RealEstateInput,
    SimulateInput,
    SimulateMonteCarloInput,
)


def test_simulate_input_accepts_camelcase_payload():
    payload = {
        "capital": 230_000.0,
        "horizon": 10,
        "reinvest": True,
        "realEstate": {
            "propertyValue": 230_000.0,
            "monthlyRent": 1_500.0,
            "annualAppreciation": 0.055,
            "iptuRate": 0.010,
            "vacancyMonthsPerYear": 1.0,
            "managementFeePct": 0.10,
            "maintenanceAnnual": 900.0,
            "insuranceAnnual": 600.0,
            "incomeTaxBracket": 0.075,
            "acquisitionCostPct": 0.05,
            "appreciationVolatility": 0.10,
            "financing": None,
        },
        "portfolio": {
            "capital": 230_000.0,
            "monthlyContribution": 0.0,
            "contributionInflationIndexed": True,
            "assets": [
                {"name": "FIIs", "weight": 1.0, "expectedYield": 0.10,
                 "capitalGain": 0.0, "taxRate": 0.0, "note": "", "volatility": 0.15},
            ],
        },
        "benchmark": {"selicRate": 0.1475, "taxRate": 0.175},
    }
    parsed = SimulateInput.model_validate(payload)
    assert parsed.capital == 230_000.0
    assert parsed.real_estate.monthly_rent == 1_500.0
    assert parsed.portfolio.assets[0].expected_yield == 0.10
    assert parsed.benchmark.selic_rate == 0.1475


def test_simulate_input_rejects_horizon_out_of_range():
    payload = {
        "capital": 100_000.0, "horizon": 50, "reinvest": True,
        "realEstate": {"propertyValue": 100_000, "monthlyRent": 0,
                       "annualAppreciation": 0, "iptuRate": 0,
                       "vacancyMonthsPerYear": 0, "managementFeePct": 0,
                       "maintenanceAnnual": 0, "insuranceAnnual": 0,
                       "incomeTaxBracket": 0, "acquisitionCostPct": 0,
                       "appreciationVolatility": 0, "financing": None},
        "portfolio": {"capital": 100_000, "monthlyContribution": 0,
                      "contributionInflationIndexed": True, "assets": []},
        "benchmark": {"selicRate": 0.10, "taxRate": 0.15},
    }
    with pytest.raises(ValidationError, match="horizon"):
        SimulateInput.model_validate(payload)


def test_fixed_income_position_input_parses_iso_dates():
    payload = {
        "name": "LCI Banco X",
        "initialAmount": 30_000.0,
        "purchaseDate": "2025-03-15",
        "indexer": "cdi",
        "rate": 0.95,
        "maturityDate": "2027-03-15",
        "isTaxExempt": True,
    }
    parsed = FixedIncomePositionInput.model_validate(payload)
    assert parsed.indexer == "cdi"
    assert str(parsed.purchase_date) == "2025-03-15"
    assert parsed.is_tax_exempt is True


def test_fixed_income_position_input_rejects_invalid_indexer():
    with pytest.raises(ValidationError, match="indexer"):
        FixedIncomePositionInput.model_validate({
            "name": "X", "initialAmount": 1000, "purchaseDate": "2025-01-01",
            "indexer": "bitcoin", "rate": 0.1,
        })
```

- [ ] **Step 5.2: Run test — should FAIL with import error**

```bash
.venv/bin/pytest tests/test_schemas_inputs.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'schemas'`.

- [ ] **Step 5.3: Write `api/schemas/__init__.py`** (empty)

```bash
: > schemas/__init__.py
```

- [ ] **Step 5.4: Write `api/schemas/inputs.py`**

```python
"""Pydantic input schemas — the public API contract from the frontend.

Naming convention: API uses camelCase (matching the TypeScript frontend);
internally fields use snake_case via `Field(alias=...)`. Validation rules
mirror the spec's "Validações" tables.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _camel(s: str) -> str:
    """Convert snake_case to camelCase for API field aliases."""
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class _CamelModel(BaseModel):
    """Base model: accept and emit camelCase, populate by name allowed."""
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
    )


class FinancingInput(_CamelModel):
    term_years: int = Field(ge=1, le=40)
    annual_rate: float = Field(ge=0.0, le=1.0)
    entry_pct: float = Field(ge=0.0, le=1.0)
    system: Literal["SAC", "Price"] = "SAC"
    monthly_insurance_rate: float = Field(ge=0.0, le=0.01, default=0.0005)


class RealEstateInput(_CamelModel):
    property_value: float = Field(gt=0)
    monthly_rent: float = Field(ge=0)
    annual_appreciation: float = Field(ge=-0.5, le=1.0)
    iptu_rate: float = Field(ge=0, le=0.5)
    vacancy_months_per_year: float = Field(ge=0, le=12)
    management_fee_pct: float = Field(ge=0, le=1.0)
    maintenance_annual: float = Field(ge=0)
    insurance_annual: float = Field(ge=0)
    income_tax_bracket: float = Field(ge=0, le=0.5)
    acquisition_cost_pct: float = Field(ge=0, le=0.5)
    appreciation_volatility: float = Field(ge=0, le=1.0)
    financing: FinancingInput | None = None


class PortfolioAssetInput(_CamelModel):
    name: str = Field(min_length=1)
    weight: float = Field(ge=0, le=1.0)
    expected_yield: float = Field(ge=-1.0, le=1.0)
    capital_gain: float = Field(default=0.0)
    tax_rate: float = Field(default=0.0, ge=0, le=1.0)
    note: str = ""
    volatility: float = Field(default=0.15, ge=0, le=1.0)


class PortfolioInput(_CamelModel):
    capital: float = Field(gt=0)
    monthly_contribution: float = Field(default=0.0, ge=0)
    contribution_inflation_indexed: bool = True
    assets: list[PortfolioAssetInput]


class BenchmarkInput(_CamelModel):
    selic_rate: float = Field(ge=0, le=1.0)
    tax_rate: float = Field(default=0.175, ge=0, le=1.0)


class MonteCarloInput(_CamelModel):
    n_trajectories: int = Field(default=10_000, ge=100, le=50_000)
    seed: int | None = None
    target_patrimony: float = Field(default=0.0, ge=0)


class SimulateInput(_CamelModel):
    capital: float = Field(gt=0)
    horizon: int = Field(ge=1, le=30)
    reinvest: bool = True
    real_estate: RealEstateInput
    portfolio: PortfolioInput
    benchmark: BenchmarkInput


class SimulateMonteCarloInput(_CamelModel):
    horizon: int = Field(ge=1, le=30)
    real_estate: RealEstateInput
    portfolio: PortfolioInput
    mc: MonteCarloInput


class FixedIncomePositionInput(_CamelModel):
    name: str = Field(min_length=1)
    initial_amount: float = Field(gt=0)
    purchase_date: date
    indexer: Literal["prefixado", "cdi", "selic", "ipca"]
    rate: float
    maturity_date: date | None = None
    is_tax_exempt: bool = False

    @field_validator("maturity_date")
    @classmethod
    def maturity_after_purchase(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        purchase = info.data.get("purchase_date")
        if purchase is not None and v <= purchase:
            raise ValueError("maturity_date must be after purchase_date")
        return v


class FixedIncomeSimulateInput(_CamelModel):
    positions: list[FixedIncomePositionInput]
    horizon_years: int = Field(ge=1, le=50)
    start_date: date | None = None
```

- [ ] **Step 5.5: Run test — should PASS**

```bash
.venv/bin/pytest tests/test_schemas_inputs.py -v
```

Expected: 4 passed.

- [ ] **Step 5.6: Commit**

```bash
git add api/schemas/__init__.py api/schemas/inputs.py api/tests/test_schemas_inputs.py
git commit -m "$(cat <<'EOF'
feat(api): pydantic input schemas with camelCase API contract

Adds schemas/inputs.py mirroring the user-controlled simulation params
(realEstate, portfolio, benchmark, MC). Uses camelCase aliases matching
the TS frontend convention; internally snake_case for Python idiom.
Validators enforce ranges (horizon 1-30, weights 0-1, dates) and
type-narrow indexer to a Literal. 4 tests cover happy path + 3 reject
paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Pydantic output schemas + numpy converters

**Files:**
- Create: `api/schemas/outputs.py`
- Create: `api/converters.py`
- Create: `api/tests/test_converters.py`

- [ ] **Step 6.1: Write `api/schemas/outputs.py`**

```python
"""Pydantic output schemas — what the API returns. camelCase aliases.

numpy arrays in core/models.py results are converted to list[float] via
api/converters.py before being passed to these models.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


def _camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


class MacroOut(_CamelModel):
    selic: float
    cdi: float
    ipca: float
    usd_brl: float
    is_stale: bool
    source_label: str


class SimulationResultOut(_CamelModel):
    """Yearly arrays for a single scenario (RE / Portfolio / Benchmark)."""
    label: str
    color: str
    years: list[float]
    patrimony: list[float]
    annual_income: list[float]
    cumulative_income: list[float]
    debt_balance: list[float] | None = None
    internal_portfolio: list[float] | None = None


class SensitivityRowOut(_CamelModel):
    parameter: str
    pessimistic: float
    optimistic: float


class TaxComparisonRowOut(_CamelModel):
    scenario: str
    gross_income: float
    annual_tax: float
    net_income: float
    effective_tax_burden: float


class SimulateOut(_CamelModel):
    """Full deterministic-simulation output."""
    real_estate: SimulationResultOut
    portfolio: SimulationResultOut
    benchmark: SimulationResultOut
    sensitivity: list[SensitivityRowOut]
    tax_comparison: list[TaxComparisonRowOut]


class MonteCarloResultOut(_CamelModel):
    label: str
    color: str
    p10: list[float]
    p50: list[float]
    p90: list[float]
    final_distribution: list[float]
    max_drawdowns: list[float]


class SimulateMonteCarloOut(_CamelModel):
    real_estate: MonteCarloResultOut
    portfolio: MonteCarloResultOut


class FixedIncomeProjectionOut(_CamelModel):
    name: str
    color: str
    indexer: Literal["prefixado", "cdi", "selic", "ipca"]
    years: list[int]
    gross_values: list[float]
    net_values: list[float]
    matured: list[bool]


class FixedIncomePortfolioOut(_CamelModel):
    projections: list[FixedIncomeProjectionOut]
    total_gross: list[float]
    total_net: list[float]
    total_initial: float


class PortfolioDefaultsOut(_CamelModel):
    real_estate: dict
    portfolio: dict
    benchmark: dict


class HealthOut(_CamelModel):
    status: str
    version: str


class ApiError(_CamelModel):
    error: str
    message: str
    details: dict | None = None
```

- [ ] **Step 6.2: Write `api/converters.py`**

```python
"""Convert core dataclasses (with numpy arrays) to Pydantic DTOs.

Centralizes the ndarray → list[float] coercion so endpoints stay clean.
"""
from __future__ import annotations

import numpy as np

from core.models import (
    FixedIncomePortfolio,
    FixedIncomeProjection,
    MonteCarloResult,
    SimulationResult,
)
from schemas.outputs import (
    FixedIncomePortfolioOut,
    FixedIncomeProjectionOut,
    MonteCarloResultOut,
    SimulationResultOut,
)


def _to_list(arr: np.ndarray | None) -> list[float] | None:
    """Convert ndarray to a JSON-friendly list of floats. None passes through."""
    if arr is None:
        return None
    return [float(x) for x in arr]


def simulation_result_to_dto(r: SimulationResult) -> SimulationResultOut:
    return SimulationResultOut(
        label=r.label,
        color=r.color,
        years=_to_list(r.years),
        patrimony=_to_list(r.patrimony),
        annual_income=_to_list(r.annual_income),
        cumulative_income=_to_list(r.cumulative_income),
        debt_balance=_to_list(r.debt_balance),
        internal_portfolio=_to_list(r.internal_portfolio),
    )


def monte_carlo_result_to_dto(r: MonteCarloResult) -> MonteCarloResultOut:
    return MonteCarloResultOut(
        label=r.label,
        color=r.color,
        p10=_to_list(r.percentiles["p10"]),
        p50=_to_list(r.percentiles["p50"]),
        p90=_to_list(r.percentiles["p90"]),
        final_distribution=_to_list(r.final_distribution),
        max_drawdowns=_to_list(r.max_drawdowns),
    )


def fixed_income_projection_to_dto(p: FixedIncomeProjection) -> FixedIncomeProjectionOut:
    return FixedIncomeProjectionOut(
        name=p.position.name,
        color=p.position.color,
        indexer=p.position.indexer,
        years=[int(x) for x in p.years],
        gross_values=_to_list(p.gross_values),
        net_values=_to_list(p.net_values),
        matured=[bool(x) for x in p.matured],
    )


def fixed_income_portfolio_to_dto(p: FixedIncomePortfolio) -> FixedIncomePortfolioOut:
    return FixedIncomePortfolioOut(
        projections=[fixed_income_projection_to_dto(proj) for proj in p.projections],
        total_gross=_to_list(p.total_gross),
        total_net=_to_list(p.total_net),
        total_initial=p.total_initial,
    )
```

- [ ] **Step 6.3: Write `api/tests/test_converters.py`**

```python
"""Tests for converters (ndarray → list)."""
from datetime import date

import numpy as np

from core.config import FixedIncomePosition, MacroParams
from core.models import simulate_fixed_income
from converters import (
    fixed_income_portfolio_to_dto,
    fixed_income_projection_to_dto,
    simulation_result_to_dto,
)


def test_simulation_result_dto_converts_arrays_to_lists():
    """Build a SimulationResult by hand and convert."""
    from core.models import SimulationResult
    r = SimulationResult(
        years=np.arange(4),
        patrimony=np.array([1000.0, 1100.0, 1210.0, 1331.0]),
        annual_income=np.array([0.0, 100.0, 110.0, 121.0]),
        cumulative_income=np.array([0.0, 100.0, 210.0, 331.0]),
        label="Test",
        color="#FF0000",
    )
    dto = simulation_result_to_dto(r)
    assert dto.label == "Test"
    assert dto.color == "#FF0000"
    assert dto.years == [0.0, 1.0, 2.0, 3.0]
    assert dto.patrimony == [1000.0, 1100.0, 1210.0, 1331.0]
    assert dto.debt_balance is None  # None passes through


def test_fixed_income_dto_includes_position_metadata():
    macro = MacroParams(selic=0.1475, ipca=0.048, cdi=0.1465, usd_brl=5.30,
                        is_stale=False, source_label="test")
    pos = FixedIncomePosition(
        name="LCI X", initial_amount=1000, purchase_date=date(2025, 1, 1),
        indexer="cdi", rate=0.95, is_tax_exempt=True, color="#00B894",
    )
    portfolio = simulate_fixed_income([pos], macro, horizon_years=2,
                                      start_date=date(2025, 1, 1))
    dto = fixed_income_portfolio_to_dto(portfolio)
    assert len(dto.projections) == 1
    assert dto.projections[0].name == "LCI X"
    assert dto.projections[0].color == "#00B894"
    assert dto.projections[0].indexer == "cdi"
    assert dto.total_initial == 1000.0
    assert len(dto.total_gross) == 3  # horizon + 1
```

- [ ] **Step 6.4: Run tests — should PASS (after writing files in 6.1 and 6.2)**

```bash
.venv/bin/pytest tests/test_converters.py -v
```

Expected: 2 passed.

- [ ] **Step 6.5: Commit**

```bash
git add api/schemas/outputs.py api/converters.py api/tests/test_converters.py
git commit -m "$(cat <<'EOF'
feat(api): pydantic output schemas + ndarray-to-list converters

Adds schemas/outputs.py (camelCase response DTOs for all 6 endpoints)
plus converters.py centralizing the conversion from numpy ndarrays in
core/models results to JSON-friendly list[float]. Two tests cover the
deterministic SimulationResult and the FixedIncomePortfolio paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: GET /api/macro endpoint with TTL cache

**Files:**
- Create: `api/routers/macro.py`
- Modify: `api/main.py` (register router)
- Create: `api/tests/test_endpoint_macro.py`

- [ ] **Step 7.1: Write the failing test**

`api/tests/test_endpoint_macro.py`:

```python
"""Tests for /api/macro."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.config import MACRO_FALLBACK
from core.services.macro import clear_cache
from main import app


def setup_function(_func):
    """Reset cache before each test."""
    clear_cache()


def test_macro_returns_live_payload_when_bcb_succeeds(mocker):
    fake = MACRO_FALLBACK
    mocker.patch("routers.macro.get_macro_params", return_value=fake)
    client = TestClient(app)
    response = client.get("/api/macro")
    assert response.status_code == 200
    body = response.json()
    assert body["selic"] == fake.selic
    assert body["cdi"] == fake.cdi
    assert body["ipca"] == fake.ipca
    assert "isStale" in body  # camelCase
    assert "sourceLabel" in body


def test_macro_returns_fallback_payload_when_bcb_fails():
    """If BcbApiError is raised, get_macro_params returns MACRO_FALLBACK with isStale=True."""
    from core.data_sources.bcb import BcbApiError
    with patch("core.services.macro.fetch_macro", side_effect=BcbApiError("down")):
        client = TestClient(app)
        response = client.get("/api/macro")
        assert response.status_code == 200
        body = response.json()
        assert body["isStale"] is True
        assert "Fallback" in body["sourceLabel"]
```

- [ ] **Step 7.2: Run test — should FAIL with import error**

```bash
.venv/bin/pytest tests/test_endpoint_macro.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'routers.macro'`.

- [ ] **Step 7.3: Write `api/routers/macro.py`**

```python
"""GET /api/macro — current Brazilian macro indicators."""
from fastapi import APIRouter

from core.services.macro import get_macro_params
from schemas.outputs import MacroOut

router = APIRouter()


@router.get("/api/macro", response_model=MacroOut)
def macro() -> MacroOut:
    """Return Selic, CDI, IPCA, USD/BRL — live from BCB or cached fallback.

    The underlying core.services.macro.get_macro_params is itself cached
    via cachetools.TTLCache(ttl=3600), so this endpoint is essentially free.
    """
    m = get_macro_params()
    return MacroOut(
        selic=m.selic,
        cdi=m.cdi,
        ipca=m.ipca,
        usd_brl=m.usd_brl,
        is_stale=m.is_stale,
        source_label=m.source_label,
    )
```

- [ ] **Step 7.4: Register the router in `api/main.py`**

Replace the existing main.py contents with:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI

from routers import health, macro

app = FastAPI(
    title="investa API",
    description="Análise patrimonial — Imóvel vs Carteira",
    version="1.0.0",
)

app.include_router(health.router)
app.include_router(macro.router)
```

- [ ] **Step 7.5: Run tests — should PASS**

```bash
.venv/bin/pytest tests/test_endpoint_macro.py tests/test_endpoint_health.py -v
```

Expected: 3 passed (1 health + 2 macro).

- [ ] **Step 7.6: Commit**

```bash
git add api/routers/macro.py api/main.py api/tests/test_endpoint_macro.py
git commit -m "$(cat <<'EOF'
feat(api): GET /api/macro with TTL cache + BCB fallback

Wraps core.services.macro.get_macro_params (already cached for 1h via
cachetools) in a FastAPI endpoint. Returns camelCase MacroOut. Two
tests cover the happy path (live BCB) and the fallback path (BcbApiError
returns is_stale=True).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: GET /api/portfolio/defaults endpoint

**Files:**
- Create: `api/routers/portfolio.py`
- Modify: `api/main.py`
- Create: `api/tests/test_endpoint_portfolio.py`

- [ ] **Step 8.1: Write the failing test**

`api/tests/test_endpoint_portfolio.py`:

```python
"""Tests for /api/portfolio/defaults."""
from fastapi.testclient import TestClient

from main import app


def test_defaults_includes_all_three_param_groups():
    client = TestClient(app)
    response = client.get("/api/portfolio/defaults")
    assert response.status_code == 200
    body = response.json()
    assert "realEstate" in body
    assert "portfolio" in body
    assert "benchmark" in body


def test_defaults_real_estate_has_expected_fields():
    client = TestClient(app)
    body = client.get("/api/portfolio/defaults").json()
    re = body["realEstate"]
    assert "propertyValue" in re
    assert "monthlyRent" in re
    assert "annualAppreciation" in re
    assert isinstance(re["propertyValue"], (int, float))
    assert re["propertyValue"] > 0


def test_defaults_portfolio_assets_sum_to_one():
    client = TestClient(app)
    body = client.get("/api/portfolio/defaults").json()
    weights = [a["weight"] for a in body["portfolio"]["assets"]]
    assert abs(sum(weights) - 1.0) < 1e-6
```

- [ ] **Step 8.2: Run test — FAIL**

```bash
.venv/bin/pytest tests/test_endpoint_portfolio.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'routers.portfolio'`.

- [ ] **Step 8.3: Write `api/routers/portfolio.py`**

```python
"""GET /api/portfolio/defaults — default scenario for first form load."""
from dataclasses import asdict

from fastapi import APIRouter

from core.config import (
    BenchmarkParams,
    PortfolioParams,
    RealEstateParams,
)

router = APIRouter()


def _camel_dict(d: dict) -> dict:
    """Convert a snake_case dict to camelCase recursively."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        parts = k.split("_")
        camel_key = parts[0] + "".join(p.title() for p in parts[1:])
        if isinstance(v, dict):
            out[camel_key] = _camel_dict(v)
        elif isinstance(v, list):
            out[camel_key] = [_camel_dict(x) if isinstance(x, dict) else x for x in v]
        else:
            out[camel_key] = v
    return out


@router.get("/api/portfolio/defaults")
def defaults() -> dict:
    """Return the default scenario (RealEstate + Portfolio + Benchmark) for first load."""
    re_defaults = asdict(RealEstateParams())
    pf_defaults = asdict(PortfolioParams())
    bench_defaults = asdict(BenchmarkParams())
    return {
        "realEstate": _camel_dict(re_defaults),
        "portfolio": _camel_dict(pf_defaults),
        "benchmark": _camel_dict(bench_defaults),
    }
```

- [ ] **Step 8.4: Register the router in `api/main.py`**

Add to the imports and `include_router` calls:

```python
from routers import health, macro, portfolio

# ...

app.include_router(portfolio.router)
```

- [ ] **Step 8.5: Run tests — PASS**

```bash
.venv/bin/pytest tests/test_endpoint_portfolio.py -v
```

Expected: 3 passed.

- [ ] **Step 8.6: Commit**

```bash
git add api/routers/portfolio.py api/main.py api/tests/test_endpoint_portfolio.py
git commit -m "$(cat <<'EOF'
feat(api): GET /api/portfolio/defaults

Returns the default scenario (RealEstateParams + PortfolioParams +
BenchmarkParams) with snake_case → camelCase keys for the TS frontend.
Three tests cover structure, RE shape, and that portfolio weights
sum to 1.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: POST /api/simulate endpoint

**Files:**
- Create: `api/routers/simulation.py`
- Modify: `api/main.py`
- Create: `api/tests/test_endpoint_simulate.py`

- [ ] **Step 9.1: Write the failing test**

`api/tests/test_endpoint_simulate.py`:

```python
"""Tests for POST /api/simulate."""
from fastapi.testclient import TestClient

from main import app


def _default_payload() -> dict:
    """Minimal valid payload mirroring the default scenario."""
    return {
        "capital": 230_000.0,
        "horizon": 10,
        "reinvest": True,
        "realEstate": {
            "propertyValue": 230_000.0,
            "monthlyRent": 1_500.0,
            "annualAppreciation": 0.055,
            "iptuRate": 0.010,
            "vacancyMonthsPerYear": 1.0,
            "managementFeePct": 0.10,
            "maintenanceAnnual": 900.0,
            "insuranceAnnual": 600.0,
            "incomeTaxBracket": 0.075,
            "acquisitionCostPct": 0.05,
            "appreciationVolatility": 0.10,
            "financing": None,
        },
        "portfolio": {
            "capital": 230_000.0,
            "monthlyContribution": 0.0,
            "contributionInflationIndexed": True,
            "assets": [
                {"name": "FIIs Papel", "weight": 0.25, "expectedYield": 0.130,
                 "capitalGain": 0.0, "taxRate": 0.0, "note": "", "volatility": 0.14},
                {"name": "FIIs Tijolo", "weight": 0.25, "expectedYield": 0.090,
                 "capitalGain": 0.02, "taxRate": 0.0, "note": "", "volatility": 0.16},
                {"name": "Ações BR", "weight": 0.20, "expectedYield": 0.090,
                 "capitalGain": 0.03, "taxRate": 0.0, "note": "", "volatility": 0.27},
                {"name": "Aristocrats", "weight": 0.15, "expectedYield": 0.040,
                 "capitalGain": 0.06, "taxRate": 0.30, "note": "", "volatility": 0.18},
                {"name": "Tesouro IPCA+", "weight": 0.15, "expectedYield": 0.115,
                 "capitalGain": 0.0, "taxRate": 0.10, "note": "", "volatility": 0.05},
            ],
        },
        "benchmark": {"selicRate": 0.1475, "taxRate": 0.175},
    }


def test_simulate_returns_full_output_shape():
    client = TestClient(app)
    response = client.post("/api/simulate", json=_default_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert "realEstate" in body
    assert "portfolio" in body
    assert "benchmark" in body
    assert "sensitivity" in body
    assert "taxComparison" in body


def test_simulate_yearly_arrays_have_horizon_plus_one_points():
    payload = _default_payload()
    payload["horizon"] = 5
    client = TestClient(app)
    body = client.post("/api/simulate", json=payload).json()
    assert len(body["realEstate"]["years"]) == 6  # 0..5 inclusive
    assert len(body["realEstate"]["patrimony"]) == 6
    assert len(body["portfolio"]["patrimony"]) == 6


def test_simulate_rejects_invalid_horizon():
    payload = _default_payload()
    payload["horizon"] = 100  # > 30
    client = TestClient(app)
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 422  # Pydantic validation error
```

- [ ] **Step 9.2: Run test — FAIL**

```bash
.venv/bin/pytest tests/test_endpoint_simulate.py -v
```

Expected: FAIL.

- [ ] **Step 9.3: Write `api/routers/simulation.py`**

> **Function name reference (verified against `dashboard-investimentos/models.py`):**
> - `simulate_real_estate(params, horizon_years, reinvest_income=True, capital_initial=None, internal_portfolio_rate=0.0)` — no `ipca` arg
> - `simulate_portfolio(params, horizon_years, reinvest_income=True, ipca=0.0)` — has `ipca` for inflation-indexed contributions
> - `simulate_benchmark(params, horizon_years)` — only two args
> - `sensitivity_real_estate(base_params, horizon_years, deltas)` — note name has `_real_estate` suffix; takes a `deltas: dict[str, tuple[float, float]]`
> - `annual_tax_comparison(real_estate, portfolio)`

```python
"""POST /api/simulate — deterministic simulation across all scenarios."""
from fastapi import APIRouter

from converters import simulation_result_to_dto
from core.config import (
    AssetClass,
    BenchmarkParams,
    FinancingParams,
    PortfolioParams,
    RealEstateParams,
)
from core.models import (
    annual_tax_comparison,
    sensitivity_real_estate,
    simulate_benchmark,
    simulate_portfolio,
    simulate_real_estate,
)
from core.services.macro import get_macro_params
from schemas.inputs import SimulateInput
from schemas.outputs import SensitivityRowOut, SimulateOut, TaxComparisonRowOut

router = APIRouter()


def _to_real_estate_params(input_re) -> RealEstateParams:
    """Map RealEstateInput Pydantic model to RealEstateParams dataclass."""
    financing = None
    if input_re.financing is not None:
        f = input_re.financing
        financing = FinancingParams(
            term_years=f.term_years,
            annual_rate=f.annual_rate,
            entry_pct=f.entry_pct,
            system=f.system,
            monthly_insurance_rate=f.monthly_insurance_rate,
        )
    return RealEstateParams(
        property_value=input_re.property_value,
        monthly_rent=input_re.monthly_rent,
        annual_appreciation=input_re.annual_appreciation,
        iptu_rate=input_re.iptu_rate,
        vacancy_months_per_year=input_re.vacancy_months_per_year,
        management_fee_pct=input_re.management_fee_pct,
        maintenance_annual=input_re.maintenance_annual,
        insurance_annual=input_re.insurance_annual,
        income_tax_bracket=input_re.income_tax_bracket,
        acquisition_cost_pct=input_re.acquisition_cost_pct,
        appreciation_volatility=input_re.appreciation_volatility,
        financing=financing,
    )


def _to_portfolio_params(input_pf) -> PortfolioParams:
    return PortfolioParams(
        capital=input_pf.capital,
        monthly_contribution=input_pf.monthly_contribution,
        contribution_inflation_indexed=input_pf.contribution_inflation_indexed,
        assets=[
            AssetClass(
                name=a.name, weight=a.weight, expected_yield=a.expected_yield,
                capital_gain=a.capital_gain, tax_rate=a.tax_rate, note=a.note,
                volatility=a.volatility,
            )
            for a in input_pf.assets
        ],
    )


def _to_benchmark_params(input_bench) -> BenchmarkParams:
    return BenchmarkParams(
        selic_rate=input_bench.selic_rate,
        tax_rate=input_bench.tax_rate,
    )


def _build_sensitivity_deltas(re_params: RealEstateParams) -> dict:
    """Standard ±% sensitivity ranges used by the dashboard."""
    return {
        "monthly_rent": (re_params.monthly_rent * 0.8, re_params.monthly_rent * 1.2),
        "annual_appreciation": (
            re_params.annual_appreciation - 0.03,
            re_params.annual_appreciation + 0.03,
        ),
        "vacancy_months_per_year": (0.0, 3.0),
        "management_fee_pct": (0.0, 0.15),
        "iptu_rate": (0.005, 0.020),
        "income_tax_bracket": (0.0, 0.275),
    }


@router.post("/api/simulate", response_model=SimulateOut)
def simulate(payload: SimulateInput) -> SimulateOut:
    """Run all three deterministic simulations + sensitivity + tax comparison."""
    re_params = _to_real_estate_params(payload.real_estate)
    pf_params = _to_portfolio_params(payload.portfolio)
    bench_params = _to_benchmark_params(payload.benchmark)
    macro = get_macro_params()

    re_result = simulate_real_estate(
        re_params,
        horizon_years=payload.horizon,
        reinvest_income=payload.reinvest,
        capital_initial=payload.capital,
    )
    pf_result = simulate_portfolio(
        pf_params,
        horizon_years=payload.horizon,
        reinvest_income=payload.reinvest,
        ipca=macro.ipca,
    )
    bench_result = simulate_benchmark(bench_params, horizon_years=payload.horizon)

    deltas = _build_sensitivity_deltas(re_params)
    sens_rows = sensitivity_real_estate(re_params, payload.horizon, deltas)
    sensitivity = [
        SensitivityRowOut(
            parameter=row["Parâmetro"],
            pessimistic=float(row["Cenário Pessimista"]),
            optimistic=float(row["Cenário Otimista"]),
        )
        for row in sens_rows.to_dict("records")
    ]

    tax_rows = annual_tax_comparison(re_params, pf_params)
    tax_comparison = [
        TaxComparisonRowOut(
            scenario=row["Cenário"],
            gross_income=float(row["Receita Bruta"]),
            annual_tax=float(row["Imposto Anual"]),
            net_income=float(row["Receita Líquida"]),
            effective_tax_burden=float(row["Carga Tributária Efetiva"]),
        )
        for row in tax_rows.to_dict("records")
    ]

    return SimulateOut(
        real_estate=simulation_result_to_dto(re_result),
        portfolio=simulation_result_to_dto(pf_result),
        benchmark=simulation_result_to_dto(bench_result),
        sensitivity=sensitivity,
        tax_comparison=tax_comparison,
    )
```

- [ ] **Step 9.4: Register the router in `api/main.py`**

```python
from routers import health, macro, portfolio, simulation

# ...

app.include_router(simulation.router)
```

- [ ] **Step 9.5: Run tests — PASS**

```bash
.venv/bin/pytest tests/test_endpoint_simulate.py -v
```

Expected: 3 passed.

- [ ] **Step 9.6: Commit**

```bash
git add api/routers/simulation.py api/main.py api/tests/test_endpoint_simulate.py
git commit -m "$(cat <<'EOF'
feat(api): POST /api/simulate — deterministic simulations

Wraps simulate_real_estate, simulate_portfolio, simulate_benchmark plus
sensitivity_analysis and annual_tax_comparison from core.models. Maps
SimulateInput Pydantic to the underlying dataclasses, runs the engine,
and returns SimulateOut with camelCase keys + ndarray-to-list arrays.

Three tests cover the happy path, the horizon=5 array length, and the
horizon validation rejection (422).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: POST /api/simulate/monte-carlo endpoint

**Files:**
- Modify: `api/routers/simulation.py` (add monte-carlo handler)
- Create: `api/tests/test_endpoint_monte_carlo.py`

- [ ] **Step 10.1: Write the failing test**

`api/tests/test_endpoint_monte_carlo.py`:

```python
"""Tests for POST /api/simulate/monte-carlo."""
from fastapi.testclient import TestClient

from main import app


def _payload() -> dict:
    return {
        "horizon": 5,
        "realEstate": {
            "propertyValue": 230_000.0, "monthlyRent": 1500.0,
            "annualAppreciation": 0.055, "iptuRate": 0.010,
            "vacancyMonthsPerYear": 1.0, "managementFeePct": 0.10,
            "maintenanceAnnual": 900.0, "insuranceAnnual": 600.0,
            "incomeTaxBracket": 0.075, "acquisitionCostPct": 0.05,
            "appreciationVolatility": 0.10, "financing": None,
        },
        "portfolio": {
            "capital": 230_000.0, "monthlyContribution": 0.0,
            "contributionInflationIndexed": True,
            "assets": [
                {"name": "FIIs", "weight": 1.0, "expectedYield": 0.10,
                 "capitalGain": 0.0, "taxRate": 0.0, "note": "", "volatility": 0.15},
            ],
        },
        "mc": {"nTrajectories": 500, "seed": 42, "targetPatrimony": 0.0},
    }


def test_monte_carlo_returns_two_results():
    client = TestClient(app)
    response = client.post("/api/simulate/monte-carlo", json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert "realEstate" in body
    assert "portfolio" in body


def test_monte_carlo_each_result_has_percentile_arrays():
    client = TestClient(app)
    body = client.post("/api/simulate/monte-carlo", json=_payload()).json()
    for key in ("realEstate", "portfolio"):
        result = body[key]
        assert len(result["p10"]) == 6
        assert len(result["p50"]) == 6
        assert len(result["p90"]) == 6
        # final_distribution has nTrajectories elements
        assert len(result["finalDistribution"]) == 500
        assert len(result["maxDrawdowns"]) == 500


def test_monte_carlo_with_seed_is_deterministic():
    client = TestClient(app)
    body1 = client.post("/api/simulate/monte-carlo", json=_payload()).json()
    body2 = client.post("/api/simulate/monte-carlo", json=_payload()).json()
    assert body1["realEstate"]["p50"] == body2["realEstate"]["p50"]
```

- [ ] **Step 10.2: Run — FAIL**

```bash
.venv/bin/pytest tests/test_endpoint_monte_carlo.py -v
```

Expected: 404 / FAIL.

- [ ] **Step 10.3: Add the monte-carlo handler to `api/routers/simulation.py`**

> **Function name reference (verified against `dashboard-investimentos/models.py`):**
> - `simulate_real_estate_mc(params, horizon_years, mc_params, capital_initial=None, portfolio_for_internal=None)` — note the `_mc` suffix; takes `capital_initial` not `ipca`
> - `simulate_portfolio_mc(params, horizon_years, mc_params, ipca=0.0)` — has `ipca` for inflation

Append (do not replace) to the existing `simulation.py`:

```python
from core.config import MonteCarloParams
from core.models import simulate_real_estate_mc, simulate_portfolio_mc
from converters import monte_carlo_result_to_dto
from schemas.inputs import SimulateMonteCarloInput
from schemas.outputs import SimulateMonteCarloOut


def _to_mc_params(input_mc) -> MonteCarloParams:
    return MonteCarloParams(
        n_trajectories=input_mc.n_trajectories,
        seed=input_mc.seed,
        target_patrimony=input_mc.target_patrimony,
    )


@router.post("/api/simulate/monte-carlo", response_model=SimulateMonteCarloOut)
def simulate_monte_carlo(payload: SimulateMonteCarloInput) -> SimulateMonteCarloOut:
    """Run Monte Carlo for both Real Estate and Portfolio scenarios."""
    re_params = _to_real_estate_params(payload.real_estate)
    pf_params = _to_portfolio_params(payload.portfolio)
    mc_params = _to_mc_params(payload.mc)
    macro = get_macro_params()

    re_mc = simulate_real_estate_mc(
        re_params,
        horizon_years=payload.horizon,
        mc_params=mc_params,
    )
    pf_mc = simulate_portfolio_mc(
        pf_params,
        horizon_years=payload.horizon,
        mc_params=mc_params,
        ipca=macro.ipca,
    )

    return SimulateMonteCarloOut(
        real_estate=monte_carlo_result_to_dto(re_mc),
        portfolio=monte_carlo_result_to_dto(pf_mc),
    )
```

- [ ] **Step 10.4: Run tests — PASS**

```bash
.venv/bin/pytest tests/test_endpoint_monte_carlo.py -v
```

Expected: 3 passed (test takes ~5-10s due to MC).

- [ ] **Step 10.5: Commit**

```bash
git add api/routers/simulation.py api/tests/test_endpoint_monte_carlo.py
git commit -m "$(cat <<'EOF'
feat(api): POST /api/simulate/monte-carlo

Wraps simulate_monte_carlo_* engines for both Real Estate and Portfolio.
Returns SimulateMonteCarloOut with p10/p50/p90 arrays per horizon,
plus the final_distribution and max_drawdowns of all trajectories.
Three tests: shape, array lengths, and deterministic seed reproducibility.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: POST /api/fixed-income/simulate endpoint

**Files:**
- Create: `api/routers/fixed_income.py`
- Modify: `api/main.py`
- Create: `api/tests/test_endpoint_fixed_income.py`

- [ ] **Step 11.1: Write the failing test**

`api/tests/test_endpoint_fixed_income.py`:

```python
"""Tests for POST /api/fixed-income/simulate."""
from fastapi.testclient import TestClient

from main import app


def test_fixed_income_simulate_returns_projection_per_position():
    payload = {
        "horizonYears": 3,
        "startDate": "2025-01-01",
        "positions": [
            {"name": "LCI X", "initialAmount": 30000, "purchaseDate": "2025-01-01",
             "indexer": "cdi", "rate": 0.95, "isTaxExempt": True},
            {"name": "Prefixado Y", "initialAmount": 20000, "purchaseDate": "2025-01-01",
             "indexer": "prefixado", "rate": 0.12, "isTaxExempt": False},
        ],
    }
    client = TestClient(app)
    response = client.post("/api/fixed-income/simulate", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["projections"]) == 2
    assert body["totalInitial"] == 50000.0
    assert len(body["totalGross"]) == 4  # horizon + 1
    assert len(body["totalNet"]) == 4
    assert body["projections"][0]["name"] == "LCI X"
    assert body["projections"][0]["indexer"] == "cdi"


def test_fixed_income_simulate_rejects_invalid_indexer():
    payload = {
        "horizonYears": 3,
        "positions": [
            {"name": "X", "initialAmount": 1000, "purchaseDate": "2025-01-01",
             "indexer": "bitcoin", "rate": 0.1, "isTaxExempt": False},
        ],
    }
    client = TestClient(app)
    response = client.post("/api/fixed-income/simulate", json=payload)
    assert response.status_code == 422


def test_fixed_income_simulate_empty_positions_returns_empty_projection():
    payload = {"horizonYears": 3, "positions": []}
    client = TestClient(app)
    response = client.post("/api/fixed-income/simulate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["projections"] == []
    assert body["totalInitial"] == 0.0
```

- [ ] **Step 11.2: Run — FAIL**

```bash
.venv/bin/pytest tests/test_endpoint_fixed_income.py -v
```

Expected: 404.

- [ ] **Step 11.3: Write `api/routers/fixed_income.py`**

```python
"""POST /api/fixed-income/simulate — RF projection given user positions."""
from datetime import date

from fastapi import APIRouter

from converters import fixed_income_portfolio_to_dto
from core.config import FixedIncomePosition
from core.models import simulate_fixed_income
from core.services.macro import get_macro_params
from schemas.inputs import FixedIncomeSimulateInput
from schemas.outputs import FixedIncomePortfolioOut

router = APIRouter()

_PALETTE = [
    "#3498DB", "#E67E22", "#9B59B6", "#1ABC9C",
    "#E74C3C", "#16A085", "#F39C12", "#34495E",
]


@router.post("/api/fixed-income/simulate", response_model=FixedIncomePortfolioOut)
def fixed_income_simulate(payload: FixedIncomeSimulateInput) -> FixedIncomePortfolioOut:
    """Project each position year-by-year applying regressive IR."""
    macro = get_macro_params()
    positions = [
        FixedIncomePosition(
            name=p.name,
            initial_amount=p.initial_amount,
            purchase_date=p.purchase_date,
            indexer=p.indexer,
            rate=p.rate,
            maturity_date=p.maturity_date,
            is_tax_exempt=p.is_tax_exempt,
            color=_PALETTE[i % len(_PALETTE)],
        )
        for i, p in enumerate(payload.positions)
    ]
    portfolio = simulate_fixed_income(
        positions=positions,
        macro=macro,
        horizon_years=payload.horizon_years,
        start_date=payload.start_date,
    )
    return fixed_income_portfolio_to_dto(portfolio)
```

- [ ] **Step 11.4: Register the router in `api/main.py`**

```python
from routers import fixed_income, health, macro, portfolio, simulation

# ...

app.include_router(fixed_income.router)
```

- [ ] **Step 11.5: Run tests — PASS**

```bash
.venv/bin/pytest tests/test_endpoint_fixed_income.py -v
```

Expected: 3 passed.

- [ ] **Step 11.6: Commit**

```bash
git add api/routers/fixed_income.py api/main.py api/tests/test_endpoint_fixed_income.py
git commit -m "$(cat <<'EOF'
feat(api): POST /api/fixed-income/simulate

Maps incoming FixedIncomePositionInput[] to the core
FixedIncomePosition dataclass, runs simulate_fixed_income, and returns
FixedIncomePortfolioOut. Auto-assigns colors from the palette per
position index. Three tests: 2-position happy path, invalid indexer
422, empty positions list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: CORS + structured error handler

**Files:**
- Modify: `api/main.py`
- Create: `api/tests/test_cors_and_errors.py`

- [ ] **Step 12.1: Write the failing test**

`api/tests/test_cors_and_errors.py`:

```python
"""Tests for CORS middleware and the structured error handler."""
from fastapi.testclient import TestClient

from main import app


def test_cors_allows_vercel_origin():
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://investa.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://investa.vercel.app"


def test_cors_allows_localhost_dev():
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_validation_error_returns_structured_400():
    """Pydantic validation errors should be returned in the documented format."""
    client = TestClient(app)
    response = client.post("/api/simulate", json={"capital": -100, "horizon": 100})
    # Pydantic returns 422 by default; we want a structured payload.
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    assert "message" in body
```

- [ ] **Step 12.2: Run — FAIL on CORS and structured-error tests**

```bash
.venv/bin/pytest tests/test_cors_and_errors.py -v
```

Expected: CORS tests fail (no middleware yet), structured-error test fails (FastAPI's default 422 doesn't have `error` / `message`).

- [ ] **Step 12.3: Update `api/main.py` with CORS + error handler**

Replace `api/main.py` contents with:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import fixed_income, health, macro, portfolio, simulation


app = FastAPI(
    title="investa API",
    description="Análise patrimonial — Imóvel vs Carteira",
    version="1.0.0",
)


# ---------- CORS ----------

ALLOWED_ORIGINS = [
    "https://investa.vercel.app",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ---------- Structured error handler ----------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Wrap Pydantic validation errors in our documented {error, message, details} shape."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "message": first.get("msg", "validation error"),
            "details": {"field": field, "errors": exc.errors()},
        },
    )


# ---------- Routers ----------

app.include_router(health.router)
app.include_router(macro.router)
app.include_router(portfolio.router)
app.include_router(simulation.router)
app.include_router(fixed_income.router)
```

- [ ] **Step 12.4: Run tests — PASS**

```bash
.venv/bin/pytest tests/test_cors_and_errors.py tests/ -v
```

Expected: all tests pass (the full suite, not just the new ones — to confirm no regression).

- [ ] **Step 12.5: Commit**

```bash
git add api/main.py api/tests/test_cors_and_errors.py
git commit -m "$(cat <<'EOF'
feat(api): CORS middleware + structured validation errors

Allows the Vercel production origin and localhost:3000 for dev.
Wraps Pydantic RequestValidationError in our documented
{error, message, details} JSON shape so the frontend can surface
field-level validation messages consistently.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: GitHub Actions CI for api/

**Files:**
- Create: `.github/workflows/api-ci.yml`

- [ ] **Step 13.1: Write `.github/workflows/api-ci.yml`**

```yaml
name: api-ci

on:
  push:
    branches: [main]
    paths:
      - "api/**"
      - ".github/workflows/api-ci.yml"
  pull_request:
    paths:
      - "api/**"

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: api/requirements*.txt

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest -v
```

- [ ] **Step 13.2: Commit and push to trigger CI**

```bash
git add .github/workflows/api-ci.yml
git commit -m "$(cat <<'EOF'
ci(api): GitHub Actions workflow for api/ tests

Runs pytest on every push to main and every PR that touches api/.
Python 3.12 to match the Render runtime. Pip cache keyed on
requirements*.txt for faster runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 13.3: Verify CI run on GitHub**

Open `https://github.com/logomes/investa/actions` and confirm the workflow is running and (eventually) green. If it fails, fix the issue and push a follow-up commit.

---

## Task 14: render.yaml + Render deploy

**Files:**
- Create: `api/render.yaml`

- [ ] **Step 14.1: Write `api/render.yaml`**

```yaml
services:
  - type: web
    name: investa-api
    runtime: python
    rootDir: api
    plan: free
    region: oregon
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
    pythonVersion: "3.12"
    autoDeploy: true
```

- [ ] **Step 14.2: Commit**

```bash
git add api/render.yaml
git commit -m "$(cat <<'EOF'
chore(api): render.yaml for Infrastructure-as-Code deploy

Defines the Render Web Service: free tier, oregon region, Python 3.12,
auto-deploy on push to main, healthcheck at /api/health.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 14.3: Manual handoff — connect Render to the repo**

Tell the user:

> Now go to https://dashboard.render.com → "New +" → "Blueprint" → connect to `logomes/investa` → Render will detect `api/render.yaml` and provision the service automatically.
>
> Settings to confirm in the wizard:
> - Service name: `investa-api`
> - Branch: `main`
> - Root Directory: `api`
> - Plan: Free
>
> First deploy takes ~3-5 minutes. Confirm here when the service is live.

- [ ] **Step 14.4: Wait for user confirmation that Render service is live**

Do NOT proceed to Task 15 until the user confirms.

---

## Task 15: Smoke test from production URL

**Files:** none (manual verification)

- [ ] **Step 15.1: Verify health endpoint from production**

```bash
curl -s https://investa-api.onrender.com/api/health
```

Expected output:
```json
{"status":"ok","version":"1.0.0"}
```

- [ ] **Step 15.2: Verify macro endpoint returns real BCB data**

```bash
curl -s https://investa-api.onrender.com/api/macro | head
```

Expected: JSON with `selic`, `cdi`, `ipca`, `usdBrl`, `isStale`, `sourceLabel`. `selic` should be ~0.10–0.20 (current Selic range). `isStale` should be `false` if BCB is reachable, `true` otherwise (still 200 OK).

- [ ] **Step 15.3: Verify defaults endpoint**

```bash
curl -s https://investa-api.onrender.com/api/portfolio/defaults | head
```

Expected: JSON with `realEstate`, `portfolio`, `benchmark` keys.

- [ ] **Step 15.4: Verify simulate endpoint with default scenario**

```bash
curl -s -X POST https://investa-api.onrender.com/api/simulate \
  -H "Content-Type: application/json" \
  -d "$(curl -s https://investa-api.onrender.com/api/portfolio/defaults | python -c '
import sys, json
defaults = json.load(sys.stdin)
payload = {"capital": 230000, "horizon": 10, "reinvest": True, **defaults}
print(json.dumps(payload))
')" | python -c 'import sys, json; d=json.load(sys.stdin); print("realEstate years:", len(d["realEstate"]["years"]))'
```

Expected: prints `realEstate years: 11` (horizon 10 → 11 data points).

If the cold start is slow (Render free tier sleeps after 15 min idle), the first request takes ~30s. Subsequent requests are fast.

- [ ] **Step 15.5: Document the production URLs in `README.md`**

Edit the root `README.md` and replace the placeholder URLs with the confirmed production ones:

```markdown
## URLs de produção

- **API:** https://investa-api.onrender.com (status: ✅ Fase 1 completa)
- **Web:** https://investa.vercel.app (status: 🟡 Fase 2 pendente)
```

- [ ] **Step 15.6: Commit and push the README update**

```bash
git add README.md
git commit -m "docs: confirm investa-api.onrender.com URL is live (Fase 1 complete)"
git push
```

---

## Phase 1 Done

- New repo `logomes/investa` exists with monorepo skeleton
- `api/` migrated and deployed on Render free tier
- 6 endpoints live: `/api/health`, `/api/macro`, `/api/portfolio/defaults`, `/api/simulate`, `/api/simulate/monte-carlo`, `/api/fixed-income/simulate`
- All migrated tests pass + new endpoint tests pass (~35-40 total)
- CI runs on every push
- The math in `core/` is unchanged from `dashboard-investimentos`

**Next phase:** Fase 2 — Web shell + tokens. That gets its own brainstorming + spec + plan cycle when you're ready to start it.
