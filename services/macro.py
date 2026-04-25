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
