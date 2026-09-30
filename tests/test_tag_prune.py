"""孤儿标签清理: 合集/模特删除后, 关联清零的标签应被自动删除。

背景: collection_tags/model_tags 关联表无 ORM 级联, 删除合集/模特后
关联行靠 DB 外键 CASCADE 清掉, 但 tag 本体会成为 0 关联孤儿继续显示。
"""

from __future__ import annotations

from app.db import Collection, Model, Tag
from app.database import SessionLocal
from app.services import tagging


def _cleanup(names: list[str]) -> None:
    """按名字清场, 避免上次运行残留影响断言。"""
    s = SessionLocal()
    try:
        for name in names:
            for t in s.query(Tag).filter(Tag.name == name).all():
                s.delete(t)
            for m in s.query(Model).filter(Model.name == name).all():
                for c in s.query(Collection).filter(Collection.model_id == m.id).all():
                    s.delete(c)
                s.delete(m)
        s.commit()
    finally:
        s.close()


def _mk(tag_name: str, *, with_collection: bool, with_model: bool):
    s = SessionLocal()
    try:
        t = Tag(name=tag_name, slug=tag_name)
        s.add(t)
        m = c = None
        if with_model:
            m = Model(name=tag_name, slug=tag_name)
            s.add(m)
        if with_collection:
            c = Collection(slug=tag_name, title=tag_name, status="published")
            s.add(c)
        s.flush()
        if with_model:
            m.tags.append(t)
        if with_collection:
            c.tags.append(t)
        s.commit()
        return t.id
    finally:
        s.close()


def test_prune_removes_orphan_tag():
    """既无合集也无模特关联的标签被删除。"""
    _cleanup(["tag-prune-a"])
    tid = _mk("tag-prune-a", with_collection=False, with_model=False)
    s = SessionLocal()
    try:
        n = tagging.prune_empty_tags(s)
        assert s.get(Tag, tid) is None
        assert n >= 1
    finally:
        s.close()
    _cleanup(["tag-prune-a"])


def test_prune_keeps_tag_with_collection():
    """有合集关联的标签保留。"""
    _cleanup(["tag-prune-b"])
    tid = _mk("tag-prune-b", with_collection=True, with_model=False)
    s = SessionLocal()
    try:
        tagging.prune_empty_tags(s)
        assert s.get(Tag, tid) is not None
    finally:
        s.close()
    _cleanup(["tag-prune-b"])


def test_prune_keeps_tag_with_model():
    """只有模特关联(无合集)的标签保留。"""
    _cleanup(["tag-prune-c"])
    tid = _mk("tag-prune-c", with_collection=False, with_model=True)
    s = SessionLocal()
    try:
        tagging.prune_empty_tags(s)
        assert s.get(Tag, tid) is not None
    finally:
        s.close()
    _cleanup(["tag-prune-c"])


def test_collection_delete_prunes_its_tags(admin_client):
    """删除最后一个关联合集后, 该标签随之删除(admin 路由级)。"""
    _cleanup(["tag-prune-d"])
    tid = _mk("tag-prune-d", with_collection=True, with_model=False)
    s = SessionLocal()
    try:
        col_id = s.query(Collection).filter(Collection.slug == "tag-prune-d").one().id
    finally:
        s.close()

    r = admin_client.post(f"/admin/collections/{col_id}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    s = SessionLocal()
    try:
        assert s.get(Tag, tid) is None, "关联清零的标签应被自动删除"
    finally:
        s.close()
    _cleanup(["tag-prune-d"])


def test_model_delete_prunes_model_only_tags(admin_client):
    """删除模特后, 仅剩模特关联的标签随之删除; 有其他合集关联的保留。"""
    _cleanup(["tag-prune-e", "tag-prune-f"])
    # tag-e 只有模特关联; tag-f 有关联合集, 再额外挂到将被删除的模特上
    tid_e = _mk("tag-prune-e", with_collection=False, with_model=True)
    tid_f = _mk("tag-prune-f", with_collection=True, with_model=False)

    s = SessionLocal()
    try:
        m = Model(name="tag-prune-owner", slug="tag-prune-owner")
        s.add(m)
        s.flush()
        m.tags.append(s.get(Tag, tid_f))
        s.commit()
        model_id = m.id
        model_e_id = s.query(Model).filter(Model.name == "tag-prune-e").one().id
    finally:
        s.close()

    r = admin_client.post(f"/admin/models/{model_id}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)
    r = admin_client.post(f"/admin/models/{model_e_id}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    s = SessionLocal()
    try:
        assert s.get(Tag, tid_e) is None, "仅剩模特关联的标签应被删除"
        assert s.get(Tag, tid_f) is not None, "仍有合集关联的标签应保留"
    finally:
        s.close()
    _cleanup(["tag-prune-e", "tag-prune-f"])
