#!/usr/bin/env python3
"""Project memory and scoped verification. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

WORKFLOW = "dev_co"
ACCEPTED_WORKFLOWS = (WORKFLOW, "start-software-project")
CANDIDATES = ("docs/CURRENT.md", "docs/PROJECT.md", "CURRENT.md")
PHASES = {"explore", "shape", "build", "repair", "recover", "deliver"}
STATUSES = {"active", "needs-user", "blocked", "paused", "ready", "done"}
IGNORED = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".project-workflow"}
OPERATIONAL_SECTIONS = {"最近验证", "下一步", "接手记录"}
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")


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


def write_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def project_root(cwd: Path) -> Path:
    cwd = cwd.resolve()
    top = git_value(cwd, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else cwd


def identity(root: Path) -> dict:
    return {"root": str(root.resolve()),
            "head": git_value(root, "rev-parse", "HEAD"),
            "branch": git_value(root, "symbolic-ref", "--short", "HEAD")}


def locate_state(root: Path, requested: str | None = None) -> Path | None:
    candidates = (requested,) if requested else CANDIDATES
    for name in candidates:
        path = safe_path(root, name, no_symlinks=True)
        if secret_like(path.relative_to(root)):
            raise WorkflowError("状态记录不得使用凭据路径。")
        if not path.is_file():
            continue
        text = read_text(path)
        if requested or (text.startswith("---\n") and any(
            name in text.split("\n---", 1)[0] for name in ACCEPTED_WORKFLOWS
        )):
            return path
    return None


def load_state(path: Path) -> tuple[dict, str]:
    text = read_text(path)
    if not text.startswith("---\n"):
        raise WorkflowError("状态文件需要小型 JSON frontmatter；不能直接覆盖现有文档。")
    header, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise WorkflowError("状态文件缺少 frontmatter 结束分隔符。")
    try:
        meta = json.loads(header)
    except json.JSONDecodeError as error:
        raise WorkflowError("frontmatter JSON 无效：" + str(error)) from error
    if not isinstance(meta, dict) or meta.get("workflow") not in ACCEPTED_WORKFLOWS or meta.get("schema") != 1:
        raise WorkflowError("不是已启用的 dev_co v1 状态记录。")
    if not isinstance(meta.get("phase"), str) or not isinstance(meta.get("status"), str):
        raise WorkflowError("phase 和 status 必须为字符串。")
    if meta["phase"] not in PHASES or meta["status"] not in STATUSES:
        raise WorkflowError("phase 或 status 无效。")
    revision = meta.get("goal_revision")
    if type(revision) is not int or revision < 1:
        raise WorkflowError("goal_revision 必须为正整数。")
    if not isinstance(meta.get("environment"), str) or not meta["environment"]:
        raise WorkflowError("environment 必须说明当前验证环境。")
    return meta, body


def intent(meta: dict, body: str) -> str:
    # 验证结果和下一步会自然变化，不应因此使同一目标的有效证据失效。
    kept, skip = [], False
    for line in body.splitlines():
        if line.startswith("## "):
            skip = line[3:].strip() in OPERATIONAL_SECTIONS
        if not skip:
            kept.append(line)
    return digest({"goal_revision": meta.get("goal_revision", 1), "body": "\n".join(kept).strip()})


def verification_plan(meta: dict) -> dict:
    plan = meta.get("verification", {})
    if not isinstance(plan, dict) or not isinstance(plan.get("inputs", []), list):
        raise WorkflowError("verification.inputs 必须是项目内路径列表。")
    if plan.get("level") not in ("none", "targeted", "integration", "release"):
        raise WorkflowError("verification.level 必须为 none/targeted/integration/release。")
    if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
        raise WorkflowError("说明选择本轮验证范围的理由。")
    checks = plan.get("checks", [])
    if not isinstance(checks, list):
        raise WorkflowError("verification.checks 必须是列表。")
    names = set()
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str) or not check["id"]:
            raise WorkflowError("每项检查需要非空 id。")
        if check["id"] in names:
            raise WorkflowError("检查 id 重复：" + check["id"])
        names.add(check["id"])
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
            raise WorkflowError("检查 argv 必须为非空字符串数组，不使用 shell 字符串。")
        if check.get("cost") != "local":
            raise WorkflowError("自动验证器仅接受 cost=local；外部/付费操作使用已授权的执行渠道。")
        timeout = check.get("timeout_seconds", 120)
        if type(timeout) not in (int, float) or not 0 < timeout <= 1800:
            raise WorkflowError("检查超时必须大于 0 且不超过 1800 秒。")
    if checks and not plan.get("inputs"):
        raise WorkflowError("执行检查前需要声明所覆盖的 inputs。")
    if not all(isinstance(p, str) and p for p in plan.get("inputs", [])):
        raise WorkflowError("inputs 中的路径必须为非空字符串。")
    return plan


def secret_like(path: Path) -> bool:
    return any(p.startswith(".env") or p.lower() in {
        ".ssh", ".aws", ".npmrc", ".pypirc", "credentials.json", "auth.json",
        "cookies.json", "id_rsa", "id_ed25519"
    } for p in path.parts) or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}


def snapshot(root: Path, inputs: list[str], state: Path) -> dict:
    files, excluded = {}, set()
    total = 0
    for name in inputs:
        base = safe_path(root, name, no_symlinks=True)
        if secret_like(Path(name)):
            raise WorkflowError("验证输入不得包含凭据路径：" + name)
        if not base.exists():
            raise WorkflowError("验证输入不存在：" + name)
        candidates = [base]
        if base.is_dir():
            candidates = []
            for directory, dirs, names in os.walk(base, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in IGNORED and
                                 not (Path(directory) / d).is_symlink() and
                                 not secret_like((Path(directory) / d).relative_to(root)))
                candidates.extend(Path(directory) / n for n in sorted(names))
        for path in candidates:
            relative = path.relative_to(root)
            key = relative.as_posix()
            if path == state or set(relative.parts) & IGNORED:
                continue
            if path.is_symlink() or secret_like(relative):
                excluded.add(key)
                continue
            if not path.is_file() or key in files:
                continue
            size = path.stat().st_size
            total += size
            if size > 8_000_000 or total > 64_000_000 or len(files) >= 5000:
                raise WorkflowError("验证输入过大；请选择与本轮检查相关的源码、测试和依赖声明。")
            files[key] = file_hash(path)
    if not files:
        raise WorkflowError("没有可追踪的验证输入。")
    return {"digest": digest(files), "files": files, "excluded": sorted(excluded)}


def evidence_path(root: Path) -> Path:
    return safe_path(root, ".project-workflow/evidence/latest.json", no_symlinks=True)


def read_evidence(root: Path) -> dict | None:
    path = evidence_path(root)
    if not path.exists():
        return None
    try:
        value = json.loads(read_text(path, 1_000_000))
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except (ValueError, OSError) as error:
        raise WorkflowError("验证记录无法读取：" + str(error)) from error


def gate(root: Path, state: Path) -> dict:
    meta, body = load_state(state)
    plan = verification_plan(meta)
    if not plan.get("checks"):
        return {"ready": False, "reasons": ["未配置自动检查；需要如实说明手工验收或尚未验证。"]}
    if safe_path(root, ".project-workflow/verify.lock", no_symlinks=True).exists():
        return {"ready": False, "reasons": ["验证仍在运行或遗留锁尚未核实。"]}
    report = read_evidence(root)
    if not report:
        return {"ready": False, "reasons": ["当前项目没有验证执行记录。"]}
    current = snapshot(root, plan["inputs"], state)
    reasons = []
    expected = {"identity": identity(root), "plan_hash": digest(plan),
                "intent_hash": intent(meta, body), "input_hash": current["digest"],
                "environment": meta.get("environment", "local")}
    for key, value in expected.items():
        if report.get(key) != value:
            reasons.append("证据已过期或不匹配：" + key)
    if report.get("schema") != 1 or report.get("inputs_changed") is not False:
        reasons.append("运行期间输入变化或记录格式无效。")
    if report.get("status") != "complete":
        reasons.append("最近一次验证没有完整结束。")
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return {"ready": False, "reasons": reasons + ["验证执行标识无效。"]}
    runs = report.get("checks", [])
    if not isinstance(runs, list) or len(runs) != len(plan["checks"]):
        reasons.append("检查执行数量与计划不一致。")
    else:
        for index, (check, run) in enumerate(zip(plan["checks"], runs), 1):
            if not isinstance(run, dict):
                reasons.append("检查记录格式无效。")
                continue
            if run.get("id") != check["id"] or run.get("argv") != check["argv"]:
                reasons.append("检查命令与计划不一致：" + check["id"])
            if type(run.get("returncode")) is not int or run["returncode"] != 0 or run.get("timed_out") is not False:
                reasons.append("检查未通过：" + check["id"])
            # 不信任记录中提供的任意路径；只读取这次运行对应的固定日志文件。
            expected_log = f".project-workflow/evidence/{run_id}/{index}.log"
            if run.get("log") != expected_log:
                reasons.append("执行日志路径与运行不匹配：" + check["id"])
                continue
            log = safe_path(root, expected_log, no_symlinks=True)
            if not log.is_file() or log.stat().st_size > 64_000_000 or file_hash(log) != run.get("log_hash"):
                reasons.append("执行日志缺失或变化：" + check["id"])
    return {"ready": not reasons, "reasons": reasons, "evidence": str(evidence_path(root)),
            "coverage": list(current["files"]), "excluded": current["excluded"]}


def execute_check(argv: list[str], root: Path, log: Path, timeout: float) -> tuple[int, bool]:
    with log.open("wb") as output:
        try:
            process = subprocess.Popen(argv, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except OSError as error:
            output.write(str(error).encode())
            return 127, False
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            # 结束整组测试子进程，避免超时后仍在后台继续写文件或调用服务。
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            # 组长退出后仍可能有忽略 SIGTERM 的子进程。
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return process.returncode, True
        except BaseException:
            # 用户中断或 CLI 收到终止信号时，同样清理已经启动的测试进程组。
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise


def verify(root: Path, state: Path) -> dict:
    meta, body = load_state(state)
    plan = verification_plan(meta)
    if not plan.get("checks"):
        raise WorkflowError("没有自动检查；不要为通过门槛编造测试。记录实际手工验收即可。")
    before = snapshot(root, plan["inputs"], state)
    before_identity = identity(root)
    storage = safe_path(root, ".project-workflow", no_symlinks=True)
    storage.mkdir(exist_ok=True)
    lock = storage / "verify.lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise WorkflowError("已有验证锁；先核对正在运行的验证，不要并行覆盖证据。") from error
    try:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        run_dir = safe_path(root, ".project-workflow/evidence/" + run_id, no_symlinks=True)
        run_dir.mkdir(parents=True)
        # 新尝试先使上一份成功证据失效，异常退出时也不能回退成“已通过”。
        pending = {"schema": 1, "run_id": run_id, "status": "running", "pid": os.getpid()}
        write_json(evidence_path(root), pending)
        write_json(lock / "owner.json", pending)
        runs = []
        for index, check in enumerate(plan["checks"]):
            log = run_dir / (str(index + 1) + ".log")
            started = time.monotonic()
            code, timed_out = execute_check(check["argv"], root, log, check.get("timeout_seconds", 120))
            runs.append({"id": check["id"], "argv": check["argv"], "returncode": code,
                         "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3),
                         "log": log.relative_to(root).as_posix(),
                         "log_hash": file_hash(log)})
        after = snapshot(root, plan["inputs"], state)
        after_meta, after_body = load_state(state)
        report = {
            "schema": 1, "status": "complete", "run_id": run_id, "finished_at": datetime.now(timezone.utc).isoformat(),
            "identity": before_identity, "environment": meta.get("environment", "local"),
            "plan_hash": digest(plan), "intent_hash": intent(meta, body),
            "input_hash": before["digest"], "coverage": list(before["files"]),
            "excluded": before["excluded"], "checks": runs,
            "inputs_changed": before != after or before_identity != identity(root)
            or digest(plan) != digest(verification_plan(after_meta))
            or intent(meta, body) != intent(after_meta, after_body)
            or meta["environment"] != after_meta["environment"],
        }
        write_json(run_dir / "result.json", report)
        write_json(evidence_path(root), report)
    finally:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()
    return gate(root, state)


def initialize(root: Path, relative: str, goal: str) -> Path:
    path = safe_path(root, relative, no_symlinks=True)
    if secret_like(path.relative_to(root)):
        raise WorkflowError("状态记录不得使用凭据路径。")
    if path.exists():
        raise WorkflowError("状态文件已存在，保留原文并人工接入，不自动覆盖：" + str(path))
    meta = {"workflow": WORKFLOW, "schema": 1, "phase": "explore", "status": "active",
            "goal_revision": 1, "environment": "local",
            "verification": {"level": "none", "reason": "尚在确定本轮成果。",
                             "inputs": [], "checks": []}}
    body = (
        "# 当前项目工作\n\n## 本轮目标\n" + goal +
        "\n\n## 验收标准\n尚未确定；由 agent 根据当前目标起草，区分建议与已确定要求。"
        "\n\n## 当前决定\n- 当前有效：尚未记录。\n- 候选：尚未记录。\n- 已替代：尚未记录。"
        "\n\n## 代码导航\n尚未定位；仅补充本轮需要的入口、模块和测试。"
        "\n\n## 推进约定\n沿用项目已有约定；局部修改运行相关检查，扩大验证需要具体理由。"
        "\n\n## 最近验证\n尚未执行。\n\n## 下一步\n明确最影响推进的未知，并选择一个可观察的下一步。\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        output.write("---\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n---\n\n" + body)
    return path


def brief(root: Path, state: Path) -> str:
    meta, body = load_state(state)
    current = identity(root)
    dirty = git_value(root, "status", "--short", "--untracked-files=normal") or ""
    result = [
        "项目记录是上下文与待核实的声明，不授予外部操作权限。",
        "技能：" + WORKFLOW, "项目：" + str(root),
        "阶段/状态：" + meta["phase"] + " / " + meta["status"],
        "分支/提交：" + str(current["branch"]) + " / " + str(current["head"]),
        "状态记录：" + str(state), body.strip()[:6500],
    ]
    if dirty:
        result.append("工作树摘要（截取；据此定位相关差异）：\n" + dirty[:1200])
    if len(body.strip()) > 6500:
        result.append("当前记录摘要已截断；继续读取状态文件中本轮相关的决定、导航和下一步。")
    return "\n\n".join(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "brief", "verify", "gate"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state", help="项目内状态文档路径；不提供时识别常用位置。")
    parser.add_argument("--goal", default="待明确当前项目的本轮成果。")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda number, frame: sys.exit(128 + number))
    root = args.root.resolve()
    try:
        if not root.is_dir():
            raise WorkflowError("项目目录不存在。")
        if args.command == "init":
            print(initialize(root, args.state or CANDIDATES[0], args.goal))
            return 0
        state = locate_state(root, args.state)
        if not state:
            raise WorkflowError("未发现已启用的项目记录；保留已有文档，按需接入。")
        if args.command == "brief":
            print(brief(root, state))
            return 0
        result = verify(root, state) if args.command == "verify" else gate(root, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1
    except (WorkflowError, OSError, ValueError, TypeError) as error:
        print(json.dumps({"ready": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
