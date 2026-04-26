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
