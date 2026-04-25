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
