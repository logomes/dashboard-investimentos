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
    assert MACRO_FALLBACK.source_label  # non-empty string
