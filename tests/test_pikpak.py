"""PikPak 推送 API(/api/ext/pikpak)— 入队/去重/鉴权/校验。

覆盖: 鉴权、items 必填、files 全空的勾选项被过滤、批量入队、
同 file_id 已入队则跳过、模特名与标签落库、压缩包判定。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def ext_key(admin_client):
    from app.database import SessionLocal
    from app.routers.ext_api import get_or_create_api_key

    s = SessionLocal()
    try:
        return get_or_create_api_key(s)
    finally:
        s.close()


H = lambda k: {"X-PhotoBook-Key": k}


def _clean():
    from app.database import SessionLocal
    from app.db import PikPakFile, PikPakJob

    s = SessionLocal()
    try:
        for f in s.query(PikPakFile).all():
            s.delete(f)
        for j in s.query(PikPakJob).all():
            s.delete(j)
        s.commit()
    finally:
        s.close()


def _jobs():
    from app.database import SessionLocal
    from app.db import PikPakJob

    s = SessionLocal()
    try:
        return s.query(PikPakJob).order_by(PikPakJob.id).all()
    finally:
        s.close()


def _files(job_id: int):
    from app.database import SessionLocal
    from app.db import PikPakFile

    s = SessionLocal()
    try:
        return s.query(PikPakFile).filter(PikPakFile.job_id == job_id) \
            .order_by(PikPakFile.id).all()
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _cleanup():
    _clean()
    yield
    _clean()


def _item(file_id: str, name: str, files: list[dict], size: int = 0):
    return {"file_id": file_id, "name": name, "size": size,
            "files": files}


# 一个文件夹勾选项 = 3 张图(带相对路径)
FOLDER = _item("album-1", "坎特蕾拉写真", [
    {"file_id": "a", "url": "https://dl.mypikpak.com/a.jpg",
     "rel": "001.jpg", "size": 100},
    {"file_id": "b", "url": "https://dl.mypikpak.com/b.jpg",
     "rel": "002.jpg", "size": 200},
    {"file_id": "c", "url": "https://dl.mypikpak.com/c.jpg",
     "rel": "003.jpg", "size": 300},
], size=600)

# 一个压缩包勾选项 = 1 个文件
ZIP = _item("zip-1", "写真相册.zip", [
    {"file_id": "z", "url": "https://dl.mypikpak.com/album.zip",
     "rel": "album.zip", "size": 4096},
], size=4096)


# ---- 鉴权 ---------------------------------------------------------------------

def test_pikpak_requires_key(client):
    r = client.post("/api/ext/pikpak", json={"items": [FOLDER]})
    assert r.status_code == 401


def test_pikpak_rejects_bad_key(client):
    r = client.post("/api/ext/pikpak", json={"items": [FOLDER]},
                    headers=H("nope"))
    assert r.status_code == 401


def test_pikpak_requires_items(ext_key, client):
    r = client.post("/api/ext/pikpak", json={"items": []}, headers=H(ext_key))
    assert r.status_code == 422


# ---- 入队 ---------------------------------------------------------------------

def test_pikpak_enqueues_with_model_and_tags(ext_key, client):
    r = client.post("/api/ext/pikpak", headers=H(ext_key), json={
        "items": [FOLDER],
        "model_name": "九言",
        "tags": ["模特", "Cosplay"],
    })
    body = r.json()
    assert body["ok"] is True and body["queued"] == 1 and body["skipped"] == 0
    assert body["batchId"]

    jobs = _jobs()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.file_id == "album-1" and j.name == "坎特蕾拉写真"
    assert j.status == "queued"
    assert j.model_name == "九言"
    assert j.tags == "模特,Cosplay"
    assert j.is_archive is False
    # 展开出的文件明细各占一行, rel 带上相对路径
    assert j.files_total == 3
    fs = _files(j.id)
    assert [f.rel for f in fs] == ["001.jpg", "002.jpg", "003.jpg"]
    assert [f.url for f in fs][0] == "https://dl.mypikpak.com/a.jpg"
    assert all(f.status == "queued" for f in fs)


def test_pikpak_archive_item(ext_key, client):
    """压缩包勾选项: 单文件, 落库标 is_archive(worker 下载后解压)。"""
    r = client.post("/api/ext/pikpak", headers=H(ext_key),
                    json={"items": [ZIP], "model_name": "半半子"})
    assert r.json()["queued"] == 1
    j = _jobs()[0]
    assert j.is_archive is True
    assert j.files_total == 1
    assert _files(j.id)[0].rel == "album.zip"


def test_pikpak_batch(ext_key, client):
    items = [_item(f"a-{i}", f"写真 {i}", [
        {"file_id": f"f{i}", "url": f"https://d/{i}.jpg", "rel": f"{i}.jpg"},
    ]) for i in range(3)]
    r = client.post("/api/ext/pikpak", headers=H(ext_key),
                    json={"items": items, "model_name": "半半子"})
    assert r.json()["queued"] == 3
    assert len(_jobs()) == 3


def test_pikpak_dedupes_by_file_id(ext_key, client):
    """同勾选项(同 file_id)已在队列 → 跳过(不重复入队)。"""
    r1 = client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [FOLDER]})
    assert r1.json()["queued"] == 1
    r2 = client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [FOLDER]})
    body = r2.json()
    assert body["queued"] == 0 and body["skipped"] == 1
    assert body["ok"] is False
    assert len(_jobs()) == 1


def test_pikpak_dedupes_after_finished(ext_key, client):
    """已下载完成的勾选项(终态)再推 → 也跳过, 不重复入队。"""
    client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [FOLDER]})
    from app.database import SessionLocal
    from app.db import PikPakJob

    s = SessionLocal()
    try:
        for j in s.query(PikPakJob).all():
            j.status = "done"
        s.commit()
    finally:
        s.close()
    r = client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [FOLDER]})
    assert r.json()["queued"] == 0 and r.json()["skipped"] == 1
    assert len(_jobs()) == 1


def test_pikpak_rejects_too_many_files(ext_key, client):
    """展开后文件总数超上限 → 422(防请求体过大)。"""
    from app.routers import ext_api

    files = [{"file_id": f"f{i}", "url": f"https://d/{i}.jpg", "rel": f"{i}.jpg"}
             for i in range(3)]
    item = {"file_id": "big", "name": "big", "files": files}
    old = ext_api.MAX_PIKPAK_FILES
    ext_api.MAX_PIKPAK_FILES = 2
    try:
        r = client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [item]})
        assert r.status_code == 422
    finally:
        ext_api.MAX_PIKPAK_FILES = old


def test_pikpak_subdir_rel_paths_preserved(ext_key, client):
    """勾选项里有子文件夹 → rel 带层级路径, worker 据此建子目录。"""
    item = _item("nested-1", "写真集", [
        {"file_id": "n1", "url": "https://d/1.jpg", "rel": "vol1/001.jpg"},
        {"file_id": "n2", "url": "https://d/2.jpg", "rel": "vol1/002.jpg"},
        {"file_id": "n3", "url": "https://d/3.jpg", "rel": "vol2/001.jpg"},
    ])
    client.post("/api/ext/pikpak", headers=H(ext_key), json={"items": [item]})
    j = _jobs()[0]
    assert [f.rel for f in _files(j.id)] == ["vol1/001.jpg", "vol1/002.jpg",
                                             "vol2/001.jpg"]


def test_pikpak_skips_items_without_files(ext_key, client):
    """没解析出任何直链的勾选项被过滤, 不占任务位。"""
    r = client.post("/api/ext/pikpak", headers=H(ext_key), json={
        "items": [_item("no-files", "空", []),
                  _item("empty-url", "空", [{"file_id": "x", "url": "  "}]),
                  FOLDER],
    })
    body = r.json()
    assert body["queued"] == 1 and body["skipped"] == 2
    jobs = _jobs()
    assert len(jobs) == 1 and jobs[0].file_id == "album-1"


def test_pikpak_skips_items_without_file_id(ext_key, client):
    r = client.post("/api/ext/pikpak", headers=H(ext_key), json={
        "items": [{"file_id": "", "name": "x", "files": [
            {"url": "https://d/1.jpg", "rel": "1.jpg"}]}]})
    assert r.json()["queued"] == 0
    assert not _jobs()


def test_pikpak_empty_model_becomes_uncategorized(ext_key, client):
    """模特名留空 → model_name 为 None(导入时归「未分类」)。"""
    r = client.post("/api/ext/pikpak", headers=H(ext_key),
                    json={"items": [FOLDER], "model_name": "   "})
    assert r.json()["queued"] == 1
    assert _jobs()[0].model_name is None


def test_pikpak_tags_joined(ext_key, client):
    r = client.post("/api/ext/pikpak", headers=H(ext_key), json={
        "items": [FOLDER], "tags": ["模特", "Cosplay", "", "  "]})
    # 空串 tag 不入库
    assert _jobs()[0].tags == "模特,Cosplay"


def test_pikpak_size_sums_from_files(ext_key, client):
    """勾选项总大小按其 files 求和(脚本传的 size 兜底)。"""
    r = client.post("/api/ext/pikpak", headers=H(ext_key),
                    json={"items": [FOLDER], "model_name": "九言"})
    assert r.json()["queued"] == 1
    assert _jobs()[0].size == 600
