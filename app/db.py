"""SQLAlchemy 模型 — 全部 12 张表。库中只存元数据,文件在磁盘 volume。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_dt(dt: datetime | None) -> datetime | None:
    """DB 里的 naive UTC 时间 → 本地时间(展示用)。

    优先 ZoneInfo("Asia/Shanghai"); slim 镜像无 tzdata 时回退固定 +8
    (中国无夏令时, 固定偏移永远正确)。输入 None 原样返回。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite 存的是 naive UTC
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return dt.astimezone(timezone(timedelta(hours=8)))


class Base(DeclarativeBase):
    pass


# ---- 用户与权限 -----------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user")  # user | admin
    avatar_seed: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str] = mapped_column(String(8), default="")  # 界面语言(""=跟随站点默认)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete")


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


# ---- 内容库 ---------------------------------------------------------------

class Model(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    stage_name: Mapped[str | None] = mapped_column(String(120), default=None)
    avatar_path: Mapped[str | None] = mapped_column(String(400), default=None)  # /media 相对路径
    hero_path: Mapped[str | None] = mapped_column(String(400), default=None)
    gender: Mapped[str | None] = mapped_column(String(20), default=None)
    age: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[str | None] = mapped_column(String(30), default=None)
    measurements: Mapped[str | None] = mapped_column(String(60), default=None)
    agency: Mapped[str | None] = mapped_column(String(120), default=None)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    since: Mapped[str | None] = mapped_column(String(20), default=None)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft|published|hidden
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collections: Mapped[list["Collection"]] = relationship(back_populates="model")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="model_tags", lazy="selectin", order_by="ModelTag.pos")


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    cover_photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"), default=None)
    published_at: Mapped[str | None] = mapped_column(String(20), default=None)  # YYYY.MM.DD
    status: Mapped[str] = mapped_column(String(20), default="published")  # processing|draft|published|hidden
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_weight: Mapped[int] = mapped_column(Integer, default=0)
    # 源站序号:采集导入时写入,浏览器联动脚本用它精确判定「已入库」。
    # source_serial = 入库时那一站的序号;source_serials(JSON 数组)额外收录
    # 同一本写真在其他站的序号 —— 三站转载同一作品时序号体系各自独立
    # (buondua 56556 ↔ misskon 117727),只有单序号会让另外两站的链接
    # 永远显示「可下载」,点了重复下一遍已入库的包。
    source_serial: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    source_serials: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    model: Mapped[Model | None] = relationship(back_populates="collections")
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan",
        order_by="Photo.sort_order", lazy="selectin",
        foreign_keys="Photo.collection_id")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="collection_tags", lazy="selectin", order_by="CollectionTag.pos")

    __table_args__ = (Index("ix_collections_status_date", "status", "published_at"),)


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))       # /media 相对路径
    width: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[int | None] = mapped_column(default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collection: Mapped[Collection] = relationship(back_populates="photos",
                                                   foreign_keys=[collection_id])

    __table_args__ = (UniqueConstraint("collection_id", "filename", name="uq_photo_file"),)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)

    models: Mapped[list[Model]] = relationship(secondary="model_tags", back_populates="tags")
    collections: Mapped[list[Collection]] = relationship(secondary="collection_tags", back_populates="tags")


class ModelTag(Base):
    __tablename__ = "model_tags"
    # pos = 挂载时的输入顺序(详情页标签按用户输入顺序展示)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    pos: Mapped[int] = mapped_column(Integer, default=0)


class CollectionTag(Base):
    __tablename__ = "collection_tags"
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    pos: Mapped[int] = mapped_column(Integer, default=0)


# ---- 用户行为 ---------------------------------------------------------------

class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(12))  # model | collection | photo
    target_key: Mapped[str] = mapped_column(String(255))  # slug 或 collection:idx
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_key", name="uq_fav"),)


# ---- 采集子系统(需求 §29)----------------------------------------------------

class HarvestJob(Base):
    __tablename__ = "harvest_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    serial: Mapped[int] = mapped_column(Integer, index=True)       # 源站序号
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    model_name: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    # queued | parsing | downloading | extracting | done | exists | skipped | failed
    bytes_done: Mapped[int] = mapped_column(Integer, default=0)
    bytes_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    # failed 时若已归档到 library(import 失败等), 记录残留目录路径供删除任务时清理
    archive_dir: Mapped[str | None] = mapped_column(String(500), default=None)
    # 导入成功后写真 slug: 用于任务列表实时判断缩略图是否生成完(替代静态文案)
    collection_slug: Mapped[str | None] = mapped_column(String(220), default=None)
    source: Mapped[str] = mapped_column(String(10), default="auto")  # auto | manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    # 最后一次进度更新时间: 看门狗据此判定进行中任务是否停滞
    updated_at: Mapped[datetime | None] = mapped_column(default=None, onupdate=utcnow)

    __table_args__ = (Index("ix_jobs_status_id", "status", "id"),)


class HarvestHistory(Base):
    __tablename__ = "harvest_history"
    serial: Mapped[int] = mapped_column(Integer, primary_key=True)  # 源站序号,去重判据
    status: Mapped[str] = mapped_column(String(12))
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---- PikPak 对接(油猴脚本 PikPak to PhotoBook)--------------------------------

class PikPakJob(Base):
    """PikPak 下载任务 — 由油猴脚本推送勾选的文件/文件夹入队。

    与 HarvestJob 是两条独立的队列: harvest 走「详情页 → 短链 → MediaFire」,
    这里由脚本把勾选项展开成直链列表, 不解析详情页(用户 2026-10 决定:
    PikPak 勾选的文件夹本身就是写真集)。

    粒度是 **一个勾选项 = 一个任务 = 一个写真集**: 勾文件夹时脚本展开它的
    所有文件(递归/翻页, 不受 100 条限制), 按相对路径写进 PikPakFile, worker
    逐个下载到同一写真目录; 勾压缩包时只有一个文件, 该文件即写真集本体,
    下载后走解压归档。压缩包与纯图片目录都能落地成写真集。
    """
    __tablename__ = "pikpak_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    # 勾选项标识: 同一批勾选共享同一个 uuid(前端回显与分组用)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    # 勾选项显示名(文件夹名, 或压缩包/单图文件名), 用作写真标题
    name: Mapped[str] = mapped_column(String(255))
    # 勾选项在 PikPak 侧的文件 ID(单个勾选项一个, 去重判据)
    file_id: Mapped[str] = mapped_column(String(64), index=True)
    # 是压缩包(zip/rar/7z/…): 下载后解压归档; 否则按图片目录下载
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer, default=0)    # 勾选项总字节
    # 模特名(脚本可填;空=未分类)
    model_name: Mapped[str | None] = mapped_column(String(120), default=None)
    # 脚本填写的 tag,逗号分隔(入库时拆分挂到合集与模特)
    tags: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    # queued | downloading | extracting | done | failed
    files_done: Mapped[int] = mapped_column(Integer, default=0)
    files_total: Mapped[int] = mapped_column(Integer, default=0)
    bytes_done: Mapped[int] = mapped_column(Integer, default=0)
    bytes_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    # 导入成功后写真 slug(任务列表实时判态用)
    collection_slug: Mapped[str | None] = mapped_column(String(220), default=None)
    # 下载/导入失败时残留在 library 的归档目录,删除任务时清理
    archive_dir: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime | None] = mapped_column(default=None, onupdate=utcnow)

    __table_args__ = (Index("ix_pikpak_jobs_status_id", "status", "id"),)


class PikPakFile(Base):
    """勾选项展开后的单个文件(直链)。job_id 相同的行属于同一个写真集。

    rel 是相对勾选项的路径(含文件名), 下载时按它落到写真目录, 子文件夹结构
    因此能原样保留。dedupe_key 是 PikPak 侧文件 ID: 同一勾选项在同一次推送里
    不会重复, 但换批重新推送同名勾选项时用它判「已入队/已下过」。
    """
    __tablename__ = "pikpak_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("pikpak_jobs.id",
                                                  ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    rel: Mapped[str] = mapped_column(String(500))     # 相对勾选项的路径
    size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="queued")
    # queued | done | failed
    error: Mapped[str | None] = mapped_column(Text, default=None)


# ---- 配置 -------------------------------------------------------------------

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)


# ---- 外部存储与上传 ----------------------------------------------------------

class Storage(Base):
    """外部存储后端(图床等)。type 决定用哪个 backend 实现。"""
    __tablename__ = "storages"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(20), default="imgbed")  # imgbed | webdav | (预留 s3/r2)
    root_dir: Mapped[str] = mapped_column(String(200), default="")   # 远端根目录,如 /PhotoBook
    api_url: Mapped[str] = mapped_column(String(300), default="")    # imgbed: 站点地址; webdav: 服务地址(如 http://host:5244,不含 /dav)
    token: Mapped[str] = mapped_column(String(300), default="")      # imgbed: API Key; webdav: 密码
    username: Mapped[str] = mapped_column(String(120), default="")   # webdav 用户名(imgbed 不用)
    priority: Mapped[int] = mapped_column(Integer, default=0)        # 直链优先级,越大越优先(本地缺失时按此排序回源/302)
    manual_upload: Mapped[bool] = mapped_column(Boolean, default=False)  # 参与写真集列表的手动上传(需 enabled)
    direct_link: Mapped[bool] = mapped_column(Boolean, default=True)  # 参与 URL 直链(302/回源);关闭=纯备份
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UploadJob(Base):
    """一个写真集 × 一个存储的上传任务(DB 表作队列,重启不丢)。"""
    __tablename__ = "upload_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    storage_id: Mapped[int] = mapped_column(ForeignKey("storages.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    # queued | running | done | failed
    photos_done: Mapped[int] = mapped_column(Integer, default=0)
    photos_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(default=None, onupdate=utcnow)

    __table_args__ = (Index("ix_upload_jobs_status_id", "status", "id"),)


class PhotoUpload(Base):
    """单张照片在某存储上的上传结果。remote_path 是 /file/ 后的真实路径
    (imgbed 会给文件名加时间戳前缀,必须逐张记录返回值)。"""
    __tablename__ = "photo_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    storage_id: Mapped[int] = mapped_column(ForeignKey("storages.id", ondelete="CASCADE"), index=True)
    remote_path: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("photo_id", "storage_id", name="uq_photo_upload"),)
