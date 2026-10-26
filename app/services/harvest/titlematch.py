"""跨站写真标题比对 — 判定「另一个站的这个 URL 是否就是库里这本」。

三个源站(buondua / misskon / nicesss)会转载同一本写真, 各自的序号体系
相互独立: buondua 尾段 56556 ↔ misskon 117727 ↔ nicesss 496839。
采集入库时只把当前站的序号写进 collections.source_serial, 另外两站的
链接因此在油猴脚本上永远显示「可下载」, 点了会重复下一遍已入库的包。

比对思路(与既有 slug 无关, 纯文本层):
1. 剥掉各站自己的装饰: "(71 photos)" / "(101 photos + 6 videos)" 尾缀、
   "[101P + 6V／585.6MB]" 张数体积后缀、nicesss 的 "- 呦糖社" 尾巴;
2. 分隔符(冒号/连字符/下划线/斜杠)统一为空格, 连续重复的词合并
   ("yeonyu yeonyu" → "yeonyu", 源站目录名会把拼音名写两遍);
3. 数字 token 与前一个 token 粘连("no 5988" ≡ "no5988");
4. 短的一方的全部 token 必须按序是长的一方的子序列, 且短的一方至少
   两个 token、有一个 >= 6 字符、字符总数 >= 8 —— 单个模特名
   ("Suji (수지)")不构成写真级匹配。
"""

from __future__ import annotations

import re

# "(71 photos)" / "(101 photos + 6 videos)" — buondua og:title 与 misskon h1
_PHOTOS_TAIL_RE = re.compile(
    r"\(\s*\d+\s*photos?(?:\s*\+\s*\d+\s*videos?)?\s*\)", re.I)
# 同上,单独抓照片数(张数等价判定用): "(71 photos)" / "(101 photos + 6 videos)"
_PHOTOS_COUNT_RE = re.compile(
    r"\(\s*(\d+)\s+photos?(?:\s*\+\s*\d+\s+videos?)?\s*\)", re.I)
# "[101P + 6V／585.6MB]" / "[192P／307MB]" / "[70+1P／959MB]" — nicesss 标题
_COUNT_SIZE_RE = re.compile(
    r"\[\s*\d+(?:\s*\+\s*\d+)?\s*p(?:hotos)?(?:\s*\+\s*\d+\s*v)?"
    r"[／/]\s*[\d.]+\s*[kmg]b\s*\]", re.I)
# 同上,单独抓照片数(首段 P 数;P+V 的 V 不算照片)
_P_COUNT_RE = re.compile(
    r"\[\s*(\d+)(?:\s*\+\s*\d+)?\s*p(?:hotos)?(?:\s*\+\s*\d+\s*v)?"
    r"[／/]\s*[\d.]+\s*[kmg]b\s*\]", re.I)
# nicesss og:title 尾巴(另一个无后缀的 og:title 在 JSON-LD 里)
_SITE_SUFFIX_RE = re.compile(r"\s*[-–—]+\s*呦糖社\s*$")
# 分隔符 → 空格
_SEP_RE = re.compile(r"[:\-–—/_]+")
_SPACE_RE = re.compile(r"\s+")
# 归一化后只留 CJK / 拉丁字母数字
_KEEP_RE = re.compile(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", re.UNICODE)


def title_tokens(title: str | None) -> list[str]:
    """标题 → 归一化 token 序列(供子序列包含比对)。

    数字 token 会粘到前一个 token 上: "no.5988" / "no 5988" / "no5988"
    三站写法不一, 粘起来才等价。
    """
    s = (title or "").lower()
    s = _PHOTOS_TAIL_RE.sub("", s)
    s = _COUNT_SIZE_RE.sub("", s)
    s = _SITE_SUFFIX_RE.sub("", s)
    s = _SEP_RE.sub(" ", s)
    s = _SPACE_RE.sub(" ", s).strip()
    tokens: list[str] = []
    for raw in s.split():
        tok = _KEEP_RE.sub("", raw)
        if not tok:
            continue
        # "no" + "5988" → "no5988"(跨站数字分隔不一致)
        if tok.isdigit() and tokens:
            tokens[-1] += tok
        else:
            tokens.append(tok)
    return tokens


def strip_counts(title: str | None) -> str:
    """剥掉源站的张数/体积尾缀(`(60 photos)` / `[101P／307MB]` / `- 呦糖社`)。

    归档目录名里没有这些尾缀(它们是站点装饰),页面标题有 —— 采集侧
    「这本导过没有」的 slug 预检要拿剥掉尾缀的形态去比,否则永远差一截
    (2026-10-27 那 4 本白白下了一遍)。剥完可能就和别的批次同名了,
    所以调用方必须配 `photo_count()` 张数守卫再用。
    """
    s = _PHOTOS_TAIL_RE.sub("", title or "")
    s = _COUNT_SIZE_RE.sub("", s)
    s = _SITE_SUFFIX_RE.sub("", s)
    return s.strip(" -–—")


def photo_count(title: str | None) -> int | None:
    """标题里的照片张数;解析不出返回 None。

    识别三站写法: "(310 photos)" / "(101 photos + 6 videos)"(buondua /
    misskon)与 "[192P／307MB]" / "[101P + 6V／585.6MB]"(nicesss)。
    只取首个命中 —— 标题正文若出现相似写法,尾缀剥除后 正文里的写法
    仍在,但写真标题正文出现 "(N photos)" 的概率可忽略。
    """
    s = title or ""
    m = _PHOTOS_COUNT_RE.search(s)
    if m:
        return int(m.group(1))
    m = _P_COUNT_RE.search(s)
    return int(m.group(1)) if m else None


def titles_match(a: str | None, b: str | None) -> bool:
    """两标题是否指向同一本写真(跨站等价)。

    要求短的一方的全部 token 按序出现在长的一方里, 且短的一方本身有
    足够辨识度(>= 2 token、最大 token >= 6 字符、总长 >= 8)——
    同模特不同写真(Blue / Butterfly / Duisburg)、同系列不同期
    (ag627 / ag674)都不会误配。

    张数守卫:两边标题的照片数都解析得出且不相等 → 不是同一本。
    泛化标题(模特+角色名,如「[AI Generated] 诛仙-陆雪琪」)是系列名,
    不同批次的写真共用同一标题(25/100/310 张各一期),子序列比对必然
    全部命中 —— 张数是唯一可靠区分(47799 ↔ 44755 误判实录)。
    张数解析不出(归档目录名、老帖标题)时退回纯文本判定,行为同旧版。
    """
    ca, cb = photo_count(a), photo_count(b)
    if ca is not None and cb is not None and ca != cb:
        return False
    short, long = title_tokens(a), title_tokens(b)
    if len(short) > len(long):
        short, long = long, short
    if len(short) < 2:
        return False
    # 短的一方必须按序是长的一方的子序列
    it = iter(long)
    if not all(tok in it for tok in short):
        return False
    if max(len(t) for t in short) < 6:
        return False
    return sum(len(t) for t in short) >= 8


def title_matches_collection(title: str | None, col_title: str | None,
                             col_photos: int | None) -> bool:
    """源站标题 ↔ 已入库写真集的等价判定(带真实张数守卫)。

    入库写真集的 title 是解压产物目录名/源站标题去尾缀后的形态,不带
    「(N photos)」(生产库 310/310 无),photo_count(col_title) 恒为
    None —— titles_match 的张数守卫对它单向失效,泛化系列标题依然全部
    误配。这里用 photos 表的真实张数补上库里那一侧:上报标题解析得出
    张数且与真实张数不等 → 不是同一本(25/100/310 张各一期只该命中
    100 张那本)。col_photos 为 None/0(尚未入库/无照片行,张数未知)
    时退回纯文本判定。
    """
    if not titles_match(title, col_title):
        return False
    reported = photo_count(title)
    if reported is not None and col_photos and reported != col_photos:
        return False
    return True
