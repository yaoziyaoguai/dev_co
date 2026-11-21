"""Behavioral tests for local evidence and host adapters; no external services."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_workflow as workflow
import repository_check as repository
import workflow_hooks as hooks


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="project-workflow-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "project with spaces"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src/logic.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "check.py").write_text(
            "from pathlib import Path\n"
            "assert Path('src/logic.py').read_text() == 'value = 1\\n'\n"
            "print('behavior passed')\n"
        , encoding="utf-8")
        self.state = workflow.initialize(self.root, "docs/CURRENT.md", "验证局部行为")
        self.meta, self.body = workflow.load_state(self.state)
        self.meta["phase"] = "repair"
        self.meta["verification"] = {
            "level": "targeted", "reason": "只修改局部行为及其测试。",
            "inputs": ["src", "check.py"],
            "checks": [{"id": "behavior", "argv": [sys.executable, "check.py"],
                        "cost": "local", "timeout_seconds": 5}],
        }
        self.save()

    def save(self):
        self.state.write_text("---\n" + json.dumps(self.meta, ensure_ascii=False, indent=2)
                              + "\n---\n" + self.body, encoding="utf-8")

    def verify(self):
        return workflow.verify(self.root, self.state)

    def gate(self):
        return workflow.gate(self.root, self.state)

    def event(self, name, **kwargs):
        return {"hook_event_name": name, "cwd": str(self.root), **kwargs}

    def cli(self, command, **kwargs):
        return subprocess.run([sys.executable, str(SCRIPTS / "project_workflow.py"),
                               command, "--root", str(self.root)],
                              capture_output=True, encoding="utf-8", timeout=10, **kwargs)


class EvidenceTests(ProjectFixture):
    def test_adopt_state_preserves_original_markdown_bytes_and_permissions(self):
        path = self.root / "docs/NOTES.md"
        original = "# 原始记录\r\n保留换行。\r\n".encode("utf-8")
        path.write_bytes(original)
        path.chmod(0o600)
        args = [sys.executable, str(SCRIPTS / "project_workflow.py"), "adopt-state", "--root", str(self.root),
                "--state", "docs/NOTES.md", "--phase", "build"]
        result = subprocess.run(args, capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        first = path.read_bytes()
        self.assertTrue(first.endswith(original))
        self.assertEqual(workflow.load_state(path)[0]["phase"], "build")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(subprocess.run(args, capture_output=True, timeout=10).returncode, 0)
        self.assertEqual(path.read_bytes(), first)

    def test_init_preserves_existing_work(self):
        before = self.state.read_bytes()
        with self.assertRaises(workflow.WorkflowError):
            workflow.initialize(self.root, "docs/CURRENT.md", "overwrite")
        self.assertEqual(self.state.read_bytes(), before)

    def test_new_records_declare_content_freshness(self):
        other = workflow.initialize(self.root, "notes/new.md", "new goal")
        meta, _ = workflow.load_state(other)
        self.assertEqual(meta["verification"]["freshness"], "content")

    def test_custom_state_and_unconfigured_document(self):
        self.state.unlink()
        custom = workflow.initialize(self.root, "notes/active.md", "custom goal")
        self.assertEqual(workflow.locate_state(self.root, "notes/active.md"), custom)
        self.state.write_text("# User's existing document\nDo not rewrite.\n", encoding="utf-8")
        self.assertIsNone(workflow.locate_state(self.root))

    def test_auto_detection_skips_ordinary_candidates_before_enabled_state(self):
        active = self.state.with_name("PROJECT.md")
        original = self.state.read_bytes()
        active.write_bytes(original)
        for ordinary in ("---\ntitle: dev_co notes\n---\n" + "x" * 150_000,
                         '---\n{"title":"dev_co notes","settings":{"workflow":"dev_co"}}\n---\n',
                         '---\n{"settings":{"workflow":"dev_co"}, // JSONC example\n}\n---\n',
                         "# Ordinary project notes\n" + "x" * 150_000):
            with self.subTest(prefix=ordinary[:36]):
                self.state.write_text(ordinary, encoding="utf-8")
                self.assertEqual(workflow.locate_state(self.root), active)
                result = hooks.respond(self.event("SessionStart"))
                self.assertIn(str(active), result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(active.read_bytes(), original)

    def test_existing_records_remain_usable_after_skill_rename(self):
        self.assertEqual(self.meta["workflow"], "dev_co")
        self.meta["workflow"] = "start-software-project"
        self.save()
        self.assertEqual(workflow.locate_state(self.root), self.state)
        self.assertTrue(self.verify()["ready"])
        restored = hooks.respond(self.event("SessionStart"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("技能：dev_co", restored)
        self.meta["workflow"] = "dev_co"
        self.save()
        self.assertTrue(self.gate()["ready"])

    def test_brief_restores_context_without_executing(self):
        self.body += "\n## 代码入口补充\nsrc/logic.py\n"
        self.save()
        before = set(self.root.rglob("*"))
        result = workflow.brief(self.root, self.state)
        self.assertIn("验证局部行为", result)
        self.assertIn("src/logic.py", result)
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_passing_checks_produce_current_evidence(self):
        self.assertTrue(self.verify()["ready"])
        self.assertTrue(self.gate()["ready"])
        report = workflow.read_evidence(self.root)
        self.assertEqual(report["checks"][0]["returncode"], 0)
        log = self.root / report["checks"][0]["log"]
        self.assertIn("behavior passed", log.read_text(encoding="utf-8"))
        self.assertEqual(set(report["coverage"]), {"src/logic.py", "check.py"})

    def test_failure_replaces_previous_success(self):
        self.assertTrue(self.verify()["ready"])
        (self.root / "check.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
        self.assertFalse(self.verify()["ready"])
        self.assertEqual(workflow.read_evidence(self.root)["checks"][0]["returncode"], 3)
        self.assertFalse(self.gate()["ready"])

    def test_missing_executable_is_failure(self):
        self.meta["verification"]["checks"][0]["argv"] = [str(self.root / "missing")]
        self.save()
        self.assertFalse(self.verify()["ready"])
        self.assertEqual(workflow.read_evidence(self.root)["checks"][0]["returncode"], 127)

    def test_timeout_kills_descendant_processes(self):
        child = "import signal,time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(0.9); Path('leaked.txt').write_text('alive')"
        (self.root / "check.py").write_text(
            "import subprocess,sys,time\n"
            + "subprocess.Popen([sys.executable, '-c', " + repr(child) + "])\n"
            + "time.sleep(5)\n"
        , encoding="utf-8")
        self.meta["verification"]["checks"][0]["timeout_seconds"] = 0.25
        self.save()
        self.assertFalse(self.verify()["ready"])
        self.assertTrue(workflow.read_evidence(self.root)["checks"][0]["timed_out"])
        time.sleep(1)
        self.assertFalse((self.root / "leaked.txt").exists())

    def test_uncommitted_edit_invalidates_evidence(self):
        self.verify()
        (self.root / "src/logic.py").write_text("value = 2\n", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])

    def test_new_and_removed_files_in_declared_directory(self):
        self.verify()
        added = self.root / "src/new.py"
        added.write_text("extra = True\n", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])
        self.verify()
        added.unlink()
        self.assertFalse(self.gate()["ready"])

    def test_unrelated_edits_and_operational_notes_preserve_evidence(self):
        self.verify()
        (self.root / "notes.md").write_text("unrelated note", encoding="utf-8")
        self.body += "\n## 最近验证\n已通过，见证据。\n## 下一步\n交接。\n"
        self.save()
        self.assertTrue(self.gate()["ready"])

    def test_goal_acceptance_revision_and_environment_invalidate(self):
        mutations = (
            lambda: setattr(self, "body", self.body + "\n## 验收补充\n新增行为。\n"),
            lambda: self.meta.update(goal_revision=self.meta["goal_revision"] + 1),
            lambda: self.meta.update(environment="other runtime"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.assertTrue(self.verify()["ready"])
                mutate()
                self.save()
                self.assertFalse(self.gate()["ready"])

    def test_plan_change_invalidates(self):
        self.verify()
        self.meta["verification"]["checks"][0]["argv"].append("new-argument")
        self.save()
        self.assertFalse(self.gate()["ready"])

    def test_fenced_headings_cannot_hide_effective_decisions(self):
        for opening, closing, nested in (
            ("```markdown", "```", ""),
            ("~~~markdown", "~~~", ""),
            ("````markdown", "`````", "```\n"),
            ("   ~~~~ markdown", "  ~~~~  ", "~~~\n```\n"),
        ):
            with self.subTest(opening=opening):
                self.body = ("## 当前决定\n引用示例：\n" + opening + "\n" + nested
                             + "## 下一步\n示例文字\n" + closing
                             + "\n\n当前有效决定：保留旧接口。\n\n## 验收标准\n检查通过。\n")
                self.save()
                self.assertTrue(self.verify()["ready"])
                self.body = self.body.replace("保留旧接口", "删除旧接口")
                self.save()
                self.assertFalse(self.gate()["ready"])

    def test_old_intent_algorithm_requires_fresh_evidence(self):
        self.assertTrue(self.verify()["ready"])
        report = workflow.read_evidence(self.root)
        kept, skip = [], False
        for line in self.body.splitlines():
            if line.startswith("## "):
                skip = line[3:].strip() in {"最近验证", "下一步", "接手记录"}
            if not skip:
                kept.append(line)
        report["intent_hash"] = workflow.digest({
            "goal_revision": self.meta["goal_revision"], "body": "\n".join(kept).strip(),
        })
        workflow.write_json(workflow.evidence_path(self.root), report)
        self.assertFalse(self.gate()["ready"])
        self.assertTrue(self.verify()["ready"])

    def test_fenced_headings_do_not_end_operational_section(self):
        self.body = "## 本轮目标\n维持行为。\n## 最近验证\n```md\n## 验收标准\n示例 A\n```\n"
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("示例 A", "示例 B")
        self.save()
        self.assertTrue(self.gate()["ready"])

    def test_container_fences_cannot_hide_following_acceptance(self):
        for prefix, indent in (("- ", "  "), ("1. ", "   "), ("> ", "> ")):
            for following in ("", "\n```\n另一个例子\n```\n"):
                with self.subTest(prefix=prefix, following=following):
                    self.body = ("## 候选想法\n" + prefix + "```markdown\n"
                                 + indent + "示例\n" + indent + "```\n\n"
                                 + "## 验收标准\n必须保留旧接口。\n" + following)
                    self.save()
                    self.assertTrue(self.verify()["ready"])
                    self.body = self.body.replace("保留旧接口", "删除旧接口")
                    self.save()
                    self.assertFalse(self.gate()["ready"])

    def test_unclosed_fence_uses_conservative_intent(self):
        self.body = "## 下一步\n```\n未闭合的代码块\n## 当前决定\n保留旧接口。\n"
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("保留旧接口", "删除旧接口")
        self.save()
        self.assertFalse(self.gate()["ready"])

    def test_list_continuation_fence_uses_conservative_intent(self):
        self.body = ("## 候选想法\n- 示例\n  ```markdown\n  列表内代码\n\n"
                     "## 验收标准\n保留旧接口。\n\n```python\nexample\n```\n")
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("保留旧接口", "删除旧接口")
        self.save()
        self.assertFalse(self.gate()["ready"])

    def test_effective_heading_after_candidate_section_invalidates(self):
        for heading in ("## 当前决定", "   ## 当前决定 ##", "# 新阶段"):
            with self.subTest(heading=heading):
                self.body = "## 候选想法\n未确定。\n" + heading + "\n保留旧接口。\n"
                self.save()
                self.assertTrue(self.verify()["ready"])
                self.body = self.body.replace("保留旧接口", "删除旧接口")
                self.save()
                self.assertFalse(self.gate()["ready"])

    def test_only_dedicated_candidates_preserve_evidence(self):
        self.body = ("## 本轮目标\n维持行为。\n## 当前决定\n有效：保留接口。\n"
                     "## 候选想法\n也许增加导出。\n## 验收标准\n现有检查通过。\n")
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("也许增加导出", "也许增加搜索")
        self.save()
        self.assertTrue(self.gate()["ready"])
        self.body = self.body.replace("有效：保留接口。", "有效：保留接口。\n候选：增加导出。")
        self.save()
        self.assertFalse(self.gate()["ready"])
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("候选：增加导出。", "有效：增加搜索。")
        self.save()
        self.assertFalse(self.gate()["ready"])

    def test_content_freshness_reuses_checks_across_git_only_changes(self):
        subprocess.run(["git", "init", "-q", "-b", "codex/test", str(self.root)], check=True)
        self.meta["verification"]["freshness"] = "content"
        self.save()
        self.assertTrue(self.verify()["ready"])
        original = workflow.read_evidence(self.root)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
                        "commit", "--allow-empty", "-qm", "Metadata only"], check=True)
        subprocess.run(["git", "-C", str(self.root), "switch", "-qc", "codex/other"], check=True)
        self.assertTrue(self.gate()["ready"])
        self.assertEqual(workflow.read_evidence(self.root), original)
        (self.root / "src/logic.py").write_text("value = 2\n", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])

    def test_git_dependent_checks_stay_strict(self):
        for mode in (None, "git"):
            with self.subTest(mode=mode):
                if mode is None:
                    self.meta["verification"].pop("freshness", None)
                else:
                    self.meta["verification"]["freshness"] = mode
                self.save()
                with patch.object(workflow, "identity", return_value={"root": str(self.root), "head": "one", "branch": "main"}):
                    self.assertTrue(self.verify()["ready"])
                with patch.object(workflow, "identity", return_value={"root": str(self.root), "head": "two", "branch": "main"}):
                    self.assertFalse(self.gate()["ready"])

    def test_content_freshness_still_binds_root_environment_goal_and_plan(self):
        self.meta["verification"]["freshness"] = "content"
        self.save()
        for field, value in (("root", str(self.base)), ("head", "other")):
            self.assertTrue(self.verify()["ready"])
            report = workflow.read_evidence(self.root)
            report["identity"][field] = value
            workflow.write_json(workflow.evidence_path(self.root), report)
            self.assertEqual(self.gate()["ready"], field == "head")
        for mutate in (
            lambda: self.meta.update(environment="new runtime"),
            lambda: self.meta.update(goal_revision=2),
            lambda: self.meta["verification"].update(freshness="git"),
        ):
            self.assertTrue(self.verify()["ready"])
            mutate()
            self.save()
            self.assertFalse(self.gate()["ready"])

    def test_git_changes_during_run_follow_declared_freshness(self):
        first = {"root": str(self.root), "head": "one", "branch": "main"}
        second = {**first, "head": "two"}
        for mode in ("content", "git"):
            with self.subTest(mode=mode):
                self.meta["verification"]["freshness"] = mode
                self.save()
                with patch.object(workflow, "identity", side_effect=[first, second, second]):
                    self.assertEqual(self.verify()["ready"], mode == "content")

    def test_git_identity_changes_invalidate(self):
        subprocess.run(["git", "init", "-q", "-b", "codex/test", str(self.root)], check=True)
        self.assertTrue(self.verify()["ready"])
        subprocess.run(["git", "-C", str(self.root), "symbolic-ref", "HEAD", "refs/heads/codex/other"], check=True)
        self.assertFalse(self.gate()["ready"])

    def test_input_mutation_during_execution_is_not_success(self):
        (self.root / "check.py").write_text("from pathlib import Path\nPath('src/logic.py').write_text('value = 2\\n')\n", encoding="utf-8")
        self.assertFalse(self.verify()["ready"])
        self.assertTrue(workflow.read_evidence(self.root)["inputs_changed"])

    def test_goal_mutation_during_execution_is_not_success(self):
        (self.root / "check.py").write_text(
            "from pathlib import Path\np=Path('docs/CURRENT.md')\n"
            "p.write_text(p.read_text(encoding='utf-8') + '\\n## New decision\\nChanged requirement\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.assertFalse(self.verify()["ready"])
        self.assertTrue(workflow.read_evidence(self.root)["inputs_changed"])

    def test_interrupted_attempt_never_reuses_old_success(self):
        (self.root / "check.py").write_text(
            "from pathlib import Path\n"
            "if Path('delete.flag').exists(): Path('check.py').unlink()\n"
        , encoding="utf-8")
        source = (self.root / "check.py").read_text(encoding="utf-8")
        self.assertTrue(self.verify()["ready"])
        old = workflow.read_evidence(self.root)["run_id"]
        (self.root / "delete.flag").write_text("1", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError):
            self.verify()
        (self.root / "check.py").write_text(source, encoding="utf-8")
        report = workflow.read_evidence(self.root)
        self.assertNotEqual(report["run_id"], old)
        self.assertNotEqual(report["status"], "complete")
        self.assertFalse(self.gate()["ready"])

    def test_concurrent_run_is_rejected(self):
        (self.root / "check.py").write_text("from pathlib import Path\nimport time\nPath('started').write_text('1')\ntime.sleep(1)\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(SCRIPTS / "project_workflow.py"),
                                    "verify", "--root", str(self.root)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / "started").exists())
            self.assertFalse(self.gate()["ready"])
            second = self.cli("verify")
            self.assertEqual(second.returncode, 2, second.stderr)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr + stdout)
            self.assertTrue(self.gate()["ready"])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_termination_cleans_up_running_checks(self):
        (self.root / "check.py").write_text("from pathlib import Path\nimport time\nPath('started').write_text('1')\ntime.sleep(0.9)\nPath('leaked.txt').write_text('alive')\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(SCRIPTS / "project_workflow.py"),
                                    "verify", "--root", str(self.root)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / "started").exists())
            process.terminate()
            process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, 0)
            time.sleep(1)
            self.assertFalse((self.root / "leaked.txt").exists())
            self.assertFalse(self.gate()["ready"])
            self.assertFalse((self.root / ".project-workflow/verify.lock").exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_manual_plan_does_not_fabricate_automatic_pass(self):
        self.meta["verification"] = {"level": "none", "reason": "人工核对文案。", "inputs": [], "checks": []}
        self.save()
        self.assertFalse(self.gate()["ready"])
        with self.assertRaises(workflow.WorkflowError):
            self.verify()

    def test_malformed_state_and_plan_are_reported(self):
        good = self.state.read_text(encoding="utf-8")
        for content in ("---\n{}\n---\n", "---\nnot json\n---\n", "plain document", "---\n[]\n---\n"):
            self.state.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(workflow.WorkflowError):
                workflow.load_state(self.state)
        self.state.write_text(good, encoding="utf-8")
        for field, value in (("phase", []), ("status", {}), ("goal_revision", True), ("environment", None)):
            old = self.meta[field]
            self.meta[field] = value
            self.save()
            with self.subTest(field=field), self.assertRaises(workflow.WorkflowError):
                workflow.load_state(self.state)
            self.meta[field] = old
        self.save()
        original = json.loads(json.dumps(self.meta))
        for change in ({"inputs": "src"}, {"checks": {}}, {"level": []}, {"reason": ""},
                       {"freshness": "unknown"}, {"freshness": []}):
            meta = json.loads(json.dumps(original))
            meta["verification"].update(change)
            with self.subTest(change=change), self.assertRaises(workflow.WorkflowError):
                workflow.verification_plan(meta)

    def test_explicit_nonlocal_and_invalid_commands_are_rejected(self):
        original = json.loads(json.dumps(self.meta))
        for field, value in (("cost", "paid"), ("argv", "python check.py"), ("argv", []), ("timeout_seconds", True), ("timeout_seconds", -1)):
            meta = json.loads(json.dumps(original))
            meta["verification"]["checks"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(workflow.WorkflowError):
                workflow.verification_plan(meta)

    def test_unsafe_paths_and_symlinks_are_rejected(self):
        outside = self.base / "private.txt"
        outside.write_text("synthetic sentinel", encoding="utf-8")
        (self.root / "link.txt").symlink_to(outside)
        for name in ("../private.txt", str(outside), "link.txt"):
            with self.subTest(name=name), self.assertRaises(workflow.WorkflowError):
                workflow.snapshot(self.root, [name], self.state)

    def test_sensitive_names_and_recursive_symlinks_not_read(self):
        (self.root / ".env").write_text("synthetic sentinel", encoding="utf-8")
        (self.root / ".aws").mkdir()
        (self.root / ".aws/credentials").write_text("synthetic sentinel", encoding="utf-8")
        (self.root / "src/internal-link.py").symlink_to(self.root / "check.py")
        with patch.object(workflow, "file_hash", wraps=workflow.file_hash) as hashing:
            snapshot = workflow.snapshot(self.root, ["."], self.state)
        read = {args.args[0].relative_to(self.root).as_posix() for args in hashing.call_args_list}
        self.assertFalse(any(".env" in p or ".aws" in p or "internal-link" in p for p in read))
        self.assertIn(".env", snapshot["excluded"])
        for path in (".env", ".aws"):
            with self.assertRaises(workflow.WorkflowError):
                workflow.snapshot(self.root, [path], self.state)

    def test_evidence_cannot_redirect_log_reads(self):
        self.verify()
        private = self.root / ".env"
        private.write_text("synthetic sentinel", encoding="utf-8")
        for log in (".env", "../private.txt", ["bad type"]):
            report = workflow.read_evidence(self.root)
            report["checks"][0]["log"] = log
            workflow.write_json(workflow.evidence_path(self.root), report)
            with patch.object(workflow, "file_hash", wraps=workflow.file_hash) as hashing:
                self.assertFalse(self.gate()["ready"])
            self.assertFalse(any(args.args[0] == private for args in hashing.call_args_list))

    def test_evidence_symlink_refused(self):
        outside = self.base / "external-evidence"
        outside.mkdir()
        (self.root / ".project-workflow").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(workflow.WorkflowError):
            self.verify()
        self.assertEqual(list(outside.iterdir()), [])

    def test_changed_or_missing_log_fails(self):
        self.verify()
        report = workflow.read_evidence(self.root)
        log = self.root / report["checks"][0]["log"]
        log.write_text("edited", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])
        log.unlink()
        self.assertFalse(self.gate()["ready"])

    def test_malformed_report_never_passes(self):
        self.verify()
        original = workflow.read_evidence(self.root)
        cases = ({"run_id": []}, {"checks": [None]}, {"checks": {}}, {"status": "running"}, {"inputs_changed": None})
        for change in cases:
            report = {**original, **change}
            workflow.write_json(workflow.evidence_path(self.root), report)
            with self.subTest(change=change):
                self.assertFalse(self.gate()["ready"])
        workflow.evidence_path(self.root).write_text("[broken", encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError):
            self.gate()

    def test_shell_metacharacters_are_literal_arguments(self):
        literal = "$(touch injected) ; `touch injected`"
        self.meta["verification"]["checks"][0]["argv"] = [sys.executable, "-c", "import sys; print(sys.argv[1])", literal]
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.assertFalse((self.root / "injected").exists())
        report = workflow.read_evidence(self.root)
        self.assertIn(literal, (self.root / report["checks"][0]["log"]).read_text(encoding="utf-8"))

    def test_input_and_state_size_limits(self):
        with (self.root / "src/large").open("wb") as target:
            target.truncate(8_000_001)
        with self.assertRaises(workflow.WorkflowError):
            self.verify()
        with self.state.open("a", encoding="utf-8") as output:
            output.write("x" * 128_001)
        self.assertEqual(workflow.locate_state(self.root), self.state)
        with self.assertRaisesRegex(workflow.WorkflowError, "文件过大"):
            workflow.load_state(self.state)

    def test_cli_exit_status_distinguishes_success_missing_and_error(self):
        self.assertEqual(self.cli("gate").returncode, 1)
        self.assertEqual(self.cli("verify").returncode, 0)
        self.assertEqual(self.cli("gate").returncode, 0)
        self.state.write_text("broken", encoding="utf-8")
        self.assertEqual(self.cli("gate").returncode, 2)

    def test_redirected_standard_streams_keep_their_text_encoding(self):
        with (patch.object(sys, "stdin", io.StringIO()), patch.object(sys, "stdout", io.StringIO()),
              patch.object(sys, "stderr", io.StringIO())):
            workflow.configure_cli_output(include_stdin=True)

    def test_non_utf8_record_fails_before_writing_an_evidence_file(self):
        data = {"path": "bad\udcff"}
        path = self.root / "result.json"
        with self.assertRaisesRegex(workflow.WorkflowError, "UTF-8"):
            workflow.digest(data)
        before = list(self.root.iterdir())
        with self.assertRaisesRegex(workflow.WorkflowError, "UTF-8"):
            workflow.write_json(path, data)
        self.assertEqual(list(self.root.iterdir()), before)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux 文件系统允许非 UTF-8 文件名")
    def test_verify_rejects_an_invalid_utf8_filename_without_publishing_evidence(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        scratch = self.root / "src/scratch"
        scratch.mkdir()
        with open(os.fsencode(scratch) + b"/bad\xff.py", "wb") as stream:
            stream.write(b"pass\n")
        result = self.cli("verify")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("须使用有效的 UTF-8", json.loads(result.stderr)["error"])
        self.assertFalse(workflow.evidence_path(self.root).exists())
        self.meta["verification"]["exclude"] = ["src/scratch/"]
        self.save()
        self.assertTrue(self.verify()["ready"])

    def test_verify_lock_reports_a_missing_owner_pid(self):
        lock = self.root / ".project-workflow/verify.lock"
        lock.mkdir(parents=True)
        run_id = "20261122T000000Z-01234567"
        workflow.write_json(lock / "owner.json", {"pid": 42_000, "run_id": run_id})
        with patch.object(workflow.os, "kill", side_effect=ProcessLookupError) as lookup:
            self.assertIn(f"{run_id}，PID 42000 已不存在", self.gate()["reasons"][0])
            with self.assertRaisesRegex(workflow.WorkflowError, "PID 42000 已不存在"):
                self.verify()
        lookup.assert_called_with(42_000, 0)
        self.assertTrue(lock.is_dir())

    def test_explicit_log_retention_keeps_current_and_unfinished_runs(self):
        self.assertTrue(self.verify()["ready"])
        evidence = workflow.evidence_path(self.root).parent
        unfinished = evidence / "20250101T000000Z-00000000"
        unfinished.mkdir()
        (unfinished / "1.log").write_text("unfinished", encoding="utf-8")
        self.assertTrue(workflow.verify(self.root, self.state, keep_runs=1)["ready"])
        current = evidence / workflow.read_evidence(self.root)["run_id"]
        self.assertEqual({p for p in evidence.iterdir() if p.is_dir()}, {current, unfinished})
        self.assertTrue(self.gate()["ready"])

    def test_commands_keep_utf8_state_and_output_in_ascii_locale(self):
        relative_state = self.state.relative_to(self.root)
        self.root = self.root.rename(self.base / os.fsdecode("中文项目".encode("utf-8")))
        self.state = self.root / relative_state
        subprocess.run(["git", "init", "-q", "-b", "工作线".encode("utf-8"), str(self.root)], check=True)
        source = self.root / os.fsdecode("实现/入口.py".encode("utf-8"))
        source.parent.mkdir()
        source.write_text("pass\n", encoding="utf-8")
        self.meta["verification"]["inputs"].append("实现")
        self.meta["verification"]["checks"][0]["id"] = "局部验证"
        self.meta["verification"]["checks"][0]["argv"].append("检查")
        self.save()
        (self.root / repository.POLICY).write_text(json.dumps({"schema": 1, "paths": {"实现/": "实现"}}),
                                                  encoding="utf-8")
        locale_env = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                      "PYTHONIOENCODING": ""}

        def run(script, *argv, payload=None):
            result = subprocess.run([sys.executable, str(SCRIPTS / script), *argv], cwd=self.root,
                                    env=locale_env, input=payload, capture_output=True,
                                    encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        custom = "docs/交接.md".encode("utf-8")
        goal = "记录新目标".encode("utf-8")
        run("project_workflow.py", "init", "--state", custom, "--goal", goal)
        self.assertIn(goal.decode("utf-8"), run("project_workflow.py", "brief", "--state", custom))
        self.assertIn("验证局部行为", run("project_workflow.py", "brief"))
        result = json.loads(run("project_workflow.py", "verify"))
        self.assertTrue(result["ready"])
        self.assertIn("实现/入口.py", result["coverage"])
        self.assertEqual(workflow.read_evidence(self.root)["checks"][0]["id"], "局部验证")
        self.assertTrue(json.loads(run("project_workflow.py", "gate"))["ready"])
        scope = "工作线".encode("utf-8")
        run("repository_check.py", "adopt", "--scope", scope)
        self.assertIn("工作线", run("repository_check.py", "check", "--scope", scope))
        event = json.dumps(self.event("SessionStart", cwd=os.fsencode(self.root).decode("utf-8")), ensure_ascii=False)
        response = run("workflow_hooks.py", "--host", "codex", payload=event)
        self.assertIn("验证局部行为", json.loads(response)["hookSpecificOutput"]["additionalContext"])


class HookTests(ProjectFixture):
    def test_unconfigured_sessions_do_not_mutate_project(self):
        self.state.unlink()
        before = set(self.root.rglob("*"))
        for event in ("SessionStart", "Stop"):
            self.assertEqual(hooks.respond(self.event(event)), {})
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_session_restores_goal_without_running_checks(self):
        result = hooks.respond(self.event("SessionStart"))
        self.assertIn("验证局部行为", result["hookSpecificOutput"]["additionalContext"])
        self.assertFalse((self.root / ".project-workflow").exists())

    def test_session_start_matches_all_supported_sources(self):
        for host in ("codex", "claude"):
            matcher = hooks.config(host, None, [])["hooks"]["SessionStart"][0]["matcher"]
            for source in ("startup", "resume", "clear", "compact", "fork"):
                with self.subTest(host=host, source=source):
                    self.assertIsNotNone(re.fullmatch(matcher, source))

    def test_session_start_compacts_long_chinese_context(self):
        self.body += "\n## 历史\n" + "历史记录。" * 1000
        self.save()
        self.assertGreater(len(workflow.brief(self.root, self.state).encode("utf-8")), 6000)
        result = hooks.respond(self.event("SessionStart"))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context.encode("utf-8")), 6000)
        self.assertIn(str(self.state), context)
        self.assertIn("验证局部行为", context)
        self.assertNotIn("历史记录。", context)

    def test_session_start_points_to_state_if_compact_summary_is_still_oversized(self):
        self.meta["brief_sections"] = ["长标题" * 1000]
        self.save()
        result = hooks.respond(self.event("SessionStart"))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context.encode("utf-8")), 6000)
        self.assertIn(str(self.state), context)
        self.assertIn("读取该记录", context)

    def test_only_codex_sets_session_context_limit(self):
        for host in ("codex", "claude"):
            config = hooks.config(host, None, [])
            handler = config["hooks"]["SessionStart"][0]["hooks"][0]
            self.assertEqual(handler.get("additionalContextLimit"), 4000 if host == "codex" else None)

    def test_stop_defaults_to_no_work_even_when_project_is_building(self):
        with patch.object(workflow, "gate") as gate, patch.object(workflow, "load_state") as load:
            self.assertEqual(hooks.respond(self.event("Stop")), {})
        gate.assert_not_called()
        load.assert_not_called()
        self.assertNotIn("Stop", hooks.config("codex", None, [])["hooks"])

    def test_opted_in_stop_is_advisory_and_never_forces_continuation(self):
        for active in (False, True):
            result = hooks.respond(self.event("Stop", stop_hook_active=active), check_on_stop=True)
            self.assertNotIn("decision", result)
            self.assertIn("systemMessage", result)
        self.assertFalse((self.root / ".project-workflow").exists())
        config = hooks.config("codex", None, [], check_on_stop=True)
        self.assertIn("--check-on-stop", config["hooks"]["Stop"][0]["hooks"][0]["command"])

    def test_discussion_waiting_and_paused_states_do_not_continue(self):
        for phase in ("explore", "shape", "recover"):
            self.meta["phase"] = phase
            self.save()
            self.assertEqual(hooks.respond(self.event("Stop"), check_on_stop=True), {})
        self.meta["phase"] = "repair"
        for status in ("needs-user", "blocked", "paused"):
            self.meta["status"] = status
            self.save()
            self.assertEqual(hooks.respond(self.event("Stop"), check_on_stop=True), {})

    def test_success_does_not_grant_permission(self):
        self.verify()
        self.assertEqual(hooks.respond(self.event("Stop")), {})
        self.assertEqual(hooks.respond(self.event("PreToolUse"), protect=True), {})

    def test_stale_evidence_blocks_selected_tool(self):
        self.verify()
        (self.root / "src/logic.py").write_text("value = 2\n", encoding="utf-8")
        result = hooks.respond(self.event("PreToolUse"), protect=True)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_missing_record_is_denied_only_for_explicit_protection(self):
        self.state.unlink()
        self.assertEqual(hooks.respond(self.event("PreToolUse")), {})
        result = hooks.respond(self.event("PreToolUse"), protect=True)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_manual_verification_only_advises(self):
        self.meta["verification"]["checks"] = []
        self.meta["verification"]["inputs"] = []
        self.save()
        result = hooks.respond(self.event("Stop"), check_on_stop=True)
        self.assertNotIn("decision", result)
        self.assertIn("systemMessage", result)

    def test_malformed_record_and_cwd_do_not_claim_success(self):
        self.state.write_text('---\n{"workflow":"dev_co",}\n---\n', encoding="utf-8")
        self.assertIn("systemMessage", hooks.respond(self.event("Stop"), check_on_stop=True))
        result = hooks.respond(self.event("PreToolUse"), protect=True)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        result = hooks.respond({"hook_event_name": "PreToolUse"}, protect=True)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_generated_configs_execute_for_each_host(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                config = hooks.config(host, None, [])
                self.assertNotIn("PreToolUse", config["hooks"])
                command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                result = subprocess.run(shlex.split(command), input=json.dumps(self.event("SessionStart")),
                                        capture_output=True, encoding="utf-8", timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("验证局部行为", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_protect_tool_matcher_uses_exact_escaped_names(self):
        chosen = "publisher.send|release"
        config = hooks.config("claude", "docs/CURRENT.md", [chosen])
        matcher = config["hooks"]["PreToolUse"][0]["matcher"]
        self.assertIsNotNone(re.fullmatch(matcher, chosen))
        for name in ("publisherXsend", "release", "prefix" + chosen, "Bash"):
            self.assertIsNone(re.fullmatch(matcher, name))

    def test_invalid_json_protected_cli_returns_blocking_error(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "workflow_hooks.py"), "--host", "codex", "--protect"],
                                input="not json", capture_output=True, encoding="utf-8", timeout=5)
        self.assertEqual(result.returncode, 2)

    def test_unexpected_protected_cli_error_returns_blocking_status(self):
        argv = ["workflow_hooks.py", "--host", "codex", "--protect"]
        payload = io.StringIO(json.dumps(self.event("PreToolUse")))
        with (patch.object(workflow, "gate", side_effect=RuntimeError("synthetic read failure")),
              patch.object(sys, "argv", argv), patch.object(sys, "stdin", payload),
              patch.object(sys, "stderr", io.StringIO()) as stderr):
            self.assertEqual(hooks.main(), 2)
        self.assertIn("synthetic read failure", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
