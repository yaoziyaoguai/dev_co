#!/usr/bin/env python3
"""Optional lifecycle adapters. Never execute checks or publish from a hook."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

import project_workflow as workflow


def config(host: str, state: str | None, protect_tools: list[str]) -> dict:
    base = [sys.executable, str(Path(__file__).resolve()), "--host", host]
    if state:
        base.extend(["--state", state])
    command = shlex.join(base)
    matcher = "startup|resume|compact" if host == "codex" else "startup|resume|clear|compact|fork"
    hooks = {
        "SessionStart": [{"matcher": matcher, "hooks": [
            {"type": "command", "command": command, "timeout": 10}]}],
        "Stop": [{"hooks": [{"type": "command", "command": command, "timeout": 10}]}],
    }
    if protect_tools:
        hooks["PreToolUse"] = [{
            "matcher": "^(?:" + "|".join(re.escape(t) for t in protect_tools) + ")$",
            "hooks": [{"type": "command", "command": command + " --protect", "timeout": 10}],
        }]
    return {"hooks": hooks}


def respond(payload: dict, state_name: str | None = None, protect: bool = False) -> dict:
    event = payload.get("hook_event_name")
    if event not in {"SessionStart", "Stop", "PreToolUse"}:
        return {}
    try:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise workflow.WorkflowError("hook 缺少有效的项目 cwd。")
        root = workflow.project_root(Path(cwd))
        state = workflow.locate_state(root, state_name)
        if not state:
            if protect or state_name:
                raise workflow.WorkflowError("未找到指定或已接入的项目状态记录。")
            return {}
        meta, _ = workflow.load_state(state)
        if event == "SessionStart":
            return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                    "additionalContext": workflow.brief(root, state)}}
        if event == "PreToolUse" and protect:
            outcome = workflow.gate(root, state)
            if not outcome["ready"]:
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "项目就绪检查未通过：" + "；".join(outcome["reasons"])}}
            # 就绪检查通过只是不拦截，不能替代宿主权限或用户授权。
            return {}
        if event != "Stop" or meta["phase"] in {"explore", "shape", "recover"}:
            return {}
        if meta["status"] in {"needs-user", "blocked", "paused"}:
            return {}
        plan = workflow.verification_plan(meta)
        if not plan.get("checks"):
            return {"systemMessage": "本轮没有自动验证计划；请明确说明实际手工检查和未验证部分。"}
        result = workflow.gate(root, state)
        if result["ready"]:
            return {}
        reason = "；".join(result["reasons"])
        if payload.get("stop_hook_active"):
            return {"systemMessage": "验证仍未满足：" + reason + "。保留未完成状态，避免无限续跑。"}
        return {"decision": "block",
                "reason": "本轮证据不足：" + reason +
                "。仅执行已授权的相关检查；如有真实阻塞或需要用户决定，更新状态并如实报告。"}
    except (workflow.WorkflowError, OSError, ValueError, TypeError) as error:
        message = "项目工作记录/证据无法核对：" + str(error)
        if event == "PreToolUse" and protect:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "deny", "permissionDecisionReason": message}}
        return {"systemMessage": message + "。先修复记录或核对源码，不要声称已验证。"}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude"), required=True)
    parser.add_argument("--state")
    parser.add_argument("--protect", action="store_true")
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--protect-tool", action="append", default=[])
    args = parser.parse_args()
    if args.print_config:
        print(json.dumps(config(args.host, args.state, args.protect_tool), ensure_ascii=False, indent=2))
        return 0
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook 输入必须为对象")
        result = respond(payload, args.state, args.protect)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, workflow.WorkflowError) as error:
        # 保护性执行前检查无法解析时拒绝本次调用；其他事件报告错误，不制造续跑循环。
        print(str(error), file=sys.stderr)
        return 2 if args.protect else 1


if __name__ == "__main__":
    raise SystemExit(main())
