"""Test phân loại lỗi tạm thời (retry) vs terminal."""
import httpx
import pytest

from app.services.http_retry import TransientError, is_transient, raise_if_transient


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)


def test_network_errors_are_transient():
    assert is_transient(httpx.ConnectError("boom"))
    assert is_transient(httpx.ReadTimeout("slow"))


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_5xx_and_429_are_transient(code):
    assert is_transient(_status_error(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_4xx_are_terminal(code):
    assert not is_transient(_status_error(code))


def test_non_http_errors_are_terminal():
    assert not is_transient(ValueError("bad data"))


def test_raise_if_transient():
    with pytest.raises(TransientError):
        raise_if_transient(httpx.ConnectError("boom"))
    # Lỗi terminal: không raise.
    raise_if_transient(ValueError("bad data"))
