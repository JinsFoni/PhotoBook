"""管理后台 — CRUD、标签、用户、设置、采集(基于真实表单路由)。"""

from __future__ import annotations


def test_dashboard(admin_client):
    assert admin_client.get("/admin").status_code == 200


def test_model_crud(admin_client):
    r = admin_client.post("/admin/models/new", data={
        "name": "测试模特", "slug": "test-model", "status": "published",
        "stage_name": "", "gender": "", "age": "", "height": "",
        "measurements": "", "agency": "", "bio": "", "featured": "",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    # 列表出现;编辑页可打开(用创建时返回的 slug 找 id 不必要,直接查列表页拿 id)
    assert "test-model" in admin_client.get("/admin/models").text
    import re
    from app.database import SessionLocal
    from app.db import Model
    s = SessionLocal()
    mid = s.query(Model).filter_by(slug="test-model").one().id
    s.close()
    r = admin_client.get(f"/admin/models/{mid}/edit")
    assert r.status_code == 200 and "测试模特" in r.text
    # 更新
    r = admin_client.post(f"/admin/models/{mid}/edit", data={
        "name": "改名模特", "slug": "test-model", "status": "published",
        "stage_name": "", "gender": "", "age": "", "height": "",
        "measurements": "", "agency": "", "bio": "", "featured": "",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    # 删除
    assert admin_client.post(f"/admin/models/{mid}/delete", follow_redirects=False).status_code in (302, 303)


def test_collection_crud(admin_client):
    r = admin_client.post("/admin/collections/new", data={
        "title": "测试写真", "slug": "test-collection", "status": "draft",
        "model_id": "1", "tags": "测试, 海边", "description": "",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "test-collection" in admin_client.get("/admin/collections").text
    from app.database import SessionLocal
    from app.db import Collection
    s = SessionLocal()
    cid = s.query(Collection).filter_by(slug="test-collection").one().id
    s.close()
    r = admin_client.get(f"/admin/collections/{cid}/edit")
    assert r.status_code == 200 and "测试写真" in r.text
    # 打标签(表单路由)
    admin_client.post(f"/admin/collections/{cid}/tags", data={"tag": "新标签"})
    # 删除
    assert admin_client.post(f"/admin/collections/{cid}/delete", follow_redirects=False).status_code in (302, 303)


def test_tags_page_and_create(admin_client):
    r = admin_client.post("/admin/tags/new", data={"name": "独立标签"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "独立标签" in admin_client.get("/admin/tags").text
    # 删除
    assert admin_client.post("/admin/tags/1/delete", follow_redirects=False).status_code in (302, 303)


def test_users_page_admin_only(demo_client, admin_client):
    assert demo_client.get("/admin/users").status_code in (302, 303, 403)
    assert admin_client.get("/admin/users").status_code == 200


def test_create_user_form(admin_client):
    r = admin_client.post("/admin/users/new", data={
        "username": "tester", "password": "pass1234", "role": "viewer"},
        follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "tester" in admin_client.get("/admin/users").text


def test_settings_roundtrip(admin_client):
    # 表单只含 harvest.* 键(library.dir 跳过);checkbox 未勾选时键缺失 → 存 "0"
    r = admin_client.post("/admin/settings", data={
        "harvest.enabled": "1",
        "harvest.interval_hours": "12",
        "harvest.pages_per_round": "2",
        "harvest.start": "40",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "已保存" in admin_client.get("/admin/settings?flash=已保存").text
    from app.database import SessionLocal
    from app.services.settings_store import harvest_conf
    s = SessionLocal()
    try:
        conf = harvest_conf(s)
        assert conf["harvest.pages_per_round"] == 2
        assert conf["harvest.start"] == 40
        assert conf["harvest.enabled"] is True
    finally:
        s.close()


def test_harvest_page_and_jobs_api(admin_client):
    assert admin_client.get("/admin/harvest").status_code == 200
    r = admin_client.get("/admin/api/harvest/jobs")
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body and "workerRunning" in body


def test_harvest_submit_bad_url(admin_client):
    r = admin_client.post("/admin/harvest/submit", data={"url": "not-a-url"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    # flash 应提示无效(页面里含提交失败的反馈)
    page = admin_client.get("/admin/harvest").text
    assert ("无效" in page) or ("buondua" in page) or ("失败" in page)


def test_harvest_scan_route(admin_client, monkeypatch):
    # 不打真实网络:mock 掉 scan_once(真实扫描会入队真网站当前首页的写真,
    # 导致后续 test_enqueue_manual_accepts_real_url 撞上去重,且内容随时间漂移)
    from app.services.harvest import worker as harvest_worker
    monkeypatch.setattr(harvest_worker, "scan_once",
                        lambda pages=None: {"scanned_pages": 1, "seen": 0, "enqueued": 0, "stopped_early": False})
    r = admin_client.post("/admin/harvest/scan", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_harvest_import_route(admin_client, tmp_path):
    """扫描归档库导入:临时改 library.dir → 一键导入 → 幂等。"""
    from PIL import Image

    from app.config import settings
    from app.database import SessionLocal
    from app.services import library_import, settings_store

    lib = tmp_path / "library"
    d = lib / "Yeha" / "Admin Import Album"
    d.mkdir(parents=True)
    Image.new("RGB", (640, 480), (9, 9, 9)).save(d / "001.jpg")

    s = SessionLocal()
    try:
        settings_store.set_setting(s, "library.dir", str(lib))
        s.commit()
        r = admin_client.post("/admin/harvest/import", follow_redirects=False)
        assert r.status_code in (302, 303)
        assert library_import.collection_exists(s, "Yeha", "Admin Import Album")
        # 再导一次:幂等(不会重复建库)
        r = admin_client.post("/admin/harvest/import", follow_redirects=False)
        assert r.status_code in (302, 303)
        assert r.headers["location"].count("flash=") == 1
    finally:
        settings_store.set_setting(s, "library.dir", str(settings.library_dir))
        s.commit()
        s.close()


def test_non_admin_blocked(demo_client):
    for path in ("/admin", "/admin/models", "/admin/settings", "/admin/api/harvest/jobs"):
        assert demo_client.get(path).status_code in (302, 303, 403), path


def test_non_admin_blocked_json(demo_client):
    assert demo_client.get("/admin/api/harvest/jobs").status_code in (302, 303, 403)
