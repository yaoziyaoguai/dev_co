"""恢复关键内容与低频验证的回归。"""
from pathlib import Path
import json
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from context_brief import summarize
import project_workflow as workflow
import repository_check as repository
from test_workflow import ProjectFixture


class BriefTests(unittest.TestCase):
    def test_history_cannot_hide_tail_constraints_or_next_step(self):
        body = ("# Project\n## 本轮目标\n实现 CSV 导出\n## 历史\n" + "old history\n" * 1000
                + "## 验收标准\n逗号字段完整\n## 当前决定\n禁止网络访问\n## 下一步\n修复导出编码\n")
        result = summarize(body)
        for value in ("实现 CSV 导出", "逗号字段完整", "禁止网络访问", "修复导出编码"):
            self.assertIn(value, result)
        self.assertNotIn("old history", result)
        self.assertLess(len(result), 6500)

    def test_oversized_essential_section_is_explicitly_incomplete(self):
        result = summarize("## 本轮目标\n" + "long goal " * 1000 + "\n## 下一步\ncontinue")
        self.assertIn("本段截断", result)
        self.assertIn("continue", result)
        self.assertIn("未定位恢复章节", result)

    def test_fenced_examples_do_not_override_actual_next_action(self):
        body = "## 历史\n```md\n## 下一步\nwrong\n```\n" + "history " * 1000 + "\n## 下一步\nactual next action"
        result = summarize(body)
        self.assertIn("actual next action", result)
        self.assertNotIn("wrong", result)

    def test_ambiguous_sections_do_not_silently_choose_a_requirement(self):
        body = "## 当前决定\nA\n## 历史\n" + "history " * 1000 + "\n## 当前决定\nB"
        result = summarize(body)
        self.assertIn("同名段落存在歧义", result)

    def test_custom_titles_keep_original_document_structure(self):
        body = "## History\n" + "old\n" * 3000 + "\n## Goal\nShip locally\n## Next\nTest CSV"
        result = summarize(body, ["Goal", "Next"])
        self.assertIn("Ship locally", result)
        self.assertIn("Test CSV", result)
        self.assertNotIn("未定位恢复章节", result)

    def test_short_record_is_returned_without_another_summary_copy(self):
        body = "# Existing custom format\nDo not deploy.\nNext: test locally.\n"
        self.assertEqual(summarize(body), body.strip())

    def test_global_constraint_before_first_section_is_kept(self):
        body = "# Current\nNever send project data outside this machine.\n## 历史\n" + "history\n" * 1200
        self.assertIn("Never send project data outside this machine.", summarize(body))


class ReuseTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.counter = self.root / "run-count"
        self.counter.write_text("0")
        with (self.root / "check.py").open("a") as output:
            output.write("p = Path('run-count')\np.write_text(str(int(p.read_text()) + 1))\n")

    def test_valid_evidence_is_reused_without_running_or_rewriting_logs(self):
        first = workflow.verify(self.root, self.state, reuse=True)
        evidence = workflow.read_evidence(self.root)
        self.assertFalse(first["reused"])
        second = workflow.verify(self.root, self.state, reuse=True)
        self.assertTrue(second["reused"])
        self.assertEqual(self.counter.read_text(), "1")
        self.assertEqual(workflow.read_evidence(self.root), evidence)

    def test_changed_intent_invalidates_reuse_but_operational_notes_do_not(self):
        workflow.verify(self.root, self.state, reuse=True)
        self.body += "\n## 下一步\nInspect the output.\n"
        self.save()
        self.assertTrue(workflow.verify(self.root, self.state, reuse=True)["reused"])
        self.meta["goal_revision"] += 1
        self.save()
        self.assertFalse(workflow.verify(self.root, self.state, reuse=True)["reused"])
        self.assertEqual(self.counter.read_text(), "2")

    def test_force_verify_still_runs_and_cli_reuse_does_not(self):
        self.verify()
        self.verify()
        self.assertEqual(self.counter.read_text(), "2")
        result = subprocess.run([sys.executable, str(SCRIPTS / "project_workflow.py"), "verify",
                                 "--reuse", "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["reused"])
        self.assertEqual(self.counter.read_text(), "2")

    def test_changed_inputs_do_not_reuse_previous_success(self):
        workflow.verify(self.root, self.state, reuse=True)
        (self.root / "src/logic.py").write_text("value = 2\n")
        result = workflow.verify(self.root, self.state, reuse=True)
        self.assertFalse(result["reused"])
        self.assertFalse(result["ready"])


class RepositoryGateTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.policy = {"schema": 1, "paths": {"src/": "implementation", "docs/": "current context"},
                       "required": ["docs/CURRENT.md"], "links": ["docs/CURRENT.md"]}
        (self.root / repository.POLICY).write_text(json.dumps(self.policy))
        repository.adopt(self.root, scope="work")
        self.meta["verification"]["repository_policy"] = repository.POLICY
        self.meta["verification"]["repository_scope"] = "work"
        self.save()

    def test_untracked_file_outside_test_inputs_cannot_bypass_gate_or_reuse(self):
        self.assertTrue(workflow.verify(self.root, self.state, reuse=True)["ready"])
        evidence = workflow.read_evidence(self.root)
        extra = self.root / "random-plan.md"
        extra.write_text("a new unassigned plan")
        result = workflow.verify(self.root, self.state, reuse=True)
        self.assertFalse(result["ready"])
        self.assertIn("random-plan.md", " ".join(result["reasons"]))
        self.assertEqual(workflow.read_evidence(self.root), evidence)
        extra.unlink()
        self.assertTrue(workflow.verify(self.root, self.state, reuse=True)["reused"])

    def test_missing_baseline_is_error_not_silent_manual_fallback(self):
        (self.root / repository.BASELINE).unlink()
        result = self.cli("verify")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / ".project-workflow/evidence").exists())

    def test_changed_link_in_document_not_hashed_by_tests_still_fails_gate(self):
        self.assertTrue(self.verify()["ready"])
        self.body += "\n## 下一步\n[needed artifact](missing.md)\n"
        self.save()
        self.assertFalse(self.gate()["ready"])
        self.assertIn("失效引用", " ".join(self.gate()["reasons"]))


if __name__ == "__main__":
    unittest.main()
