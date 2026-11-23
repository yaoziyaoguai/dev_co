"""大型项目审计中已复现的范围、输入和验证顺序回归。"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_workflow import ProjectFixture
import project_workflow as workflow
import workflow_hooks as hooks
import repository_check as repository


class InputCoverageTests(ProjectFixture):
    def test_unregistered_nested_git_worktree_is_reported_and_can_be_excluded(self):
        nested = self.root / "src/nested_repo"
        for root in (self.root, nested):
            subprocess.run(["git", "init", "-q", str(root)], check=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "未注册为子模块.*src/nested_repo"):
            self.verify()
        with self.assertRaisesRegex(workflow.WorkflowError, "未注册为子模块.*src/nested_repo"):
            repository.fingerprints(self.root, ["src/nested_repo"])
        self.meta["verification"]["exclude"] = ["src/nested_repo/"]
        self.save()
        self.assertTrue(self.verify()["ready"])

    def test_gitlink_with_uninitialized_and_clean_checkout(self):
        module = self.base / "module"
        module.mkdir()

        def git(root, *argv):
            return subprocess.check_output(["git", "-C", str(root), "-c", "user.name=Fixture",
                                            "-c", "user.email=fixture@example.test",
                                            "-c", "core.hooksPath=/dev/null", *argv], encoding="utf-8").strip()

        git(module, "init", "-q")
        (module / "data.txt").write_text("first", encoding="utf-8")
        git(module, "add", "data.txt")
        git(module, "commit", "-qm", "First snapshot")
        commit = git(module, "rev-parse", "HEAD")
        git(self.root, "init", "-q")
        vendor = self.root / "vendor"
        vendor.mkdir()
        git(self.root, "update-index", "--add", "--cacheinfo", "160000," + commit + ",vendor")
        policy = {"schema": 1, "paths": {"vendor": "依赖"}, "updates": [
            {"id": "vendor", "inputs": ["vendor"], "documents": ["docs/dependency.md"]},
        ]}
        (self.root / "docs/dependency.md").write_text("依赖记录", encoding="utf-8")
        (self.root / repository.POLICY).write_text(json.dumps(policy), encoding="utf-8")
        repository.adopt(self.root, scope="submodule")
        self.assertTrue(repository.check(self.root, scope="submodule")["ready"])
        self.meta["verification"]["inputs"].append("vendor")
        self.save()
        self.assertTrue(self.verify()["ready"])

        vendor.rmdir()
        module.rename(vendor)
        self.assertFalse(self.gate()["ready"])
        self.assertFalse(repository.check(self.root, scope="submodule")["ready"])
        self.assertTrue(self.verify()["ready"])
        (vendor / "data.txt").write_text("dirty", encoding="utf-8")
        self.assertIn("子模块有未提交的变化", self.cli("gate").stderr)
        with self.assertRaisesRegex(workflow.WorkflowError, "子模块有未提交的变化"):
            repository.check(self.root, scope="submodule")

    def test_explicit_symlink_requires_its_inside_target(self):
        link = self.root / "src/linked.py"
        link.symlink_to("logic.py")
        self.meta["verification"]["inputs"] = ["src/linked.py", "check.py"]
        self.save()
        with self.assertRaisesRegex(workflow.WorkflowError, "链接目标未进入实际验证输入"):
            self.verify()
        self.meta["verification"]["inputs"].append("src/logic.py")
        self.save()
        self.assertTrue(self.verify()["ready"])

    def test_executable_bit_invalidates_success(self):
        entry = self.root / "check.sh"
        entry.write_text("#!/bin/sh\n[ -s src/logic.py ]\n", encoding="utf-8")
        entry.chmod(0o755)
        self.meta["verification"]["inputs"].append("check.sh")
        try:
            subprocess.run([str(entry)], cwd=self.root, capture_output=True, check=True, timeout=5)
            argv = ["./check.sh"]
        except PermissionError:
            argv = [sys.executable, "-c", "from pathlib import Path; import sys; "
                    "sys.exit(0 if (Path('check.sh').stat().st_mode & 0o111) "
                    "and Path('src/logic.py').stat().st_size > 0 else 1)"]
        self.meta["verification"]["checks"][0]["argv"] = argv
        self.save()
        self.assertTrue(self.verify()["ready"])
        entry.chmod(0o644)
        self.assertFalse(self.gate()["ready"])
        self.assertFalse(workflow.verify(self.root, self.state, reuse=True)["ready"])
        entry.chmod(0o755)
        self.assertTrue(self.verify()["ready"])

    def test_execution_permission_error_mentions_mount_and_interpreter(self):
        entry = self.root / "check.sh"
        entry.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        entry.chmod(0o755)
        log = self.root / "check.log"
        with patch.object(workflow.subprocess, "Popen", side_effect=PermissionError(13, "Permission denied")):
            self.assertEqual(workflow.execute_check(["./check.sh"], self.root, log, 5), (127, False))
        text = log.read_text(encoding="utf-8")
        self.assertIn("Permission denied", text)
        self.assertIn("noexec", text)
        self.assertIn("shebang", text)

    def test_parent_and_partial_directory_links_require_full_target_coverage(self):
        other = self.root / "other"
        other.mkdir()
        (other / "hidden_dep.py").write_text("x = 1\n", encoding="utf-8")
        up = self.root / "src/up"
        up.symlink_to("..", target_is_directory=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "链接目标未进入实际验证输入.*src/up"):
            self.verify()
        up.unlink()

        shared = self.root / "shared"
        shared.mkdir()
        (shared / "a.txt").write_text("1", encoding="utf-8")
        (shared / "b.txt").write_text("2", encoding="utf-8")
        (self.root / "src/shared").symlink_to(shared, target_is_directory=True)
        self.meta["verification"]["inputs"].append("shared/a.txt")
        self.save()
        with self.assertRaisesRegex(workflow.WorkflowError, "链接目标未进入实际验证输入.*src/shared"):
            self.verify()
        self.meta["verification"]["inputs"].append("shared/b.txt")
        self.save()
        self.assertTrue(self.verify()["ready"])

    def test_broken_git_metadata_fails_closed_without_non_git_fallback(self):
        (self.root / ".git").write_text("gitdir: /nonexistent/devco-gitdir\n", encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "拒绝降级为无 Git 模式"):
            workflow.snapshot(self.root, ["src"], self.state)
        with self.assertRaisesRegex(workflow.WorkflowError, "拒绝降级为无 Git 模式"):
            repository.git_origin(self.root)
        with self.assertRaisesRegex(workflow.WorkflowError, "拒绝降级为无 Git 模式"):
            workflow.identity(self.root)

    def test_git_timeout_is_reported_in_identity_and_surfaced_in_brief(self):
        timeout_err = subprocess.TimeoutExpired(["git", "status"], 10)
        with patch("workflow_files.subprocess.run", side_effect=timeout_err):
            with self.assertRaisesRegex(workflow.WorkflowError, "超时"):
                workflow.identity(self.root)
        with patch.object(workflow, "identity", return_value={"root": str(self.root), "head": "abc", "branch": "main"}):
            with patch("project_workflow.git_value", side_effect=workflow.WorkflowError("Git 查询超时（status）")):
                summary = workflow.brief(self.root, self.state, compact=True)
        self.assertIn("工作树状态未能完成核对", summary)

    def test_directory_link_requires_actual_target_coverage(self):
        shared = self.root / "shared"
        shared.mkdir()
        (shared / "value.txt").write_text("1", encoding="utf-8")
        (self.root / "src/shared").symlink_to(shared, target_is_directory=True)
        (self.root / "check.py").write_text(
            "from pathlib import Path\nassert Path('src/shared/value.txt').read_text() == '1'\n"
        , encoding="utf-8")
        with self.assertRaises(workflow.WorkflowError):
            self.verify()
        self.meta["verification"]["inputs"].append("shared")
        self.save()
        self.assertTrue(self.verify()["ready"])
        (shared / "value.txt").write_text("2", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])
        self.assertFalse(workflow.verify(self.root, self.state, reuse=True)["ready"])

    def test_ignored_build_output_does_not_dirty_success(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("src/build/\n", encoding="utf-8")
        with (self.root / "check.py").open("a", encoding="utf-8") as stream:
            stream.write("p = Path('src/build/output.txt')\np.parent.mkdir(exist_ok=True)\np.write_text('generated')\n")
        self.assertTrue(self.verify()["ready"])
        (self.root / "src/build/output.txt").write_text("a different build output", encoding="utf-8")
        self.assertTrue(workflow.verify(self.root, self.state, reuse=True)["reused"])
        (self.root / "src/new.py").write_text("new_source = True\n", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])

    def test_tracked_generated_file_is_still_an_input(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("src/__pycache__/\n", encoding="utf-8")
        generated = self.root / "src/__pycache__/required.txt"
        generated.parent.mkdir()
        generated.write_text("generated but versioned", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-f", str(generated)], check=True)
        self.assertTrue(self.verify()["ready"])
        generated.write_text("changed versioned input", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])
        self.assertTrue(self.verify()["ready"])
        generated.unlink()
        self.assertFalse(self.gate()["ready"])

    def test_selected_broken_or_external_link_fails(self):
        outside = self.base / "external.txt"
        outside.write_text("outside project", encoding="utf-8")
        link = self.root / "src/link"
        for target in (outside, self.root / "missing"):
            with self.subTest(target=target):
                link.symlink_to(target)
                with self.assertRaises(workflow.WorkflowError):
                    self.verify()
                link.unlink()

    def test_indexed_file_cannot_read_through_replaced_parent_link(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        nested = self.root / "src/nested"
        nested.mkdir()
        (nested / "value.txt").write_text("inside", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "src"], check=True)
        (nested / "value.txt").unlink()
        nested.rmdir()
        outside = self.base / "external"
        outside.mkdir()
        (outside / "value.txt").write_text("synthetic outside value", encoding="utf-8")
        nested.symlink_to(outside, target_is_directory=True)
        (self.root / ".gitignore").write_text("src/nested\n", encoding="utf-8")
        with patch.object(workflow, "file_hash", wraps=workflow.file_hash) as hashing:
            with self.assertRaises(workflow.WorkflowError):
                workflow.snapshot(self.root, ["src"], self.state)
        self.assertTrue(all(call.args[0].resolve().is_relative_to(self.root)
                            for call in hashing.call_args_list))

    def test_ignored_link_target_requires_explicit_real_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("generated/\nsrc/build/\n", encoding="utf-8")
        target = self.root / "generated/shared"
        target.mkdir(parents=True)
        (target / "value.txt").write_text("1", encoding="utf-8")
        (self.root / "src/shared").symlink_to(target, target_is_directory=True)
        self.meta["verification"]["inputs"].append("generated/shared")
        self.save()
        with self.assertRaises(workflow.WorkflowError):
            self.verify()
        self.meta["verification"]["inputs"].append("generated/shared/value.txt")
        self.save()
        self.assertTrue(self.verify()["ready"])
        build = self.root / "src/build"
        build.mkdir()
        (build / "unrelated-link").symlink_to(self.base / "missing")
        self.assertTrue(self.gate()["ready"])
        (target / "value.txt").write_text("2", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])

    def test_non_git_exclude_and_explicit_cache_file(self):
        cache = self.root / "src/__pycache__"
        cache.mkdir()
        (cache / "required.txt").write_text("required input", encoding="utf-8")
        output = self.root / "src/build"
        output.mkdir()
        (output / "ignored-link").symlink_to(self.base / "outside")
        self.meta["verification"]["exclude"] = ["src/build/", "src/__pycache__/"]
        self.meta["verification"]["inputs"].append("src/__pycache__/required.txt")
        self.save()
        self.assertTrue(self.verify()["ready"])
        (cache / "required.txt").write_text("changed input", encoding="utf-8")
        self.assertFalse(self.gate()["ready"])

    def test_custom_progress_sections_and_configuration_change(self):
        self.body = "# Current\n## Goal\nKeep behavior.\n## Next steps\nRun checks.\n"
        self.meta["non_intent_sections"] = ["Next steps"]
        self.save()
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("Run checks.", "Checks passed.")
        self.save()
        self.assertTrue(self.gate()["ready"])
        self.body = self.body.replace("Keep behavior.", "New accepted behavior.")
        self.save()
        self.assertFalse(self.gate()["ready"])
        self.assertTrue(self.verify()["ready"])
        self.meta["non_intent_sections"] = []
        self.save()
        self.assertFalse(self.gate()["ready"])
        self.assertTrue(self.verify()["ready"])
        self.body = self.body.replace("Checks passed.", "Next action.")
        self.save()
        self.assertFalse(self.gate()["ready"])
        self.meta["non_intent_sections"] = "Next steps"
        self.save()
        with self.assertRaises(workflow.WorkflowError):
            self.verify()


class HookScopeTests(ProjectFixture):
    def test_fixed_root_rejects_other_project_and_accepts_child(self):
        self.assertTrue(self.verify()["ready"])
        other = self.base / "different-project"
        other.mkdir()
        event = {"hook_event_name": "SessionStart", "cwd": str(other)}
        self.assertEqual(hooks.respond(event, root=self.root), {})
        self.assertEqual(hooks.respond({**event, "hook_event_name": "Stop"}, root=self.root, check_on_stop=True), {})
        event["hook_event_name"] = "PreToolUse"
        response = hooks.respond(event, root=self.root, protect=True)
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        event["cwd"] = str(self.root / "src")
        self.assertEqual(hooks.respond(event, root=self.root, protect=True), {})


class BaselineScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="devco-scope-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "src/value.txt").write_text("1", encoding="utf-8")
        (self.root / "docs/api.md").write_text("API unchanged", encoding="utf-8")
        (self.root / "docs/other.md").write_text("Existing document", encoding="utf-8")
        (self.root / "README.md").write_text("Existing usage", encoding="utf-8")
        (self.root / ".gitignore").write_text(".project-workflow/\n", encoding="utf-8")
        self.policy = {"schema": 1, "paths": {"src/": "source", "docs/": "docs", "README.md": "usage"},
                       "updates": [{"id": "api", "inputs": ["src/"], "documents": ["docs/api.md"]}]}
        self.save_policy()
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial fixture")
        repository.adopt(self.root, scope="A")

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=dev_co test", "-c", "user.email=devco@example.invalid",
                               "-c", "core.hooksPath=/dev/null", "-C", str(self.root), *args],
                              check=True, capture_output=True, encoding="utf-8", timeout=10)

    def save_policy(self):
        (self.root / repository.POLICY).write_text(json.dumps(self.policy), encoding="utf-8")

    def test_scope_and_branch_mismatch_but_normal_commit_is_allowed(self):
        original = (self.root / repository.BASELINE).read_bytes()
        with self.assertRaises(workflow.WorkflowError):
            repository.check(self.root, scope="B")
        self.git("checkout", "-qb", "different")
        with self.assertRaises(workflow.WorkflowError):
            repository.check(self.root, scope="A")
        self.git("checkout", "-q", "main")
        (self.root / "README.md").write_text("Updated usage", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "Continue same scope")
        self.assertTrue(repository.check(self.root, scope="A")["ready"])
        self.assertEqual((self.root / repository.BASELINE).read_bytes(), original)
        repository.checkpoint(self.root, scope="A")
        self.git("reset", "--hard", "HEAD~1")
        with self.assertRaises(workflow.WorkflowError):
            repository.check(self.root, scope="A")

    def test_rule_relationship_change_requires_review_without_input_change(self):
        self.policy["updates"][0]["documents"].append("docs/other.md")
        self.save_policy()
        self.assertFalse(repository.check(self.root, scope="A")["ready"])
        repository.review(self.root, repository.POLICY, "api", "Existing API document covers this scope.", scope="A")
        self.assertTrue(repository.check(self.root, scope="A")["ready"])

    def test_unrelated_policy_description_does_not_create_document_obligation(self):
        self.policy["paths"]["src/"] = "A clearer description of the same source directory"
        self.save_policy()
        result = repository.check(self.root, scope="A")
        self.assertTrue(result["ready"])
        self.assertTrue(result["policy_changed"])

    def test_review_cannot_transfer_to_another_scope(self):
        source = self.root / "src/value.txt"
        source.write_text("2", encoding="utf-8")
        repository.review(self.root, repository.POLICY, "api", "Internal marker; API is unchanged.", scope="A")
        old_review = (self.root / repository.REVIEWS).read_bytes()
        self.assertTrue(repository.checkpoint(self.root, scope="A")["ready"])
        archive = self.root / ".project-workflow/archive/A"
        archive.mkdir(parents=True)
        (self.root / repository.BASELINE).rename(archive / "baseline.json")
        (self.root / repository.REVIEWS).rename(archive / "reviews.json")
        source.write_text("1", encoding="utf-8")
        repository.adopt(self.root, scope="B")
        source.write_text("2", encoding="utf-8")
        (self.root / repository.REVIEWS).write_bytes(old_review)
        self.assertFalse(repository.check(self.root, scope="B")["ready"])
        self.assertTrue((archive / "baseline.json").is_file())

    def test_review_binds_the_baseline_difference_in_same_scope(self):
        source = self.root / "src/value.txt"
        source.write_text("2", encoding="utf-8")
        repository.review(self.root, repository.POLICY, "api", "Internal marker only.", scope="A")
        old_review = (self.root / repository.REVIEWS).read_bytes()
        repository.checkpoint(self.root, scope="A")
        source.write_text("3", encoding="utf-8")
        repository.review(self.root, repository.POLICY, "api", "Another internal marker change.", scope="A")
        repository.checkpoint(self.root, scope="A")
        source.write_text("2", encoding="utf-8")
        (self.root / repository.REVIEWS).write_bytes(old_review)
        self.assertFalse(repository.check(self.root, scope="A")["ready"])

    def test_schema_one_and_missing_scope_fail_without_rewriting(self):
        with self.assertRaises(workflow.WorkflowError):
            repository.check(self.root)
        path = self.root / repository.BASELINE
        value = json.loads(path.read_text(encoding="utf-8"))
        value["schema"] = 1
        path.write_text(json.dumps(value), encoding="utf-8")
        original = path.read_bytes()
        with self.assertRaises(workflow.WorkflowError):
            repository.check(self.root, scope="A")
        self.assertEqual(path.read_bytes(), original)


class VerificationOrderTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        (self.root / "docs/api.md").write_text("Version 1", encoding="utf-8")
        policy = {"schema": 1, "paths": {"src/": "source", "docs/": "docs"},
                  "updates": [{"id": "api", "inputs": ["src/"], "documents": ["docs/api.md"]}]}
        (self.root / repository.POLICY).write_text(json.dumps(policy), encoding="utf-8")
        repository.adopt(self.root, scope="work")
        self.meta["verification"].update(repository_policy=repository.POLICY, repository_scope="work")
        self.save()
        self.count = self.root / ".project-workflow/count.txt"

    def write_counted_check(self):
        (self.root / "check.py").write_text(
            "from pathlib import Path\n"
            "p = Path('.project-workflow/count.txt')\n"
            "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\n"
            "assert Path('src/logic.py').read_text() == 'value = 2\\n'\n"
        , encoding="utf-8")

    def test_functional_evidence_survives_pending_and_completed_documentation(self):
        self.write_counted_check()
        (self.root / "src/logic.py").write_text("value = 2\n", encoding="utf-8")
        pending = workflow.verify(self.root, self.state, reuse=True)
        self.assertTrue(pending["verification_ready"])
        self.assertFalse(pending["ready"])
        self.assertEqual(self.count.read_text(encoding="utf-8"), "1")
        (self.root / "docs/api.md").write_text("Version 2", encoding="utf-8")
        completed = workflow.verify(self.root, self.state, reuse=True)
        self.assertTrue(completed["ready"])
        self.assertTrue(completed["reused"])
        self.assertEqual(self.count.read_text(encoding="utf-8"), "1")
        repository.checkpoint(self.root, scope="work")
        (self.root / "src/logic.py").write_text("value = 3\n", encoding="utf-8")
        failed = workflow.verify(self.root, self.state, reuse=True)
        self.assertFalse(failed["ready"])
        self.assertFalse(failed["verification_ready"])
        self.assertTrue(any("检查未通过" in reason for reason in failed["reasons"]))
        self.assertTrue(any("更新义务" in reason for reason in failed["reasons"]))
        self.assertEqual(self.count.read_text(encoding="utf-8"), "2")
        self.assertEqual(hooks.respond(self.event("PreToolUse"), protect=True)
                         ["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_scope_mismatch_never_starts_checks(self):
        self.write_counted_check()
        self.meta["verification"]["repository_scope"] = "wrong-scope"
        self.save()
        for reuse in (False, True):
            with self.assertRaises(workflow.WorkflowError):
                workflow.verify(self.root, self.state, reuse=reuse)
        self.assertFalse(self.count.exists())


if __name__ == "__main__":
    unittest.main()
