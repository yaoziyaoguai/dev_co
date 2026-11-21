"""核对维护资料的本地链接和合成场景输入。"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from repository_check import broken_links
from workflow_files import safe_path


class SkillContentTests(unittest.TestCase):
    def test_maintained_documents_link_to_existing_files(self):
        documents = ["README.md", "SKILL.md", "assets/README.md", "evals/README.md"]
        documents.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / "references").glob("*.md"))
        self.assertEqual(broken_links(ROOT, documents), [])

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
