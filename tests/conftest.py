"""Pytest fixtures — 每个角色的 TestClient 相互独立(独立 cookie jar)。

环境变量必须在 app 模块导入之前设置(否则 config 已固化)。
"""

from __future__ import annotations

import os
import tempfile

TMP = tempfile.mkdtemp(prefix="pb-tests-")
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))
os.environ.setdefault("MEDIA_DIR", os.path.join(TMP, "media"))
os.environ.setdefault("LIBRARY_DIR", os.path.join(TMP, "library"))
os.environ.setdefault("HARVEST_ENABLED", "0")
os.environ.setdefault("SEED_DEMO", "1")  # 测试依赖种子内容(demo 写真/模特)
os.environ.setdefault("PHOTOBOOK_SECRET", "test-secret")
os.environ.setdefault("PHOTOBOOK_PORT", "8777")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _new_client() -> TestClient:
    c = TestClient(app)
    c.__enter__()
    return c


@pytest.fixture(scope="session", autouse=True)
def _boot():
    """会话开始时初始化一次库与种子(lifespan 幂等)。"""
    with TestClient(app):
        yield


def _login(username: str, password: str) -> TestClient:
    c = _new_client()
    r = c.post("/login", data={"username": username, "password": password},
               follow_redirects=False)
    assert r.status_code in (302, 303), f"login failed for {username}"
    return c


@pytest.fixture()
def client():
    """未登录客户端。"""
    c = _new_client()
    yield c
    c.__exit__(None, None, None)


@pytest.fixture()
def admin_client():
    c = _login("admin", "admin123")
    yield c
    c.__exit__(None, None, None)


@pytest.fixture()
def demo_client():
    c = _login("demo", "demo123")
    yield c
    c.__exit__(None, None, None)


@pytest.fixture()
def fresh_client():
    """未登录(独立 cookie jar 的)客户端,与 client 等价。"""
    c = _new_client()
    yield c
    c.__exit__(None, None, None)
