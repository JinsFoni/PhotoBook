"""收藏 — API 增查删、跨页同步、页面联动。"""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.db import Video, VideoAlbum


def _video_album(slug: str = "clip-set", n: int = 2) -> None:
    """造一个已发布的视频专辑(无真实视频文件, poster=None 亦可渲染)。"""
    s = SessionLocal()
    try:
        if s.scalar(select(VideoAlbum).where(VideoAlbum.slug == slug)):
            return
        a = VideoAlbum(slug=slug, title="Clip Set", status="published",
                       published_at="2026-10-01 10:00:00")
        s.add(a)
        s.flush()
        for i in range(n):
            s.add(Video(album_id=a.id, filename=f"demo/{slug}/clip{i}.mp4",
                        width=1920, height=1080, duration=12.5 + i, sort_order=i))
        a.cover_video_id = s.scalar(select(Video.id).where(
            Video.album_id == a.id).order_by(Video.sort_order).limit(1))
        s.commit()
    finally:
        s.close()


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


# ---- 写真视频收藏(video_album / video 两种新类型) ---------------------------

def test_video_album_favorite_roundtrip(admin_client):
    _video_album()
    admin_client.post("/api/favorites", json={"type": "video_album", "key": "clip-set", "added": True})
    data = admin_client.get("/api/favorites").json()
    assert "clip-set" in data["video_album"]
    # 收藏页两个新 tab 的数据桶
    r = admin_client.get("/favorites")
    assert r.status_code == 200
    assert "clip-set" in r.text


def test_video_favorite_key_uses_v_prefix(admin_client):
    """单条视频的收藏键是 "<album_slug>:v<idx>" —— v 前缀与照片的
    "<slug>:<idx>" 区分, 两个模块的键永不相撞。"""
    _video_album()
    admin_client.post("/api/favorites", json={"type": "video", "key": "clip-set:v0", "added": True})
    data = admin_client.get("/api/favorites").json()
    assert "clip-set:v0" in data["video"]
    r = admin_client.get("/favorites?tab=video")
    assert r.status_code == 200
    assert "clip-set:v0" in r.text


def test_video_favorites_toggle_off(admin_client):
    _video_album()
    for added in (True, False):
        admin_client.post("/api/favorites", json={"type": "video", "key": "clip-set:v1", "added": added})
    assert "clip-set:v1" not in admin_client.get("/api/favorites").json()["video"]
