"""视频媒体服务 — /video 原片(Range/206 + MIME)与 /poster 封面帧。

与 test_media.py 平行的视频侧:这里只验证「视频作为媒体的基础设施」——
路由、MIME 映射、Range 部分内容、封面帧 404 语义。抽帧(ffmpeg)本身
在 test_library_import.py 的降级用例里覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import video as video_service


@pytest.fixture()
def video_file(tmp_path, monkeypatch):
    """在 video_dir 下造一个可播放的 mp4(内容不重要,Range/MIME 只看文件)。"""
    base = video_service.settings.video_dir
    base.mkdir(parents=True, exist_ok=True)
    rel = "demo/clip-set/clip0.mp4"
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 500)
    yield rel
    p.unlink(missing_ok=True)


# ---- MIME 映射 ---------------------------------------------------------------

def test_mime_of_known_exts():
    assert video_service.mime_of("a/b.mp4") == "video/mp4"
    assert video_service.mime_of("a/b.m4v") == "video/mp4"
    assert video_service.mime_of("a/b.mov") == "video/quicktime"
    assert video_service.mime_of("a/b.mkv") == "video/x-matroska"
    assert video_service.mime_of("a/b.webm") == "video/webm"
    assert video_service.mime_of("a/b.ts") == "video/mp2t"


def test_mime_of_unknown_falls_back_to_mp4():
    assert video_service.mime_of("a/b.xyz") == "video/mp4"


# ---- /video 路由 -------------------------------------------------------------

def test_video_served_with_range_206(client, video_file):
    """Range 请求 → 206 部分内容(拖动进度条的前提;Starlette FileResponse 原生支持)。"""
    r = client.get(f"/video/{video_file}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert r.headers["content-range"].startswith("bytes 0-99/")


def test_video_full_get_200_with_mime(client, video_file):
    r = client.get(f"/video/{video_file}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers.get("accept-ranges") == "bytes"


def test_video_missing_404(client):
    assert client.get("/video/demo/nope/missing.mp4").status_code == 404


def test_video_path_traversal_rejected(client, video_file):
    """目录穿越必须被挡(HTTP 客户端会先规范化,这里直连服务端守卫函数)。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        video_service._safe_path("../app/config.py")
    assert e.value.status_code == 404
    # 合法 rel 正常解析
    assert video_service._safe_path(video_file).is_file()


def test_video_second_range_window(client, video_file):
    """拖到中段再 Range:另一段区间也返回 206,证明不是只支持首段。"""
    r = client.get(f"/video/{video_file}", headers={"Range": "bytes=200-299"})
    assert r.status_code == 206
    assert len(r.content) == 100


# ---- /poster 路由 ------------------------------------------------------------

def test_poster_404_without_cache_and_without_source(client):
    """无缓存且本地无视频 → 404(前端回退占位,不崩)。"""
    assert client.get("/poster/demo/nope/clip0.mp4").status_code == 404


def test_poster_served_from_cache(client, video_file, monkeypatch, tmp_path):
    """缓存命中即回 webp,不再碰 ffmpeg。"""
    from app.services import media

    rel = video_file
    cache = media._cache_path(900, None, 78, rel, short=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"RIFF....WEBP")
    r = client.get(f"/poster/{rel}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content == b"RIFF....WEBP"
    cache.unlink(missing_ok=True)


def test_poster_bad_width_rejected(client, video_file):
    """只有 900/2400 两档,其他宽度直接 404。"""
    assert client.get(f"/poster/{video_file}?w=300").status_code == 404


# ---- ffmpeg 探测 -------------------------------------------------------------

def test_ffmpeg_available_is_cached(monkeypatch):
    """which 结果进程内只探一次(避免每次抽帧都 fork which)。"""
    from app.services import video as v

    v._ffmpeg_state = None
    calls = {"n": 0}

    def fake_which(name):
        calls["n"] += 1
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    assert v.ffmpeg_available() is False
    assert v.ffmpeg_available() is False
    assert calls["n"] == 1
    v._ffmpeg_state = None


def test_extract_frame_without_ffmpeg_returns_none(monkeypatch, tmp_path):
    """ffmpeg 缺失 → 抽帧返回 None(导入/worker 全链路降级的开关点)。"""
    from app.services import video as v

    v._ffmpeg_state = False
    src = tmp_path / "x.mp4"
    src.write_bytes(b"x")
    assert v.extract_frame(src) is None
    v._ffmpeg_state = None


def test_probe_without_ffmpeg_returns_nones(monkeypatch, tmp_path):
    from app.services import video as v

    v._ffmpeg_state = False
    src = tmp_path / "x.mp4"
    src.write_bytes(b"x")
    assert v.probe(src) == (None, None, None)
    v._ffmpeg_state = None
