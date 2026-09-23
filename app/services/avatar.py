"""生成式默认头像 — "光圈徽记"。

由 avatar_seed 确定性生成一枚 SVG 徽记: 同心圆环 + 断弧对焦环 +
焦点光点 + 虚化光斑, 呼应摄影主题。无外部资源、无上传文件, 任意种子
稳定产出同一图案; 6 个色板 × 3 个环数档位 × 光斑/断位随机, 组合足够多。

全站统一从 avatar.py 取头像: 顶栏(PC.renderChrome)、个人资料页、
管理区直接内嵌 data URI, 避免重复实现。
"""

from __future__ import annotations

import hashlib
import random

# 色板: (底色, 环主色, 点缀色) — 低饱和, 深浅主题下都成立
_PALETTES: list[tuple[str, str, str]] = [
    ("#23262b", "#c8a24a", "#e8e2d4"),  # 黄铜 / 象牙
    ("#1f2a26", "#7fae9d", "#e3ede8"),  # 青瓷 / 月白
    ("#2a2430", "#b48ead", "#ece4f0"),  # 暮紫 / 藕荷
    ("#302620", "#c98a5e", "#f0e4d8"),  # 琥珀 / 米白
    ("#22282e", "#7d9cb5", "#e2ebf2"),  # 青灰蓝 / 雾白
    ("#2d2222", "#bd7d7d", "#f2e4e4"),  # 绛红 / 樱粉
]


def _rand(seed: str):
    """种子 → 确定性随机源。"""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(digest)


def avatar_svg(seed: str) -> str:
    """生成头像 SVG 文本。同名种子永远得到同一枚徽记。"""
    seed = (seed or "").strip() or "photobook"
    rng = _rand(seed)
    bg, ring, spark = _PALETTES[rng.randrange(len(_PALETTES))]

    # 环数档位: 2 / 3 / 4(细环越少的构图越留白)
    n_rings = (2, 3, 4)[rng.randrange(3)]
    cx = cy = 50.0
    rings: list[str] = []
    for i in range(n_rings):
        # 半径从外往里排, 混入少量随机避免档位感过重
        r = 38 - i * (30 / max(1, n_rings - 1)) + rng.uniform(-1.5, 1.5)
        r = max(7.0, min(40.0, r))
        w = rng.choice([0.8, 1.1, 1.1, 1.6, 2.2])
        op = rng.uniform(0.28, 0.6)
        dash = ""
        # 约一半的环带一段缺口(对焦环的隐喻), 缺口 30°~70°
        if rng.random() < 0.5:
            gap = rng.uniform(30, 70)
            start = rng.uniform(0, 360)
            circ = 2 * 3.14159265 * r
            dash = (f' stroke-dasharray="{circ - gap * circ / 360:.2f} '
                    f'{gap * circ / 360:.2f}"'
                    f' stroke-dashoffset="-{start * circ / 360:.2f}"')
        rings.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r:.2f}" fill="none" '
            f'stroke="{ring}" stroke-width="{w}" opacity="{op:.2f}"{dash}/>'
        )

    # 焦点光点: 落在最内环附近
    fx = cx + rng.uniform(-6, 6)
    fy = cy + rng.uniform(-6, 6)
    fr = rng.uniform(2.2, 3.6)

    # 虚化光斑: 0~2 个, 模拟焦外成像
    blobs: list[str] = []
    for _ in range(rng.randrange(3)):
        bx = rng.uniform(8, 92)
        by = rng.uniform(8, 92)
        br = rng.uniform(9, 18)
        blobs.append(
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{br:.1f}" '
            f'fill="{spark}" opacity="{rng.uniform(0.05, 0.12):.2f}"/>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'role="img" aria-label="avatar">'
        f'<rect width="100" height="100" fill="{bg}"/>'
        + "".join(blobs)
        + "".join(rings)
        + f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="{fr:.2f}" fill="{spark}"/>'
        + "</svg>"
    )


def avatar_data_uri(seed: str) -> str:
    """头像 SVG 的 data URI(可直接放 <img src>)。"""
    svg = avatar_svg(seed)
    # data URI 内不能直接嵌原始 XML, 用 URL 编码转义(比 base64 短且可读)
    from urllib.parse import quote
    return "data:image/svg+xml," + quote(svg, safe="")
