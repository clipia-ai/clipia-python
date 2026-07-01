"""Tests for base_url HTTPS validation (FU-8) on both clients."""

from __future__ import annotations

import pytest

from clipia import AsyncClipia, Clipia

API_KEY = "clipia_live_test_key"


# -- Clipia (sync) ------------------------------------------------------------


def test_default_base_url_is_https() -> None:
    client = Clipia(api_key=API_KEY)
    assert client.base_url.startswith("https://")
    client.close()


def test_custom_https_base_url_ok() -> None:
    client = Clipia(api_key=API_KEY, base_url="https://api.example.com/v1/")
    # trailing slash stripped, scheme preserved
    assert client.base_url == "https://api.example.com/v1"
    client.close()


def test_http_localhost_allowed() -> None:
    client = Clipia(api_key=API_KEY, base_url="http://localhost:3000")
    assert client.base_url == "http://localhost:3000"
    client.close()


def test_http_127_0_0_1_allowed() -> None:
    client = Clipia(api_key=API_KEY, base_url="http://127.0.0.1:8080/v1")
    assert client.base_url == "http://127.0.0.1:8080/v1"
    client.close()


def test_plain_http_rejected() -> None:
    with pytest.raises(ValueError, match="https"):
        Clipia(api_key=API_KEY, base_url="http://api.example.com")


def test_http_lookalike_host_rejected() -> None:
    # "localhost.evil.com" must NOT pass the localhost allowlist.
    with pytest.raises(ValueError, match="https"):
        Clipia(api_key=API_KEY, base_url="http://localhost.evil.com")


def test_uppercase_http_scheme_rejected() -> None:
    with pytest.raises(ValueError, match="https"):
        Clipia(api_key=API_KEY, base_url="HTTP://api.example.com")


# -- AsyncClipia --------------------------------------------------------------


def test_async_default_base_url_is_https() -> None:
    client = AsyncClipia(api_key=API_KEY)
    assert client.base_url.startswith("https://")


def test_async_custom_https_ok() -> None:
    client = AsyncClipia(api_key=API_KEY, base_url="https://api.example.com")
    assert client.base_url == "https://api.example.com"


def test_async_http_localhost_allowed() -> None:
    client = AsyncClipia(api_key=API_KEY, base_url="http://localhost:3000")
    assert client.base_url == "http://localhost:3000"


def test_async_plain_http_rejected() -> None:
    with pytest.raises(ValueError, match="https"):
        AsyncClipia(api_key=API_KEY, base_url="http://api.example.com")
