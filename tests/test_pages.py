"""公开页面 — 状态码、关键内容、PB_DATA 注入、缩略图服务。"""

from __future__ import annotations

import json
import re


def _pb_data(html: str) -> dict:
    m = re.search(r"window\.PB_DATA = (.*?);\nwindow\.PB_BOOT", html, re.S)
    assert m, "PB_DATA missing"
    return json.loads(m.group(1))


def test_discovery(admin_client):
    r = admin_client.get("/")
    assert r.status_code == 200
    assert "PB_DATA" in r.text


def test_collections_page_lists_seed(admin_client):
    r = admin_client.get("/collections")
    assert r.status_code == 200
    assert "summer-editorial" in r.text


def test_collection_detail_data(admin_client):
    r = admin_client.get("/collections/summer-editorial")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert d["slug"] == "summer-editorial"
    assert d["photos"] and d["photos"][0]["file"].startswith("demo/")


def test_models_page_and_detail(admin_client):
    assert admin_client.get("/models").status_code == 200
    r = admin_client.get("/models/yang-chenchen")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert d["slug"] == "yang-chenchen"


def test_unknown_collection_404(admin_client):
    assert admin_client.get("/collections/nope-nope").status_code == 404


def test_unknown_model_404(admin_client):
    assert admin_client.get("/models/nope-nope").status_code == 404


def test_profile_page(admin_client):
    r = admin_client.get("/profile")
    assert r.status_code == 200
    assert "admin" in r.text


def test_search_api(admin_client):
    r = admin_client.get("/api/search?q=summer")
    assert r.status_code == 200
    d = r.json()
    assert any(c["slug"] == "summer-editorial" for c in d["collections"])
    assert admin_client.get("/api/search?q=zzzz").json()["collections"] == []


def test_thumbnail_endpoint(admin_client):
    r = admin_client.get("/t/300/demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg.webp")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"


def test_thumbnail_bad_width(admin_client):
    # 宽度上限 2400,超出被钳制而非 404
    r = admin_client.get("/t/99999/demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg.webp")
    assert r.status_code == 200
    assert admin_client.get("/t/0/demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg.webp").status_code == 404


def test_media_traversal_blocked(admin_client):
    assert admin_client.get("/media/../../etc/passwd").status_code == 404


def test_original_media_served(admin_client):
    r = admin_client.get("/media/demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
