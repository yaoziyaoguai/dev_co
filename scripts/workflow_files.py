"""验证器与仓库检查器共用的本地文件边界和摘要函数。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

IGNORED = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".project-workflow"}


class WorkflowError(Exception):
    pass

def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def safe_path(root: Path, relative: str, *, no_symlinks: bool = False) -> Path:
    if not isinstance(relative, str) or not relative:
        raise WorkflowError("路径必须为非空字符串。")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise WorkflowError("路径必须位于项目内：" + relative)
    if no_symlinks:
        current = root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise WorkflowError("状态和证据路径不得经过符号链接：" + relative)
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise WorkflowError("路径或符号链接越过项目边界：" + relative)
    return resolved

def read_text(path: Path, limit: int = 128_000) -> str:
    with path.open(encoding="utf-8") as source:
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


def git_file_names(root: Path, paths: list[str]) -> list[str] | None:
    """仅非 Git 项目返回 None；已识别仓库的枚举失败不能降级成另一套范围。"""
    try:
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
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
             "--others", "--exclude-standard", "--", *[":(literal)" + p for p in paths]],
            capture_output=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorkflowError("Git 输入枚举失败：" + str(error)) from error
    if result.returncode != 0:
        raise WorkflowError("Git 输入枚举失败：" + result.stderr.decode(errors="replace").strip())
    return sorted({os.fsdecode(name) for name in result.stdout.split(b"\0") if name})

def write_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)

def secret_like(path: Path) -> bool:
    return any(p.startswith(".env") or p.lower() in {
        ".ssh", ".aws", ".npmrc", ".pypirc", "credentials.json", "auth.json",
        "cookies.json", "id_rsa", "id_ed25519"
    } for p in path.parts) or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
