#!/usr/bin/env python3
"""按接入基线检查新增文件归属、文档引用和声明的更新义务；不修改产品文件。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import workflow_files as workflow

POLICY = "devco-repository.json"
BASELINE = workflow.REPOSITORY_BASELINE
REVIEWS = ".project-workflow/repository-reviews.json"
LINK_DESTINATION = r"\(\s*(?:<([^>\n]+)>|((?:[^\s()]|\([^\s()]*\))*))(?:\s+[^\n)]*)?\)"


def repository_context_root(cwd: Path, policy_name: str) -> Path:
    cwd = cwd.resolve()
    configured = workflow.discover_project_root(cwd, lambda root: workflow.project_marker(root, BASELINE) is not None
                                                or workflow.project_marker(root, policy_name) is not None)
    if configured != cwd:
        from project_workflow import locate_state

        # 状态单独存在时仍是子项目边界，不能借用其上级的仓库基线。
        for root in (cwd, *cwd.parents):
            if root == configured:
                break
            if locate_state(root) is not None:
                return root
    return configured


def load_json(root: Path, name: str) -> dict:
    path = workflow.safe_path(root, name, no_symlinks=True, label="规则或检查记录路径")
    if workflow.secret_like(Path(name)):
        raise workflow.WorkflowError("规则和检查记录不得使用凭据路径：" + name)
    try:
        text = workflow.read_text(path, 8_000_000)
    except FileNotFoundError as error:
        raise workflow.WorkflowError(
            f"找不到仓库规则或检查记录 {workflow.path_text(path)}。"
            f"当前项目根为 {workflow.path_text(root.resolve())}，请核对 --root 与相对路径 {name}。"
        ) from error
    value = json.loads(text)
    if not isinstance(value, dict):
        raise workflow.WorkflowError("需要 JSON 对象：" + name)
    return value


def path_names(root: Path, values: object, *, directories: bool = False) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise workflow.WorkflowError("路径配置必须为非空字符串列表。")
    for name in values:
        workflow.safe_path(root, name)
        if name.rstrip("/") != Path(name).as_posix() or name == "." or "\\" in name:
            raise workflow.WorkflowError("使用规范的项目相对路径：" + name)
        if name.endswith("/") and not directories:
            raise workflow.WorkflowError("此处需要文件路径：" + name)
    return values


def load_policy(root: Path, name: str) -> dict:
    policy = load_json(root, name)
    fields = {"schema", "paths", "required", "links", "updates", "ignore", "check_anchors"}
    if policy.get("schema") != 1 or set(policy) - fields:
        raise workflow.WorkflowError("仓库规则 schema 必须为 1，且不能含未知字段。")
    if "check_anchors" in policy and not isinstance(policy["check_anchors"], bool):
        raise workflow.WorkflowError("check_anchors 必须为布尔值。")
    paths = policy.get("paths")
    if not isinstance(paths, dict) or not paths or not all(isinstance(v, str) and v.strip() for v in paths.values()):
        raise workflow.WorkflowError("paths 需要将文件/目录路径映射到具体职责。")
    path_names(root, list(paths), directories=True)
    for key in ("required", "links", "ignore"):
        path_names(root, policy.get(key, []), directories=key == "ignore")
    rules = policy.get("updates", [])
    if not isinstance(rules, list):
        raise workflow.WorkflowError("updates 必须是列表。")
    ids = set()
    for rule in rules:
        if (not isinstance(rule, dict) or set(rule) != {"id", "inputs", "documents"}
                or not isinstance(rule["id"], str) or not rule["id"].strip() or rule["id"] in ids):
            raise workflow.WorkflowError("每条更新规则需要唯一 id、inputs 和 documents。")
        ids.add(rule["id"])
        if not path_names(root, rule["inputs"], directories=True) or not path_names(root, rule["documents"]):
            raise workflow.WorkflowError("更新规则的输入和文档不能为空。")
    return policy


def matches(name: str, paths: list[str] | dict) -> bool:
    return any(name.startswith(path) if path.endswith("/") else name == path for path in paths)


def inventory(root: Path, policy: dict) -> list[str]:
    root = root.resolve()
    # Git 只枚举文件名并沿用 ignore；不会为了接入老项目读取全部源码和历史产物。
    listed = workflow.git_file_names(root, ["."])
    if listed is not None:
        names = set(listed)
    else:
        names = set()
        for directory, dirs, files in os.walk(root, followlinks=False):
            parent = Path(directory).relative_to(root)
            dirs[:] = [d for d in dirs if d not in workflow.IGNORED
                       and not matches(workflow.path_text(parent / d) + "/", policy.get("ignore", []))]
            names.update(workflow.path_text(parent / name) for name in files)
            names.update(workflow.path_text(parent / name) for name in dirs if (root / parent / name).is_symlink())
    return sorted(name for name in names
                  if not set(Path(name).parts) & workflow.IGNORED
                  and not matches(name, policy.get("ignore", []))
                  and os.path.lexists(root / workflow.filesystem_path(name)))


def fingerprints(root: Path, names: list[str]) -> dict:
    result = {}
    total = 0
    for name in sorted(set(names)):
        path = workflow.safe_path(root, name, no_symlinks=True, label="更新规则输入或文档路径")
        if workflow.secret_like(Path(name)):
            raise workflow.WorkflowError("更新规则不得读取凭据路径：" + name)
        if not path.exists():
            result[name] = None
            continue
        if not path.is_file():
            fingerprint = workflow.gitlink_fingerprint(root, name) if path.is_dir() else None
            if fingerprint is not None:
                result[name] = fingerprint
                continue
            raise workflow.WorkflowError("需要文件：" + name)
        total += path.stat().st_size
        if path.stat().st_size > 8_000_000 or total > 64_000_000:
            raise workflow.WorkflowError("声明的更新输入过大；只选择本次增量相关的源码和资料。")
        result[name] = workflow.file_hash(path)
    return result


def markdown_lines(path: Path):
    fence = None
    in_list = False
    blank = True
    for line in workflow.read_text(path, 1_000_000).splitlines():
        if fence:
            if re.fullmatch(r"[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line):
                fence = None
            continue
        if not line.strip():
            blank = True
            continue
        list_match = re.match(r"^(?: {0,12}|\t{1,3})(?:[-+*]|\d+[.)])[ \t]+(.*)$", line)
        if list_match:
            in_list = True
            fence = workflow.fence_start(list_match[1])
            blank = False
            if not fence:
                yield line
            continue
        if in_list and line.startswith(("  ", "\t")) and not blank:
            list_fence = workflow.fence_start(line.lstrip(" \t"))
            if list_fence:
                fence = list_fence
                continue
            yield line
            continue
        if not line.startswith((" ", "\t")):
            in_list = False
        fence = workflow.fence_start(line)
        blank = False
        if not fence and not line.startswith(("    ", "\t")):
            yield line


def markdown_anchors(path: Path) -> set[str]:
    generated, explicit = set(), set()
    for line in markdown_lines(path):
        explicit.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', line))
        heading = workflow.atx_heading(line, max_level=6)
        if heading:
            title = re.sub(r"!?\[([^\]]*)\]" + LINK_DESTINATION, r"\1", heading[1])
            title = re.sub(
                r"(`+)(.+?)\1|(?<![0-9A-Za-z_])_([^_]+)_(?![0-9A-Za-z_])",
                lambda match: match[2] if match[1] is not None else match[3], title,
            )
            base = re.sub(r"[^\w -]", "", title.lower()).strip().replace(" ", "-")
            slug, suffix = base, 1
            while slug in generated:
                slug = f"{base}-{suffix}"
                suffix += 1
            generated.add(slug)
    return generated | explicit


def broken_links(root: Path, sources: list[str], *, check_anchors: bool = False) -> list[list[str]]:
    root = root.resolve()
    broken = set()
    anchors: dict[Path, set[str]] = {}
    for name in sources:
        path = workflow.safe_path(root, name, no_symlinks=True, label="引用检查路径")
        if workflow.secret_like(Path(name)):
            raise workflow.WorkflowError("引用检查不得读取凭据路径：" + name)
        if not path.is_file():
            continue  # 必须保留的入口由 required 声明；可选资料允许归档/删除。
        text = "\n".join(re.sub(r"(`+).*?\1", "", line) for line in markdown_lines(path))
        targets = re.findall(r"\]" + LINK_DESTINATION, text)
        targets += re.findall(r"^ {0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))", text, re.M)
        for angle, plain in targets:
            target = angle or plain
            url = urlsplit(target)
            if url.scheme or url.netloc or url.path.startswith("/") or not (url.path or check_anchors and url.fragment):
                continue
            try:
                destination = (path.parent / workflow.filesystem_path(unquote(url.path))).resolve() if url.path else path
                valid = destination.is_relative_to(root) and destination.exists()
            except (OSError, RuntimeError):
                # 无法解开的符号链接也属于失效引用。
                valid = False
            if (valid and check_anchors and url.fragment and destination.suffix.lower() == ".md"
                    and destination.is_file() and not workflow.secret_like(destination.relative_to(root))):
                if destination not in anchors:
                    anchors[destination] = markdown_anchors(destination)
                valid = unquote(url.fragment) in anchors[destination]
            if not valid:
                broken.add((name, target))
    return [list(item) for item in sorted(broken)]


def observe(root: Path, policy: dict) -> dict:
    files = inventory(root, policy)
    inputs = {rule["id"]: fingerprints(root, [f for f in files if matches(f, rule["inputs"])])
              for rule in policy.get("updates", [])}
    documents = fingerprints(root, [p for rule in policy.get("updates", []) for p in rule["documents"]])
    return {"files": files, "inputs": inputs, "documents": documents,
            "broken_links": broken_links(root, policy.get("links", []), check_anchors=policy.get("check_anchors", False))}


def require_scope(scope: str | None) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise workflow.WorkflowError("需要当前开发工作线/增量的 scope；继续同一工作时沿用，不重复接入。")
    return scope


def git_origin(root: Path) -> dict | None:
    return workflow.git_head_and_branch(root)


def load_baseline(root: Path, policy_name: str, scope: str | None = None) -> dict:
    require_scope(scope)
    baseline = load_json(root, BASELINE)
    if (baseline.get("schema") != 2 or baseline.get("root") != workflow.path_text(root)
            or baseline.get("policy") != policy_name
            or not isinstance(baseline.get("scope"), str)
            or not isinstance(baseline.get("policy_hash"), str)
            or not isinstance(baseline.get("rule_hashes"), dict)
            or "git_origin" not in baseline
            or not isinstance(baseline.get("files"), list)
            or not isinstance(baseline.get("inputs"), dict)
            or not isinstance(baseline.get("documents"), dict)
            or not isinstance(baseline.get("broken_links"), list)):
        raise workflow.WorkflowError("需要有来源的 schema 2 基线且项目/规则路径一致；保留旧基线，核对原增量后再从明确起点接入，不静默重建。")
    if baseline["scope"] != scope:
        raise workflow.WorkflowError("基线 scope 不匹配：当前 " + scope + "，基线 " + baseline["scope"])
    recorded, current = baseline["git_origin"], git_origin(root)
    if recorded != current:
        if (not isinstance(recorded, dict) or not isinstance(current, dict)
                or set(recorded) != {"branch", "head"} or recorded["branch"] != current["branch"]):
            raise workflow.WorkflowError("基线 Git 来源不匹配；不要将另一开发线的快照当作当前比较起点。")
        if recorded["head"] is not None:
            if not isinstance(recorded["head"], str) or not current["head"]:
                raise workflow.WorkflowError("基线 Git 提交来源无法核对。")
            try:
                ancestor = subprocess.run(
                    ["git", "--no-optional-locks", "-C", str(root), "merge-base", "--is-ancestor", recorded["head"], current["head"]],
                    capture_output=True, timeout=5,
                )
            except subprocess.TimeoutExpired as error:
                raise workflow.WorkflowError("基线 Git 祖先关系核对超时。") from error
            if ancestor.returncode != 0:
                raise workflow.WorkflowError("当前 HEAD 不再延续基线 Git 起点；先核对改写或切换的开发范围。")
    return baseline


def review_fingerprint(rule: dict, observed: dict, baseline: dict) -> str:
    comparison = {"root": baseline["root"], "scope": baseline["scope"],
                  "baseline_rule": baseline["rule_hashes"].get(rule["id"]),
                  "baseline_inputs": baseline["inputs"].get(rule["id"], {}),
                  "baseline_documents": {p: baseline["documents"].get(p) for p in rule["documents"]},
                  "rule": rule, "inputs": observed["inputs"][rule["id"]],
                  "documents": {p: observed["documents"].get(p) for p in rule["documents"]}}
    if "revision" in baseline:
        comparison["baseline_revision"] = baseline["revision"]
    return workflow.digest(comparison)


def pending_documents(rule: dict, baseline: dict, observed: dict) -> list[str]:
    if (baseline["rule_hashes"].get(rule["id"]) == workflow.digest(rule)
            and observed["inputs"][rule["id"]] == baseline["inputs"].get(rule["id"], {})):
        return []
    return [p for p in rule["documents"] if p not in baseline["documents"]
            or observed["documents"].get(p) == baseline["documents"][p]]


def assess(root: Path, policy: dict, baseline: dict, observed: dict) -> dict:
    errors, warnings = [], []
    added = sorted(set(observed["files"]) - set(baseline["files"]))
    for name in added:
        if not matches(name, policy["paths"]):
            errors.append("新增文件没有声明归属：" + name)
    for name in policy.get("required", []):
        if not workflow.safe_path(root, name).is_file():
            errors.append("缺少必需入口：" + name)
    previous_links = {tuple(item) for item in baseline["broken_links"]}
    for source, target in observed["broken_links"]:
        if (source, target) not in previous_links:
            errors.append("新增失效引用：" + source + " → " + target)
    old_count = sum(tuple(item) in previous_links for item in observed["broken_links"])
    if old_count:
        warnings.append(f"声明资料中仍有 {old_count} 处接入前的失效引用，本次不追溯整改。")
    reviews = load_json(root, REVIEWS) if workflow.safe_path(root, REVIEWS, no_symlinks=True).exists() else {}
    for rule in policy.get("updates", []):
        for name in rule["documents"]:
            if observed["documents"].get(name) is None:
                errors.append("更新规则的文档不存在：" + name)
        pending = pending_documents(rule, baseline, observed)
        review = reviews.get(rule["id"], {})
        if pending and not (isinstance(review, dict) and isinstance(review.get("reason"), str)
                            and review["reason"].strip()
                            and review.get("fingerprint") == review_fingerprint(rule, observed, baseline)):
            errors.append("更新义务 " + rule["id"] + "：更新或说明无需更新的理由：" + ", ".join(pending))
    return {"ready": not errors, "errors": errors, "warnings": warnings,
            "added": added, "checked_rules": len(policy.get("updates", [])),
            "scope": baseline["scope"], "git_origin": baseline["git_origin"],
            "policy_changed": workflow.digest(policy) != baseline["policy_hash"]}


def check(root: Path, policy_name: str = POLICY, *, scope: str | None = None) -> dict:
    root = root.resolve()
    policy = load_policy(root, policy_name)
    baseline = load_baseline(root, policy_name, scope)
    return assess(root, policy, baseline, observe(root, policy))


def record_baseline(root: Path, policy_name: str, policy: dict, observed: dict, scope: str) -> None:
    path = workflow.safe_path(root, BASELINE, no_symlinks=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_json(path, {"schema": 2, "root": workflow.path_text(root), "policy": policy_name,
                              "scope": scope, "git_origin": git_origin(root),
                              "revision": uuid4().hex,
                              "policy_hash": workflow.digest(policy),
                              "rule_hashes": {r["id"]: workflow.digest(r) for r in policy.get("updates", [])},
                              **observed})


def adopt(root: Path, policy_name: str = POLICY, *, scope: str | None = None) -> dict:
    root = root.resolve()
    scope = require_scope(scope)
    if workflow.safe_path(root, BASELINE, no_symlinks=True).exists():
        raise workflow.WorkflowError("已有基线；增量完成后使用 checkpoint，不覆盖基线掩盖问题。")
    policy = load_policy(root, policy_name)
    observed = observe(root, policy)
    record_baseline(root, policy_name, policy, observed, scope)
    return {"ready": True, "message": "已记录接入基线；不是验收通过。", "files": len(observed["files"]),
            "existing_broken_links": len(observed["broken_links"])}


def checkpoint(root: Path, policy_name: str = POLICY, *, scope: str | None = None) -> dict:
    root = root.resolve()
    policy = load_policy(root, policy_name)
    baseline = load_baseline(root, policy_name, scope)
    observed = observe(root, policy)
    result = assess(root, policy, baseline, observed)
    if result["ready"]:
        record_baseline(root, policy_name, policy, observed, baseline["scope"])
        result["message"] = "已推进仓库基线；功能验证与用户验收仍以各自证据为准。"
    return result


def switch_scope(root: Path, policy_name: str, scope: str, next_scope: str, *, state_name: str | None = None) -> dict:
    from project_workflow import load_state, locate_state

    root = root.resolve()
    next_scope = require_scope(next_scope)
    if scope == next_scope:
        raise workflow.WorkflowError("请为新工作线指定不同的 --next-scope。")
    policy = load_policy(root, policy_name)
    baseline = load_baseline(root, policy_name, scope)
    observed = observe(root, policy)
    result = assess(root, policy, baseline, observed)
    if not result["ready"]:
        return result
    warnings = result["warnings"]
    try:
        state = locate_state(root, state_name)
        if state is not None:
            meta, _ = load_state(state)
            verification = meta.get("verification")
            if isinstance(verification, dict) and verification.get("repository_scope") == scope:
                warnings.append(f"请同步将 {workflow.path_text(state.relative_to(root))} 中的 "
                                f"verification.repository_scope 更新为 {next_scope}。")
    except (workflow.WorkflowError, OSError, UnicodeDecodeError) as error:
        warnings.append(f"无法核对当前状态记录的工作线：{error}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", scope).strip("._-")[:24]
    if not slug:
        slug = "scope"
    archive = workflow.safe_path(root, f".project-workflow/archive/{stamp}-{slug}-{uuid4().hex[:8]}",
                                 no_symlinks=True)
    archive.mkdir(parents=True)
    for name in (BASELINE, REVIEWS):
        path = workflow.safe_path(root, name, no_symlinks=True)
        if path.exists():
            shutil.copy2(path, archive / path.name)
    record_baseline(root, policy_name, policy, observed, next_scope)
    workflow.safe_path(root, REVIEWS, no_symlinks=True).unlink(missing_ok=True)
    archive_path = workflow.path_text(archive)
    return {"ready": True, "scope": next_scope, "archive": archive_path, "warnings": warnings,
            "git_origin": git_origin(root), "message": f"已切换工作线。旧基线和核对记录归档在 {archive_path}。"}


def review(root: Path, policy_name: str, rule_id: str | None, reason: str, *, scope: str | None = None) -> dict:
    root = root.resolve()
    if not rule_id or not rule_id.strip():
        raise workflow.WorkflowError("review 命令需要用 --rule 指定更新规则 ID。")
    if not reason.strip():
        raise workflow.WorkflowError("需要说明为何当前输入变化不要求修改文档。")
    policy = load_policy(root, policy_name)
    baseline = load_baseline(root, policy_name, scope)
    rule = next((r for r in policy.get("updates", []) if r["id"] == rule_id), None)
    if rule is None:
        raise workflow.WorkflowError("没有此更新规则：" + rule_id)
    observed = observe(root, policy)
    if not pending_documents(rule, baseline, observed):
        raise workflow.WorkflowError("此规则没有待核对的文档，无需重复记录。")
    path = workflow.safe_path(root, REVIEWS, no_symlinks=True)
    reviews = load_json(root, REVIEWS) if path.exists() else {}
    reviews[rule_id] = {"reason": reason.strip(), "fingerprint": review_fingerprint(rule, observed, baseline)}
    workflow.write_json(path, reviews)
    return {"ready": True, "message": "已记录核对理由；后续相关输入或文档变化会使其失效。"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("adopt", "check", "review", "checkpoint", "switch-scope"))
    parser.add_argument("--root", type=Path, help="固定项目根。省略时 adopt 使用当前目录，其他命令查找最近的已接入目录。")
    parser.add_argument("--policy", default=POLICY)
    parser.add_argument("--scope", required=True, help="沿用当前工作线/增量标识；普通继续开发不更换。")
    parser.add_argument("--next-scope", help="switch-scope 接入的新工作线。")
    parser.add_argument("--state", help="可选状态记录路径；供 switch-scope 核对自定义记录的 repository_scope。")
    parser.add_argument("--rule")
    parser.add_argument("--reason", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = (args.root or Path.cwd()).resolve()
    try:
        if not root.is_dir():
            raise workflow.WorkflowError("项目目录不存在。")
        policy_name = workflow.path_text(args.policy)
        scope = workflow.path_text(args.scope)
        state_name = workflow.path_text(args.state) if args.state else None
        if args.state and args.command != "switch-scope":
            raise workflow.WorkflowError("--state 只用于 switch-scope。")
        if args.root is None and args.command != "adopt":
            root = repository_context_root(root, policy_name)
        if args.command == "review":
            rule = workflow.path_text(args.rule) if args.rule else None
            result = review(root, policy_name, rule, workflow.path_text(args.reason), scope=scope)
        elif args.command == "switch-scope":
            if not args.next_scope or not args.next_scope.strip():
                raise workflow.WorkflowError("switch-scope 需要 --next-scope。")
            result = switch_scope(root, policy_name, scope, workflow.path_text(args.next_scope),
                                  state_name=state_name)
        else:
            result = {"adopt": adopt, "check": check, "checkpoint": checkpoint}[args.command](root, policy_name, scope=scope)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result.get("message", "仓库增量检查通过。" if result["ready"] else "仓库增量检查未通过。"))
            if "scope" in result:
                print("比较范围：" + result["scope"] + "；Git 起点：" + str(result["git_origin"]))
            for message in (result.get("errors", []) + result.get("warnings", []))[:20]:
                print("- " + message)
            if len(result.get("errors", [])) + len(result.get("warnings", [])) > 20:
                print("其余问题请用 --json 查看。")
        return 0 if result["ready"] else 1
    except (workflow.WorkflowError, OSError, ValueError, TypeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ready": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    workflow.configure_cli_output()
    raise SystemExit(main())
