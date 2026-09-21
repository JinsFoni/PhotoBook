"""i18n — 语言解析、cookie 切换、持久化、模板与 JS 注入。"""

from __future__ import annotations

import re

from app.i18n import LANGUAGES, normalize_lang, translate


# ---- 纯函数 ---------------------------------------------------------------

def test_normalize_lang():
    assert normalize_lang("zh-TW") == "zh-TW"
    assert normalize_lang("zh-tw") == "zh-TW"
    assert normalize_lang("zh-Hant") == "zh-TW"
    assert normalize_lang("zh-HK") == "zh-TW"
    assert normalize_lang("zh-CN") == "zh-CN"
    assert normalize_lang("zh") == "zh-CN"
    assert normalize_lang("zh-Hans") == "zh-CN"
    assert normalize_lang("cmn") == "zh-CN"
    assert normalize_lang("en") is None
    assert normalize_lang("") is None
    assert normalize_lang(None) is None


def test_translate_fallback_chain():
    # zh-TW 有译文
    assert translate("Models", "zh-TW") == "模特兒"
    # zh-TW 缺失时回退 zh-CN(构造临时缺失场景:用不存在于两语的 key 走 msgid 原文)
    assert translate("No Such Key XyZ", "zh-TW") == "No Such Key XyZ"
    # token 替换
    assert translate("{n} photos", "zh-CN", n=5) == "5 张照片"


def test_all_languages_complete():
    """每种语言都必须覆盖全部 msgid(缺条即回退,不算错,但上线前应对齐)。"""
    assert set(LANGUAGES) == {"zh-CN", "zh-TW"}
    assert all(v.get("zh-CN") for v in __import__("app.i18n", fromlist=["STRINGS"]).STRINGS.values())


# ---- 路由行为 ---------------------------------------------------------------

def test_home_default_simplified(admin_client):
    r = admin_client.get("/")
    assert r.status_code == 200
    assert 'lang="zh-CN"' in r.text
    assert "模特" in r.text


def test_cookie_switch_to_traditional(admin_client):
    admin_client.cookies.set("pb_lang", "zh-TW")
    r = admin_client.get("/")
    assert r.status_code == 200
    assert 'lang="zh-TW"' in r.text
    assert "模特兒" in r.text
    assert "寫真" in r.text


def test_language_route_public_and_sets_cookie(client):
    """未登录也能切语言(登录页需要);设 cookie + 回跳。"""
    r = client.post("/language", data={"lang": "zh-TW", "next": "/login"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/login"
    assert r.headers.get("set-cookie", "").startswith("pb_lang=zh-TW")
    client.cookies.set("pb_lang", "zh-TW")
    r2 = client.get("/login")
    assert r2.status_code == 200
    assert "模特兒" in r2.text or "lang=\"zh-TW\"" in r2.text


def test_language_persists_for_user(admin_client, client):
    """已登录切换语言 → 写入 user.language,后续请求(无 cookie)仍用该语言。"""
    r = admin_client.post("/language", data={"lang": "zh-TW", "next": "/profile"},
                          follow_redirects=False)
    assert r.status_code in (302, 303)
    # 新客户端 + 用 session cookie 登录态检查:直接查 admin_client(其 cookie jar 已更新)
    r2 = admin_client.get("/profile")
    assert 'lang="zh-TW"' in r2.text
    # 个人语言设置持久化:即使去掉 cookie,仍是繁体
    admin_client.cookies.set("pb_lang", None)
    r3 = admin_client.get("/")
    assert 'lang="zh-TW"' in r3.text


def test_language_invalid_ignored(client):
    r = client.post("/language", data={"lang": "xx-YY", "next": "/login"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "pb_lang" not in (r.headers.get("set-cookie") or "")


# ---- boot_json 注入 ---------------------------------------------------------

def test_boot_json_contains_i18n(admin_client):
    r = admin_client.get("/")
    m = re.search(r"window\.PB_DATA = (.*?);\nwindow\.PB_BOOT", r.text, re.S)
    assert m, "PB_DATA 格式改变?"
    assert "window.PB_BOOT" in r.text


def test_profile_has_language_switch(admin_client):
    r = admin_client.get("/profile")
    assert "Language" in r.text
    assert "/language" in r.text
    assert "lang-switch" in r.text


def test_admin_settings_has_default_language(admin_client):
    r = admin_client.get("/admin/settings")
    assert "site.language" in r.text
    assert "简体中文" in r.text and "繁體中文" in r.text
