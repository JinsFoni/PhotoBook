"""标题/标签黑白名单过滤 + 模特名挑选(需求 §29)。

两套规则刻意不同:
- 黑/白名单(harvest.blacklist / whitelist):**子串**匹配,标题与 tag 一起看。
- 模特名排除词(harvest.model_exclude):**按词**匹配,只用于从 tag 里挑模特名
  (短词如 `jp`/`ag` 用子串会误伤 `magda` 之类)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...config import settings as _settings
from .titlemodel import (model_name_from_title, native_name_for_model,
                         norm_name, split_trailing_native)

# 模特名排除词默认值 —— 2026-09 对 buondua 全站采样(1020 个专辑 / 601 个 tag)
# 统计得出:凡是「总是排在 tag 列表首位」(从不处于模特位)且出现 ≥3 次的 tag,
# 全部是出品方/分类,无一个人名;再补 AI Generated / AI Enhanced /
# General Collection / Korea 等跨专辑标记类 tag。详见 docs/architecture.md §十一。
DEFAULT_MODEL_EXCLUDE = _settings.harvest_model_exclude


@dataclass
class FilterResult:
    allowed: bool
    keyword: str = ""  # 命中的关键词(拒绝时)


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    # 逗号或换行分隔(设置页 textarea 用换行)
    return [k.strip().lower() for k in raw.replace(";", ",").replace("\r", "")
            .replace("\n", ",").split(",") if k.strip()]


# ---- 按词匹配(模特名排除词) ------------------------------------------------

_SEP_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def normalize_key(text: str | None) -> str:
    """归一:小写,非「字母数字/汉字」一律当分隔符(连字符、下划线、点…)。"""
    return _SEP_RE.sub(" ", (text or "").lower()).strip()


def keyword_hit(text: str | None, keyword: str | None) -> bool:
    """按词匹配:关键词两侧不得紧邻 ASCII 字母数字。

    这样 `jp` 命中 "jp 11853"、`ag` 命中 "ag 11787",但都不会误伤 "magda";
    中文关键词(内购无水印 / ns纳丝摄影)按原样匹配,不受影响。
    """
    kw = normalize_key(keyword)
    if not kw:
        return False
    norm = normalize_key(text)
    return re.search(r"(?<![0-9a-z])" + re.escape(kw) + r"(?![0-9a-z])", norm) is not None


def matches_any(text: str | None, keywords: str | None) -> str:
    """返回第一个命中的关键词;未命中返回空串。"""
    for kw in _split(keywords):
        if keyword_hit(text, kw):
            return kw
    return ""


# 明显不是人名的标签(如 "(42 photos)")
_JUNK_TAG_RE = re.compile(r"^[\(\[]?\s*\d+\s*photos?\s*[\)\]]?$", re.I)


def pick_model_name(tags: list[str] | None, exclude: str | None = None) -> str:
    """从 tag 列表挑模特名:第一个未被排除词命中的 tag(取显示名)。

    全被排除或没有 tag → 返回空串(调用方落到「未分类」)。
    """
    raw = DEFAULT_MODEL_EXCLUDE if exclude is None else exclude
    for name in tags or ():
        label = str(name).strip()
        if not label or _JUNK_TAG_RE.match(label) or not normalize_key(label):
            continue  # 空标签 / "(42 photos)" / 纯符号
        if not matches_any(label, raw):
            return label
    return ""


# ---- 模特名判定:标题规则 × tag 交叉验证 ---------------------------------------
#
# 标题规则优先、tag 兜底,但两路都算出来再交叉验证 —— 只走任何一路都有
# 实测过的坑:
#   只信 tag:出品方 tag 总排在 tag 列表前面(misskon 的 `[LE] GMS-006A: GMS`
#     模特名被抽成 `LE`,还建出一个假模特 le,14 本写真集挂错),每冒出一个
#     新出品方就得手工往排除词里补一条;
#   只信标题:`Coser@水淼Aqua: …` 这类账号写法、`[MAXIM] Green` 这类带出品方
#     前缀的标题会抽歪,标题里真没人名的帖子还只能落「未分类」。

_BRACKET_RE = re.compile(r"^\[([^\[\]]{1,20})\]\s*")


def _bracket_tokens(title: str) -> list[str]:
    """标题开头连续的方括号块(`[LE] [AI Enhanced] …`)里的内容 —— 出品方/分类标记位。"""
    out: list[str] = []
    rest = (title or "").lstrip()
    while True:
        m = _BRACKET_RE.match(rest)
        if not m:
            return out
        out.append(m.group(1))
        rest = rest[m.end():]


def _is_title_marker(title: str, name: str) -> bool:
    """name 是不是只是标题里的出品方/分类标记(而不是人名)。"""
    key = norm_name(name)
    return bool(key) and any(norm_name(tok) == key for tok in _bracket_tokens(title))


def resolve_model(title: str, tags: list[str] | None,
                  exclude: str | None = None) -> tuple[str, str]:
    """模特名判定 → (模特名, 原生名)。

    1) tag 全被排除 → 用标题规则抽到的名字(以前一律落「未分类」);
    2) 两路指向同一个人 → 同一写法用 tag 名,写法不同(tag `U Hwa` /
       标题 `U.Hwa`)取标题写法,与库里既有模特和媒体目录 slug 对齐;
    3) tag 命中的正是标题里的出品方方括号(如 `[LE] …`) → 用标题里的名字;
    4) 其余不一致 → 保持 tag 名,不拿标题规则去覆盖可靠的 tag。
    """
    tag_name = pick_model_name(tags, exclude)
    tag_native = ""
    if tag_name:
        tag_name, tag_native = split_trailing_native(tag_name)
        if not tag_native:
            tag_native = native_name_for_model(title, tag_name)

    title_name, title_native = model_name_from_title(title or "")
    if not title_name:
        return tag_name, tag_native
    if not tag_name:
        return title_name, title_native
    if norm_name(tag_name) == norm_name(title_name):
        # 只差大小写 → 保留 tag 写法(库里既有模特常是全大写/小写,别造第二条);
        # 差在标点/空格(tag `U Hwa` / 标题 `U.Hwa`)→ 取标题写法
        same_case = tag_name.lower() == title_name.lower()
        return ((tag_name if same_case else title_name),
                tag_native or title_native)
    if _is_title_marker(title, tag_name):
        return title_name, title_native
    return tag_name, tag_native


# ---- 黑/白名单(标题 + 标签) -------------------------------------------------

def check_title(title: str, whitelist: str | None, blacklist: str | None,
                tags: list[str] | None = None) -> FilterResult:
    """黑名单优先(命中即拒)→ 白名单非空须命中。标题与 tag 合并后子串匹配。"""
    hay = " ".join([title or "", *(tags or ())]).lower()
    for kw in _split(blacklist):
        if kw in hay:
            return FilterResult(allowed=False, keyword=kw)
    wl = _split(whitelist)
    if wl and not any(kw in hay for kw in wl):
        return FilterResult(allowed=False, keyword=wl[0])
    return FilterResult(allowed=True)


def sanitize_path_part(name: str) -> str:
    """路径非法字符 → '-',去首尾空白与点(防目录穿越/隐藏文件)。"""
    import re

    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name or "")
    cleaned = re.sub(r"\.{2,}", ".", cleaned).strip(" .")
    return cleaned or "untitled"
