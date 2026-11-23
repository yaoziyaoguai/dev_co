#!/usr/bin/env python3
"""Project memory and scoped verification. Standard library only."""
from __future__ import annotations

import argparse
from codecs import BOM_UTF8
import json
import os
from collections.abc import Callable
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from context_brief import summarize, truncate_utf8
from workflow_files import (IGNORED, REPOSITORY_BASELINE, WorkflowError, atx_heading, configure_cli_output, digest,
                            discover_project_root, fence_end, fence_start, file_hash, filesystem_path,
                            git_file_names, git_head_and_branch, git_value, gitlink_fingerprint, path_text,
                            project_marker, read_text, safe_path, secret_like, utf8_bytes, write_atomic, write_json)

WORKFLOW = "dev_co"
ACCEPTED_WORKFLOWS = (WORKFLOW, "start-software-project")
CANDIDATES = ("docs/CURRENT.md", "docs/PROJECT.md", "CURRENT.md")
STATE_LIMIT = 128_000
PHASES = {"explore", "shape", "build", "repair", "recover", "deliver"}
STATUSES = {"active", "needs-user", "blocked", "paused", "ready", "done"}
NON_INTENT_SECTIONS = {"最近验证", "下一步", "接手记录", "候选想法"}
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")


def identity(root: Path) -> dict:
    resolved = root.resolve()
    origin = git_head_and_branch(resolved)
    if origin is None:
        return {"root": path_text(resolved), "head": None, "branch": None}
    return {"root": path_text(resolved), "head": origin["head"], "branch": origin["branch"]}


def dependent_identity(value: dict, plan: dict) -> dict:
    # 分支/提交仍保留在证据中；只有声明依赖 Git 时才据此作废检查。
    if plan.get("freshness", "git") == "content":
        return {"root": value.get("root")}
    return value


def locate_state(root: Path, requested: str | None = None) -> Path | None:
    root = root.resolve()
    if requested is not None:
        path = safe_path(root, requested, no_symlinks=True)
        if secret_like(path.relative_to(root)):
            raise WorkflowError("状态记录不得使用凭据路径。")
        return path if path.is_file() else None
    for name in CANDIDATES:
        path = project_marker(root, name)
        if path is None:
            continue
        with path.open(encoding="utf-8-sig", errors="surrogateescape") as source:
            if source.readline(5) != "---\n":
                continue
            header = source.read(STATE_LIMIT).split("\n---\n", 1)[0]
        if not header.lstrip().startswith("{"):
            continue
        try:
            marker = json.loads(header).get("workflow")
        except (ValueError, RecursionError):
            # 内置模板把 workflow 放在首字段，损坏时仍能识别该标记。
            match = re.match(r'\s*\{\s*"workflow"\s*:\s*"([^"]*)"', header)
            marker = match[1] if match else None
        if marker in ACCEPTED_WORKFLOWS:
            return path
    return None


def project_context_root(cwd: Path, state: str | None = None) -> Path:
    return discover_project_root(cwd, lambda root: project_marker(root, REPOSITORY_BASELINE) is not None
                                 or locate_state(root, state) is not None)


def load_state(path: Path) -> tuple[dict, str]:
    text = read_text(path, STATE_LIMIT, encoding="utf-8-sig")
    if not text.startswith("---\n"):
        raise WorkflowError("状态文件需要小型 JSON frontmatter；不能直接覆盖现有文档。")
    header, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise WorkflowError("状态文件缺少 frontmatter 结束分隔符。")
    return parse_state_meta(header), body


def parse_state_meta(header: str) -> dict:
    try:
        meta = json.loads(header)
    except (ValueError, RecursionError) as error:
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
    sections = meta.get("non_intent_sections", [])
    if not isinstance(sections, list) or not all(isinstance(s, str) and s.strip() for s in sections):
        raise WorkflowError("non_intent_sections 必须为非空标题字符串的列表；空列表表示全部正文参与。")
    return meta


def intent(meta: dict, body: str) -> str:
    # 仅真正的一级/二级标题切换段落；示例代码内的标题或 Setext 标题不能隐藏有效要求。
    kept, skip = [], False
    fence = None
    conservative = False
    previous_nonblank = False
    sections = meta.get("non_intent_sections", sorted(NON_INTENT_SECTIONS))
    for line in body.splitlines():
        if fence:
            if fence_end(line, fence):
                fence = None
        else:
            # 缩进/容器围栏或 Setext 标题保守绑定整篇，避免列表结束后把闭围栏误作开围栏或漏掉混合标题。
            if (re.match(r"^[ \t]+(?:`{3,}|~{3,})", line)
                    or re.match(r"^[ \t]*(?:(?:[-+*]|\d+[.)])[ \t]+|>).*?(?:`{3,}|~{3,})", line)
                    or (previous_nonblank and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line))):
                conservative = True
                break
            fence = fence_start(line)
            if not fence:
                heading = atx_heading(line)
                if heading:
                    level, title = heading
                    skip = level == 2 and title in sections
                    previous_nonblank = False
                else:
                    previous_nonblank = bool(line.strip()) and not re.match(r"^ {0,3}(?:[-+*]|\d+[.)]|>)[ \t]*", line)
        if not skip:
            kept.append(line)
    # 旧算法可能漏掉围栏之后的要求，不能把旧指纹直接视作已修复的证据。
    return digest({"version": 3, "goal_revision": meta["goal_revision"],
                   "non_intent_sections": sections,
                   "body": body.strip() if conservative or fence else "\n".join(kept).strip()})


def verification_plan(meta: dict) -> dict:
    plan = meta.get("verification", {})
    if not isinstance(plan, dict) or not isinstance(plan.get("inputs", []), list):
        raise WorkflowError("verification.inputs 必须是项目内路径列表。")
    if plan.get("level") not in ("none", "targeted", "integration", "release"):
        raise WorkflowError("verification.level 必须为 none/targeted/integration/release。")
    if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
        raise WorkflowError("说明选择本轮验证范围的理由。")
    if plan.get("freshness", "git") not in ("git", "content"):
        raise WorkflowError("verification.freshness 必须为 git/content；省略时沿用 git。")
    if "repository_policy" in plan and (not isinstance(plan["repository_policy"], str) or not plan["repository_policy"]):
        raise WorkflowError("repository_policy 必须是仓库规则的项目内相对路径。")
    if "repository_policy" in plan and (not isinstance(plan.get("repository_scope"), str)
                                       or not plan["repository_scope"].strip()):
        raise WorkflowError("启用 repository_policy 时必须声明当前 repository_scope。")
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
    exclusions = plan.get("exclude", [])
    if not isinstance(exclusions, list) or not all(
            isinstance(p, str) and p and not Path(p).is_absolute() and ".." not in Path(p).parts
            and "\\" not in p and p != "." and Path(p).as_posix() == p.rstrip("/") for p in exclusions):
        raise WorkflowError("exclude 必须为规范的项目内相对路径列表；目录以 / 结尾，不使用 glob。")
    return plan


def snapshot(root: Path, inputs: list[str], state: Path, exclusions: list[str] | None = None) -> dict:
    root = root.resolve()
    state = state.resolve()
    files, excluded, links = {}, set(), {}
    candidates: dict[Path, bool] = {}
    total = 0
    exclusions = exclusions or []

    def omitted(name: str) -> bool:
        return any(name == p.rstrip("/") or p.endswith("/") and name.startswith(p) for p in exclusions)

    directories = []
    for name in inputs:
        base = safe_path(root, name, no_symlinks=True, preserve_leaf=True)
        if secret_like(Path(name)) or set(Path(name).parts) & {".git", ".project-workflow"}:
            raise WorkflowError("验证输入不得包含凭据、Git 元数据或验证证据路径：" + name)
        if base.is_symlink():
            candidates[base] = True
        elif not base.exists():
            raise WorkflowError("验证输入不存在：" + name)
        elif base.is_dir():
            directories.append(base)
        else:
            candidates[base] = True
    names = git_file_names(root, [path_text(p.relative_to(root)) for p in directories]) if directories else []
    if names is not None:
        for name in names:
            if omitted(name):
                continue
            # 保留链接本身，不能先 resolve 后把链接身份丢掉。
            path = root / filesystem_path(name)
            if os.path.lexists(path):
                candidates.setdefault(path, False)
    else:
        for base in directories:
            for directory, dirs, names in os.walk(base, followlinks=False):
                kept = []
                for entry in sorted(dirs + names):
                    path = Path(directory) / entry
                    relative = path.relative_to(root)
                    if secret_like(relative):
                        excluded.add(path_text(relative))
                        continue
                    if set(relative.parts) & IGNORED or omitted(path_text(relative)):
                        continue
                    if entry in dirs and not path.is_symlink():
                        kept.append(entry)
                    else:
                        candidates.setdefault(path, False)
                dirs[:] = kept
    for path, explicit in sorted(candidates.items()):
        relative = path.relative_to(root)
        key = path_text(relative)
        if path == state or set(relative.parts) & {".git", ".project-workflow"}:
            continue
        if secret_like(relative):
            excluded.add(key)
            continue
        if not explicit and omitted(key):
            continue
        # Git 索引可能保留已被链接替换的父目录下的旧路径，不能沿该路径读取目标。
        safe_path(root, path_text(relative.parent), no_symlinks=True)
        if len(files) >= 5000:
            raise WorkflowError("验证输入过大；请选择与本轮检查相关的源码、测试和依赖声明。")
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise WorkflowError("链接目标不可核对：" + key) from error
            if not target.is_relative_to(root) or secret_like(target.relative_to(root)):
                raise WorkflowError("链接目标越界或涉及敏感路径：" + key)
            links[key] = target
            files[key] = {"type": "symlink", "target": path_text(os.readlink(path)),
                          "resolved": path_text(target.relative_to(root))}
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if info.st_size > 8_000_000 or total > 64_000_000:
                raise WorkflowError("验证输入过大；请选择与本轮检查相关的源码、测试和依赖声明。")
            files[key] = {"type": "file", "content": file_hash(path), "executable": info.st_mode & 0o111}
        else:
            fingerprint = gitlink_fingerprint(root, key) if stat.S_ISDIR(info.st_mode) else None
            if fingerprint is None:
                raise WorkflowError("验证输入不是普通文件或可核对链接：" + key)
            files[key] = fingerprint
    regular = {root / filesystem_path(name) for name, value in files.items() if value["type"] == "file"}
    for name, target in links.items():
        covered = (target in regular if target.is_file()
                   else _directory_link_covered(root, target, files, regular, state, omitted))
        if not covered:
            raise WorkflowError("链接目标未进入实际验证输入：" + name + "；请显式声明所依赖的项目内真实文件。")
    if not files:
        raise WorkflowError("没有可追踪的验证输入。")
    return {"digest": digest(files), "files": files, "excluded": sorted(excluded)}


def _directory_link_covered(root: Path, target: Path, files: dict[str, dict], regular: set[Path],
                            state: Path, omitted: Callable[[str], bool]) -> bool:
    if not any(p.is_relative_to(target) for p in regular):
        return False
    rel_target = "." if target == root else path_text(target.relative_to(root))
    listed = git_file_names(root, [rel_target])
    if listed is not None:
        expected = [
            name for name in listed
            if not omitted(name)
            and (root / filesystem_path(name)) != state
            and not (set(Path(name).parts) & {".git", ".project-workflow"})
            and not secret_like(Path(name))
            and os.path.lexists(root / filesystem_path(name))
        ]
    else:
        expected = []
        for directory, dirs, names in os.walk(target, followlinks=False):
            kept = []
            for entry in sorted(dirs + names):
                candidate = Path(directory) / entry
                rel = candidate.relative_to(root)
                rel_text = path_text(rel)
                if candidate == state or secret_like(rel) or set(rel.parts) & IGNORED or omitted(rel_text):
                    continue
                if entry in dirs and not candidate.is_symlink():
                    kept.append(entry)
                else:
                    expected.append(rel_text)
            dirs[:] = kept
    return all(name in files for name in expected)


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


def repository_status(root: Path, plan: dict) -> dict | None:
    if "repository_policy" not in plan:
        return None
    import repository_check
    result = repository_check.check(root, plan["repository_policy"], scope=plan["repository_scope"])
    return {"ready": result["ready"], "reasons": result["errors"], "repository": result}


def repository_preflight(root: Path, plan: dict) -> None:
    if "repository_policy" in plan:
        import repository_check
        repository_check.load_policy(root, plan["repository_policy"])
        repository_check.load_baseline(root, plan["repository_policy"], plan["repository_scope"])


def describe_verify_lock(lock: Path) -> str:
    message = "已有验证锁。请先核对运行状态。"
    owner_path = safe_path(lock, "owner.json", no_symlinks=True)
    try:
        owner = json.loads(read_text(owner_path))
    except (FileNotFoundError, ValueError):
        return message
    if not isinstance(owner, dict):
        return message
    pid, run_id = owner.get("pid"), owner.get("run_id")
    if type(pid) is not int or pid <= 0 or not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return message
    owner_host = owner.get("host")
    if isinstance(owner_host, str) and owner_host and owner_host != socket.gethostname():
        return f"已有跨环境验证锁（运行 {run_id}，主机 {owner_host}，PID {pid}）。请在对应环境核对运行状态。"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"已有遗留验证锁（运行 {run_id}，PID {pid} 已不存在）。请核对后清理。"
    except PermissionError:
        pass
    return f"已有验证锁（运行 {run_id}，PID {pid} 存在）。请检查进程。"


def evidence_status(root: Path, state: Path, meta: dict, body: str, plan: dict) -> dict:
    if not plan.get("checks"):
        return {"ready": False, "reasons": ["未配置自动检查；需要如实说明手工验收或尚未验证。"]}
    lock = safe_path(root, ".project-workflow/verify.lock", no_symlinks=True)
    if lock.exists():
        return {"ready": False, "reasons": [describe_verify_lock(lock)]}
    report = read_evidence(root)
    if not report:
        return {"ready": False, "reasons": ["当前项目没有验证执行记录。"]}
    current = snapshot(root, plan["inputs"], state, plan.get("exclude"))
    return compare_evidence(root, meta, body, plan, report, current)


def compare_evidence(root: Path, meta: dict, body: str, plan: dict, report: dict, current: dict) -> dict:
    reasons = []
    expected = {"plan_hash": digest(plan),
                "intent_hash": intent(meta, body), "input_hash": current["digest"],
                "environment": meta["environment"]}
    recorded_identity = report.get("identity")
    if (not isinstance(recorded_identity, dict)
            or dependent_identity(recorded_identity, plan) != dependent_identity(identity(root), plan)):
        reasons.append("证据已过期或不匹配：identity")
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
    return {"ready": not reasons, "reasons": reasons, "evidence": path_text(evidence_path(root)),
            "coverage": list(current["files"]), "excluded": current["excluded"]}


def combine_gate_result(evidence: dict, repository: dict | None) -> dict:
    result = {**evidence, "verification_ready": evidence["ready"]}
    if repository is not None:
        result.update(ready=evidence["ready"] and repository["ready"],
                      reasons=evidence["reasons"] + repository["reasons"],
                      repository=repository["repository"])
    return result


def gate(root: Path, state: Path) -> dict:
    root = root.resolve()
    meta, body = load_state(state)
    plan = verification_plan(meta)
    repository = repository_status(root, plan)
    return combine_gate_result(evidence_status(root, state, meta, body, plan), repository)


def execute_check(argv: list[str], root: Path, log: Path, timeout: float) -> tuple[int, bool]:
    with log.open("wb") as output:
        try:
            process = subprocess.Popen([utf8_bytes(arg) for arg in argv], cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except OSError as error:
            output.write(str(error).encode())
            if isinstance(error, PermissionError) and "/" in argv[0]:
                try:
                    mode = (root / filesystem_path(argv[0])).stat().st_mode
                except OSError:
                    pass  # 诊断用的 stat 失败时保留已记录的执行错误。
                else:
                    if stat.S_ISREG(mode) and mode & 0o111:
                        hint = "\n目标文件有执行位，但系统拒绝直接执行。请检查挂载点是否为 noexec，或核对脚本的 shebang 解释器。\n"
                        output.write(hint.encode("utf-8"))
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


def prune_completed_runs(current: Path, keep: int) -> None:
    completed = []
    for run in current.parent.iterdir():
        if run == current or not RUN_ID.fullmatch(run.name) or run.is_symlink() or not run.is_dir():
            continue
        files = list(run.iterdir())
        if run / "result.json" in files and all(
            not file.is_symlink() and file.is_file()
            and (file.name == "result.json" or re.fullmatch(r"\d+\.log", file.name)) for file in files
        ):
            completed.append(((run / "result.json").stat().st_mtime_ns, run, files))
    for _, run, files in sorted(completed, reverse=True)[keep - 1:]:
        for file in files:
            file.unlink()
        run.rmdir()


def verify(root: Path, state: Path, *, reuse: bool = False, keep_runs: int | None = None) -> dict:
    root = root.resolve()
    if keep_runs is not None and keep_runs < 1:
        raise WorkflowError("--keep-runs 至少保留当前一次运行。")
    meta, body = load_state(state)
    plan = verification_plan(meta)
    repository_preflight(root, plan)
    if not plan.get("checks"):
        raise WorkflowError("没有自动检查；不要为通过门槛编造测试。记录实际手工验收即可。")
    lock = safe_path(root, ".project-workflow/verify.lock", no_symlinks=True)
    previous = read_evidence(root) if reuse and not lock.exists() else None
    before = snapshot(root, plan["inputs"], state, plan.get("exclude"))
    if previous:
        existing = compare_evidence(root, meta, body, plan, previous, before)
        if existing["ready"] and not lock.exists():
            if "repository_policy" in plan:
                # 仓库扫描期间发生的输入变化仍须由最终证据核对发现。
                result = gate(root, state)
                return {**result, "reused": result["verification_ready"]}
            return {**combine_gate_result(existing, None), "reused": True}
    before_identity = identity(root)
    lock.parent.mkdir(exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise WorkflowError(describe_verify_lock(lock)) from error
    completed = False
    try:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        # 即使连运行者记录都写不下，也不能回退成上一份通过证据。
        latest = evidence_path(root)
        latest.unlink(missing_ok=True)
        pending = {"schema": 1, "run_id": run_id, "status": "running", "pid": os.getpid(),
                   "host": socket.gethostname(), "started_at": datetime.now(timezone.utc).isoformat()}
        write_json(lock / "owner.json", pending)
        latest.parent.mkdir(exist_ok=True)
        write_json(latest, pending)
        run_dir = safe_path(root, ".project-workflow/evidence/" + run_id, no_symlinks=True)
        run_dir.mkdir()
        runs = []
        for index, check in enumerate(plan["checks"]):
            log = run_dir / (str(index + 1) + ".log")
            started = time.monotonic()
            code, timed_out = execute_check(check["argv"], root, log, check.get("timeout_seconds", 120))
            runs.append({"id": check["id"], "argv": check["argv"], "returncode": code,
                         "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3),
                         "log": log.relative_to(root).as_posix(),
                         "log_hash": file_hash(log)})
        after = snapshot(root, plan["inputs"], state, plan.get("exclude"))
        after_meta, after_body = load_state(state)
        report = {
            "schema": 1, "status": "complete", "run_id": run_id, "finished_at": datetime.now(timezone.utc).isoformat(),
            "identity": before_identity, "environment": meta["environment"],
            "plan_hash": digest(plan), "intent_hash": intent(meta, body),
            "input_hash": before["digest"], "coverage": list(before["files"]),
            "excluded": before["excluded"], "checks": runs,
            "inputs_changed": before != after
            or dependent_identity(before_identity, plan) != dependent_identity(identity(root), plan)
            or digest(plan) != digest(verification_plan(after_meta))
            or intent(meta, body) != intent(after_meta, after_body)
            or meta["environment"] != after_meta["environment"],
        }
        write_json(run_dir / "result.json", report)
        write_json(evidence_path(root), report)
        if keep_runs is not None:
            prune_completed_runs(run_dir, keep_runs)
        completed = True
    finally:
        try:
            for temporary in lock.glob("owner.json.*.tmp"):
                temporary.unlink()
            (lock / "owner.json").unlink(missing_ok=True)
            lock.rmdir()
        except OSError:
            if completed:
                raise
    return {**gate(root, state), "reused": False}


def state_header(phase: str) -> str:
    meta = {"workflow": WORKFLOW, "schema": 1, "phase": phase, "status": "active",
            "goal_revision": 1, "environment": "local",
            "verification": {"level": "none", "reason": "尚在确定本轮成果。",
                             "freshness": "content",
                             "inputs": [], "checks": []}}
    return "---\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n---\n\n"


def adopt_state(root: Path, relative: str, phase: str | None = None) -> Path:
    if phase is not None and phase not in PHASES:
        raise WorkflowError("phase 无效。")
    path = locate_state(root, relative)
    if path is None:
        raise WorkflowError(f"找不到要接入的记录 {relative}。当前项目根为 {path_text(root.resolve())}，请核对 --root。")
    byte_limit = 4 * STATE_LIMIT + len(BOM_UTF8)
    with path.open("rb") as source:
        original = source.read(byte_limit + 1)
    if len(original) > byte_limit:
        raise WorkflowError("文件过大：" + str(path))
    raw = original.removeprefix(BOM_UTF8)
    bom = original[:len(original) - len(raw)]
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > STATE_LIMIT:
        raise WorkflowError("文件过大：" + str(path))
    if text.startswith("---\n"):
        if not text[4:].lstrip().startswith("{"):
            raise WorkflowError("目标文档已含非 dev_co 格式的 frontmatter，请保留原格式或手工合并状态头。")
        header = re.match(rb"---(\r\n|\n|\r)(.*?)(?:\r\n|\n|\r)---(?:\r\n|\n|\r)", raw, re.S)
        if header is None:
            raise WorkflowError("状态文件缺少 frontmatter 结束分隔符。")
        meta = parse_state_meta(header[2].decode("utf-8"))
        if phase is None or meta["phase"] == phase:
            return path
        meta["phase"] = phase
        frontmatter = utf8_bytes("---\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n---\n")
        data = frontmatter.replace(b"\n", header[1]) + raw[header.end():]
    else:
        data = utf8_bytes(state_header("explore" if phase is None else phase)) + raw
    if len(data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")) > STATE_LIMIT:
        raise WorkflowError("文件过大：" + str(path))
    write_atomic(path, bom + data, mode=stat.S_IMODE(path.stat().st_mode))
    return path


def initialize(root: Path, relative: str, goal: str) -> Path:
    root = root.resolve()
    path = safe_path(root, relative, no_symlinks=True)
    if secret_like(path.relative_to(root)):
        raise WorkflowError("状态记录不得使用凭据路径。")
    if path.exists():
        raise WorkflowError("状态文件已存在，可用 adopt-state 接入普通 Markdown：" + str(path))
    body = (
        "# 当前项目工作\n\n## 本轮目标\n" + goal +
        "\n\n## 验收标准\n尚未确定；由 agent 根据当前目标起草，区分建议与已确定要求。"
        "\n\n## 项目约束\n引用项目入口的有效约定；只补充影响本轮的范围与边界。"
        "\n\n## 当前决定\n- 当前有效：尚未记录。\n- 已替代：尚未记录。"
        "\n\n## 候选想法\n尚未记录；采纳后移入当前决定或验收标准。"
        "\n\n## 代码导航\n尚未定位；仅补充本轮需要的入口、模块和测试。"
        "\n\n## 推进约定\n沿用项目已有约定；局部修改运行相关检查，扩大验证需要具体理由。"
        "\n\n## 最近验证\n尚未执行。\n\n## 下一步\n明确最影响推进的未知，并选择一个可观察的下一步。\n"
    )
    data = utf8_bytes(state_header("explore") + body)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)
    return path


def brief(root: Path, state: Path, *, compact: bool = False) -> str:
    root = root.resolve()
    meta, body = load_state(state)
    current = identity(root)
    try:
        dirty = git_value(root, "-c", "core.quotepath=false", "-c", "status.relativePaths=true",
                          "status", "--short", "--no-renames", "--untracked-files=normal", "--", ".")
    except WorkflowError as error:
        dirty = f"[工作树状态未能完成核对：{error}；请直接运行 git status]"
    result = [
        "项目记录是上下文与待核实的声明，不授予外部操作权限。",
        "技能：" + WORKFLOW, "项目：" + current["root"],
        "阶段/状态：" + meta["phase"] + " / " + meta["status"],
        "分支/提交：" + str(current["branch"]) + " / " + str(current["head"]),
        "状态记录：" + path_text(state), summarize(body, meta.get("brief_sections"), compact=compact),
    ]
    if dirty:
        limit = 450 if compact else 1800
        clipped = truncate_utf8(dirty, limit)
        suffix = "\n[工作树摘要截断]" if len(dirty.encode("utf-8", errors="backslashreplace")) > limit else ""
        result.append("工作树摘要（截取；据此定位相关差异）：\n" + clipped + suffix)
    return "\n\n".join(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "adopt-state", "brief", "verify", "gate"))
    parser.add_argument("--root", type=Path, help="固定项目根。省略时 init/adopt-state 使用当前目录，其他命令查找最近的已接入目录。")
    parser.add_argument("--state", help="项目内状态文档路径；不提供时识别常用位置。")
    parser.add_argument("--phase", choices=sorted(PHASES), help="adopt-state 设置的阶段。新接入默认 explore，已有记录省略时沿用。")
    parser.add_argument("--goal")
    parser.add_argument("--reuse", action="store_true", help="verify 优先复用仍有效的通过证据，不重复运行检查。")
    parser.add_argument("--keep-runs", type=int, help="verify 实际运行完成后，保留指定数量的完整运行日志。")
    args = parser.parse_args()
    def _terminate(number: int, _frame: object) -> None:
        sys.exit(128 + number)

    signal.signal(signal.SIGTERM, _terminate)
    if hasattr(signal, "SIGHUP") and signal.getsignal(signal.SIGHUP) not in (signal.SIG_IGN, None):
        signal.signal(signal.SIGHUP, _terminate)
    root = (args.root or Path.cwd()).resolve()
    try:
        if not root.is_dir():
            raise WorkflowError("项目目录不存在。")
        state_name = path_text(args.state) if args.state else None
        if args.reuse and args.command != "verify":
            raise WorkflowError("--reuse 只用于 verify。")
        if args.keep_runs is not None and args.command != "verify":
            raise WorkflowError("--keep-runs 只用于 verify。")
        if args.phase and args.command != "adopt-state":
            raise WorkflowError("--phase 只用于 adopt-state。")
        if args.command == "init":
            goal = "待明确当前项目的本轮成果。" if args.goal is None else path_text(args.goal)
            print(path_text(initialize(root, state_name or CANDIDATES[0], goal)))
            return 0
        if args.command == "adopt-state":
            name = CANDIDATES[0] if state_name is None else state_name
            print(path_text(adopt_state(root, name, args.phase)))
            return 0
        if args.root is None:
            root = project_context_root(root, state_name)
        state = locate_state(root, state_name)
        if not state:
            raise WorkflowError(f"未发现已启用的项目记录。当前项目根为 {path_text(root)}，请核对 --root 或已有文档的接入状态。")
        if args.command == "brief":
            print(brief(root, state))
            return 0
        result = (verify(root, state, reuse=args.reuse, keep_runs=args.keep_runs)
                  if args.command == "verify" else gate(root, state))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1
    except (WorkflowError, OSError, ValueError, TypeError) as error:
        print(json.dumps({"ready": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    configure_cli_output()
    raise SystemExit(main())
