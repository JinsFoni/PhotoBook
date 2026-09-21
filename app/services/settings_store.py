"""设置存取 — settings 表覆盖 config 默认值,后台修改即时生效。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings as defaults
from ..db import Setting

# key -> (默认值, 说明, 类型)
HARVEST_KEYS: dict[str, tuple[str, str, type]] = {
    "harvest.enabled": ("1", "启用定时采集", bool),
    "harvest.interval_hours": ("6", "采集周期(小时)", float),
    "harvest.pages_per_round": ("1", "单轮抓取页数", int),
    "harvest.start": ("0", "起始页(从新到旧,0=首页)", int),
    "harvest.whitelist": ("", "白名单关键词(逗号分隔,空=不限制)", str),
    "harvest.blacklist": ("", "黑名单关键词(逗号分隔,标题或标签命中即跳过)", str),
    "harvest.model_exclude": (defaults.harvest_model_exclude,
                             "模特名排除词(逗号分隔,按词匹配,用于从标签里挑模特名)", str),
    "harvest.unsorted_dir": (defaults.harvest_unsorted_dir, "未分类目录名", str),
    "library.dir": (str(defaults.library_dir), "归档根目录", str),
}


def get_setting(s: Session, key: str) -> str | None:
    row = s.get(Setting, key)
    return row.value if row else None


def set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))


def harvest_conf(s: Session) -> dict[str, object]:
    """读取采集配置(settings 表 → 默认)。"""
    out: dict[str, object] = {}
    for key, (dflt, _label, typ) in HARVEST_KEYS.items():
        raw = get_setting(s, key)
        val = raw if raw is not None and raw != "" else dflt
        if typ is bool:
            out[key] = str(val) in ("1", "true", "True", "on")
        elif typ is int:
            out[key] = int(float(val))
        elif typ is float:
            out[key] = float(val)
        else:
            out[key] = str(val)
    return out
