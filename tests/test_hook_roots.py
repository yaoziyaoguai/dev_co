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
        (root / "source.txt").write_text(goal)
        (root / "check.py").write_text(
            "from pathlib import Path\n"
            + "assert Path('source.txt').read_text() == " + repr(goal) + "\n"
        )
        state = workflow.initialize(root, "docs/CURRENT.md", goal)
        meta, body = workflow.load_state(state)
        meta["phase"] = "build"
        meta["verification"] = {
            "level": "targeted", "reason": "核对当前子项目输入。",
            "inputs": ["source.txt", "check.py"],
            "checks": [{"id": "local", "argv": [sys.executable, "check.py"],
                        "cost": "local", "timeout_seconds": 5}],
        }
        state.write_text("---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n" + body)
        return state

    def event(self, event):
        return {"hook_event_name": event, "cwd": str(self.project)}

    def hook_cli(self, *args, cwd=None, payload=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "workflow_hooks.py"), "--host", "codex", *args],
            cwd=cwd or self.base, input=json.dumps(payload) if payload else None,
            capture_output=True, text=True, timeout=10,
        )

    def assert_denied(self, result):
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_explicit_root_selects_subproject_record(self):
        result = hooks.respond(self.event("SessionStart"), root=self.project)
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("子项目目标", context)
        self.assertNotIn("顶层项目目标", context)
        self.assertIn("项目：" + str(self.project), context)

    def test_default_keeps_git_top_level_discovery(self):
        result = hooks.respond(self.event("SessionStart"))
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("顶层项目目标", context)
        self.assertNotIn("子项目目标", context)
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                config = hooks.config(host, None, [])
                command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                self.assertNotIn("--root", shlex.split(command))

    def test_generated_commands_pin_relative_root_for_both_hosts(self):
        self.assertTrue(workflow.verify(self.project, self.state)["ready"])
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                generated = subprocess.run(
                    [sys.executable, str(SCRIPTS / "workflow_hooks.py"), "--host", host,
                     "--root", "packages/app with spaces", "--state", "docs/CURRENT.md",
                     "--protect-tool", "publisher.send", "--print-config"],
                    cwd=self.repo, capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                config = json.loads(generated.stdout)
                for event, groups in config["hooks"].items():
                    command = shlex.split(groups[0]["hooks"][0]["command"])
                    self.assertEqual(command[command.index("--root") + 1], str(self.project))
                    result = subprocess.run(
                        command, cwd=self.base, input=json.dumps(self.event(event)),
                        capture_output=True, text=True, timeout=10,
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
            cwd=self.base, capture_output=True, text=True, timeout=10,
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
        self.assert_denied(hooks.respond(event, protect=True))
        (self.repo / "source.txt").write_text("顶层改动")
        self.assertEqual(hooks.respond(event, protect=True, root=self.project), {})
        (self.project / "source.txt").write_text("子项目改动")
        self.assert_denied(hooks.respond(event, protect=True, root=self.project))
        self.assertEqual(hooks.respond(self.event("Stop"), root=self.project)["decision"], "block")

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
        self.state.write_text("---\n" + json.dumps(meta) + "\n---\n" + body)
        result = hooks.respond(event, protect=True, root=self.project)
        self.assert_denied(result)
        self.assertIn("路径必须位于项目内", result["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
