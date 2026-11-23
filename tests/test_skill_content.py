"""核对维护资料的本地链接和合成场景输入。"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from repository_check import POLICY, broken_links, inventory, load_policy, markdown_anchors, matches
from workflow_files import safe_path


class SkillContentTests(unittest.TestCase):
    def test_standalone_deslop_routing_and_fast_path_are_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        admission = skill.split("## 核心约定", 1)[0]
        self.assertRegex(admission, r"独立的增量反防御清理[^\n]+`de-slop`")
        self.assertRegex(readme, r"\| 独立的增量反防御清理[^\n]+\| 直接使用可用的 `de-slop`")
        self.assertIn("Route standalone anti-fallback diff cleanups directly to an available `de-slop`", readme)
        fast_path = next(line for line in skill.splitlines() if "`git diff`" in line and "`de-slop`" in line)
        for boundary in ("本轮新增的未跟踪源码", "仅报告", "主交付摘要"):
            self.assertIn(boundary, fast_path)
        self.assertLessEqual(len(skill.splitlines()), 65)
        self.assertLessEqual(len(skill.encode("utf-8")), 8_800)

    def test_maintained_documents_link_to_existing_files(self):
        documents = ["AGENTS.md", "README.md", "SKILL.md", "assets/README.md",
                     "docs/verification-history.md", "evals/README.md"]
        documents.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / "references").glob("*.md"))
        self.assertEqual(broken_links(ROOT, documents, check_anchors=True), [])

    def test_self_repository_policy_covers_all_files_and_required_entries(self):
        policy = load_policy(ROOT, POLICY)
        files = inventory(ROOT, policy)
        self.assertTrue(files)
        unassigned = [name for name in files if not matches(name, policy["paths"])]
        self.assertEqual(unassigned, [])
        for required in policy["required"]:
            self.assertTrue((ROOT / required).is_file(), required)
        self.assertEqual(broken_links(ROOT, policy["links"], check_anchors=policy["check_anchors"]), [])

    def test_reference_navigation_targets_match_second_level_headings(self):
        localized = {"architecture-and-risk.md", "delivery-and-release.md",
                     "prototyping.md", "research-and-positioning.md"}
        total_bytes = 0
        references = sorted((ROOT / "references").glob("*.md"))
        self.assertEqual(len(references), 13)
        for path in references:
            with self.subTest(reference=path.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertTrue(any(line.startswith("**按需读取：** ") for line in lines[:5]))
                navigation = [line for line in lines[:8] if line.startswith("章节导航：")]
                self.assertEqual(len(navigation), 1)
                if path.name in localized:
                    total_bytes += path.stat().st_size
                headings = {line.removeprefix("## ") for line in lines if line.startswith("## ")}
                for line in navigation:
                    targets = set(re.findall(r"`([^`]+)`", line))
                    self.assertTrue(targets)
                    self.assertEqual(targets - headings, set())
        self.assertLessEqual(total_bytes, 21_000)

    def test_readme_cover_uses_webp_within_size_budget(self):
        cover = ROOT / "assets/dev-co-cover.webp"
        self.assertLessEqual(cover.stat().st_size, 300_000)
        with cover.open("rb") as stream:
            header = stream.read(12)
        self.assertEqual((header[:4], header[8:]), (b"RIFF", b"WEBP"))
        self.assertIn("(assets/dev-co-cover.webp)", (ROOT / "README.md").read_text(encoding="utf-8"))

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

    def test_heading_anchors_use_link_text_and_keep_underscores_in_code(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            guide = root / "guide.md"
            guide.write_text(
                "## 包含 [链接文字](other.md) 的标题\n"
                "## 中文_斜体_标题\n"
                "## 使用 `dev_co` 入口\n"
                "## ![插图](cover(v2).webp) 和 `_helper_`\n", encoding="utf-8",
            )
            expected = {"包含-链接文字-的标题", "中文斜体标题", "使用-dev_co-入口", "插图-和-_helper_"}
            self.assertEqual(markdown_anchors(guide), expected)
            (root / "README.md").write_text(
                "\n".join(f"[入口](guide.md#{anchor})" for anchor in sorted(expected))
                + "\n[错误](guide.md#包含-链接文字othermd-的标题)\n", encoding="utf-8",
            )
            self.assertEqual(broken_links(root, ["README.md"], check_anchors=True),
                             [["README.md", "guide.md#包含-链接文字othermd-的标题"]])

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
                                      capture_output=True, encoding="utf-8", timeout=30)

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

    def test_eval_detects_links_without_traversing_them_in_ascii_locale(self):
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            outside = parent / "outside"
            outside.mkdir()
            (outside / "untouched.txt").touch()
            root = parent / "workspace"

            def run(command):
                return subprocess.run(
                    [sys.executable, str(ROOT / "scripts/eval_scenarios.py"), command,
                     "--scenario", "standalone_evaluation", "--dest", str(root)],
                    capture_output=True, encoding="utf-8", timeout=30,
                    env=dict(os.environ, LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0"),
                )

            self.assertEqual(run("prepare").returncode, 0)
            (root / os.fsdecode("资料链接".encode("utf-8"))).symlink_to(outside, target_is_directory=True)
            changes = ["资料链接"]
            if sys.platform.startswith("linux"):
                (root / os.fsdecode(b"bad\xff.py")).touch()
                changes.insert(0, r"bad\udcff.py")
            result = run("verify-clean")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["目录变化：", *changes])

    def test_deslop_fixtures_prepare_untracked_source_and_tracked_diff(self):
        for scenario in ("increment_deslop_before_verify", "standalone_deslop_review"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as temporary:
                subprocess.run([sys.executable, str(ROOT / "scripts/eval_scenarios.py"), "prepare",
                                "--scenario", scenario, "--dest", temporary],
                               capture_output=True, check=True, timeout=30)

                def git(*args):
                    return subprocess.check_output(["git", "--no-optional-locks", "-C", temporary, *args],
                                                   encoding="utf-8", timeout=30).splitlines()

                self.assertEqual(git("diff", "--cached", "--name-only"), [])
                if scenario == "increment_deslop_before_verify":
                    self.assertEqual(git("ls-files", "--others", "--exclude-standard"), ["amounts.py", "scratch.py"])
                else:
                    self.assertFalse((Path(temporary) / "fixtures").exists())
                    self.assertEqual(git("ls-tree", "--name-only", "HEAD", "--", "fixtures"), [])
                    self.assertEqual(git("diff", "--name-only"), ["names.py", "tests/test_names.py"])

    def test_git_eval_detects_worktree_index_and_head_changes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            def run(command):
                return subprocess.run([sys.executable, str(ROOT / "scripts/eval_scenarios.py"), command,
                                       "--scenario", "standalone_deslop_review", "--dest", temporary],
                                      capture_output=True, encoding="utf-8", timeout=30)

            def git(*args):
                subprocess.run(["git", "-C", temporary, "-c", "user.name=Fixture", "-c",
                                "user.email=fixture@example.test", "-c", "commit.gpgsign=false",
                                "-c", "core.hooksPath=/dev/null", *args], check=True, timeout=30)

            prepared = run("prepare")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            clean = run("verify-clean")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            source = root / "names.py"
            previous = source.read_bytes()
            source.write_bytes(previous + b"\n# extra\n")
            edited = run("verify-clean")
            self.assertEqual(edited.returncode, 1, edited.stderr)
            self.assertIn("names.py", edited.stdout)
            source.write_bytes(previous)
            mode = source.stat().st_mode & 0o777
            source.chmod(mode | 0o100)
            permission_change = run("verify-clean")
            self.assertEqual(permission_change.returncode, 1, permission_change.stderr)
            self.assertIn("names.py", permission_change.stdout)
            source.chmod(mode)
            git("add", "--", "names.py")
            staged = run("verify-clean")
            self.assertEqual(staged.returncode, 1, staged.stderr)
            self.assertIn(".git/index", staged.stdout)
            git("restore", "--staged", "--", "names.py")
            git("branch", "unexpected-branch")
            branched = run("verify-clean")
            self.assertEqual(branched.returncode, 1, branched.stderr)
            self.assertIn(".git/refs", branched.stdout)
            git("branch", "-qD", "unexpected-branch")
            git("commit", "--allow-empty", "-qm", "unexpected commit")
            committed = run("verify-clean")
            self.assertEqual(committed.returncode, 1, committed.stderr)
            self.assertIn(".git/HEAD", committed.stdout)
