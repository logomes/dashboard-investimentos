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
    # Year 0 (today, 2025-01-01): holding=731 days (2024 is leap) → IR=15%
    # gross = 1000 * 1.1^(731/365), net = 1000 + (gross-1000)*0.85
    expected_gross = 1000.0 * 1.1 ** (731 / 365)
    expected_net = 1000.0 + (expected_gross - 1000.0) * 0.85
    np.testing.assert_allclose(proj.gross_values[0], expected_gross, rtol=1e-6)
    np.testing.assert_allclose(proj.net_values[0], expected_net, rtol=1e-6)


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


def test_csv_handles_string_boolean_values():
    """CSV imports may have 'true'/'false' as strings — must coerce correctly."""
    record_true = {
        "name": "X", "initial_amount": 1000.0, "purchase_date": "2025-01-01",
        "indexer": "cdi", "rate": 1.0, "maturity_date": "", "is_tax_exempt": "true",
    }
    record_false = dict(record_true, is_tax_exempt="false")
    assert FixedIncomePosition.from_record(record_true).is_tax_exempt is True
    assert FixedIncomePosition.from_record(record_false).is_tax_exempt is False


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
