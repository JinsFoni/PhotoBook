"""收藏 — API 增查删、跨页同步、页面联动。"""

from __future__ import annotations


def test_favorites_requires_login(fresh_client):
    r = fresh_client.get("/api/favorites", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_add_and_list(admin_client):
    r = admin_client.post("/api/favorites", json={"type": "photo", "key": "summer-editorial:0", "added": True})
    assert r.status_code == 200
    r = admin_client.get("/api/favorites")
    data = r.json()
    assert "summer-editorial:0" in data["photo"]


def test_toggle_off_removes(admin_client):
    admin_client.post("/api/favorites", json={"type": "collection", "key": "summer-editorial", "added": True})
    admin_client.post("/api/favorites", json={"type": "collection", "key": "summer-editorial", "added": False})
    assert "summer-editorial" not in admin_client.get("/api/favorites").json()["collection"]


def test_invalid_type_rejected(admin_client):
    r = admin_client.post("/api/favorites", json={"type": "meme", "key": "x", "added": True})
    assert r.status_code in (400, 422)


def test_favorites_page_renders(admin_client):
    admin_client.post("/api/favorites", json={"type": "photo", "key": "summer-editorial:1", "added": True})
    r = admin_client.get("/favorites")
    assert r.status_code == 200
    assert "summer-editorial:1" in r.text  # 服务端渲染出已存键
