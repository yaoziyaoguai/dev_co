"""验证器与仓库检查器共用的本地文件边界和摘要函数。"""
from __future__ import annotations

from collections.abc import Callable
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

IGNORED = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".project-workflow"}
REPOSITORY_BASELINE = ".project-workflow/repository-baseline.json"


class WorkflowError(Exception):
    pass


class SymlinkPathError(WorkflowError):
    pass


def utf8_bytes(value: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise WorkflowError("项目路径和记录须使用有效的 UTF-8。") from error


def path_text(path: Path | str | bytes) -> str:
    """Decode POSIX path or argv bytes without losing names during filtering."""
    return os.fsencode(path).decode("utf-8", errors="surrogateescape")


def filesystem_path(value: str) -> Path:
    """Turn a UTF-8 metadata path into a native filesystem path."""
    return Path(os.fsdecode(utf8_bytes(value)))


def digest(value: object) -> str:
    return hashlib.sha256(utf8_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False))).hexdigest()

def safe_path(root: Path, relative: str, *, no_symlinks: bool = False, preserve_leaf: bool = False) -> Path:
    if not isinstance(relative, str) or not relative:
        raise WorkflowError("路径必须为非空字符串。")
    path = filesystem_path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise WorkflowError("路径必须位于项目内：" + relative)
    if no_symlinks:
        current = root
        for part in path.parts[:-1] if preserve_leaf else path.parts:
            current = current / part
            if current.is_symlink():
                raise SymlinkPathError("状态和证据路径不得经过符号链接：" + relative)
    resolved = (root / path.parent).resolve() / path.name if preserve_leaf and path.parts else (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise WorkflowError("路径或符号链接越过项目边界：" + relative)
    return resolved


def project_marker(root: Path, name: str) -> Path | None:
    """自动寻根只读取真实的项目入口，不沿共享文档链接查找。"""
    try:
        path = safe_path(root, name, no_symlinks=True)
    except SymlinkPathError:
        return None
    return path if path.is_file() else None


def read_text(path: Path, limit: int = 128_000, *, encoding: str = "utf-8") -> str:
    with path.open(encoding=encoding) as source:
        value = source.read(limit + 1)
    if len(value) > limit:
        raise WorkflowError("文件过大：" + str(path))
    return value

def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def git_value(root: Path, *args: str | bytes) -> str | None:
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                                capture_output=True, encoding="utf-8", errors="surrogateescape", timeout=5)
        return result.stdout.removesuffix("\n") if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def discover_project_root(cwd: Path, has_marker: Callable[[Path], bool]) -> Path:
    cwd = cwd.resolve()
    top = git_value(cwd, "rev-parse", "--show-toplevel")
    ceiling = filesystem_path(top).resolve() if top else cwd
    for root in (cwd, *cwd.parents):
        if not root.is_relative_to(ceiling):
            break
        if has_marker(root):
            return root
    return cwd


def git_file_names(root: Path, paths: list[str]) -> list[str] | None:
    """仅非 Git 项目返回 None；已识别仓库的枚举失败不能降级成另一套范围。"""
    try:
        probe = subprocess.run(["git", "--no-optional-locks", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, timeout=5)
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired as error:
        raise WorkflowError("无法确认 Git 输入范围：查询超时。") from error
    if probe.returncode != 0:
        return None
    if probe.stdout.strip() != b"true":
        raise WorkflowError("验证输入需要 Git 工作树，不能使用裸仓库。")
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), "ls-files", "-z", "--cached",
             "--others", "--exclude-standard", "--", *[utf8_bytes(":(literal)" + p) for p in paths]],
            capture_output=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorkflowError("Git 输入枚举失败：" + str(error)) from error
    if result.returncode != 0:
        raise WorkflowError("Git 输入枚举失败：" + result.stderr.decode(errors="replace").strip())
    return sorted({path_text(name).rstrip("/") for name in result.stdout.split(b"\0") if name})


def gitlink_fingerprint(root: Path, name: str) -> dict | None:
    directory = root / filesystem_path(name)
    index = git_value(root, "ls-files", "--stage", "-z", "--", utf8_bytes(":(literal)" + name)) or ""
    for item in index.split("\0"):
        fields, _, path = item.partition("\t")
        if path != name:
            continue
        mode, commit, stage = fields.split()
        if mode != "160000":
            break
        if stage != "0":
            raise WorkflowError("子模块 Git 索引有冲突：" + name)
        if not (directory / ".git").exists():
            if any(directory.iterdir()):
                raise WorkflowError("未初始化的子模块目录含文件：" + name)
            return {"type": "gitlink", "index": commit, "checkout": None}
        head = git_value(directory, "rev-parse", "--verify", "HEAD")
        status = git_value(directory, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none")
        if not head or status is None:
            raise WorkflowError("无法核对子模块：" + name)
        if status:
            raise WorkflowError("已声明的子模块有未提交的变化：" + name)
        return {"type": "gitlink", "index": commit, "checkout": head}
    if os.path.lexists(directory / ".git"):
        raise WorkflowError(f"发现未注册为子模块的嵌套 Git 工作树：{name}；请加入 .gitignore 或验证 exclude，或注册为子模块。")
    return None


def write_atomic(path: Path, data: bytes, *, mode: int | None = None) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    stream = temporary.open("xb")
    try:
        with stream:
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    write_atomic(path, utf8_bytes(json.dumps(value, ensure_ascii=False, indent=2) + "\n"))


def configure_cli_output(*, include_stdin: bool = False) -> None:
    if include_stdin and isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(encoding="utf-8")
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def fence_start(line: str) -> str | None:
    match = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
    if match and (match[1][0] == "~" or "`" not in match[2]):
        return match[1]
    return None


def fence_end(line: str, marker: str) -> bool:
    return bool(re.fullmatch(r" {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*", line))


def atx_heading(line: str, *, max_level: int = 2) -> tuple[int, str] | None:
    match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*))?", line)
    if not match or len(match[1]) > max_level:
        return None
    title = re.sub(r"[ \t]+#+[ \t]*$", "", match[2] or "").strip()
    return len(match[1]), title


def secret_like(path: Path) -> bool:
    return any(p.startswith(".env") or p.lower() in {
        ".ssh", ".aws", ".npmrc", ".pypirc", "credentials.json", "auth.json",
        "cookies.json", "id_rsa", "id_ed25519"
    } for p in path.parts) or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
