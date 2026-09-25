"""tagging(M5 补课)— 采集 tag 落库:apply_tags 幂等打标、retag_from_history 补录。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.database import SessionLocal
from app.db import Collection, CollectionTag, HarvestJob, Model, ModelTag, Tag
from app.services import tagging


def test_apply_tags_creates_and_links(s=None):
    """apply_tags: 新 tag 建记录,合集与模特同时挂上。"""
    s = SessionLocal()
    try:
        m = Model(slug="tagtest-model", name="TagTest Model", status="published")
        s.add(m)
        s.flush()
        c = Collection(slug="tagtest-col", title="TagTest Col", model_id=m.id,
                       status="published")
        s.add(c)
        s.flush()
        n = tagging.apply_tags(s, c, m, ["Cosplay", "Swimsuit", " Cosplay "])
        s.flush()
        # 去重后 2 个新 tag,合集+模特各 2 条关联
        assert n == 4, f"added={n}"
        assert s.scalar(select(func.count(Tag.id))) >= 2
        assert s.scalar(select(func.count(CollectionTag.collection_id))
                        .where(CollectionTag.collection_id == c.id)) == 2
        assert s.scalar(select(func.count(ModelTag.model_id))
                        .where(ModelTag.model_id == m.id)) == 2
        # 幂等:再跑一遍不新增
        n2 = tagging.apply_tags(s, c, m, ["Cosplay", "Swimsuit"])
        assert n2 == 0
        assert s.scalar(select(func.count(CollectionTag.collection_id))
                        .where(CollectionTag.collection_id == c.id)) == 2
    finally:
        s.rollback()
        s.close()


def test_apply_tags_empty_noop():
    """空 tag 列表或无挂载对象 → 直接返回 0。"""
    s = SessionLocal()
    try:
        assert tagging.apply_tags(s, None, None, ["x"]) == 0
        assert tagging.apply_tags(s, None, None, []) == 0
    finally:
        s.close()


def test_retag_from_history_matches_and_skips(monkeypatch):
    """retag_from_history: done 任务按 title 匹配合集并打标(清空任务表防种子串扰)。"""
    s = SessionLocal()
    try:
        for j in s.scalars(select(HarvestJob)).all():
            s.delete(j)
        s.flush()
        c = Collection(slug="retag-col", title="[JP] Retag Target: FRIDA", 
                       status="published")
        s.add(c)
        s.flush()
        job = HarvestJob(serial=990001, url="https://example.com/retag-target",
                         title="[JP] Retag Target: FRIDA", status="done")
        s.add(job)
        s.flush()

        class FakeTarget:
            tags = ["Gravure", "Weekly"]

        monkeypatch.setattr(tagging.net, "fetch_html", lambda url, **kw: "<html>")
        monkeypatch.setattr(tagging.net, "parse_detail_page",
                            lambda url, **kw: FakeTarget())
        stats = tagging.retag_from_history(s)
        assert stats["matched"] >= 1
        assert stats["tagged"] >= 2
        tags_now = [t.name for t in
                    s.scalar(select(Collection).where(Collection.slug == "retag-col")).tags]
        assert "Gravure" in tags_now and "Weekly" in tags_now
    finally:
        s.rollback()
        s.close()


def test_retag_skips_without_collection(monkeypatch):
    """title 对不上任何合集 → skipped,不建 tag(清空任务表防种子串扰)。"""
    s = SessionLocal()
    try:
        for j in s.scalars(select(HarvestJob)).all():
            s.delete(j)
        s.flush()
        job = HarvestJob(serial=990002, url="https://example.com/orphan",
                         title="Orphan No Match", status="done")
        s.add(job)
        s.flush()
        monkeypatch.setattr(tagging.net, "fetch_html", lambda url, **kw: "<html>")

        class FakeTarget:
            tags = ["X"]

        monkeypatch.setattr(tagging.net, "parse_detail_page",
                            lambda url, **kw: FakeTarget())
        before = s.scalar(select(func.count(Tag.id)))
        stats = tagging.retag_from_history(s)
        assert s.scalar(select(func.count(Tag.id))) == before
        assert stats["skipped"] >= 1
    finally:
        s.rollback()
        s.close()
