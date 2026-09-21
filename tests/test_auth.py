"""认证与访问控制 — 登录墙、角色、改密踢会话。"""

from __future__ import annotations


def test_redirects_to_login_when_anonymous(fresh_client):
    r = fresh_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers["location"]


def test_public_paths_accessible(fresh_client):
    assert fresh_client.get("/login").status_code == 200
    assert fresh_client.get("/healthz").status_code == 200


def test_static_served_without_login(fresh_client):
    r = fresh_client.get("/static/app.js")
    assert r.status_code == 200
    assert "window.PC" in r.text


def test_login_wrong_password(fresh_client):
    r = fresh_client.post("/login", data={"username": "admin", "password": "nope"},
                          follow_redirects=False)
    assert r.status_code in (200, 401, 303)
    assert fresh_client.get("/", follow_redirects=False).status_code in (302, 303)


def test_login_success(admin_client):
    r = admin_client.get("/")
    assert r.status_code == 200
    assert "PB_BOOT" in r.text


def test_demo_user_cannot_enter_admin(demo_client):
    assert demo_client.get("/admin").status_code in (302, 303, 403)


def test_admin_can_enter_admin(admin_client):
    assert admin_client.get("/admin").status_code == 200


def test_logout(fresh_client):
    fresh_client.post("/login", data={"username": "demo", "password": "demo123"})
    r = fresh_client.get("/logout", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert fresh_client.get("/", follow_redirects=False).status_code in (302, 303)


def test_password_change_kicks_other_sessions(demo_client, admin_client):
    # demo 已登录(自己的 cookie jar)
    assert demo_client.get("/").status_code == 200

    # 管理员改 demo 密码(表单路由;demo 是 id=2)
    r = admin_client.post("/admin/users/2/password", data={"password": "new-demo-pass"},
                          follow_redirects=False)
    assert r.status_code in (302, 303)

    # 旧会话失效 → 登录墙
    r = demo_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 303)

    # 新密码可登录
    r = demo_client.post("/login", data={"username": "demo", "password": "new-demo-pass"},
                         follow_redirects=False)
    assert r.status_code in (302, 303)
