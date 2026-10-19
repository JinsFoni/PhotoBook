"""上传 worker 并发 —— 每个存储同时在飞的 PUT 数受 UPLOAD_CONCURRENCY 约束。

上传是「一个文件一个请求」(WebDAV 与 OpenList 都没有批量上传接口), 并发是
唯一能提速的维度。这里用一个打桩 backend 记录峰值并发数, 不碰网络。
"""

from __future__ import annotations

import threading
import time

from app.database import SessionLocal
from app.db import Collection, Photo, PhotoUpload, Storage, UploadJob
from app.services import media
from app.services.storage import base as storage_base
from app.services.storage import worker as upload_worker

SLUG = "zz-conc"


class _ConcBackend:
    """记录峰值并发; upload 睡一小会儿, 让并发真的叠起来。"""

    peak = 0
    inflight = 0
    lock = threading.Lock()
    done: list[str] = []

    def upload(self, st, data, filename, remote_folder):
        cls = type(self)
        with cls.lock:
            cls.inflight += 1
            cls.peak = max(cls.peak, cls.inflight)
        time.sleep(0.02)
        with cls.lock:
            cls.inflight -= 1
            cls.done.append(f"{remote_folder}/{filename}")
        return f"{remote_folder}/{filename}"

    def delete_batch(self, st, remote_paths):
        pass

    def public_url(self, st, remote_path):
        return remote_path

    def test_connection(self, st):
        return "ok"

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.peak = 0
            cls.inflight = 0
            cls.done = []


class _VerifyFailBackend(_ConcBackend):
    """上传成功但远端列表永远是空的 → 校验必须判失败, 不能假装完成。"""

    def list_sizes(self, st, remote_dir):
        return {}

    def delete_dir(self, st, remote_dir, allowed=None):
        return False


def _mk_case(kind: str, n: int = 12) -> tuple[int, int]:
    """建写真集 + 本地原图 + 一个存储, 返回 (collection_id, job_id)。"""
    s = SessionLocal()
    try:
        st = Storage(name=f"zz-{kind}-conc", type=kind, api_url="http://127.0.0.1:1",
                     root_dir="/root", enabled=True)
        s.add(st)
        s.flush()
        col = Collection(slug=SLUG, title=SLUG, status="draft")
        s.add(col)
        s.flush()
        for i in range(n):
            rel = f"{SLUG}/{i:03d}.jpg"
            p = Photo(collection_id=col.id, filename=rel, width=10, height=10,
                      sort_order=i)
            s.add(p)
            local = media.abs_path(rel)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b"\xff\xd8\xff" + b"x" * 64)
        s.flush()
        job = UploadJob(collection_id=col.id, storage_id=st.id, status="running",
                        photos_total=n)
        s.add(job)
        s.commit()
        return col.id, job.id
    finally:
        s.close()


def _cleanup(cid: int, sid: int):
    s = SessionLocal()
    try:
        s.query(PhotoUpload).filter_by(storage_id=sid).delete()
        s.query(UploadJob).filter_by(storage_id=sid).delete()
        col = s.get(Collection, cid)
        if col is not None:
            s.delete(col)
        st = s.get(Storage, sid)
        if st is not None:
            s.delete(st)
        s.commit()
    finally:
        s.close()
    for f in (media.abs_path(f"{SLUG}/{i:03d}.jpg") for i in range(30)):
        try:
            f.unlink()
        except OSError:
            pass


def test_group_uploads_concurrently(monkeypatch):
    _ConcBackend.reset()
    storage_base.BACKENDS["zzconc"] = _ConcBackend
    try:
        cid, jid = _mk_case("zzconc")
        s = SessionLocal()
        try:
            sid = s.get(UploadJob, jid).storage_id
        finally:
            s.close()

        upload_worker._run_group([jid])

        s = SessionLocal()
        try:
            job = s.get(UploadJob, jid)
            assert job.status == "done", job.error
            assert job.photos_done == 12
            assert s.query(PhotoUpload).filter_by(storage_id=sid).count() == 12
        finally:
            s.close()
        assert len(_ConcBackend.done) == 12
        assert 1 < _ConcBackend.peak <= upload_worker.UPLOAD_CONCURRENCY, \
            f"峰值并发 {_ConcBackend.peak}, 期望 2..{upload_worker.UPLOAD_CONCURRENCY}"
    finally:
        storage_base.BACKENDS.pop("zzconc", None)
        _cleanup(cid, sid)


def test_group_fails_when_remote_verify_mismatch(monkeypatch):
    """远端列表说文件都没了 → 重传一次仍不符, 任务必须 failed 而不是 done。"""
    _VerifyFailBackend.reset()
    storage_base.BACKENDS["zzvfail"] = _VerifyFailBackend
    try:
        cid, jid = _mk_case("zzvfail", n=4)
        s = SessionLocal()
        try:
            sid = s.get(UploadJob, jid).storage_id
        finally:
            s.close()

        upload_worker._run_group([jid])

        s = SessionLocal()
        try:
            job = s.get(UploadJob, jid)
            assert job.status == "failed"
            assert "校验失败" in (job.error or "")
        finally:
            s.close()
        # 重传发生在校验之后: 4 张首传 + 4 张重传
        assert len(_VerifyFailBackend.done) == 8
        # 失败的任务不能删本地原图(还要留着重传)
        assert media.abs_path(f"{SLUG}/000.jpg").is_file()
    finally:
        storage_base.BACKENDS.pop("zzvfail", None)
        _cleanup(cid, sid)
