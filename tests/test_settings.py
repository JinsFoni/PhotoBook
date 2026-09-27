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


def test_proxy_roundtrip(s):
    # 代理设置: 写入 → conf 读回;清空 → None(直连)
    set_setting(s, "harvest.proxy", "http://192.168.0.2:7890")
    s.flush()
    assert harvest_conf(s)["harvest.proxy"] == "http://192.168.0.2:7890"
    set_setting(s, "harvest.proxy", "")
    s.flush()
    assert harvest_conf(s)["harvest.proxy"] == ""


def test_net_proxy_reads_settings(s):
    # 整个采集链路走代理: net(页面/短链/API) + pipeline.download_stream 都应接线
    import inspect
    from app.services.harvest import net, pipeline as pl

    assert net_src_proxies(net) == 3, "net 应有 3 处 proxy 接线(fetch/ouo Session/mediafire API)"
    assert "harvest.proxy" in inspect.getsource(pl), "下载流应读取 harvest.proxy"


def net_src_proxies(net) -> int:
    import inspect
    return inspect.getsource(net).count("proxy=")
