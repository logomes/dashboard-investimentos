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
