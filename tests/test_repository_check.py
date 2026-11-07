"""仓库生命周期的可观察行为；所有样本隔离，不接触真实项目。"""
from __future__ import annotations

import json
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
        path.write_text(content)

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
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("loose.md", "unassigned")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ready"])
        self.policy["requird"] = []
        self.write(repository.POLICY, json.dumps(self.policy))
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
