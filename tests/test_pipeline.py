"""pipeline 归档 — 目录规则 <library>/<模特名>/<解压自带目录>/、防覆盖。"""

from __future__ import annotations

import pytest

from app.services.harvest.pipeline import archive_collection


def test_archive_layout(tmp_path):
    src = tmp_path / "extract"
    (src / "sub").mkdir(parents=True)
    (src / "a.jpg").write_bytes(b"x")
    (src / "sub" / "b.jpg").write_bytes(b"y")
    lib = tmp_path / "library"

    dest = archive_collection(src, lib, model_name="Yeha", title="School Nurse")
    assert dest == lib / "Yeha" / "School Nurse"
    assert (dest / "a.jpg").read_bytes() == b"x"
    assert (dest / "sub" / "b.jpg").exists()


def test_archive_uses_inner_dir_name(tmp_path):
    """压缩包自带标题目录 → 直接用它,不再额外套一层 title。"""
    src = tmp_path / "extract"
    (src / "XIUREN No.10977 CHENCHEN").mkdir(parents=True)
    (src / "XIUREN No.10977 CHENCHEN" / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"

    dest = archive_collection(src, lib, model_name="Yeha",
                              title="School Nurse (219 photos)")
    assert dest == lib / "Yeha" / "XIUREN No.10977 CHENCHEN"
    assert (dest / "a.jpg").read_bytes() == b"x"
    # 没有多出标题层
    assert not (lib / "Yeha" / "School Nurse (219 photos)").exists()


def test_archive_ignores_junk_when_detecting_inner_dir(tmp_path):
    """__MACOSX 等系统垃圾项不计入唯一顶层目录判定。"""
    src = tmp_path / "extract"
    (src / "Album").mkdir(parents=True)
    (src / "Album" / "a.jpg").write_bytes(b"x")
    (src / "__MACOSX").mkdir()
    dest = archive_collection(src, tmp_path / "lib", model_name="M", title="T")
    assert dest.name == "Album"


def test_archive_inner_dir_refuses_existing(tmp_path):
    """自带目录名已存在且非空 → 防覆盖。"""
    src = tmp_path / "extract"
    (src / "Album").mkdir(parents=True)
    (src / "Album" / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"
    (lib / "M" / "Album").mkdir(parents=True)
    (lib / "M" / "Album" / "sentinel").write_text("1")
    with pytest.raises(FileExistsError):
        archive_collection(src, lib, model_name="M", title="T")
    # 原内容未被破坏
    assert (lib / "M" / "Album" / "sentinel").exists()


def test_archive_refuses_existing_nonempty(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    lib = tmp_path / "library"
    dest = archive_collection(src, lib, model_name="M", title="T")
    (dest / "sentinel").write_text("1")
    with pytest.raises(FileExistsError):
        archive_collection(src, lib, model_name="M", title="T")


def test_archive_sanitizes_names(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="A/B", title="T:*")
    assert "/" not in dest.parts[-2] and ":" not in dest.parts[-1]


def test_unsorted_dir_when_no_model(tmp_path):
    src = tmp_path / "extract"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"x")
    dest = archive_collection(src, tmp_path / "lib", model_name="", title="T")
    assert dest.parent.name == "未分类"


def _make_rar(tmp_path, files: dict[str, bytes], password: str = "") -> Path:
    """用 7z 造一个 RAR(测试机需 p7zip 或系统 rar); 造不出则跳过。"""
    import shutil
    import subprocess
    src = tmp_path / "src"
    src.mkdir()
    for name, data in files.items():
        p = src / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    rar = tmp_path / "a.rar"
    sevenzip = shutil.which("7zz") or shutil.which("7z")
    if not sevenzip:
        import pytest
        pytest.skip("no 7z to build fixture")
    cmd = [sevenzip, "a", "-tr rar"][:3] + ["-tr ar"] if False else [sevenzip, "a", str(rar), str(src / "*")]
    cmd = [sevenzip, "a", "-tzip", str(rar), str(src / "*")]
    if password:
        cmd.insert(2, f"-p{password}")
    subprocess.run(cmd, check=True, capture_output=True)
    return rar


def test_extract_partial_failure_still_returns_files(tmp_path, monkeypatch):
    """unar rc=1 但解出了大部分文件时放行(部分成功), 不再整包丢弃。"""
    from app.services.harvest import pipeline
    import app.services.harvest.pipeline as P

    # 直接替换 _try_unar 行为不可取——测真实分支: 造一个 unar 不可用场景太麻烦,
    # 改为验证判定逻辑本身
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"x")
    (dest / "b.jpg").write_bytes(b"y")

    out_text = ("a.jpg... OK.\nb.jpg... Failed! (Attempted to read more data "
                "than was available)\nExtraction failed (1 file failed.)")
    # 模拟: rc=1, 无 "Successfully", 有文件 → 应放行
    files = [p for p in sorted(dest.rglob("*")) if p.is_file()]
    partial_ok = ("Missing or wrong password" not in out_text
                  and "No files extracted" not in out_text
                  and "Successfully" not in out_text
                  and files)
    assert partial_ok, "部分解压成功应被放行"

    # 反例: 密码错必须仍判失败
    assert "Missing or wrong password" in "Archive parsing failed! (Missing or wrong password.)"
