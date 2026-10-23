"""虚化主题垫底图 —— 合集按「最新入库」挑, 模特详情页兜底跟作品网格的发布日期序。

2026-10-24 修: `_blur_src` 原来按 `published_at`(源站发布日期)选合集, 与全站
「最新入库」(created_at)不是同一把尺子 —— 老站转载的旧作今天刚入库, 按发布
日期永远排在后面, 背景就永远不跟着新内容走(实测全库两个榜单前 10 名重合 0
条, 260 个模特里 47 个取到的是不同合集)。

2026-10-24 追加: 模特详情页作品网格改**发布日期**序(作品目录要按发行时间线看),
所以 `/models/<slug>` 的「没头像」兜底也跟着发布日期走 —— 背景恒等于网格第一张。
其余页面仍是入库序。
"""

from __future__ import annotations

import types
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.db import Collection, Model, Photo
from app.routers.web import _works_by_published
from app.templating import _blur_src

PREFIX = "zz-blur"
FAR_FUTURE = datetime(2099, 1, 1, 0, 0, 0)


def _request(path: str):
    """_blur_src 只用到 url.path 和 request.state。"""
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path),
                                 state=types.SimpleNamespace())


def _blur(path: str) -> str | None:
    return _blur_src(_request(path))


def _mk_collection(s, *, slug: str, model_id: int | None, created: datetime,
                   published: str | None, n_photos: int = 2) -> tuple[int, list[str]]:
    """建一本已发布写真集 + n 张照片, 返回 (id, [filename...])。"""
    c = Collection(slug=slug, title=slug, model_id=model_id, status="published",
                   created_at=created, published_at=published)
    s.add(c)
    s.flush()
    names = []
    for i in range(n_photos):
        rel = f"{slug}/{i:03d}.jpg"
        s.add(Photo(collection_id=c.id, filename=rel, width=10, height=10,
                    sort_order=i))
        names.append(rel)
    s.flush()
    return c.id, names


def _drop(slug: str, *, model: bool = False) -> None:
    """用例自建的数据必须当场删干净 —— DB 是会话级共享的, 多出来的已发布
    合集会被其它用例的「全库最新入库」兜底捡到。"""
    s = SessionLocal()
    try:
        cls = Model if model else Collection
        row = s.query(cls).filter_by(slug=slug).first()
        if row is not None:
            s.delete(row)          # 合集 cascade 会带走 photos
            s.commit()
    finally:
        s.close()


def test_model_page_falls_back_to_newest_published_collection():
    """头像缺省时: 取发布日期最新那本的第一张 —— 与作品网格第一张同一本。"""
    s = SessionLocal()
    try:
        m = Model(slug=f"{PREFIX}-m1", name="Blur Model", status="published")
        s.add(m)
        s.flush()
        # 源站日期最新(2026.10.22), 但入库更早 —— 网格里排在第一位, 背景也该是它
        _, old_names = _mk_collection(
            s, slug=f"{PREFIX}-c1-old-ingest", model_id=m.id,
            created=datetime(2026, 1, 1), published="2026.10.22")
        # 今天才入库的老作品(源站 2022) —— 网格里垫底, 背景不该取它
        _, new_names = _mk_collection(
            s, slug=f"{PREFIX}-c2-new-ingest", model_id=m.id,
            created=datetime(2026, 6, 1), published="2022.12.25")
        s.commit()
        slug = m.slug
    finally:
        s.close()

    try:
        got = _blur(f"/models/{slug}")
        assert got == "/t/s900/" + old_names[0], got
        assert got != "/t/s900/" + new_names[0]
    finally:
        _drop(f"{PREFIX}-m1", model=True)


def test_model_page_prefers_avatar_when_set():
    """设了头像就仍用头像 —— 别把这条分支一起改坏了。"""
    s = SessionLocal()
    try:
        m = Model(slug=f"{PREFIX}-m2", name="Blur Avatar", status="published",
                  avatar_path=f"{PREFIX}-avatar/000.jpg")
        s.add(m)
        s.flush()
        _mk_collection(s, slug=f"{PREFIX}-c3", model_id=m.id,
                       created=datetime(2026, 9, 9), published="2026.09.09")
        s.commit()
    finally:
        s.close()
    try:
        assert _blur(f"/models/{PREFIX}-m2") == f"/t/s900/{PREFIX}-avatar/000.jpg"
    finally:
        _drop(f"{PREFIX}-m2", model=True)


def test_collection_detail_uses_its_own_first_photo():
    """写真集详情页不参与排序: 恒取本合集 sort_order 最小的一张。"""
    s = SessionLocal()
    try:
        _, names = _mk_collection(s, slug=f"{PREFIX}-c4", model_id=None,
                                  created=datetime(1990, 1, 1),
                                  published="1990.01.01", n_photos=3)
        s.commit()
    finally:
        s.close()
    try:
        assert _blur(f"/collections/{PREFIX}-c4") == "/t/s900/" + names[0]
    finally:
        _drop(f"{PREFIX}-c4")


@contextmanager
def _park_featured():
    """把现有 featured 合集临时取消勾选(种子数据里有), 用完还原。

    兜底链是「featured 优先, 没有才全库兜底」, 不隔离的话测不到第二条。
    """
    s = SessionLocal()
    parked: list[int] = []
    try:
        for c in s.scalars(select(Collection).where(
                Collection.featured == True)).all():  # noqa: E712
            parked.append(c.id)
            c.featured = False
        s.commit()
    finally:
        s.close()
    try:
        yield
    finally:
        s = SessionLocal()
        try:
            for cid in parked:
                c = s.get(Collection, cid)
                if c is not None:
                    c.featured = True
            s.commit()
        finally:
            s.close()


def test_other_pages_fall_back_to_newest_ingested():
    """列表页/首页的兜底(无 featured 时): 按最新入库, 不是发布日期。"""
    s = SessionLocal()
    try:
        # created_at 放到 2099, 保证它是全库最新入库(种子数据都是会话期入库)
        _, names = _mk_collection(s, slug=f"{PREFIX}-c5", model_id=None,
                                  created=FAR_FUTURE, published="1990.01.01")
        s.commit()
    finally:
        s.close()
    try:
        with _park_featured():
            got = _blur("/collections")
            assert got == "/t/s900/" + names[0], got
            assert _blur("/") == got
    finally:
        _drop(f"{PREFIX}-c5")


def _set_featured(slug: str, on: bool = True) -> None:
    s = SessionLocal()
    try:
        c = s.query(Collection).filter_by(slug=slug).first()
        if c is not None:
            c.featured = on
            s.commit()
    finally:
        s.close()


def test_featured_only_affects_homepage_background():
    """featured 只影响首页背景(跟轮播一致), 不影响列表页/模特页。

    精选是首页的编辑推荐位: 首页背景必须和首屏轮播同一本, 否则头图和垫底图
    各说各话; 而 /collections、/models 这些浏览页只看最新入库。
    """
    s = SessionLocal()
    try:
        # 精选: 更早入库(2026-01) —— 首页该用它的第一张
        _, featured_names = _mk_collection(
            s, slug=f"{PREFIX}-c6", model_id=None,
            created=datetime(2026, 1, 1), published="1990.01.01")
        # 非精选: 最新入库(2099) —— 浏览页该用它
        _, plain_names = _mk_collection(
            s, slug=f"{PREFIX}-c7", model_id=None,
            created=FAR_FUTURE, published="1990.01.01")
        s.commit()
    finally:
        s.close()
    try:
        # 种子数据里也有精选, 先全部按下, 只留自己那一本(否则首页会挑到种子)
        with _park_featured():
            _set_featured(f"{PREFIX}-c6", True)
            # 首页: 精选优先(哪怕它更早入库)
            assert _blur("/") == "/t/s900/" + featured_names[0]
            # 浏览页: 忽略精选, 只认最新入库
            for path in ("/collections", "/models", "/favorites", "/profile"):
                assert _blur(path) == "/t/s900/" + plain_names[0], path
            _set_featured(f"{PREFIX}-c6", False)
    finally:
        _drop(f"{PREFIX}-c6")
        _drop(f"{PREFIX}-c7")


def test_homepage_falls_back_to_newest_when_no_featured():
    """一本精选都没有时, 首页背景退化为最新入库。"""
    s = SessionLocal()
    try:
        _, names = _mk_collection(s, slug=f"{PREFIX}-c8", model_id=None,
                                  created=FAR_FUTURE, published="1990.01.01")
        s.commit()
    finally:
        s.close()
    try:
        with _park_featured():
            assert _blur("/") == "/t/s900/" + names[0]
    finally:
        _drop(f"{PREFIX}-c8")


def test_works_order_is_publish_date_desc():
    """模特详情页作品序 = 源站发布日期新→旧; 入库时间不参与。"""
    early_in = Collection(slug="zz-a", title="a", status="published",
                          created_at=datetime(2026, 1, 1), published_at="2026.10.22")
    late_in = Collection(slug="zz-b", title="b", status="published",
                         created_at=datetime(2026, 6, 1), published_at="2022.12.25")
    got = _works_by_published([early_in, late_in])
    assert [c.slug for c in got] == ["zz-a", "zz-b"]
    # 同一天出版 → 按合集 id 倒序兜底
    same_day_a = Collection(id=11, slug="zz-c", title="c", status="published",
                            published_at="2026.05.05")
    same_day_b = Collection(id=12, slug="zz-d", title="d", status="published",
                            published_at="2026.05.05")
    got = _works_by_published([same_day_a, same_day_b])
    assert [c.slug for c in got] == ["zz-d", "zz-c"]
    # 没填发布日期 → 沉到最后
    undated = Collection(id=13, slug="zz-e", title="e", status="published",
                         published_at=None)
    got = _works_by_published([undated, same_day_a])
    assert [c.slug for c in got] == ["zz-c", "zz-e"]
