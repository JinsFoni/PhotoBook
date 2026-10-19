"""删除写真集: 远端清理必须后台化, handler 不能是 async。

故障现场(2026-10-20, 绿联 NAS 实测):
- 管理后台删一本 137 张的写真集要等 70s+, 773 张的那本 6min+;
- 删 40 张期间 /healthz 要 22s 才返回 —— 整站被钉死。

三个叠加原因, 对应下面三条回归:
1. WebDAV 无批量删除, ``purge_remote_of_collection`` 逐张 DELETE
   (115 盘实测 0.48s/张), 却跑在请求线程里;
2. 该 handler 是 ``async def``, 里面全是同步网络/文件 IO, 直接堵事件循环;
3. 模特删除会把名下每个写真集串行清一遍远端。
"""

from __future__ import annotations

import inspect
import time

from app.database import SessionLocal
from app.db import Collection, Model, Photo, PhotoUpload, Storage
from app.routers import admin as admin_router
from app.services import storage as storage_svc
from app.services.storage import base as storage_base


def _mk_storage(name: str) -> int:
    s = SessionLocal()
    try:
        st = Storage(name=name, type="webdav", api_url="http://127.0.0.1:1",
                     username="u", token="p", enabled=False)
        s.add(st)
        s.commit()
        return st.id
    finally:
        s.close()


def _mk_collection(slug: str, n: int, storage_id: int) -> int:
    s = SessionLocal()
    try:
        col = Collection(slug=slug, title=slug, status="draft")
        s.add(col)
        s.flush()
        for i in range(n):
            p = Photo(collection_id=col.id, filename=f"{slug}/{i}.jpg",
                      width=10, height=10, sort_order=i)
            s.add(p)
            s.flush()
            s.add(PhotoUpload(photo_id=p.id, storage_id=storage_id,
                              remote_path=f"root/{slug}/{i}.jpg"))
        s.commit()
        return col.id
    finally:
        s.close()


def test_collection_delete_handlers_are_sync():
    """同步 def 才会被 Starlette 丢进线程池; async def + 阻塞 IO = 全站卡死。"""
    assert not inspect.iscoroutinefunction(admin_router.admin_collection_delete)
    assert not inspect.iscoroutinefunction(admin_router.admin_model_delete)


def test_delete_collection_defers_remote_purge(admin_client, monkeypatch):
    st_id = _mk_storage("zz-defer-storage")
    cid = _mk_collection("zz-defer-collection", 3, st_id)

    seen: dict = {}

    def fake_purge(by_storage, collection_id, label=""):
        seen["by_storage"] = by_storage
        seen["collection_id"] = collection_id
        seen["label"] = label
        return sum(len(v) for v in by_storage.values())

    monkeypatch.setattr(admin_router, "purge_remote_async", fake_purge)

    t0 = time.perf_counter()
    r = admin_client.post(f"/admin/collections/{cid}/delete", follow_redirects=False)
    elapsed = time.perf_counter() - t0

    assert r.status_code in (302, 303)
    assert elapsed < 2.0, f"删除请求不该等远端清理, 实测 {elapsed:.1f}s"
    # 远端清单在删行前快照, 按存储分组交给后台
    assert seen["collection_id"] == cid
    assert seen["label"] == "zz-defer-collection"
    assert seen["by_storage"][st_id] == [
        f"root/zz-defer-collection/{i}.jpg" for i in range(3)]
    # 本地(DB)删除已完成, photo_uploads 随 photos 级联清空
    s = SessionLocal()
    try:
        assert s.get(Collection, cid) is None
        assert s.query(PhotoUpload).filter_by(storage_id=st_id).count() == 0
    finally:
        s.close()


def test_model_delete_defers_remote_purge_for_every_collection(admin_client, monkeypatch):
    st_id = _mk_storage("zz-model-storage")
    s = SessionLocal()
    try:
        m = Model(slug="zz-model-defer", name="ZZ 模特", status="published")
        s.add(m)
        s.commit()
        mid = m.id
    finally:
        s.close()
    for i in range(2):
        s = SessionLocal()
        try:
            col = Collection(slug=f"zz-model-col-{i}", title=f"zz{i}",
                             model_id=mid, status="draft")
            s.add(col)
            s.flush()
            p = Photo(collection_id=col.id, filename=f"zz-model-col-{i}/0.jpg",
                      width=10, height=10, sort_order=0)
            s.add(p)
            s.flush()
            s.add(PhotoUpload(photo_id=p.id, storage_id=st_id,
                              remote_path=f"root/zz-model-col-{i}/0.jpg"))
            s.commit()
        finally:
            s.close()

    calls: list[tuple] = []
    monkeypatch.setattr(admin_router, "purge_remote_async",
                        lambda by_storage, col_id, label="": calls.append((col_id, label)))

    t0 = time.perf_counter()
    r = admin_client.post(f"/admin/models/{mid}/delete", follow_redirects=False)
    elapsed = time.perf_counter() - t0

    assert r.status_code in (302, 303)
    assert elapsed < 3.0
    assert sorted(label for _cid, label in calls) == ["zz-model-col-0", "zz-model-col-1"]
    s = SessionLocal()
    try:
        assert s.get(Model, mid) is None
        assert s.query(PhotoUpload).filter_by(storage_id=st_id).count() == 0
    finally:
        s.close()


def test_purge_chunk_skips_paths_reuploaded_meanwhile(monkeypatch):
    """后台清理要跑几十秒到几分钟; 期间同一本写真集可能被重新导入上传。

    远端路径相同, 照单全删会误删刚上传的新文件 —— 删前回查 photo_uploads。
    """
    st_id = _mk_storage("zz-guard-storage")
    cid = _mk_collection("zz-guard-collection", 2, st_id)
    paths = [f"root/zz-guard-collection/{i}.jpg" for i in range(2)]

    # 删掉原写真集(级联清 photo_uploads), 再把第 0 张「重新上传」回来
    s = SessionLocal()
    try:
        s.delete(s.get(Collection, cid))
        s.commit()
        col = Collection(slug="zz-guard-reimport", title="reimport", status="draft")
        s.add(col)
        s.flush()
        p = Photo(collection_id=col.id, filename="zz-guard-reimport/0.jpg",
                  width=10, height=10, sort_order=0)
        s.add(p)
        s.flush()
        s.add(PhotoUpload(photo_id=p.id, storage_id=st_id, remote_path=paths[0]))
        s.commit()
    finally:
        s.close()

    deleted: list[str] = []

    class FakeBackend:
        def delete_batch(self, st, remote_paths):
            deleted.extend(remote_paths)

    monkeypatch.setattr(storage_base, "get_backend", lambda st: FakeBackend())
    storage_svc._purge_dir(st_id, "root/zz-guard-collection",
                           ["0.jpg", "1.jpg"], cid, "zz-guard-collection")

    assert deleted == [paths[1]], "仍被 photo_uploads 引用的路径不能删"


def test_collect_remote_paths_groups_by_storage():
    st1 = _mk_storage("zz-collect-a")
    st2 = _mk_storage("zz-collect-b")
    s = SessionLocal()
    try:
        col = Collection(slug="zz-collect-paths", title="zz", status="draft")
        s.add(col)
        s.flush()
        for i, sid in enumerate((st1, st2)):
            p = Photo(collection_id=col.id, filename=f"zz-collect-paths/{i}.jpg",
                      width=10, height=10, sort_order=i)
            s.add(p)
            s.flush()
            s.add(PhotoUpload(photo_id=p.id, storage_id=sid,
                              remote_path=f"root/zz-collect-paths/{i}.jpg"))
        s.commit()
        by_storage = storage_svc.collect_remote_paths(col.id, s)
        assert by_storage == {st1: ["root/zz-collect-paths/0.jpg"],
                              st2: ["root/zz-collect-paths/1.jpg"]}
    finally:
        s.rollback()
        s.delete(s.get(Collection, col.id))
        s.commit()
        s.close()
