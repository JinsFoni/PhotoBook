"""上传 worker 并发 —— 每个存储同时在飞的 PUT 数受 UPLOAD_CONCURRENCY 约束。

上传是「一个文件一个请求」(WebDAV 与 OpenList 都没有批量上传接口), 并发是
唯一能提速的维度。这里用一个打桩 backend 记录峰值并发数, 不碰网络。
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from sqlalchemy import select

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
            assert job.photos_done == 0, "判失败的照片数不该还算已完成"
            # 校验没过的行必须撤掉, 否则重试会把它当已上传跳过
            assert s.query(PhotoUpload).filter_by(storage_id=sid).count() == 0
        finally:
            s.close()
        # 重传发生在校验之后: 4 张首传 + 4 张重传
        assert len(_VerifyFailBackend.done) == 8
        # 失败的任务不能删本地原图(还要留着重传)
        assert media.abs_path(f"{SLUG}/000.jpg").is_file()
    finally:
        storage_base.BACKENDS.pop("zzvfail", None)
        _cleanup(cid, sid)


class _StoreBackend:
    """内存里真的存文件: upload 收下, list_sizes 如实回大小。"""

    files: dict[str, int] = {}

    def upload(self, st, data, filename, remote_folder):
        rp = f"{remote_folder}/{filename}"
        type(self).files[rp] = len(data)
        return rp

    def list_sizes(self, st, remote_dir):
        pre = remote_dir.strip("/") + "/"
        return {k[len(pre):]: v for k, v in type(self).files.items()
                if k.startswith(pre)}

    def delete_dir(self, st, remote_dir, allowed=None):
        return True

    def delete_batch(self, st, remote_paths):
        pass

    def public_url(self, st, remote_path):
        return remote_path

    def test_connection(self, st):
        return "ok"

    @classmethod
    def reset(cls):
        cls.files = {}


class _DropBackend(_StoreBackend):
    """fs/put 回 200 但字节没落地 —— 123 盘真实出现过的形态(不是杜撰)。"""

    files: dict[str, int] = {}  # 自己的空账本, 不能跟另一个存储共用

    def upload(self, st, data, filename, remote_folder):
        return f"{remote_folder}/{filename}"


@contextmanager
def _only_enabled(sids: list[int]):
    """临时停用别的存储。

    「能否删本地原图」按「所有启用的存储都已上传」判定, 全量跑测试时库里的
    其它存储会让这批照片永远算没传完 —— 这个用例只关心自己建的两个。
    """
    s = SessionLocal()
    others: list[Storage] = []
    try:
        for st in s.scalars(select(Storage).where(Storage.enabled == True)).all():  # noqa: E712
            if st.id not in sids:
                st.enabled = False
                others.append(st)
        s.commit()
    finally:
        s.close()
    try:
        yield
    finally:
        s = SessionLocal()
        try:
            for st in others:
                row = s.get(Storage, st.id)
                if row is not None:
                    row.enabled = True
            s.commit()
        finally:
            s.close()


def _mk_two_storage_case(kinds: tuple[str, str], n: int = 3):
    """一个写真集 + 两个启用的存储, 两个任务同时 running。"""
    s = SessionLocal()
    try:
        col = Collection(slug=SLUG, title=SLUG, status="draft")
        s.add(col)
        s.flush()
        for i in range(n):
            rel = f"{SLUG}/{i:03d}.jpg"
            s.add(Photo(collection_id=col.id, filename=rel, width=10, height=10,
                        sort_order=i))
            local = media.abs_path(rel)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b"\xff\xd8\xff" + b"x" * 64)
        s.flush()
        sids, jids = [], []
        for kind in kinds:
            st = Storage(name=f"zz-{kind}-sib", type=kind, api_url="http://127.0.0.1:1",
                         root_dir="/root", enabled=True)
            s.add(st)
            s.flush()
            job = UploadJob(collection_id=col.id, storage_id=st.id, status="running",
                            photos_total=n)
            s.add(job)
            s.flush()
            sids.append(st.id)
            jids.append(job.id)
        s.commit()
        return col.id, sids, jids
    finally:
        s.close()


def test_originals_kept_when_sibling_storage_drops_files(monkeypatch):
    """一个存储掉了文件(校验失败)时, 另一个存储收尾不得删本地原图。

    本地原图是所有存储共用的唯一字节来源; 删了就没法补传, 只能从备份存储
    回补(线上 ID13/ID28 就是这么丢的两张)。
    """
    _StoreBackend.reset()
    storage_base.BACKENDS["zzok"] = _StoreBackend
    storage_base.BACKENDS["zzdrop"] = _DropBackend
    # 缩略图缓存门槛在本用例里不关心, 直接放行
    monkeypatch.setattr(upload_worker.media, "thumb_cache_ready", lambda rel: True)
    monkeypatch.setattr(upload_worker.media, "cleanup_empty_dirs", lambda rel: None)
    cid = None
    try:
        cid, sids, jids = _mk_two_storage_case(("zzok", "zzdrop"))
        with _only_enabled(sids):
            upload_worker._run_group(jids)

        s = SessionLocal()
        try:
            ok = s.get(UploadJob, jids[0])
            drop = s.get(UploadJob, jids[1])
            assert ok.status == "done", ok.error
            assert drop.status == "failed", drop.error
            assert "校验失败" in (drop.error or "")
            assert "保留本地原图" in (ok.error or ""), ok.error
        finally:
            s.close()
        for i in range(3):
            assert media.abs_path(f"{SLUG}/{i:03d}.jpg").is_file(), \
                f"{i:03d}.jpg 被误删, 掉文件的存储就再也补不上了"
    finally:
        storage_base.BACKENDS.pop("zzok", None)
        storage_base.BACKENDS.pop("zzdrop", None)
        if cid:
            _cleanup(cid, sids[0])
            _cleanup(cid, sids[1])


def test_originals_deleted_when_all_storages_pass(monkeypatch):
    """两个存储都校验通过时, 原图照常删(别把删除逻辑改成永不删)。"""
    _StoreBackend.reset()
    storage_base.BACKENDS["zzok"] = _StoreBackend
    monkeypatch.setattr(upload_worker.media, "thumb_cache_ready", lambda rel: True)
    monkeypatch.setattr(upload_worker.media, "cleanup_empty_dirs", lambda rel: None)
    cid = None
    try:
        cid, sids, jids = _mk_two_storage_case(("zzok", "zzok"))
        with _only_enabled(sids):
            upload_worker._run_group(jids)
        s = SessionLocal()
        try:
            jobs = [s.get(UploadJob, j) for j in jids]
            assert [j.status for j in jobs] == ["done", "done"], [j.error for j in jobs]
        finally:
            s.close()
        assert not media.abs_path(f"{SLUG}/000.jpg").is_file()
    finally:
        storage_base.BACKENDS.pop("zzok", None)
        if cid:
            _cleanup(cid, sids[0])
            _cleanup(cid, sids[1])
