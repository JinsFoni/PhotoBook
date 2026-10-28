"""上传校验的重传轮次 + 原图保留按「每个存储的最新任务」判断。

2026-10-29 线上 879(`Coser@Machi馬吉 - Castorice Swimsuit`,131 张,每张 17-24MB)
上传到 123 盘卡在 128/131:三张 `fs/put` 回 200 但文件没落地。原来只重传一轮,
三张两轮都没落地 → 任务判 failed,页面一直显示 128/131(用户眼里就是「卡住」)。
隔一阵手工单张重传,一次就上去了 —— 说明是概率丢包,得给几轮带间隔的重传。

顺带:重试成功后新建的任务是 done,但早先那条 failed 还在,`_originals_needed`
按「任意一条 failed 就保留」判断 → 原图(3GB)永远删不掉、任务还报
「完成,保留本地原图(其他存储上传失败)」。所以改成每个存储只看最新那条。
"""

from __future__ import annotations

from app.database import SessionLocal
from app.db import Collection, Photo, PhotoUpload, Storage, UploadJob
from app.services import media
from app.services.storage import base as storage_base
from app.services.storage import worker as upload_worker

SLUG = "zz-verify-retry"


class _FlakyBackend:
    """前 drop_first 次 PUT 静默丢文件(回 200 不落地), 之后正常落盘。"""

    def __init__(self, drop_first: int = 2):
        self.drop_first = drop_first
        self.store: dict[str, bytes] = {}
        self.attempts: dict[str, int] = {}

    def upload(self, st, data, filename, remote_folder):
        rp = f"{remote_folder}/{filename}"
        n = self.attempts.get(rp, 0) + 1
        self.attempts[rp] = n
        if n > self.drop_first:
            self.store[rp] = data
        return rp

    def list_sizes(self, st, remote_dir):
        return {rp.rsplit("/", 1)[-1]: len(b)
                for rp, b in self.store.items()
                if rp.rsplit("/", 1)[0] == remote_dir}

    def delete_dir(self, st, remote_dir, allowed=None):
        return False


def _mk(n: int = 1):
    s = SessionLocal()
    try:
        st = Storage(name="zz-flaky", type="zzflaky", api_url="http://127.0.0.1:1",
                     root_dir="/root", enabled=True)
        s.add(st)
        s.flush()
        col = Collection(slug=SLUG, title=SLUG, status="draft")
        s.add(col)
        s.flush()
        rels = []
        for i in range(n):
            rel = f"{SLUG}/{i:03d}.jpg"
            s.add(Photo(collection_id=col.id, filename=rel, width=10, height=10,
                        sort_order=i))
            local = media.abs_path(rel)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b"\xff\xd8\xff" + b"y" * 128)
            rels.append(rel)
        s.flush()
        job = UploadJob(collection_id=col.id, storage_id=st.id, status="running",
                        photos_total=n)
        s.add(job)
        s.commit()
        return col.id, st.id, job.id, rels
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
    for i in range(5):
        try:
            media.abs_path(f"{SLUG}/{i:03d}.jpg").unlink()
        except OSError:
            pass


def test_verify_recovers_from_transient_silent_drops(monkeypatch):
    """回 200 但不落地是概率事件: 隔一轮重传就能补齐, 任务不该判失败。"""
    monkeypatch.setattr(upload_worker, "_VERIFY_PAUSES", (0.0, 0.0, 0.0))
    backend = _FlakyBackend(drop_first=2)      # 每张前两次静默丢
    storage_base.BACKENDS["zzflaky"] = backend
    cid = sid = None
    try:
        cid, sid, jid, rels = _mk(n=1)
        rel = rels[0]
        rp = f"root/{rel.rsplit('/', 1)[-1]}"       # 远端就是 root/ 下的文件名
        with SessionLocal() as s:
            st = s.get(Storage, sid)
            job = s.get(UploadJob, jid)
            s.add(PhotoUpload(photo_id=s.query(Photo).filter_by(filename=rel).one().id,
                             storage_id=sid, remote_path=rp))
            s.flush()
            upload_worker._verify_job(s, st, backend, job,
                                     {rp: (rel, media.abs_path(rel).stat().st_size)},
                                     remote_root="root")
            s.commit()
            assert job.status != "failed", job.error
            assert backend.store.get(rp)            # 第三次终于落地
            assert backend.attempts[rp] == 3        # 前两次静默丢, 第三次成功
    finally:
        storage_base.BACKENDS.pop("zzflaky", None)
        if cid and sid:
            _cleanup(cid, sid)


def test_verify_still_fails_after_all_rounds(monkeypatch):
    """一直丢就该判失败, 并把 photo_uploads 行撤掉(重试才会真重传)。"""
    monkeypatch.setattr(upload_worker, "_VERIFY_PAUSES", (0.0, 0.0))
    backend = _FlakyBackend(drop_first=99)
    storage_base.BACKENDS["zzflaky"] = backend
    cid = sid = None
    try:
        cid, sid, jid, rels = _mk(n=1)
        rel = rels[0]
        rp = f"root/{rel.rsplit('/', 1)[-1]}"
        with SessionLocal() as s:
            st = s.get(Storage, sid)
            job = s.get(UploadJob, jid)
            s.add(PhotoUpload(photo_id=s.query(Photo).filter_by(filename=rel).one().id,
                             storage_id=sid, remote_path=rp))
            s.flush()
            upload_worker._verify_job(s, st, backend, job,
                                     {rp: (rel, media.abs_path(rel).stat().st_size)},
                                     remote_root="root")
            s.commit()
            assert job.status == "failed"
            assert "校验失败" in (job.error or "")
            assert s.query(PhotoUpload).filter_by(storage_id=sid).count() == 0
    finally:
        storage_base.BACKENDS.pop("zzflaky", None)
        if cid and sid:
            _cleanup(cid, sid)


def test_originals_freed_after_successful_retry():
    """同一存储重试成功后, 早先那条 failed 不该再把本地原图钉住。"""
    cid = sid = None
    try:
        cid, sid, jid, rels = _mk(n=1)
        with SessionLocal() as s:
            old = s.get(UploadJob, jid)
            old.status = "failed"                # _mk 那条当「早先失败的那次」
            s.add(UploadJob(collection_id=cid, storage_id=sid, status="done",
                            photos_total=1))     # 重试新建的任务, 成功了
            s.commit()
            new = s.query(UploadJob).filter(UploadJob.id != jid).one()
            assert new.id > old.id
            assert upload_worker._originals_needed(s, new) is None

            # 反过来: 最新那条是失败的, 原图仍要保留
            new.status = "failed"
            s.commit()
            assert upload_worker._originals_needed(s, old) == "其他存储上传失败"
    finally:
        if cid and sid:
            _cleanup(cid, sid)
