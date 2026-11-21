#!/usr/bin/env python3
"""Link this checkout into the selected host skill directories."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from workflow_files import configure_cli_output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude", "all"), default="all")
    parser.add_argument("--codex-home", type=Path, help="Codex 配置目录，默认使用 CODEX_HOME 或 ~/.codex。")
    parser.add_argument("--claude-home", type=Path, help="Claude Code 配置目录，默认使用 CLAUDE_CONFIG_DIR 或 ~/.claude。")
    args = parser.parse_args()

    source = Path(__file__).resolve().parents[1]
    if not (source / "SKILL.md").is_file():
        parser.exit(1, "请从包含 SKILL.md 的 dev_co 源码运行安装脚本。\n")
    homes = {
        "codex": args.codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"),
        "claude": args.claude_home or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"),
    }
    try:
        targets = dict.fromkeys(home.expanduser().resolve() / "skills" / "dev_co"
                                for host, home in homes.items() if args.host in (host, "all"))
        existing = [str(target) for target in targets if target.exists() or target.is_symlink()]
        if existing:
            parser.exit(1, "请先检查并备份已有安装。\n" + "\n".join(existing) + "\n")
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
        for target in targets:
            target.symlink_to(source, target_is_directory=True)
            print(f"{target} → {source}")
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"安装链接失败。{error}\n")
    return 0


if __name__ == "__main__":
    configure_cli_output()
    raise SystemExit(main())
