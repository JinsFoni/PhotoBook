"""运行配置 — 全部可用环境变量覆盖(Docker 部署只改 env)。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Photo Collection"
    host: str = "0.0.0.0"
    port: int = 8777

    # ---- 存储 ------------------------------------------------------------
    data_dir: Path = Path("./data")        # SQLite
    media_dir: Path = Path("./media")      # 平台图片库 + 缩略图缓存
    library_dir: Path = Path("./library")  # 采集归档库(素材库)

    # ---- 种子内容 -------------------------------------------------------
    # 导入内置 demo 写真(23 个示例集合 + 8 位示例模特,需联网拉图)。
    # 生产环境保持 False;pytest 在 conftest.py 里显式开为 True。
    seed_demo: bool = False

    # ---- 采集(默认值,可在管理后台的 settings 表覆盖) ---------------------
    harvest_enabled: bool = True
    harvest_interval_hours: float = 6.0
    harvest_pages_per_round: int = 1
    harvest_source: str = "https://buondua.com"
    harvest_whitelist: str = ""            # 逗号分隔
    harvest_blacklist: str = "jav, leaked"
    harvest_unsorted_dir: str = "未分类"
    # 模特名排除词(逗号分隔,按词匹配):从详情页 tag 里挑模特名时,命中即跳过
    # (值为 buondua 全站统计得出的出品方/分类 tag,见 docs/architecture.md §十一)
    harvest_model_exclude: str = (
        "cosplay, jp, xiuren, atfm, otherxxx, ai generated, ai enhanced, "
        "general collection, korea, 内购无水印, aigirl, xr uncensored, djawa, "
        "rosi, bimilstory, ag, x-level, private photoshoot, ns纳丝摄影, "
        "sweetbox, pure media, dongeuran, herovia, bluecake, feilin, ishow, "
        "kelagirls, toutiao, ugirls, youmi, kimlemon, jisam, gms, jvid, patreon, mzsock, "
        "graphis, wanimal"
    )
    harvest_max_bytes: int = 4 * 1024**3   # 单文件上限 4GB
    harvest_session_secret: str = "change-me"

    # ---- 会话 -------------------------------------------------------------
    session_ttl_hours: int = 24 * 14

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.media_dir, self.library_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
