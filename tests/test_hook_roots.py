"""Project-root consistency between the verification CLI and lifecycle hooks."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_workflow as workflow
import repository_check as repository
import workflow_hooks as hooks


class HookRootTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hook-roots-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / "repository"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.project = self.repo / "packages/app with spaces"
        self.project.mkdir(parents=True)
        self.top_state = self.initialize(self.repo, "顶层项目目标")
        self.state = self.initialize(self.project, "子项目目标")

    def initialize(self, root, goal):
        (root / "source.txt").write_text(goal, encoding="utf-8")
        (root / "check.py").write_text(
            "from pathlib import Path\n"
            + "assert Path('source.txt').read_text(encoding='utf-8') == " + repr(goal) + "\n"
        , encoding="utf-8")
        state = workflow.initialize(root, "docs/CURRENT.md", goal)
        meta, body = workflow.load_state(state)
        meta["phase"] = "build"
        meta["verification"] = {
            "level": "targeted", "reason": "核对当前子项目输入。",
            "inputs": ["source.txt", "check.py"],
            "checks": [{"id": "local", "argv": [sys.executable, "check.py"],
                        "cost": "local", "timeout_seconds": 5}],
        }
        state.write_text("---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n" + body, encoding="utf-8")
        return state

    def event(self, event):
        return {"hook_event_name": event, "cwd": str(self.project)}

    def hook_cli(self, *args, cwd=None, payload=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "workflow_hooks.py"), "--host", "codex", *args],
            cwd=cwd or self.base, input=json.dumps(payload) if payload else None,
            capture_output=True, encoding="utf-8", timeout=30,
        )

    def assert_denied(self, result):
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_explicit_root_selects_subproject_record(self):
        result = hooks.respond(self.event("SessionStart"), root=self.project)
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("子项目目标", context)
        self.assertNotIn("顶层项目目标", context)
        self.assertIn("项目：" + str(self.project), context)

    def test_compact_brief_keeps_relative_subproject_changes(self):
        subprocess.run(["git", "-C", str(self.repo), "config", "status.relativePaths", "false"], check=True)
        subprocess.run(["git", "-C", str(self.project), "add", "--", "source.txt"], check=True)
        for index in range(30):
            (self.repo / f"aaa-unrelated-{index:02}.txt").touch()
        (self.project / "only-local-change.py").touch()
        summary = workflow.brief(self.project, self.state, compact=True)
        self.assertIn("?? only-local-change.py", summary)
        self.assertNotIn("aaa-unrelated", summary)
        context = hooks.respond(self.event("SessionStart"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("?? only-local-change.py", context)
        self.assertNotIn("aaa-unrelated", context)

    def test_default_discovers_nearest_state_and_falls_back_to_top_level(self):
        result = hooks.respond(self.event("SessionStart"))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("子项目目标", context)
        self.state.unlink()
        result = hooks.respond(self.event("SessionStart"))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("顶层项目目标", context)
        self.assertNotIn("子项目目标", context)
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                config = hooks.config(host, None, [])
                command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                self.assertNotIn("--root", shlex.split(command))

    def test_symlinked_docs_and_baseline_do_not_block_implicit_discovery(self):
        self.state.unlink()
        (self.project / "docs").rmdir()
        (self.project / "docs").symlink_to(self.repo / "docs", target_is_directory=True)
        (self.project / ".project-workflow").symlink_to(self.base, target_is_directory=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / "project_workflow.py"), "brief"], cwd=self.project,
                                capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("项目：" + str(self.repo) + "\n", result.stdout)
        context = hooks.respond(self.event("SessionStart"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("顶层项目目标", context)
        self.assert_denied(hooks.respond(self.event("PreToolUse"), "docs/CURRENT.md", True, self.project))
        self.top_state.unlink()
        self.assertEqual(hooks.respond(self.event("SessionStart")), {})

    def test_subproject_with_local_policy_is_not_hijacked_by_parent_state(self):
        self.state.unlink()
        nested = self.project / "src"
        nested.mkdir()
        (self.project / repository.POLICY).write_text(json.dumps({"schema": 1, "paths": {"src/": "source"}}),
                                                     encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPTS / "repository_check.py"), "check", "--scope", "work"],
                                cwd=nested, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(str(self.project / repository.BASELINE), json.loads(result.stderr)["error"])

    def test_cli_reports_current_root_when_invoked_below_project(self):
        self.state.unlink()
        self.top_state.unlink()
        nested = self.project / "nested"
        nested.mkdir()
        for script, argv in (("project_workflow.py", ["brief"]),
                             ("repository_check.py", ["check", "--scope", "work"])):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, str(SCRIPTS / script), *argv], cwd=nested,
                                        capture_output=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 2, result.stderr)
                error = json.loads(result.stderr)["error"]
                self.assertIn(str(nested), error)
                self.assertIn("--root", error)

    def test_cli_defaults_allow_subproject_initialization_and_baseline(self):
        self.state.unlink()
        (self.project / repository.POLICY).write_text(json.dumps({"schema": 1, "paths": {"docs/": "状态"}}),
                                                     encoding="utf-8")
        for script, argv in (("project_workflow.py", ["init", "--goal", "Local project"]),
                             ("project_workflow.py", ["brief"]),
                             ("repository_check.py", ["adopt", "--scope", "work"]),
                             ("repository_check.py", ["check", "--scope", "work"])):
            result = subprocess.run([sys.executable, str(SCRIPTS / script), *argv], cwd=self.project,
                                    capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            if argv[0] == "brief":
                self.assertIn("Local project", result.stdout)
                self.assertNotIn("顶层项目目标", result.stdout)
        self.assertTrue(self.state.is_file())
        self.assertTrue((self.project / repository.BASELINE).is_file())
        self.assertFalse((self.repo / repository.BASELINE).exists())

    def test_generated_commands_pin_relative_root_for_both_hosts(self):
        self.assertTrue(workflow.verify(self.project, self.state)["ready"])
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                generated = subprocess.run(
                    [sys.executable, str(SCRIPTS / "workflow_hooks.py"), "--host", host,
                     "--root", "packages/app with spaces", "--state", "docs/CURRENT.md",
                     "--protect-tool", "publisher.send", "--print-config"],
                    cwd=self.repo, capture_output=True, encoding="utf-8", timeout=30,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                config = json.loads(generated.stdout)
                for event, groups in config["hooks"].items():
                    command = shlex.split(groups[0]["hooks"][0]["command"])
                    self.assertEqual(command[command.index("--root") + 1], str(self.project))
                    result = subprocess.run(
                        command, cwd=self.base, input=json.dumps(self.event(event)),
                        capture_output=True, encoding="utf-8", timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout)
                    if event == "SessionStart":
                        context = output["hookSpecificOutput"]["additionalContext"]
                        self.assertIn("子项目目标", context)
                        self.assertNotIn("顶层项目目标", context)
                    else:
                        self.assertEqual(output, {})

    def test_cli_and_hook_share_input_and_evidence_root(self):
        verified = subprocess.run(
            [sys.executable, str(SCRIPTS / "project_workflow.py"), "verify",
             "--root", str(self.project)],
            cwd=self.base, capture_output=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertTrue(json.loads(verified.stdout)["ready"])
        self.assertTrue((self.project / ".project-workflow/evidence/latest.json").is_file())
        self.assertFalse((self.repo / ".project-workflow").exists())
        report = workflow.read_evidence(self.project)
        self.assertEqual(report["identity"]["root"], str(self.project))
        self.assertEqual(set(report["coverage"]), {"source.txt", "check.py"})
        event = self.event("PreToolUse")
        self.assertEqual(hooks.respond(event, protect=True, root=self.project), {})
        self.assertEqual(hooks.respond(event, protect=True), {})
        self.assert_denied(hooks.respond(event, protect=True, root=self.repo))
        (self.repo / "source.txt").write_text("顶层改动", encoding="utf-8")
        self.assertEqual(hooks.respond(event, protect=True, root=self.project), {})
        (self.project / "source.txt").write_text("子项目改动", encoding="utf-8")
        self.assert_denied(hooks.respond(event, protect=True, root=self.project))
        self.assertIn("systemMessage", hooks.respond(self.event("Stop"), root=self.project, check_on_stop=True))
        self.assertEqual(hooks.respond(self.event("Stop"), root=self.project), {})

    def test_read_and_verify_commands_find_the_nearest_initialized_root(self):
        nested = self.project / "nested"
        nested.mkdir()
        for root in (self.repo, self.project):
            (root / repository.POLICY).write_text(json.dumps({"schema": 1, "paths": {"docs/": "状态"}}),
                                                  encoding="utf-8")
        for root in (self.repo, self.project):
            repository.adopt(root, scope=root.name)
        for root, marker in ((self.project, "子项目目标"), (self.repo, "顶层项目目标")):
            with self.subTest(root=root):
                for argv in (("project_workflow.py", "brief"), ("project_workflow.py", "verify"),
                             ("project_workflow.py", "gate"), ("repository_check.py", "check", "--scope", root.name)):
                    result = subprocess.run([sys.executable, str(SCRIPTS / argv[0]), *argv[1:]], cwd=nested,
                                            capture_output=True, encoding="utf-8", timeout=30)
                    self.assertEqual(result.returncode, 0, f"{argv}\n{result.stdout}\n{result.stderr}")
                    if argv[1] == "brief":
                        self.assertIn(marker, result.stdout)
                if root == self.project:
                    self.state.unlink()
                    (self.project / repository.BASELINE).unlink()
                    (self.project / repository.POLICY).unlink()

    def test_default_root_keeps_the_boundary_of_a_partially_configured_subproject(self):
        policy = json.dumps({"schema": 1, "paths": {"docs/": "状态"}})
        (self.repo / repository.POLICY).write_text(policy, encoding="utf-8")
        repository.adopt(self.repo, scope="work")
        result = subprocess.run([sys.executable, str(SCRIPTS / "repository_check.py"), "check", "--scope", "work"],
                                cwd=self.project, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(str(self.project), json.loads(result.stderr)["error"])

        self.state.unlink()
        (self.project / repository.POLICY).write_text(policy, encoding="utf-8")
        repository.adopt(self.project, scope="work")
        self.assertEqual(hooks.respond(self.event("SessionStart")), {})

    def test_explicit_root_does_not_fall_back_to_parent_record(self):
        self.state.unlink()
        self.assertEqual(hooks.respond(self.event("SessionStart"), root=self.project), {})
        self.assert_denied(hooks.respond(self.event("PreToolUse"), protect=True, root=self.project))

    def test_invalid_explicit_roots_are_reported_and_protected(self):
        for root in (self.base / "missing", self.project / "source.txt"):
            with self.subTest(root=root):
                result = hooks.respond(self.event("SessionStart"), root=root)
                self.assertIn("项目目录不存在或不是目录", result["systemMessage"])
                self.assert_denied(hooks.respond(self.event("PreToolUse"), protect=True, root=root))
                generated = self.hook_cli("--root", str(root), "--print-config")
                self.assertNotEqual(generated.returncode, 0)
                self.assertEqual(generated.stdout, "")
                self.assertIn("项目目录不存在或不是目录", generated.stderr)

    def test_relative_root_matches_cli_process_working_directory(self):
        result = self.hook_cli("--root", "packages/app with spaces", cwd=self.repo,
                               payload=self.event("SessionStart"))
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("子项目目标", context)
        self.assertNotIn("顶层项目目标", context)

    def test_explicit_root_keeps_state_and_input_path_boundaries(self):
        event = self.event("PreToolUse")
        self.assert_denied(hooks.respond(event, "../../docs/CURRENT.md", True, self.project))
        self.assertTrue(workflow.verify(self.project, self.state)["ready"])
        meta, body = workflow.load_state(self.state)
        meta["verification"]["inputs"] = ["../../source.txt"]
        self.state.write_text("---\n" + json.dumps(meta) + "\n---\n" + body, encoding="utf-8")
        result = hooks.respond(event, protect=True, root=self.project)
        self.assert_denied(result)
        self.assertIn("路径必须位于项目内", result["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
