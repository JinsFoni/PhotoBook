"""settings_store — 默认值、类型转换、settings 表覆盖。"""

from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.services.settings_store import HARVEST_KEYS, get_setting, harvest_conf, set_setting


@pytest.fixture()
def s():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def test_defaults(s):
    # 注意:DB 是会话级共享的,前面用例可能改过 settings,这里只验类型与关内性
    conf = harvest_conf(s)
    assert isinstance(conf["harvest.enabled"], bool)
    assert isinstance(conf["harvest.pages_per_round"], int)
    assert conf["harvest.pages_per_round"] >= 1
    assert isinstance(conf["harvest.start"], int) and conf["harvest.start"] >= 0


def test_set_then_conf(s):
    set_setting(s, "harvest.pages_per_round", "3")
    s.flush()
    assert harvest_conf(s)["harvest.pages_per_round"] == 3


def test_bool_off_roundtrip(s):
    # 关闭时存 "0"(空串会被当作未设置而回退默认)
    set_setting(s, "harvest.enabled", "0")
    s.flush()
    assert harvest_conf(s)["harvest.enabled"] is False


def test_int_coercion(s):
    set_setting(s, "harvest.start", "40")
    s.flush()
    assert harvest_conf(s)["harvest.start"] == 40


def test_get_setting_missing(s):
    assert get_setting(s, "harvest.nope") is None


def test_harvest_keys_complete():
    for k in ("enabled", "interval_hours", "pages_per_round", "start", "whitelist", "blacklist"):
        assert f"harvest.{k}" in HARVEST_KEYS
