"""pytest 公共夹具（E 岗位 API 测试）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for path in (str(ROOT / "tech"), str(ROOT / "backend"), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.main import create_app  # noqa: E402
from api_support import StubEngine, default_proposals, make_settings  # noqa: E402


@pytest.fixture()
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture()
def stub_engine():
    return StubEngine(default_proposals())


@pytest.fixture()
def app(settings, stub_engine):
    return create_app(settings, stub_engine)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
