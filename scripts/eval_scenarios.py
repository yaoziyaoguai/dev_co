#!/usr/bin/env python3
"""Prepare and compare isolated workspaces for the bundled eval scenarios."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from workflow_files import WorkflowError, configure_cli_output, path_text, safe_path

SCENARIOS = Path(__file__).resolve().parents[1] / "evals/scenarios.json"


def write_files(root: Path, files: dict[str, str]) -> None:
    targets = {safe_path(root, name, no_symlinks=True): content.encode("utf-8") for name, content in files.items()}
    for path, data in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)


def run_git(root: Path, *args: str, patch: str | None = None) -> bytes:
    repo = safe_path(root, ".git", no_symlinks=True)
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_DATE="2000-01-01T00:00:00Z", GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")
    result = subprocess.run(
        ["git", "--no-optional-locks", "--git-dir=" + str(repo), "--work-tree=" + str(root),
         "-c", "init.defaultBranch=main", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", *args],
        cwd=root, env=env, input=patch.encode("utf-8") if patch is not None else None,
        capture_output=True, timeout=20,
    )
    if result.returncode != 0:
        raise WorkflowError(f"评测 Git {args[0]} 失败：" + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def prepare(root: Path, files: dict[str, str], git_settings: dict | None = None) -> None:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise WorkflowError("评测目录须为空。")
    root.mkdir(parents=True, exist_ok=True)
    if git_settings is None:
        write_files(root, files)
        return
    untracked = git_settings.get("untracked", [])
    patch = git_settings.get("unstaged_patch")
    if (set(git_settings) - {"untracked", "unstaged_patch"} or not isinstance(untracked, list)
            or not all(isinstance(name, str) and name in files for name in untracked)
            or ("unstaged_patch" in git_settings and not isinstance(patch, str))
            or any(".git" in Path(name).parts for name in files)):
        raise WorkflowError("评测 Git 配置无效：未跟踪路径须来自初始文件，Git 元数据由准备命令创建。")
    write_files(root, {name: content for name, content in files.items() if name not in untracked})
    run_git(root, "init", "--template=", "-q")
    run_git(root, "add", "--", ".")
    run_git(root, "commit", "--allow-empty", "-qm", "baseline")
    write_files(root, {name: files[name] for name in untracked})
    if patch is not None:
        run_git(root, "apply", "-", patch=patch)


def worktree_entries(root: Path, *, git: bool) -> set[Path]:
    entries = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        relative = Path(directory).relative_to(root)
        if git and relative == Path("."):
            dirs[:] = [name for name in dirs if name != ".git"]
            files = [name for name in files if name != ".git"]
        entries.update(relative / name for name in dirs + files)
    return entries


def changes(root: Path, reference: Path, *, git: bool) -> list[str]:
    if not root.is_dir():
        raise WorkflowError("找不到评测目录。")
    expected = worktree_entries(reference, git=git)
    actual = worktree_entries(root, git=git)
    differences = actual ^ expected
    for name in actual & expected:
        path, original = root / name, reference / name
        if path.is_symlink():
            differences.add(name)
        elif original.is_file():
            if not path.is_file():
                differences.add(name)
                continue
            current, initial = path.stat(), original.stat()
            if (current.st_size != initial.st_size or (current.st_mode & 0o111) != (initial.st_mode & 0o111)
                    or path.read_bytes() != original.read_bytes()):
                differences.add(name)
        elif not path.is_dir():
            differences.add(name)
    if git:
        for name, args in (
            ("HEAD", ("rev-parse", "--verify", "HEAD")),
            ("index", ("ls-files", "--stage", "-z")),
            ("refs", ("for-each-ref", "--format=%(refname) %(objectname)")),
        ):
            if run_git(root, *args) != run_git(reference, *args):
                differences.add(Path(".git") / name)
    return sorted(path_text(path) for path in differences)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list")
    for command in ("prepare", "verify-clean"):
        subparser = subcommands.add_parser(command)
        subparser.add_argument("--scenario", required=True)
        subparser.add_argument("--dest", required=True, type=Path)
    args = parser.parse_args()
    try:
        scenarios = {item["id"]: item
                     for item in json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]}
        if args.command == "list":
            print("\n".join(scenarios))
            return 0
        if args.scenario not in scenarios:
            raise WorkflowError("找不到评测场景：" + args.scenario)
        root = args.dest.resolve()
        scenario = scenarios[args.scenario]
        files, git_settings = scenario["initial_files"], scenario.get("git")
        if "git" in scenario and not isinstance(git_settings, dict):
            raise WorkflowError("评测 Git 配置须为对象。")
        if args.command == "prepare":
            prepare(root, files, git_settings)
            print(path_text(root))
            return 0
        # 用受信任的场景重建参考，不读取被测仓库里的快照作为判断依据。
        with TemporaryDirectory(prefix="devco-eval-reference-") as expected:
            reference = Path(expected).resolve()
            prepare(reference, files, git_settings)
            changed = changes(root, reference, git=git_settings is not None)
        if changed:
            print("目录变化：\n" + "\n".join(changed))
            return 1
        print("评测目录与初始场景一致。")
        return 0
    except (WorkflowError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    configure_cli_output()
    raise SystemExit(main())
