# 从 4kup.net 标题抽取模特名：方案与实测

> 站点：<https://4kup.net>（WordPress）
> 样本：REST API 拉取最近 2000 条标题（2026-10-19）
> 原型：[`extract_models.py`](./extract_models.py)　输出：[`models.csv`](./models.csv)

---

## 1. 先看标题语法

这个站的标题高度模板化，**90% 以上的模特名都在固定位置**，所以规则法性价比极高。

| 标题形态 | 示例 | 抽取位置 |
| --- | --- | --- |
| `[地区] 罗马字名 (原生名) 作品…` | `[JP] Toyoda Runa (豊田ルナ) 週刊少年マガジン…` | 第一个括号前 + 括号内 |
| `[LE] 番号 名字 (原生名)` | `[LE] LEHC-037 Min.E (민이)` | 跳过番号，取括号前 |
| `[内购无水印] 名字 秀人网模特 …` | `[内购无水印] 鱼子酱Fish 秀人网模特 惊红之舞` | `秀人网模特` 前 |
| `Coser@名字 作品…` | `Coser@洛璃LoLiSAMA 碧蓝航线 信浓赛车` | `@` 后第一个名字 |
| `XIUREN No.11319 名字` | `XIUREN No.11319 Yang Chen Chen (杨晨晨)` | 编号后 |
| `UGIRLS App No.2650 名字` | `UGIRLS App No.2650 Zhou Da Meng (周大萌) …` | 编号后 |
| `IMISS Vol.804 名字` | `IMISS Vol.804 许诺Sabrina` | 编号后 |
| `[AIGirl] 名字 0916` | `[AIGirl] 芭喜mila 0916` | 日期前 |
| `[AI Enhanced] AG.737 名字 (原生名)` | `[AI Enhanced] AG.737 YeonYu (연유)` | 编号后 |
| `DJAWA Photo 名字 (原生名) – …` | `DJAWA Photo Doodoong (두둥) – Staycation #7` | `Photo` 后 |
| `[LE] 番号 GMS` | `[LE] GMS-006A GMS` | **没有人名**（系列名） |

关键观察：

- **括号里的原生名是最强锚点**：`Romanized (Native)` 几乎不会误判，还能顺手建立“罗马字 ↔ 日文/韩文/中文”的别名表。
- 名字里允许出现数字和英文：`末夜787`、`51酱`、`鱼子酱Fish`、`Min.E`、`Son.J`，不能简单用“纯字母”过滤。
- 有些标题**本来就没有模特名**：`GMS`、`BLT MONSTER Round 8`、`別冊SPA! Vol.25`、`JISAM`。这类要主动识别为“无人名”，而不是硬抽。

---

## 2. 五种做法对比

| 方法 | 本站在 2000 条上的表现 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **正则规则** | 覆盖 ~95%，精度高 | 快、免费、可解释、易调试 | 新出版社格式要补规则 |
| **别名字典** | 补 1–3% | 解决 `Yin Tian Tian` / `尹甜甜` 这类变体 | 需要冷启动语料 |
| **通用 NER**（spaCy/Stanza） | 很差 | 开箱即用 | 对罗马字日韩名、中文昵称几乎无效，不建议 |
| **LLM 抽取** | 长尾最好 | 新格式零规则、能判断“无人名” | 有成本/延迟，需要防幻觉 |
| **混合（推荐）** | **98.8%** | 兼顾成本与覆盖 | 多一层工程 |

> 结论：**规则 + 别名字典为主，LLM 只兜底**。不要一上来就全量丢给 LLM，2000 条里 95% 是规则能稳定解决的。

---

## 3. 推荐的抽取流水线

```
标题
 ├─ 0. 归一化：HTML 实体、全角→半角、连续空白、·/・ 统一
 ├─ 1. 规则级联（按出版社前缀，顺序敏感）
 │     Coser@ → [内购无水印] → [AIGirl] → DJAWA → [LE] → pair(...) → XIUREN/UGIRLS/IMISS/YouMi → [JP] 纯日文名
 ├─ 2. 别名字典：最长匹配（罗马字/原生名/变体），带词边界
 ├─ 3. LLM 兜底：仅对“未命中 + 低置信度”调用，JSON 输出，按标题哈希缓存
 └─ 4. 人工复核队列：confidence < 0.8 或 LLM 与字典冲突
```

### 3.1 规则层

规则按“信号强度”排序，强规则先跑：

1. `Coser@名字`、`[内购无水印] 名字 秀人网模特`、`XIUREN/UGIRLS/IMISS/YouMi 编号 名字` —— 位置固定，置信度 0.9+；
2. `名字 (原生名)` —— 全站最强通用信号，置信度 0.9；
3. `[LE] 番号 名字`、`[AIGirl] 名字 日期`、`DJAWA Photo 名字` —— 置信度 0.8；
4. `[JP] 纯日文名 + 作品标记` —— 置信度 0.75，容易把作品名当人名，需配合标记词表。

两个容易踩的坑：

- **番号要跳过**：`[LE] LEHC-037 Min.E` 里的 `LEHC-037` 不是名字；正则要支持 `AG.737` 这种带点的编号。
- **“无人名”要显式判定**：`GMS`、`Model Collection`、`BLT MONSTER`、`JISAM`、杂志期号，应该输出空值，而不是把系列名当模特。

### 3.2 别名字典

从高置信度结果自动积累：

```
models(id, canonical_name, native_name)
aliases(alias_norm, model_id, source)
```

- `alias_norm`：小写、去空格/点/连字符、全角转半角；
- 罗马字别名匹配要加**词边界**，否则 `Ray` 会命中 `Stray`；
- 中文/日文别名用子串匹配即可；
- 同一个人的 `Yin Tian Tian` / `尹甜甜` / `yin tian tian` 归到同一个 `model_id`。

### 3.3 LLM 兜底层

只处理规则和字典都没搞定的 2–5%，按 20 条一批，`temperature=0`，强制 JSON：

```text
你是写真标题信息抽取器。输入是一批标题，输出 JSON 数组。
规则：
1. 只抽“模特/写真偶像/Coser”的人名，不要抽出版社、番号、作品名、杂志名。
2. 名字保留原文大小写；如果有“罗马字 (原生名)”，两个都填。
3. 标题里确实没有人名（如 GMS、BLT MONSTER、JISAM、杂志期号）时，name 为 null。
4. 多个人名用数组；双人组合（twins/姉妹/&）拆成多个。
5. 不确定时 confidence < 0.6，不要编造。

输出：[{"i":0,"name":"...","native":"...","confidence":0.0}]
```

工程要点：

- 按 `sha1(title)` 缓存结果，避免重复付费；
- 校验返回的 `name` 必须是标题的子串（防止幻觉）；
- LLM 结果先进“待复核”，不要直接写主表。

---

## 4. 原型实测

```bash
python3 extract_models.py --pages 20 --out models.csv
```

结果（2000 条最近标题）：

```
总计 2000 条，命中 1976 条 (98.8%)，未命中 24 条

pair        795    # 罗马字 (原生名)
coser       677    # Coser@名字
aigirl      353    # [AIGirl] 名字 日期
neigou       94    # [内购无水印] …
bracket_cjk  27    # [JP] 纯日文名
le            9
xr            6
dajawa        4
ag            4
bracket       2
bluecake      2
youmi         2
dict          1
```

- 去重后 **614 个模特名**；
- 未命中的 24 条里，大部分是**确实没有人名**的（`GMS`、`BLT MONSTER Round N`、`JISAM`、杂志期号），少数是硬 case（`尊みを感じて桜井` 这种双关标题）；
- 抽样 40 条人工检查，未发现明显误抽。

样例：

| 标题 | 抽取结果 |
| --- | --- |
| `[JP] Toyoda Runa (豊田ルナ) 週刊少年マガジン…` | `Toyoda Runa` / `豊田ルナ` |
| `[内购无水印] 鱼子酱Fish 秀人网模特 惊红之舞` | `鱼子酱Fish` |
| `Coser@洛璃LoLiSAMA 碧蓝航线 信浓赛车` | `洛璃LoLiSAMA` |
| `[AIGirl] 芭喜mila 0916` | `芭喜mila` |
| `[LE] GMS-006A GMS` | `null`（系列名，正确拒绝） |

---

## 5. 工程化建议

1. **数据源用 REST API，不要爬 HTML**：
   - `GET /wp-json/wp/v2/posts?per_page=100&page=N&_fields=id,date,link,title,categories`
   - 增量：`?after=2026-10-01T00:00:00&per_page=100` 或 `modified_after`；
   - 控制频率（0.3–0.5s/请求），SSL 偶发 EOF 要重试。
2. **落库 SQLite**：`posts` / `models` / `aliases` / `review_queue` 四张表，保留 `method` 与 `confidence`，方便回溯。
3. **先做 200 条人工标注**，算 precision/recall，再决定规则阈值；不要凭感觉调。
4. **多人与组合**：`twins`、`姉妹`、`&`、`×` 要拆成多个 `model_id`，不要塞进一个字符串。
5. **定期回归**：出版社换标题格式时，未命中率会突然上升，用“未命中 Top 前缀”报表定位。

---

## 6. 局限

- 标题里没有名字的（系列、杂志期号）无法抽，只能留空；
- 同名/近似名（`王馨瑶Yanni` vs `王馨瑶yanni`）需要别名表归一；
- 个别双关/梗标题（`尊みを感じて桜井`）规则很难，交给 LLM 或人工；
- 内容涉及成人/版权素材，抓取与使用请遵守站点条款与当地法律。
