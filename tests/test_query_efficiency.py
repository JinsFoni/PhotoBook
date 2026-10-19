"""列表页查询数回归 — 防止封面/模特分组/照片批量加载退化成 N+1。"""

from __future__ import annotations

from sqlalchemy import delete, event

from app.database import SessionLocal, engine
from app.db import Collection, Model, Photo
from app.routers import mobile_api, web

PREFIX = "test-query-efficiency"


def _make_fixture_data() -> tuple[list[int], int]:
    """建 20 本带封面的已发布合集(同一模特), 返回 (collection_ids, model_id)。"""
    s = SessionLocal()
    try:
        m = Model(slug=PREFIX, name="Query Efficiency", status="published")
        s.add(m)
        s.flush()
        ids = []
        for i in range(20):
            c = Collection(slug=f"{PREFIX}-{i}", title=f"Query Efficiency {i}",
                           model_id=m.id, status="published",
                           published_at="2026.01.01")
            s.add(c)
            s.flush()
            p = Photo(collection_id=c.id, filename=f"{PREFIX}/{i}.jpg",
                      width=100, height=150, sort_order=0)
            s.add(p)
            s.flush()
            c.cover_photo_id = p.id
            ids.append(c.id)
        s.commit()
        return ids, m.id
    finally:
        s.close()


def _drop_fixture_data(model_id: int) -> None:
    s = SessionLocal()
    try:
        # 写真删除会级联删 photos / collection_tags;模特单独删
        s.execute(delete(Collection).where(Collection.model_id == model_id))
        s.execute(delete(Model).where(Model.id == model_id))
        s.commit()
    finally:
        s.close()


class _QueryCounter:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        def _on(conn, cursor, statement, parameters, context, executemany):
            self.n += 1

        self._fn = _on
        event.listen(engine, "before_cursor_execute", _on)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._fn)


def test_list_helpers_do_not_n_plus_one():
    model_id = None
    try:
        _, model_id = _make_fixture_data()
        s = SessionLocal()
        try:
            cols = [c for c in web._published_collections(s)
                    if c.slug.startswith(PREFIX)]
            assert len(cols) == 20

            with _QueryCounter() as q:
                covers = web.load_covers(s, cols)
            assert q.n == 1, f"封面应一条批量查询, 实际 {q.n} 条"
            assert len(covers) == 20

            counts = web._photo_counts(s, cols)
            with _QueryCounter() as q:
                cards = [web._collection_card(s, c, counts, covers) for c in cols]
            assert q.n == 0, f"卡片不应再查封面, 实际 {q.n} 条"
            assert all(c["cover"] for c in cards)

            with _QueryCounter() as q:
                web.load_photos(s, cols)
            assert q.n == 1, f"照片应一条批量查询, 实际 {q.n} 条"
            with _QueryCounter() as q:
                assert all(len(c.photos) == 1 for c in cols)
            assert q.n == 0, f"访问 c.photos 不应触发懒加载, 实际 {q.n} 条"

            with _QueryCounter() as q:
                by_model = web._collections_by_model(cols)
                payload = web._model_payload(s, cols[0].model,
                                             by_model.get(model_id, []), counts, covers)
            assert q.n == 0, f"模特分组/头像兜底不应查询, 实际 {q.n} 条"
            assert payload["count"] == 20 and payload["photoCount"] == 20
        finally:
            s.close()
    finally:
        if model_id is not None:
            _drop_fixture_data(model_id)


def test_mobile_published_collections_eager_loads_model():
    model_id = None
    try:
        _, model_id = _make_fixture_data()
        s = SessionLocal()
        try:
            with _QueryCounter() as q:
                cols = mobile_api._published_collections(s)
            # 合集 + 模特 selectin + 合集标签 selectin + 模特标签 selectin
            assert q.n <= 5, f"_published_collections 查询过多: {q.n}"
            mine = [c for c in cols if c.slug.startswith(PREFIX)]
            assert len(mine) == 20
            with _QueryCounter() as q:
                assert all(c.model is not None for c in mine)
            assert q.n == 0, f"c.model 应已 eager load, 实际又查了 {q.n} 条"
        finally:
            s.close()
    finally:
        if model_id is not None:
            _drop_fixture_data(model_id)
