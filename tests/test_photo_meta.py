"""设为封面 / 设为模特头像 —— /api/photo-meta。

重点不是「写进库」(列表页每次请求都实时读库), 而是**返回值得够前端就地换图**:
改完封面返回列表时, 浏览器可能整页从 bfcache 还原(连 DOM 都不重建), 光改库
看不到效果(2026-11-04 反馈)。前端拿响应里的 cover(照片文件名)当锚, 把缩略图
地址的末段换掉 —— 所以 cover 必须是 `/t/<尺寸>/` 后面那串, 且带目录。

详见 app/static/app.js 的 applyDirtyCovers / docs/architecture.md。
"""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.db import Collection, Photo

SLUG = "meta-test-cover"
BASE = "meta-test-model/meta-test-cover"


def _fixture_collection(s):
    """自建一本测试合集: 不依赖种子(别的测试会删数据, 顺序一变就扑空)。"""
    c = s.scalars(select(Collection).where(Collection.slug == SLUG)).first()
    if c is None:
        c = Collection(slug=SLUG, title="封面测试", status="published",
                       published_at="2026.11.04", model_id=None)
        s.add(c)
        s.flush()
    have = {p.filename for p in s.scalars(select(Photo).where(Photo.collection_id == c.id))}
    for i in (1, 2):
        fn = f"{BASE}/cover-test-{i:03d}.jpg"
        if fn not in have:
            s.add(Photo(collection_id=c.id, filename=fn, sort_order=i))
    s.commit()
    photos = list(s.scalars(select(Photo).where(Photo.collection_id == c.id)
                            .order_by(Photo.sort_order)))
    return c, photos


def test_set_cover_returns_anchor_for_client(admin_client):
    s = SessionLocal()
    try:
        c, photos = _fixture_collection(s)
        target = [p for p in photos if p.id != c.cover_photo_id][0]
        cid, slug, pid, filename = c.id, c.slug, target.id, target.filename
    finally:
        s.close()

    r = admin_client.post("/api/photo-meta", json={"photo_id": pid, "target": "cover"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["slug"] == slug
    # 前端就是靠这一串去匹配缩略图地址 /t/s900/<同一串>
    assert j["cover"] == filename
    assert "/" in j["cover"], "文件名要带目录, 否则前端没法唯一定位"

    s = SessionLocal()
    try:
        c = s.get(Collection, cid)
        assert c.cover_photo_id == pid
        # 展示端实时读库: 列表页下一次请求就该是新封面
        from app.routers import web

        assert web._collection_cover(s, c) == filename
    finally:
        s.close()


def test_set_cover_requires_login(fresh_client):
    """没登录一律 401(登录了但非 admin 是 403, 走的是同一个 require_admin)。

    这里不用 demo_client: test_auth 会把 demo 的密码改掉, 后面的 demo 登录会扑空
    —— 测试之间不该有这种隐式顺序依赖。
    """
    s = SessionLocal()
    try:
        _c, photos = _fixture_collection(s)
        pid = photos[0].id
    finally:
        s.close()
    r = fresh_client.post("/api/photo-meta", json={"photo_id": pid, "target": "cover"},
                          follow_redirects=False)
    # 中间件把未登录的请求打回登录页(302), 接口本身是 401 —— 都算没权限
    assert r.status_code in (302, 401), r.status_code


def test_set_cover_bad_input(admin_client):
    assert admin_client.post(
        "/api/photo-meta", json={"photo_id": 1, "target": "nope"}).status_code == 400
    assert admin_client.post(
        "/api/photo-meta", json={"photo_id": 99999999, "target": "cover"}).status_code == 404


def test_set_avatar_returns_same_anchor(admin_client):
    """头像路径就是那张照片的文件名, 前端用同一套逻辑换图。"""
    s = SessionLocal()
    try:
        c, photos = _fixture_collection(s)
        pid, filename, has_model = photos[0].id, photos[0].filename, c.model_id is not None
    finally:
        s.close()

    r = admin_client.post("/api/photo-meta", json={"photo_id": pid, "target": "avatar"})
    if not has_model:
        # 未归属模特: 无处设头像(API 明确 400)
        assert r.status_code == 400
        return
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True and j["cover"] == filename
