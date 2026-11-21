"""安装只在临时宿主目录创建技能链接。"""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="devco-install-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.codex = self.base / "codex config"
        self.claude = self.base / "claude config"

    def install(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/install_skill.py"),
                               "--codex-home", str(self.codex), "--claude-home", str(self.claude), *args],
                              cwd=self.base, capture_output=True, encoding="utf-8", timeout=10)

    def test_links_both_hosts_to_this_checkout(self):
        self.claude.mkdir()
        settings = self.claude / "settings.json"
        settings.write_bytes(b'{"example": true}\n')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for host in (self.codex, self.claude):
            target = host / "skills/dev_co"
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), ROOT)
        self.assertEqual(sorted(path.name for path in self.codex.iterdir()), ["skills"])
        self.assertEqual(sorted(path.name for path in self.claude.iterdir()), ["settings.json", "skills"])
        self.assertEqual(settings.read_bytes(), b'{"example": true}\n')

    def test_existing_install_is_preserved_before_other_host_is_written(self):
        target = self.claude / "skills/dev_co"
        target.mkdir(parents=True)
        original = target / "SKILL.md"
        original.write_text("existing skill", encoding="utf-8")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(target), result.stderr)
        self.assertEqual(original.read_text(encoding="utf-8"), "existing skill")
        self.assertFalse(self.codex.exists())

    def test_rerun_fills_missing_host_and_check_does_not_install(self):
        self.assertEqual(self.install("--host", "codex").returncode, 0)
        self.assertNotEqual(self.install("--check").returncode, 0)
        self.assertFalse(self.claude.exists())
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install("--check").returncode, 0)
        self.assertEqual((self.claude / "skills/dev_co").resolve(), ROOT)

    def test_single_host_selection_preserves_other_hosts_broken_link(self):
        target = self.claude / "skills/dev_co"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.base / "previous checkout", target_is_directory=True)
        result = self.install("--host", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.codex / "skills/dev_co").resolve(), ROOT)
        result = self.install("--host", "claude")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.readlink(), self.base / "previous checkout")
