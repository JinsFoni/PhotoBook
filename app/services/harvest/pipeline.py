"""采集管线:下载(流式+断点续传)→ SHA256 校验 → 7zz 解压 → 归档 → 删包。"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from curl_cffi import requests as cr

from .filters import sanitize_path_part


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download_stream(url: str, dest: Path, *,
                    expected_sha256: str = "",
                    max_bytes: int = 4 * 1024**3,
                    on_progress=None) -> Path:
    """流式下载,支持 Range 断点续传。完成后校验 SHA256。

    on_progress(done_bytes, total_bytes) — total 可能为 0(未知)。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    headers = {}
    done = 0
    if tmp.exists():
        done = tmp.stat().st_size
        headers["Range"] = f"bytes={done}-"

    total = 0
    # curl_cffi 0.16.x 的 Response 不支持 with 语句(部分版本才支持),
    # 统一用手动 close + try/finally,流式读完后释放连接。
    r = cr.get(url, impersonate="chrome", headers=headers, stream=True,
               timeout=(20, 120))
    try:
        if r.status_code not in (200, 206):
            raise RuntimeError(f"下载失败 HTTP {r.status_code}")
        if r.status_code == 200:
            done = 0  # 服务端不支持续传,重下
        cl = r.headers.get("content-length")
        if cl:
            total = int(cl) + (done if r.status_code == 206 else 0)

        sha = hashlib.sha256()
        if done:
            sha.update(tmp.read_bytes())  # 已下载部分计入校验

        mode = "ab" if (r.status_code == 206 and done) else "wb"
        with open(tmp, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if done > max_bytes:
                    raise RuntimeError(f"超过单文件大小上限 {human(max_bytes)}")
                if on_progress:
                    on_progress(done, total)
    finally:
        r.close()

    digest = sha.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 不匹配: 期望 {expected_sha256[:12]}… 实得 {digest[:12]}…")

    tmp.replace(dest)
    return dest


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
        if proc.returncode != 0 or "Successfully" not in out:
            return False, out.strip()[:300]
        return True, ""

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
    目标已存在 → 抛 FileExistsError(由调用方标记「已存在」)。
    """
    model_part = sanitize_path_part(model_name) if model_name else sanitize_path_part(unsorted_dir)
    inner = _sole_top_dir(archive_path)
    title_part = sanitize_path_part(inner.name) if inner is not None else ""
    if not title_part:
        title_part = sanitize_path_part(title)
    target = library_root / model_part / title_part
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(str(target))
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
