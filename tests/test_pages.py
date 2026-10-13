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


def test_models_page_vm_payload(admin_client):
    """/models 与 /collections 同构: 全量数据池 + latest 字段(排序:最新用)。"""
    r = admin_client.get("/models")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert d["models"] and all("latest" in m for m in d["models"])
    # 虚拟化网格容器 + 无「加载更多」按钮(分页交互已移除)
    assert 'class="vm-grid" data-grid' in r.text
    assert "data-more-btn" not in r.text


def test_collections_page_vm_payload_has_tags(admin_client):
    """/collections 卡片条目必须带 tags 数组(标签筛选 c.tags.indexOf 依赖)。"""
    r = admin_client.get("/collections")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert d["collections"], "种子数据应有写真集"
    for c in d["collections"]:
        assert isinstance(c.get("tags"), list), f"collection {c['slug']} 缺 tags 字段"
    # 有标签的写真集, 其 tags 应出现在筛选下拉数据源里
    if any(c["tags"] for c in d["collections"]):
        names = {t["name"] for t in d["tags"]}
        assert names, "有带标签的写真集时, tags 数据源不应为空"


# ---- 写真视频(与写真集平行的独立模块) ----------------------------------------

def test_videos_page_vm_payload(admin_client):
    """/videos 与 /collections 同构: 数据池键名为 albums(不是 collections),
    卡片条目带 tags/cover/count, 空库时也必须是 200 + 空数组。"""
    r = admin_client.get("/videos")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert isinstance(d.get("albums"), list)
    assert isinstance(d.get("models"), list)
    assert isinstance(d.get("tags"), list)
    for a in d["albums"]:
        for k in ("slug", "title", "cover", "count", "tags", "model_slug", "created"):
            assert k in a, f"album {a.get('slug')} 缺字段 {k}"
    assert 'class="vm-grid" data-grid' in r.text


def test_video_detail_404_for_unknown(admin_client):
    r = admin_client.get("/videos/nope-nope")
    assert r.status_code == 404


def test_favorites_page_video_buckets(admin_client):
    """/favorites 的 PB_DATA 必须有 videoAlbums/videos 两个桶
    (前端两个新 tab 与 loadFavs 遍历都依赖它们存在)。"""
    r = admin_client.get("/favorites")
    assert r.status_code == 200
    d = _pb_data(r.text)
    assert isinstance(d.get("videoAlbums"), list)
    assert isinstance(d.get("videos"), list)
    assert d["counts"]["video_album"] == len(d["videoAlbums"])
    assert d["counts"]["video"] == len(d["videos"])
    # 两个新 tab 的按钮与面板
    assert 'data-fav-count="video_album"' in r.text
    assert 'data-fav-count="video"' in r.text
    assert 'data-panel="video_album"' in r.text
    assert 'data-panel="video"' in r.text
