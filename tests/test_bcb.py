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

    mock_get = mocker.patch("data_sources.bcb.requests.get", side_effect=fake_get)
    reading = fetch_macro()

    assert isinstance(reading, BcbReading)
    assert reading.selic == pytest.approx(0.1475)
    assert reading.cdi == pytest.approx(0.1465)
    assert reading.usd_brl == pytest.approx(5.30)
    # 1.004^12 - 1 ≈ 0.04907
    assert reading.ipca_12m == pytest.approx(0.04907, abs=1e-4)
    assert isinstance(reading.fetched_at, datetime)

    # Timeout must always be forwarded
    from data_sources.bcb import DEFAULT_TIMEOUT
    for call in mock_get.call_args_list:
        assert call.kwargs.get("timeout") == DEFAULT_TIMEOUT


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


def test_fetch_macro_other_request_exception(mocker):
    """Subclasses of RequestException not specifically caught must still become BcbApiError."""
    mocker.patch("data_sources.bcb.requests.get",
                 side_effect=requests.TooManyRedirects("loop"))
    with pytest.raises(BcbApiError):
        fetch_macro()


def test_fetch_macro_bad_valor_in_ipca_payload(mocker):
    """Malformed valor field in IPCA monthly payload becomes BcbApiError, not ValueError."""
    bad_ipca = [{"data": "01/01/2025", "valor": "N/A"}] * 12

    def fake_get(url, timeout):
        if "bcdata.sgs.432" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.75"}])
        if "bcdata.sgs.433" in url:
            return _mock_response(bad_ipca)
        if "bcdata.sgs.12" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.65"}])
        if "bcdata.sgs.1" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "5.30"}])
        raise AssertionError(f"unexpected url: {url}")

    mocker.patch("data_sources.bcb.requests.get", side_effect=fake_get)
    with pytest.raises(BcbApiError):
        fetch_macro()


def test_fetch_macro_partial_ipca_payload_is_total_failure(mocker):
    """Truncated IPCA series (< 12 months) must raise BcbApiError."""
    short_ipca = [{"data": f"01/{m:02d}/2025", "valor": "0.4"} for m in range(1, 9)]

    def fake_get(url, timeout):
        if "bcdata.sgs.432" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.75"}])
        if "bcdata.sgs.433" in url:
            return _mock_response(short_ipca)  # only 8 months
        if "bcdata.sgs.12" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "14.65"}])
        if "bcdata.sgs.1" in url:
            return _mock_response([{"data": "01/04/2026", "valor": "5.30"}])
        raise AssertionError(f"unexpected url: {url}")

    mocker.patch("data_sources.bcb.requests.get", side_effect=fake_get)
    with pytest.raises(BcbApiError) as exc:
        fetch_macro()
    assert "12 IPCA months" in str(exc.value)
