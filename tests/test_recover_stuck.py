"""recover_stuck_processing 自愈: processing 集合入队, published 不动。"""
import os, sys, tempfile
sys.path.insert(0, os.getcwd())
TMP = tempfile.mkdtemp(prefix="pfrec-")
os.environ.update({"DATA_DIR": TMP+"/data", "MEDIA_DIR": TMP+"/media",
                   "LIBRARY_DIR": TMP+"/library", "SEED_DEMO": "0"})

def make(thumbs=False):
    """独立 app 实例造数据: 2 processing + 1 published。"""
    import logging; logging.disable(logging.CRITICAL)
    from app.database import SessionLocal, engine
    from app.db import Base, Collection, Model, Photo
    import app.services.media as media
    Base.metadata.create_all(engine)
    s = SessionLocal()
    m = Model(slug="m1", name="M1", status="published")
    s.add(m); s.flush()
    slugs = []
    for i, status in enumerate(["processing", "processing", "published"]):
        slug = f"c{i}-slug"
        slugs.append(slug)
        c = Collection(slug=slug, title=f"C{i}", model_id=m.id, status=status,
                       published_at="2026.01.0%d" % (i+1))
        s.add(c); s.flush()
        s.add(Photo(collection_id=c.id, filename=f"c{i}/a.jpg",
                    width=900, height=1200, sort_order=0))
    s.commit(); s.close()
    return slugs

def test_recover(monkeypatch):
    slugs = make()
    import app.services.media as media
    # 与其它测试隔离: 换掉共享队列/事件, 拦截 worker 拉起
    calls = []
    monkeypatch.setattr(media, "_thumb_queue", [])
    monkeypatch.setattr(media, "_thumb_wake", type(media._thumb_wake)())
    monkeypatch.setattr(media, "ensure_import_worker", lambda: calls.append(1))
    n = media.recover_stuck_processing()
    assert n == 2, f"expected 2, got {n}"
    with media._thumb_lock:
        assert sorted(media._thumb_queue) == sorted(slugs[:2]), media._thumb_queue
    assert len(calls) == 1
    # 幂等: 再跑一次不重复入队
    n2 = media.recover_stuck_processing()
    assert n2 == 2
    with media._thumb_lock:
        assert len(media._thumb_queue) == 2
    # 全 published 后: 入队 0
    from app.database import SessionLocal
    from app.db import Collection
    s = SessionLocal()
    for c in s.scalars(__import__("sqlalchemy").select(Collection)).all():
        c.status = "published"
    s.commit(); s.close()
    n3 = media.recover_stuck_processing()
    assert n3 == 0
    with media._thumb_lock:
        assert len(media._thumb_queue) == 2  # 未新增
    media._thumb_queue.clear()
