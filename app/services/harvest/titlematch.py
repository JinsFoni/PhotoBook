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
# "[101P + 6V／585.6MB]" / "[192P／307MB]" / "[70+1P／959MB]" — nicesss 标题
_COUNT_SIZE_RE = re.compile(
    r"\[\s*\d+(?:\s*\+\s*\d+)?\s*p(?:hotos)?(?:\s*\+\s*\d+\s*v)?"
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


def titles_match(a: str | None, b: str | None) -> bool:
    """两标题是否指向同一本写真(跨站等价)。

    要求短的一方的全部 token 按序出现在长的一方里, 且短的一方本身有
    足够辨识度(>= 2 token、最大 token >= 6 字符、总长 >= 8)——
    同模特不同写真(Blue / Butterfly / Duisburg)、同系列不同期
    (ag627 / ag674)都不会误配。
    """
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
