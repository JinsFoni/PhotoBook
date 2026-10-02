"""移动端 API 测试 — 认证/错误体/discover/collections/favorites。"""

from __future__ import annotations

import pytest

from app.routers import mobile_api


@pytest.fixture(scope="module")
def mobile_user_name() -> str:
    """专用用户:get-or-create,不依赖 demo(其他测试会改 demo 密码,字母序执行时已失效)。"""
    from sqlalchemy import select

    from app.auth import hash_password
    from app.database import SessionLocal
    from app.db import User

    s = SessionLocal()
    try:
        user = s.scalar(select(User).where(User.username == "mobiletester"))
        if not user:
            user = User(username="mobiletester",
                        password_hash=hash_password("mobile-pass"))
            s.add(user)
            s.commit()
            s.refresh(user)
        return user.username
    finally:
        s.close()


@pytest.fixture()
def token(client, mobile_user_name):
    r = client.post("/api/mobile/auth/login",
                    json={"username": mobile_user_name, "password": "mobile-pass"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- 认证 ----

def test_login_success(client, mobile_user_name):
    r = client.post("/api/mobile/auth/login",
                    json={"username": mobile_user_name, "password": "mobile-pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["expires_at"]


def test_login_wrong_password(client, mobile_user_name):
    r = client.post("/api/mobile/auth/login",
                    json={"username": mobile_user_name, "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_user(client):
    r = client.post("/api/mobile/auth/login",
                    json={"username": "ghost", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_validation_shape(client):
    r = client.post("/api/mobile/auth/login", json={"username": "mobiletester"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation"
    assert "password" in err["message"]


def test_me_requires_token(client):
    r = client.get("/api/mobile/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_me_with_token(client, token, mobile_user_name):
    r = client.get("/api/mobile/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["username"] == mobile_user_name


def test_me_bad_token(client):
    r = client.get("/api/mobile/auth/me", headers=_auth("not-a-session"))
    assert r.status_code == 401


# ---- discover(匿名可读)----

def test_discover_shape(client):
    r = client.get("/api/mobile/discover")
    assert r.status_code == 200
    data = r.json()
    assert {"featured", "latest", "models", "tags", "stats"} <= set(data)
    assert data["stats"]["collections"] > 0
    col = data["featured"][0]
    for key in ("id", "slug", "title", "date", "model_slug", "model_name",
                "cover", "coverThumb", "count", "tags"):
        assert key in col, f"missing {key}"


def test_discover_model_payload(client):
    data = client.get("/api/mobile/discover").json()
    m = data["models"][0]
    for key in ("slug", "name", "avatar", "count", "photoCount"):
        assert key in m


# ---- collections 列表/详情 ----

def test_collections_pagination(client):
    r = client.get("/api/mobile/collections", params={"page": 1, "pageSize": 2})
    data = r.json()
    assert data["pageSize"] == 2 and data["page"] == 1
    assert len(data["items"]) <= 2
    assert data["total"] >= len(data["items"])
    if data["total"] > 2:
        page2 = client.get("/api/mobile/collections",
                           params={"page": 2, "pageSize": 2}).json()
        assert page2["items"][0]["slug"] != data["items"][0]["slug"]


def test_collections_tag_filter(client):
    tags = client.get("/api/mobile/discover").json()["tags"]
    if not tags:
        pytest.skip("no seeded tags")
    name = tags[0]["name"]
    data = client.get("/api/mobile/collections", params={"tag": name}).json()
    assert all(name in it["tags"] for it in data["items"])


def test_collection_detail(client):
    slug = client.get("/api/mobile/collections").json()["items"][0]["slug"]
    r = client.get(f"/api/mobile/collections/{slug}")
    assert r.status_code == 200
    col = r.json()
    assert col["slug"] == slug
    assert col["photos"] and {"idx", "file", "w", "h"} <= set(col["photos"][0])
    assert [p["idx"] for p in col["photos"]] == list(range(len(col["photos"])))


def test_collection_detail_not_found(client):
    r = client.get("/api/mobile/collections/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ---- favorites ----

def test_favorites_anonymous_empty(client):
    r = client.get("/api/mobile/favorites")
    assert r.status_code == 200
    assert r.json() == {"model": [], "collection": [], "photo": []}


def test_favorites_roundtrip(client, token):
    slug = client.get("/api/mobile/collections").json()["items"][0]["slug"]
    h = _auth(token)
    r = client.post("/api/mobile/favorites", headers=h,
                    json={"type": "collection", "key": slug, "added": True})
    assert r.status_code == 200
    assert client.get("/api/mobile/favorites", headers=h).json()["collection"] == [slug]
    # 重复 add 幂等
    client.post("/api/mobile/favorites", headers=h,
                json={"type": "collection", "key": slug, "added": True})
    assert client.get("/api/mobile/favorites", headers=h).json()["collection"] == [slug]
    client.post("/api/mobile/favorites", headers=h,
                json={"type": "collection", "key": slug, "added": False})
    assert client.get("/api/mobile/favorites", headers=h).json()["collection"] == []


def test_favorites_requires_login(client):
    r = client.post("/api/mobile/favorites",
                    json={"type": "collection", "key": "x", "added": True})
    assert r.status_code == 401


def test_favorites_bad_type(client, token):
    r = client.post("/api/mobile/favorites", headers=_auth(token),
                    json={"type": "album", "key": "x", "added": True})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation"
