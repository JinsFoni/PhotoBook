"""模特名判定:filters.resolve_model(标题规则 × tag 交叉验证)。

2026-10-27 线上实录:[LE] 这家出品方的 tag 排在 tag 列表首位,buondua /
misskon 的「tag → 模特名」把 `LE` 当人名,建出假模特 le,14 本写真集挂错
(合集 slug 全是 `le-[le]-…`)。往排除词里补 `LE` 只治这一家,所以改成
「标题规则优先、tag 兜底」,但用交叉验证挡住标题规则的已知抽歪形态。
"""

from app.services.harvest.filters import resolve_model
from app.services.harvest.titlemodel import model_name_from_title

# [LE] 未进排除词时的现场:tag 顺序 [LE, 真名]
LE_TAGS = ["LE", "Xiu"]


def test_tag_first_wins_when_title_has_no_name():
    """标题抽不出人名时完全走 tag(行为不变)。"""
    assert resolve_model("[Cosplay] 电玩展台随拍 (42 photos)", ["Cosplay", "麻花麻花酱"],
                         "cosplay") == ("麻花麻花酱", "")


def test_publisher_tag_loses_to_title_name():
    """tag 命中的是标题里的出品方方括号 → 标题里的人名才是模特。"""
    assert resolve_model("[LE] LEHF-209B: Xiu (74 photos)", LE_TAGS, "") == ("Xiu", "")


def test_publisher_tag_carries_native_name():
    assert resolve_model("[LE] LEBE-110: U.Hwa (은유화) (70 photos)",
                         ["LE", "U Hwa"], "") == ("U.Hwa", "은유화")


def test_excluded_publisher_falls_back_to_title():
    """tag 全被排除(补了 LE)时不再落「未分类」,用标题里的名字。"""
    assert resolve_model("[LE] LEDG-237 - Ming (73 photos)", ["LE"], "le")[0] == "Ming"


def test_same_person_keeps_tag_name_and_native():
    """两路同一人 → 保留 tag 名(它更接近站点写法),原生名照旧带上。"""
    assert resolve_model("[JP] Asano Kokoro (浅野こころ) - FRIDAYデジタル写真集",
                         ["JP", "Asano Kokoro"], "jp") == ("Asano Kokoro", "浅野こころ")


def test_same_person_different_spelling_uses_title():
    """同一人写法不同(tag `U Hwa` / 标题 `U.Hwa`)→ 取标题写法,免得建两条模特。"""
    assert resolve_model("[LE] LEDG-153 U.Hwa (은유화) (63 photos)",
                         ["LE", "U Hwa"], "") == ("U.Hwa", "은유화")


def test_disagreement_keeps_tag_name():
    """标题抽到的人与 tag 不是同一人、且 tag 不在方括号里 → 不覆盖 tag。"""
    assert resolve_model("Coser@linhi_cute (yuumeilyn): 甘露寺蜜璃",
                         ["yuumeilyn"], "")[0] == "yuumeilyn"


def test_gms_is_a_model_not_a_series():
    """2026-10-27 用户确认 GMS 是模特名(此前被当系列名写进 _STOP)。"""
    assert model_name_from_title("[LE] GMS-006A GMS") == ("GMS", "")
    assert resolve_model("[LE] GMS-006A: GMS (60 photos)", ["GMS", "LE"], "") == ("GMS", "")


def test_title_name_cleaned_of_account_colon_and_brackets():
    """标题规则的两处已知抽歪:名字后的尾冒号、名字位前的出品方方括号。"""
    assert model_name_from_title("Coser@水淼Aqua: 星穹铁道 灵砂 (24 photos)")[0] == "水淼Aqua"
    assert model_name_from_title("[AI Enhanced] [MAXIM] Green (그린): MX-GR02")[0] == "Green"
    # 尾冒号在「[内购无水印] 名字: 作品名」这条规则上也出现过,统一在收尾清洗
    assert model_name_from_title("[内购无水印] 鱼子酱Fish: 玫瑰 (120 photos)")[0] == "鱼子酱Fish"


def test_no_name_anywhere_stays_unsorted():
    assert resolve_model("[Cosplay] 随拍合集 (20 photos)", ["cosplay"], "cosplay") == ("", "")
