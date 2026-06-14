"""Shared test fixtures."""

from __future__ import annotations

import pytest

API_KEY = "clipia_live_test_key"
BASE_URL = "https://api.clipia.ai"


@pytest.fixture
def api_key() -> str:
    return API_KEY


@pytest.fixture
def base_url() -> str:
    return BASE_URL
