#!/usr/bin/env python3
"""Prepare and compare isolated workspaces for the bundled eval scenarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_files import WorkflowError, configure_cli_output, filesystem_path, safe_path

SCENARIOS = Path(__file__).resolve().parents[1] / "evals/scenarios.json"


def prepare(root: Path, files: dict[str, str]) -> None:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise WorkflowError("评测目录须为空。")
    targets = {safe_path(root, name, no_symlinks=True): content.encode("utf-8") for name, content in files.items()}
    root.mkdir(parents=True, exist_ok=True)
    for path, data in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)


def changes(root: Path, files: dict[str, str]) -> list[str]:
    if not root.is_dir():
        raise WorkflowError("找不到评测目录。")
    expected = {filesystem_path(name): text.encode("utf-8") for name, text in files.items()}
    directories = {parent for file in expected for parent in file.parents if parent != Path(".")}
    actual = {path.relative_to(root): path for path in root.rglob("*")}
    differences = set(actual).symmetric_difference(expected.keys() | directories)
    for name in actual.keys() & (expected.keys() | directories):
        path = actual[name]
        if path.is_symlink():
            differences.add(name)
        elif name in expected:
            data = expected[name]
            if not path.is_file() or path.stat().st_size != len(data) or path.read_bytes() != data:
                differences.add(name)
        elif not path.is_dir():
            differences.add(name)
    return sorted(path.as_posix() for path in differences)


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
        scenarios = {item["id"]: item["initial_files"]
                     for item in json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]}
        if args.command == "list":
            print("\n".join(scenarios))
            return 0
        if args.scenario not in scenarios:
            raise WorkflowError("找不到评测场景：" + args.scenario)
        root = args.dest.resolve()
        files = scenarios[args.scenario]
        if args.command == "prepare":
            prepare(root, files)
            print(root)
            return 0
        changed = changes(root, files)
        if changed:
            print("目录变化：\n" + "\n".join(changed))
            return 1
        print("评测目录与初始场景一致。")
        return 0
    except (WorkflowError, OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    configure_cli_output()
    raise SystemExit(main())
