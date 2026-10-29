"""采集管线:下载(流式+断点续传)→ SHA256 校验 → 7zz 解压 → 归档 → 删包。"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as cr

log = logging.getLogger(__name__)

from .filters import sanitize_path_part
from .titlematch import photo_count


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# 进行中的下载流: key -> Response。看门狗发现任务停滞时,
# 从其它线程 close() 对应流, 立即解堵阻塞中的 iter_content(实测有效)。
_STREAMS: dict = {}


def close_stream(key) -> bool:
    """关闭指定 key 的进行中下载流(另一线程调用)。返回是否找到并关闭。"""
    r = _STREAMS.pop(key, None)
    if r is None:
        return False
    try:
        r.close()
        return True
    except Exception:
        return False


def close_job_streams(job_id) -> int:
    """关闭一个任务名下的全部在途流(pikpak 并发下载的 key 是
    "<job_id>:<file_id>"; 也兼容裸 job_id 的单流任务)。返回关闭数。"""
    prefix = f"{job_id}:"
    closed = 0
    for key in [k for k in _STREAMS if k == job_id or str(k).startswith(prefix)]:
        if close_stream(key):
            closed += 1
    return closed


# 瞬时故障重试(2026-10-22): MediaFire 前置 Cloudflare 抽检会回 403
# (`cf-mitigated: challenge`),CDN 也会偶尔 5xx / 断流。这些失败都留下
# 合法前缀(.part),Range 续传接着下即可 —— 以前一次 403 就整任务判死
# (任务 596 两次重排都死在这),现在退避重试。
RETRY_STATUS = (403, 408, 425, 429, 500, 502, 503, 504)
RETRY_BACKOFF = (2.0, 5.0)
# MediaFire 拒下时回的是「软拒绝」:HTTP 200 + text/html 的
# download_repair.php 验证页(几十 KB,每次内容都不同) —— 状态码正常、长度
# 正常不了,只有 SHA 校验能发现。这类要等得久一点(实测 5 个任务在 13:46-13:57
# 连续撞上,过一会儿自愈),退避给足。
SOFT_BLOCK_BACKOFF = (5.0, 20.0)
# 大文件被反复断流(2026-10-22 实测 1.4GB 那卷):MediaFire CDN 每条连接只给
# 20-25MB 就掐断,不管直连还是代理。但每次重试都留下合法前缀、Range 续传能
# 接着下 —— 所以「有进展」的连接失败不消耗重试预算,一直滚到下完为止。
PROGRESS_BACKOFF_MAX = 10.0
PROGRESS_RETRIES = 120   # 有进展时的额外重试轮数上限(120×25MB ≈ 3GB)
# 「零进展」的连接失败(连上就被掐, 一个字节都没写)按**整卷累计**给预算, 而且
# 退避要长: 2026-10-29 任务 931(2.15GB)实测是这样的曲线 —— CDN 每 ~35MB 掐一次
# (有进展, 走 PROGRESS_RETRIES 不计), 但每隔几次就夹一个「连上即死」的, 攒到
# 3 次(旧预算)或 6 次就判死, 而重排后总能从 .part 续下去(960MB → 1.81GB)。
# 这明显是对新连接的频率限制, 不是出口不通: 给 30 次累计 + 最长 30s 退避。
CONN_STALL_BUDGET = 30
STALL_BACKOFF = (5.0, 10.0, 20.0, 30.0)


class _Retryable(RuntimeError):
    """内部标记:瞬时失败可重试。区别于 404/大小超限/SHA 不符这类终态失败。

    conn=True 表示连接层失败(建连就不通 / 流读到一半被对端断开)——
    这类失败除了重试,还值得换出口(见 proxy_fallback)。
    """

    def __init__(self, msg: str, *, conn: bool = False, soft: bool = False):
        super().__init__(msg)
        self.conn = conn    # 连接层失败(可换出口再试)
        self.soft = soft    # 软拒绝(返回网页而非文件):退避加长


# 出口选择(2026-10-22 实测):harvest.proxy 是给「页面/短链/API」过 Cloudflare
# 用的,对大文件流反而有害 —— 经 http 代理读 MediaFire CDN 到 12MB 就被对端
# 断流(curl 56)、限速到几十 KB/s;同一 dlink 直连 17MB/s 跑满 2GB 无中断。
# 所以按 host 记一份「优先走哪边」:MediaFire CDN 默认直连,其余(用户配了代理
# 就)默认代理;哪边连接层失败过就翻面,本进程内记住(worker 常驻,重启即清空)。
_EGRESS: dict[str, bool] = {}  # host -> 是否优先走代理(学到后覆盖默认)


def _part_size(tmp: Path) -> int:
    try:
        return tmp.stat().st_size
    except OSError:
        return 0


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _prefer_proxy(host: str) -> bool:
    """该 host 优先走代理吗?MediaFire 的 download####.mediafire.com 默认直连。"""
    if host in _EGRESS:
        return _EGRESS[host]
    return not host.endswith(".mediafire.com")


def download_stream(url: str, dest: Path, *,
                    expected_sha256: str = "",
                    expected_size: int = 0,
                    max_bytes: int = 4 * 1024**3,
                    on_progress=None,
                    stream_key=None,
                    use_proxy: bool = True,
                    headers: dict | None = None,
                    retries: int = 3,
                    progress_retries: int = PROGRESS_RETRIES,
                    proxy_fallback: bool = True,
                    session=None,
                    referer: str = "") -> Path:
    """流式下载,支持 Range 断点续传。完成后校验 SHA256。

    on_progress(done_bytes, total_bytes) — total 可能为 0(未知)。
    stream_key — 注册键(worker 传 job_id), 看门狗可从其它线程 close 解堵。
    use_proxy — False 时无视 harvest.proxy 强制直连(pikpak CDN 实测直连可达)。
    headers — 额外请求头(terabox CDN 校验 ndus Cookie,必须随请求带上;
      Range 头由本函数按续传状态自行填,传入同名键会被覆盖)。
    expected_size — 已知文件大小时传进来。content-length 与它不符(典型:
      MediaFire 拿一页 HTML 冒充文件)当场判软拒绝,不写盘、不等到 SHA 校验。
    retries — 瞬时失败(403/429/5xx/连接中断)**且没有进展**时的尝试次数,默认 3。
      若某次连接失败前 .part 长大了(说明是对端掐断而非不通),不消耗这个预算,
      改按 progress_retries 继续续传(大文件被切成一段段下)。
      终态失败(404/410、超过 max_bytes、SHA 不符)不重试。
    proxy_fallback — 允许按 host 自动选出口(MediaFire CDN 直连优先,连接层
      失败自动翻面并记住)。TeraBox 这类 dlink 与该出口 IP 绑定的场景传 False,
      永远只用 use_proxy 指定的那一边。
    session — 复用的 curl_cffi Session(MediaFire 直链绑定取页面的那个客户端;
      不带 cookie 换个连接下 4/4 被塞验证页)。传了就由调用方负责关闭。
    referer — 随下载请求带的 Referer(与页面一致,浏览器行为)。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    attempts = max(1, int(retries))
    host = _host_of(url)
    auto_egress = bool(use_proxy and proxy_fallback and host)
    last = "未尝试"
    attempt = 0
    stalls = 0        # 没有进展的失败次数
    progress_rounds = 0
    while True:
        attempt += 1
        eff_proxy = _prefer_proxy(host) if auto_egress else use_proxy
        before = _part_size(tmp)
        try:
            _download_once(url, dest, expected_sha256=expected_sha256,
                           expected_size=expected_size,
                           max_bytes=max_bytes, on_progress=on_progress,
                           stream_key=stream_key, use_proxy=eff_proxy,
                           headers=headers, session=session,
                           referer=referer)
        except _Retryable as exc:
            last = str(exc)
            gained = _part_size(tmp) - before
            log.warning("下载第 %d 次失败(出口%s,%s): %s — %s",
                        attempt, "代理" if eff_proxy else "直连",
                        f"已续 {gained/1048576:.1f}MB" if gained > 0 else "无进展",
                        last, url[:160])
            # 只有「一点都没下下来」才算这个出口不通。MediaFire CDN 会按连接
            # 掐流(每 ~35MB 一次 curl 56), 那是限速不是出口坏 —— 2026-10-29 实录:
            # 旧逻辑每次都翻面, 于是一半的段走了代理(慢), 而且两边来回翻。
            if auto_egress and getattr(exc, "conn", False) and gained == 0:
                _EGRESS[host] = not eff_proxy
                log.warning("下载 host %s 经%s连接失败,后续该 host 改走%s",
                            host, "代理" if eff_proxy else "直连",
                            "代理" if not eff_proxy else "直连")
            # 有进展(部分数据已落盘):不消耗重试预算,接着 Range 续传
            if gained > 0 and getattr(exc, "conn", False) \
                    and progress_rounds < progress_retries:
                progress_rounds += 1
                time.sleep(min(2.0 * min(progress_rounds, 5), PROGRESS_BACKOFF_MAX))
                continue
            stalls += 1
            limit = CONN_STALL_BUDGET if getattr(exc, "conn", False) else attempts
            if stalls >= limit:
                if getattr(exc, "soft", False):
                    raise RuntimeError(
                        f"{last}(已重试 {attempts} 次;MediaFire 这类拦是临时的,"
                        f"过一会儿重排即可)") from exc
                raise RuntimeError(last) from exc
            if getattr(exc, "soft", False):
                backoff = SOFT_BLOCK_BACKOFF
            elif getattr(exc, "conn", False):
                backoff = STALL_BACKOFF      # 连上即死: 越试越久(被限频)
            else:
                backoff = RETRY_BACKOFF
            time.sleep(backoff[min(stalls - 1, len(backoff) - 1)])
            continue
        return dest


def _download_once(url: str, dest: Path, *,
                   expected_sha256: str,
                   expected_size: int,
                   max_bytes: int,
                   on_progress,
                   stream_key,
                   use_proxy: bool,
                   headers: dict | None,
                   session=None,
                   referer: str = "") -> None:
    """跑一次下载尝试。瞬时失败抛 _Retryable(已写部分保留,下次续传)。"""
    tmp = dest.with_suffix(dest.suffix + ".part")

    hdrs = dict(headers or {})
    if referer:
        hdrs.setdefault("Referer", referer)
    done = 0
    if tmp.exists():
        done = tmp.stat().st_size
        hdrs["Range"] = f"bytes={done}-"

    total = 0
    # curl_cffi 0.16.x 的 Response 不支持 with 语句(部分版本才支持),
    # 统一用手动 close + try/finally,流式读完后释放连接。
    # 代理与 net 同源(settings 表 harvest.proxy,harvest 采集链路共用)。
    from .net import _proxy
    # 带了 Session 就用它(MediaFire 认 cookie 续接),但仍按本函数的出口策略
    # 逐请求决定走不走代理 —— Session 内的 cookie 与出口可以不一致。
    client = session if session is not None else cr
    try:
        r = client.get(url, impersonate="chrome", headers=hdrs, stream=True,
                       timeout=(20, 120),
                       proxy=_proxy() if use_proxy else None)
    except Exception as exc:
        raise _Retryable(f"下载连接失败 {type(exc).__name__}: {exc}",
                         conn=True) from exc
    if stream_key is not None:
        _STREAMS[stream_key] = r
    try:
        if r.status_code not in (200, 206):
            if r.status_code in RETRY_STATUS:
                raise _Retryable(f"下载失败 HTTP {r.status_code}")
            raise RuntimeError(f"下载失败 HTTP {r.status_code}")
        if r.status_code == 200:
            done = 0  # 服务端不支持续传,重下
        # 软拒绝拦截:MediaFire 拒绝下载时不改状态码,而是 302 到
        # download_repair.php 并回一页 HTML(几十 KB、无 content-length)。
        # 必须在写盘前识破 —— 否则这段 HTML 会被当成文件写进 .part,
        # 只能在 SHA 校验时才暴露,而那时 .part 已被删、整卷白下。
        ctype = (r.headers.get("content-type") or "").lower()
        if "text/html" in ctype or "download_repair" in str(r.url):
            raise _Retryable(
                f"MediaFire 拒绝下载(返回验证页而非文件,{ctype or 'text/html'})",
                soft=True)
        cl = r.headers.get("content-length")
        if cl:
            total = int(cl) + (done if r.status_code == 206 else 0)
            if expected_size and total != expected_size:
                raise _Retryable(
                    f"下载大小不符: 期望 {expected_size} 实得 {total}(多为验证页/截断)",
                    soft=True)
        elif expected_size:
            raise _Retryable("下载没有 content-length,无法确认是文件本体", soft=True)

        sha = hashlib.sha256()
        if done:
            # 已下载部分计入校验 —— 分块流式读: read_bytes() 会把整个 .part
            # (可达数 GB)一次性载入内存,是容器内存峰值暴冲的元凶
            with open(tmp, "rb") as pf:
                for chunk in iter(lambda: pf.read(4 * 1024 * 1024), b""):
                    sha.update(chunk)

        mode = "ab" if (r.status_code == 206 and done) else "wb"
        with open(tmp, mode) as f:
            try:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if done > max_bytes:
                        raise RuntimeError(f"超过单文件大小上限 {human(max_bytes)}")
                    if on_progress:
                        on_progress(done, total)
            except RuntimeError:
                raise
            except Exception as exc:  # 连接中断/超时: 已写字节合法,可续传
                raise _Retryable(f"下载中断 {type(exc).__name__}: {exc}",
                                 conn=True) from exc
    finally:
        if stream_key is not None:
            _STREAMS.pop(stream_key, None)
        r.close()

    digest = sha.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 不匹配: 期望 {expected_sha256[:12]}… 实得 {digest[:12]}…")

    tmp.replace(dest)


def extract_archive(archive: Path, dest_dir: Path, password: str, *,
                    on_stage=None) -> list[Path]:
    """解压(含校验)。返回解压出的文件列表。失败抛 RuntimeError。

    password 可为空串、单密码,或 "a.com or b.com" 形式的多候选
    (详情页原文如此;实际加密用哪个取决于发布站点)。逐个尝试。

    优先用 7zz;遇到 RAR5 部分加密包(7zz 26.03 会报 Unsupported Method)
    回退到 unar——实测 unar 能完整解出(2026-09 验证)。
    """
    if on_stage:
        on_stage("extracting")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 候选密码:原文含 " or " 时拆开逐试,否则 [原文, 默认]
    cands: list[str] = []
    if password:
        if " or " in password:
            cands += [p.strip() for p in password.split(" or ") if p.strip()]
        else:
            cands.append(password)
    if "mrcong.com" not in cands:
        cands.append("mrcong.com")  # 历史默认
    if "4kup" not in cands:
        cands.append("4kup")  # 4kup.net 公开解压密码(仅多余尝试,无副作用)

    def _clean() -> None:
        # 换密码/换工具前清掉半截解压产物,避免残留混入下一轮
        for p in sorted(dest_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

    def _try_7zz(pwd: str) -> tuple[bool, str]:
        sevenzip = shutil.which("7zz") or shutil.which("7z")
        if not sevenzip:
            return False, "7zz not found"
        cmd = [sevenzip, "x", "-y", f"-p{pwd}", f"-o{dest_dir}", str(archive)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        err = (proc.stderr or "").strip()[:300]
        if proc.returncode == 0:
            return True, ""
        # Unsupported Method(RAR5 新压缩方式)→ 让调用方换 unar 重试
        if "Unsupported Method" in (proc.stdout or "") + (proc.stderr or ""):
            return False, "UNSUPPORTED_METHOD"
        return False, err

    def _try_unar(pwd: str) -> tuple[bool, str]:
        if not shutil.which("unar"):
            return False, "unar not found"
        # 注:unar 与 7zz 结构不同——它会压平归档内的单一顶层目录,
        # 产物多于一项时再套一层 <archive主名>/。此处不做改名/上提,
        # 交由 archive_collection 按实际产物决定归档名。
        proc = subprocess.run(["unar", "-f", "-p", pwd, "-o", str(dest_dir),
                               str(archive)],
                              capture_output=True, text=True, timeout=3600)
        out = (proc.stdout or "") + (proc.stderr or "")
        if "Missing or wrong password" in out or "No files extracted" in out:
            return False, out.strip()[:300]
        if "Successfully" in out:
            return True, ""
        # rc=1 但解出了文件 = 部分成功(源包内个别文件损坏); 88/89 完好
        # 远好于整包丢弃, 放行并告警
        files = [p for p in sorted(dest_dir.rglob("*")) if p.is_file()]
        if files:
            bad = [ln.strip()[:120] for ln in out.splitlines() if "Failed!" in ln]
            log.warning("unar partial extraction (%d files ok): %s",
                        len(files), "; ".join(bad[:3]))
            return True, ""
        return False, out.strip()[:300]

    last_err = ""
    tools = (_try_7zz, _try_unar)
    for tool in tools:
        for pwd in cands:
            ok, err = tool(pwd)
            if ok:
                files = [p for p in sorted(dest_dir.rglob("*")) if p.is_file()]
                if not files:
                    raise RuntimeError("解压后目录为空")
                return files
            if err == "UNSUPPORTED_METHOD":
                _clean()
                break  # 换下一个工具(密码不是问题)
            last_err = err
            _clean()
    raise RuntimeError(f"解压失败(已试密码 {cands}): {last_err}")


# 解压产物根层的常见系统垃圾项(不计入"唯一顶层目录"判定)
_JUNK = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}


def _sole_top_dir(root: Path) -> Path | None:
    """解压产物根层只有唯一目录(忽略系统垃圾项)时返回它,否则 None。"""
    entries = [p for p in root.iterdir()
               if p.name not in _JUNK and not p.name.startswith("._")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return None


def archive_collection(archive_path: Path, library_root: Path, *,
                       model_name: str, title: str,
                       unsorted_dir: str = "未分类") -> Path:
    """归档到 <library>/<模特名>/<写真目录>/。返回目标目录。

    写真目录名优先用解压产物自带的顶层目录(压缩包内一般已按标题建好目录,
    不再额外套一层标题目录);产物根层没有唯一目录时才回退到传入的 title。
    目标已存在非空 → 目录名追加 " (N)" 序号落盘,不丢包(权威去重在下载
    前的预检:history/dest_dir/collection_exists/跨站等价)。同名不同批
    ——同系列泛化标题的压缩包内目录名一样——若在这里抛 FileExistsError,
    1.5GB 下载成果直接报废(任务 375/376/378 实录)。
    """
    model_part = sanitize_path_part(model_name) if model_name else sanitize_path_part(unsorted_dir)
    inner = _sole_top_dir(archive_path)
    title_part = sanitize_path_part(inner.name) if inner is not None else ""
    page_part = sanitize_path_part(title or "")
    # 包内目录名有时只是页面标题的**截短**(4kup 老帖实录:页面
    # 「MFStar Vol.076 Mu Yu Qian (慕羽茜)」/ 包内「MFStar Vol.076」)。
    # 入库 title 取自这个目录名(library_import.import_album),照抄截短名
    # 会连模特名一起丢掉(任务 825 → 合集「MFStar Vol.076」+ 未分类)。
    # 只在「包内名是页面标题的前缀」且页面标题不带「(N photos)」尾缀时
    # 改用页面标题;其他来源页内目录名通常就是完整标题,行为不变。
    if (title_part and page_part and photo_count(title) is None
            and page_part.lower().startswith(title_part.lower())):
        title_part = page_part
    if not title_part:
        title_part = page_part
    target = library_root / model_part / title_part
    if target.exists() and any(target.iterdir()):
        n = 2
        while (library_root / model_part / f"{title_part} ({n})").exists():
            n += 1
        target = library_root / model_part / f"{title_part} ({n})"
    target.parent.mkdir(parents=True, exist_ok=True)
    if inner is not None:
        # 整体改名过去:归档目录名即压缩包自带的标题目录名
        if target.exists():
            target.rmdir()  # 空目录,直接让位
        shutil.move(str(inner), str(target))
        return target
    target.mkdir(parents=True, exist_ok=True)
    # 把压缩包内容整体挪进目标目录(保留解压时的子结构)
    for p in sorted(archive_path.rglob("*")):
        if p.is_file():
            rel = p.relative_to(archive_path)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), dst)
    return target
