"""核对维护资料的本地链接和合成场景输入。"""
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from repository_check import broken_links
from workflow_files import safe_path


class SkillContentTests(unittest.TestCase):
    def test_maintained_documents_link_to_existing_files(self):
        documents = ["AGENTS.md", "README.md", "SKILL.md", "assets/README.md", "evals/README.md"]
        documents.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / "references").glob("*.md"))
        self.assertEqual(broken_links(ROOT, documents, check_anchors=True), [])

    def test_local_markdown_anchors_resolve_and_report_missing_headings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "guide.md").write_text("# 写法\n### 示例\n### 示例\n```md\n## 忽略\n```\n", encoding="utf-8")
            (root / "README.md").write_text(
                '# 标题\n<a name="alias"></a>\n[同页](#标题) [别名](#alias) [重复标题](guide.md#示例-1)\n'
                '[缺少](#不存在) [示例中的标题](guide.md#忽略)\n', encoding="utf-8",
            )
            self.assertEqual(broken_links(root, ["README.md"], check_anchors=True),
                             [["README.md", "#不存在"], ["README.md", "guide.md#忽略"]])

    def test_eval_scenarios_have_unique_ids_and_safe_initial_files(self):
        data = json.loads((ROOT / "evals/scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertIsInstance(data["scenarios"], list)
        self.assertTrue(data["scenarios"])
        ids = set()
        with TemporaryDirectory(prefix="devco-eval-paths-") as directory:
            root = Path(directory).resolve()
            for scenario in data["scenarios"]:
                scenario_id = scenario["id"]
                with self.subTest(scenario=scenario_id):
                    self.assertTrue(isinstance(scenario_id, str) and scenario_id.strip())
                    self.assertNotIn(scenario_id, ids)
                    ids.add(scenario_id)
                    self.assertTrue(isinstance(scenario["user_request"], str) and scenario["user_request"].strip())
                    for key in ("expected", "fail_if"):
                        criteria = scenario["review"][key]
                        self.assertIsInstance(criteria, list)
                        self.assertTrue(criteria and all(isinstance(item, str) and item.strip() for item in criteria))
                    for name, text in scenario["initial_files"].items():
                        self.assertNotEqual(safe_path(root, name, no_symlinks=True), root)
                        self.assertIsInstance(text, str)

    def test_eval_index_matches_scenario_ids(self):
        data = json.loads((ROOT / "evals/scenarios.json").read_text(encoding="utf-8"))
        index = (ROOT / "evals/README.md").read_text(encoding="utf-8").split("## 怎样运行", 1)[0]
        names = re.findall(r"`([a-z]+(?:_[a-z]+)*)`", index)
        self.assertEqual(set(names), {scenario["id"] for scenario in data["scenarios"]})

    def test_eval_workspace_detects_changed_and_added_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            def run(command):
                return subprocess.run([sys.executable, str(ROOT / "scripts/eval_scenarios.py"), command,
                                       "--scenario", "standalone_evaluation", "--dest", temporary],
                                      capture_output=True, encoding="utf-8", timeout=10)

            self.assertEqual(run("prepare").returncode, 0)
            self.assertEqual(run("verify-clean").returncode, 0)
            self.assertEqual(run("prepare").returncode, 2)
            results = root / "results.csv"
            results.write_bytes(results.read_bytes()[:-1] + b"!")
            (root / "new.txt").touch()
            result = run("verify-clean")
            self.assertEqual(result.returncode, 1)
            self.assertIn("results.csv", result.stdout)
            self.assertIn("new.txt", result.stdout)
