"""仓库生命周期的可观察行为；所有样本隔离，不接触真实项目。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import repository_check as repository
import project_workflow as workflow


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="devco-repository-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.policy = {
            "schema": 1,
            "paths": {"src/": "产品实现", "tests/": "验证行为", "docs/": "任务资料", "README.md": "使用入口"},
            "required": ["README.md", "docs/current.md"],
            "links": ["README.md", "docs/current.md"],
            "updates": [{"id": "usage", "inputs": ["src/"], "documents": ["README.md"]}],
        }
        self.write(repository.POLICY, json.dumps(self.policy))
        self.write("src/main.py", "print('first release')\n")
        self.write("README.md", "# Run\npython src/main.py\n")
        self.write("docs/current.md", "# Current\n[Run](../README.md)\n")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def adopt(self):
        self.write(repository.POLICY, json.dumps(self.policy))
        return repository.adopt(self.root, scope="work")

    def check(self):
        return repository.check(self.root, scope="work")

    def test_new_repository_from_empty_to_first_increment(self):
        for name in ("src/main.py", "README.md", "docs/current.md"):
            (self.root / name).unlink()
        self.adopt()
        self.assertFalse(self.check()["ready"])
        self.write("src/main.py", "print('first release')\n")
        self.write("README.md", "Run python src/main.py")
        self.write("docs/current.md", "[Run](../README.md)")
        result = self.check()
        self.assertTrue(result["ready"], result)
        self.assertEqual(set(result["added"]), {"src/main.py", "README.md", "docs/current.md"})
        self.assertTrue(repository.checkpoint(self.root, scope="work")["ready"])
        self.assertEqual(self.check()["added"], [])

    def test_legacy_layout_and_existing_broken_links_are_not_retrofitted(self):
        self.write("old-misc/notes.txt", "Leave this alone.")
        self.write("README.md", "[Old document](missing-old.md)\n")
        self.adopt()
        before = (self.root / "old-misc/notes.txt").read_bytes()
        self.write("tests/test_new.py", "assert True\n")
        result = self.check()
        self.assertTrue(result["ready"], result)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual((self.root / "old-misc/notes.txt").read_bytes(), before)
        self.write("loose-note.md", "new unassigned file")
        self.assertIn("loose-note.md", " ".join(self.check()["errors"]))

    def test_only_declared_inputs_are_hashed_and_check_is_read_only(self):
        with (self.root / "large-old-artifact").open("wb") as output:
            output.truncate(9_000_000)
        self.adopt()
        before = set(self.root.rglob("*"))
        with patch.object(repository.workflow, "file_hash", wraps=repository.workflow.file_hash) as hashed:
            self.assertTrue(self.check()["ready"])
        self.assertNotIn(self.root / "large-old-artifact", [c.args[0] for c in hashed.call_args_list])
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_existing_unrelated_edit_does_not_create_update_obligation(self):
        self.write("old.txt", "first")
        self.adopt()
        self.write("old.txt", "second")
        self.assertTrue(self.check()["ready"])

    def test_moving_a_document_exposes_incoming_broken_link(self):
        self.write("docs/api.md", "# API")
        self.write("README.md", "[API](docs/api.md)")
        self.adopt()
        (self.root / "docs/api.md").rename(self.root / "docs/api-v2.md")
        self.assertIn("失效引用", " ".join(self.check()["errors"]))
        self.write("README.md", "[API](docs/api-v2.md)")
        self.assertTrue(self.check()["ready"])

    def test_links_handle_fences_reference_definitions_and_encoded_paths(self):
        self.write("docs/a b.md", "content")
        self.adopt()
        self.write("README.md", """[space](docs/a%20b.md)
````md
[example](not-real.md)
````
`[inline example](not-real.md)`
[use][ref]
[ref]: docs/a%20b.md
""")
        self.assertTrue(self.check()["ready"])
        self.write("README.md", "[ref]: docs/missing.md\n[use][ref]\n")
        self.assertFalse(self.check()["ready"])

    def test_links_after_inline_code_include_paths_with_parentheses(self):
        self.write("docs/available(v1).md", "content")
        self.adopt()
        self.write("README.md", "```cmd``` 是行内示例\n"
                   "    ``` 这是缩进代码行\n"
                   "[已有说明](docs/available(v1).md)\n"
                   "[说明](docs/guide(v2).md)\n"
                   "[页面](app/(dashboard)/page.md \"页面说明\")\n")
        self.assertEqual(repository.broken_links(self.root, ["README.md"]),
                         [["README.md", "app/(dashboard)/page.md"], ["README.md", "docs/guide(v2).md"]])
        self.assertFalse(self.check()["ready"])

    def test_anchor_check_is_opt_in_and_checks_new_local_fragments(self):
        for option in ({}, {"check_anchors": False}, {"check_anchors": True}):
            with self.subTest(option=option):
                self.policy.pop("check_anchors", None)
                self.policy.update(option)
                (self.root / repository.BASELINE).unlink(missing_ok=True)
                self.write("README.md", '# Run\n<a id="legacy"></a>\n[Available](#legacy)\n'
                           "[Existing broken anchor](docs/current.md#old)\n")
                result = self.adopt()
                enabled = option == {"check_anchors": True}
                self.assertEqual(result["existing_broken_links"], int(enabled))
                self.assertFalse(self.check()["policy_changed"])
                self.write("README.md", '# Run\n[Same page](#run) [Missing](#new)\n'
                           "[Cross document](docs/current.md#missing) [Existing](docs/current.md#old)\n")
                errors = self.check()["errors"]
                self.assertEqual(errors, [
                    "新增失效引用：README.md → #new",
                    "新增失效引用：README.md → docs/current.md#missing",
                ] if enabled else [])

    def test_anchor_check_rejects_non_boolean_config(self):
        for value in (0, "false", None, []):
            with self.subTest(value=value):
                self.policy["check_anchors"] = value
                with self.assertRaisesRegex(workflow.WorkflowError, "check_anchors 必须为布尔值"):
                    self.adopt()
                self.assertFalse((self.root / repository.BASELINE).exists())

    def test_unresolvable_symlink_is_reported_as_broken_link(self):
        self.adopt()
        self.write("README.md", "[Reference](docs/current-link.md)\n")
        (self.root / "docs/current-link.md").symlink_to("current-link.md")
        result = self.check()
        self.assertFalse(result["ready"])
        self.assertIn("新增失效引用：README.md → docs/current-link.md", result["errors"])

    def test_reintroduced_link_after_repair_and_checkpoint_is_new_failure(self):
        self.write("README.md", "[old](missing.md)")
        self.adopt()
        self.write("README.md", "fixed")
        self.assertTrue(repository.checkpoint(self.root, scope="work")["ready"])
        self.write("README.md", "[old](missing.md)")
        self.assertFalse(self.check()["ready"])

    def test_input_changes_require_document_change_or_bound_review(self):
        self.adopt()
        self.write("src/main.py", "print('internal refactor')\n")
        self.assertIn("更新义务", " ".join(self.check()["errors"]))
        repository.review(self.root, repository.POLICY, "usage", "仅替换内部实现；启动方式和外部行为未变。", scope="work")
        self.assertTrue(self.check()["ready"])
        self.write("src/main.py", "print('different change')\n")
        self.assertFalse(self.check()["ready"])
        self.write("README.md", "Updated usage for the new behavior")
        self.assertTrue(self.check()["ready"])

    def test_partial_doc_update_and_missing_doc_do_not_satisfy_rule(self):
        self.write("docs/api.md", "old API")
        self.policy["updates"][0]["documents"].append("docs/api.md")
        self.adopt()
        self.write("src/main.py", "new behavior")
        self.write("README.md", "new usage")
        self.assertFalse(self.check()["ready"])
        repository.review(self.root, repository.POLICY, "usage", "API contract remains unchanged.", scope="work")
        self.assertTrue(self.check()["ready"])
        (self.root / "docs/api.md").unlink()
        self.assertFalse(self.check()["ready"])

    def test_deletion_of_last_input_requires_document_review(self):
        self.adopt()
        (self.root / "src/main.py").unlink()
        self.assertFalse(self.check()["ready"])

    def test_checkpoint_cannot_erase_failure_and_adopt_cannot_overwrite(self):
        self.adopt()
        baseline = (self.root / repository.BASELINE).read_bytes()
        self.write("wrong-place.txt", "unassigned")
        self.assertFalse(repository.checkpoint(self.root, scope="work")["ready"])
        self.assertEqual((self.root / repository.BASELINE).read_bytes(), baseline)
        with self.assertRaises(workflow.WorkflowError):
            self.adopt()
        self.assertEqual((self.root / repository.BASELINE).read_bytes(), baseline)

    def test_needless_review_and_blank_reasons_are_rejected(self):
        self.adopt()
        with self.assertRaises(workflow.WorkflowError):
            repository.review(self.root, repository.POLICY, "usage", "nothing changed", scope="work")
        self.write("src/main.py", "new")
        with self.assertRaises(workflow.WorkflowError):
            repository.review(self.root, repository.POLICY, "usage", " ", scope="work")

    def test_git_ignores_generated_files_without_ignoring_tracked_sources(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write(".gitignore", "generated/\n")
        self.adopt()
        self.write("generated/large.log", "runtime")
        self.assertTrue(self.check()["ready"])
        self.write("src/new.py", "new")
        self.assertFalse(self.check()["ready"])

    def test_git_subproject_inventory_stays_inside_explicit_root(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subproject = self.root / "packages/app"
        self.write("packages/app/src/new.py", "new")
        files = repository.inventory(subproject, {"paths": {"src/": "implementation"}})
        self.assertEqual(files, ["src/new.py"])

    def test_no_git_fallback_honors_declared_runtime_ignore(self):
        self.policy["ignore"] = ["runtime/"]
        self.adopt()
        self.write("runtime/session.json", "active session, do not delete")
        self.assertTrue(self.check()["ready"])
        self.assertTrue((self.root / "runtime/session.json").exists())

    def test_custom_policy_and_existing_state_need_no_format_conversion(self):
        custom = "docs/repository-rules.json"
        self.write(custom, json.dumps(self.policy))
        original = (self.root / "docs/current.md").read_bytes()
        repository.adopt(self.root, custom, scope="work")
        self.assertTrue(repository.check(self.root, custom, scope="work")["ready"])
        self.assertEqual((self.root / "docs/current.md").read_bytes(), original)

    def test_missing_policy_reports_resolved_root_and_relative_path_in_ascii_locale(self):
        policy = "./中文规则.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "repository_check.py"), "check", "--scope", "work",
             "--policy", policy.encode("utf-8")],
            cwd=self.root, capture_output=True, encoding="utf-8", timeout=30,
            env=dict(os.environ, LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0"),
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        message = json.loads(result.stderr)["error"]
        self.assertIn("当前项目根为 " + str(self.root), message)
        self.assertIn(policy, message)
        self.assertIn("--root", message)

    def test_library_and_cli_share_baselines_for_a_root_alias(self):
        with tempfile.TemporaryDirectory() as location:
            alias = Path(location) / "alias"
            alias.symlink_to(self.root, target_is_directory=True)
            repository.adopt(alias, scope="work")
            self.assertTrue(self.check()["ready"])
            self.assertTrue(repository.check(alias, scope="work")["ready"])

    def test_scope_switch_archives_only_after_old_scope_checks_pass(self):
        self.adopt()
        self.write("src/main.py", "print('internal change')\n")
        args = (self.root, repository.POLICY, "work", "next")
        self.assertFalse(repository.switch_scope(*args)["ready"])
        self.assertFalse((self.root / ".project-workflow/archive").exists())
        repository.review(self.root, repository.POLICY, "usage", "同一对外用法", scope="work")
        original = (self.root / repository.BASELINE).read_bytes()
        reviews = (self.root / repository.REVIEWS).read_bytes()
        result = repository.switch_scope(*args)
        self.assertTrue(result["ready"])
        archive = Path(result["archive"])
        self.assertEqual((archive / "repository-baseline.json").read_bytes(), original)
        self.assertEqual((archive / "repository-reviews.json").read_bytes(), reviews)
        self.assertTrue(repository.check(self.root, scope="next")["ready"])

    def test_scope_switch_keeps_ordered_archives_and_reminds_about_state(self):
        state = workflow.initialize(self.root, "CURRENT.md", "当前工作线")
        meta, body = workflow.load_state(state)
        meta["verification"].update(repository_policy=repository.POLICY, repository_scope="work")
        state.write_text("---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n" + body, encoding="utf-8")
        before = state.read_bytes()
        self.adopt()
        command = [sys.executable, str(SCRIPTS / "repository_check.py"), "switch-scope",
                   "--root", str(self.root), "--scope", "work", "--next-scope", "next/release"]
        switched = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(switched.returncode, 0, switched.stderr)
        self.assertIn("CURRENT.md 中的 verification.repository_scope 更新为 next/release", switched.stdout)
        first, = (self.root / ".project-workflow/archive").iterdir()
        second = repository.switch_scope(self.root, repository.POLICY, "next/release", "last")
        self.assertEqual(second["warnings"], [])
        second_path = Path(second["archive"])
        self.assertRegex(first.name, r"^\d{8}T\d{6}\.\d{6}Z-work-[0-9a-f]{8}$")
        self.assertRegex(second_path.name, r"^\d{8}T\d{6}\.\d{6}Z-next_release-[0-9a-f]{8}$")
        self.assertLess(first.name, second_path.name)
        self.assertEqual(state.read_bytes(), before)

    def test_scope_switch_reports_invalid_optional_state_without_changing_it(self):
        self.write("CURRENT.md", '---\n{"workflow":"dev_co",\n---\n原正文\n')
        before = (self.root / "CURRENT.md").read_bytes()
        self.adopt()
        result = repository.switch_scope(self.root, repository.POLICY, "work", "next")
        self.assertTrue(result["ready"])
        self.assertIn("frontmatter JSON 无效", result["warnings"][0])
        self.assertEqual((self.root / "CURRENT.md").read_bytes(), before)

    def test_checkpoint_does_not_revive_a_review_when_content_returns(self):
        self.adopt()
        original = (self.root / "src/main.py").read_bytes()
        guide = (self.root / "README.md").read_bytes()
        self.write("src/main.py", "print('changed')\n")
        repository.review(self.root, repository.POLICY, "usage", "当时对外用法不变", scope="work")
        self.assertTrue(repository.checkpoint(self.root, scope="work")["ready"])
        (self.root / "src/main.py").write_bytes(original)
        self.write("README.md", "# Temporary guide\n")
        self.assertTrue(repository.checkpoint(self.root, scope="work")["ready"])
        (self.root / "README.md").write_bytes(guide)
        self.assertTrue(repository.checkpoint(self.root, scope="work")["ready"])
        self.write("src/main.py", "print('changed')\n")
        self.assertFalse(self.check()["ready"])

    def test_unsafe_config_and_input_symlink_fail_before_read(self):
        self.policy["updates"][0]["inputs"] = ["../outside"]
        with self.assertRaises(workflow.WorkflowError):
            self.adopt()
        self.policy["updates"][0]["inputs"] = ["src/"]
        (self.root / "src/main.py").unlink()
        (self.root / "src/main.py").symlink_to(self.root / "README.md")
        with self.assertRaises(workflow.WorkflowError):
            self.adopt()

    def test_cli_exit_codes_and_unknown_configuration_are_honest(self):
        self.adopt()
        command = [sys.executable, str(SCRIPTS / "repository_check.py"), "check", "--root", str(self.root), "--scope", "work", "--json"]
        result = subprocess.run(command, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("loose.md", "unassigned")
        result = subprocess.run(command, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ready"])
        self.policy["requird"] = []
        self.write(repository.POLICY, json.dumps(self.policy))
        result = subprocess.run(command, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2)

    def test_nested_list_links_are_checked_while_nested_fences_are_ignored(self):
        self.write("docs/valid.md", "# Valid\n")
        self.adopt()
        self.write("README.md", "- 顶层说明\n"
                   "    - [有效嵌套链接](docs/valid.md)\n"
                   "    - [失效嵌套链接](docs/missing-nested.md)\n"
                   "    续行引用 [失效续行链接](docs/missing-cont.md)\n"
                   "    ```md\n"
                   "    [代码块内示例](docs/ignored-in-fence.md)\n"
                   "    ```\n")
        self.assertEqual(repository.broken_links(self.root, ["README.md"]),
                         [["README.md", "docs/missing-cont.md"], ["README.md", "docs/missing-nested.md"]])
        self.assertFalse(self.check()["ready"])

    def test_env_templates_are_allowed_in_update_rules_while_secrets_stay_blocked(self):
        self.write(".env.example", "PORT=8000\n")
        self.policy["paths"][".env.example"] = "无密钥配置模板"
        self.policy["updates"].append({"id": "config-template", "inputs": ["src/"], "documents": [".env.example"]})
        self.adopt()
        self.write("src/main.py", "print('with port')\n")
        self.write("README.md", "Updated usage")
        self.assertIn(".env.example", " ".join(self.check()["errors"]))
        self.write(".env.example", "PORT=8080\n")
        self.assertTrue(self.check()["ready"])
        for secret in (".ENV", ".netrc", ".git-credentials", "id_ecdsa"):
            self.policy["updates"][-1]["documents"] = [secret]
            self.write(repository.POLICY, json.dumps(self.policy))
            with self.subTest(secret=secret), self.assertRaisesRegex(workflow.WorkflowError, "不得读取凭据路径"):
                self.check()

    def test_symlink_error_reports_rule_context_and_switch_scope_accepts_custom_state(self):
        state = workflow.initialize(self.root, "notes/ACTIVE.md", "自定义记录")
        meta, body = workflow.load_state(state)
        meta["verification"].update(repository_policy=repository.POLICY, repository_scope="work")
        state.write_text("---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n" + body, encoding="utf-8")
        self.adopt()
        switched = repository.switch_scope(self.root, repository.POLICY, "work", "v2", state_name="notes/ACTIVE.md")
        self.assertTrue(switched["ready"])
        self.assertTrue(any("notes/ACTIVE.md" in w and "v2" in w for w in switched["warnings"]))
        (self.root / "src/main.py").unlink()
        (self.root / "src/main.py").symlink_to(self.root / "README.md")
        with self.assertRaisesRegex(workflow.WorkflowError, "更新规则输入或文档路径不得经过符号链接"):
            repository.check(self.root, scope="v2")

    def test_review_requires_rule_before_reading_baseline(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "repository_check.py"), "review",
                                 "--root", str(self.root), "--scope", "work", "--reason", "reviewed"],
                                capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--rule", json.loads(result.stderr)["error"])
        self.assertFalse((self.root / repository.REVIEWS).exists())


if __name__ == "__main__":
    unittest.main()
