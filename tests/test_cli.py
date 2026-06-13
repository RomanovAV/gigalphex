from pathlib import Path
import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.cli import build_parser, main, should_auto_init


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class CliTest(unittest.TestCase):
    def test_auto_init_requires_existing_plan_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                args = build_parser().parse_args(["docs/plans/missing.md"])

                self.assertFalse(should_auto_init(args))
            finally:
                os.chdir(original_cwd)

    def test_auto_init_includes_real_plan_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                args = build_parser().parse_args(["--plan", "add demo"])

                self.assertTrue(should_auto_init(args))
            finally:
                os.chdir(original_cwd)

    def test_auto_init_skips_plan_creation_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                args = build_parser().parse_args(["--plan", "add demo", "--dry-run"])

                self.assertFalse(should_auto_init(args))
            finally:
                os.chdir(original_cwd)

    def test_plan_execution_auto_initializes_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                """#!/usr/bin/env python3
import sys
sys.stdin.read()
print("<<<GIGALPHEX:ALL_TASKS_DONE>>>")
""",
            )
            plan = tmp_path / "docs/plans/20260612-smoke.md"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                """# Plan: Smoke

### Task 1: Already done
- [x] Nothing left to do
""",
                encoding="utf-8",
            )

            try:
                os.chdir(tmp_path)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            str(plan),
                            "--gigacode-command",
                            str(fake_gigacode),
                            "--allow-dirty",
                            "--tasks-only",
                            "--no-move-plan",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertTrue((tmp_path / ".gigalphex/config").exists())
            self.assertTrue((tmp_path / ".gigalphex/prompts/task.txt").exists())
            self.assertTrue((tmp_path / ".gigalphex/prompts/review_synthesis.txt").exists())

    def test_plan_creation_commits_created_plan_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                """#!/usr/bin/env python3
import sys
sys.stdin.read()
print("# Plan: Demo")
print()
print("## Overview")
print("Demo plan.")
print()
print("### Task 1: Build")
print("- [ ] Do it")
""",
            )

            try:
                os.chdir(tmp_path)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "config", "user.name", "GigaLphex Test"], check=True)
                Path("README.md").write_text("# Demo\n", encoding="utf-8")
                subprocess.run(["git", "add", "README.md"], check=True)
                subprocess.run(["git", "commit", "-m", "initial"], check=True, stdout=subprocess.PIPE)

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["--plan", "add demo feature", "--gigacode-command", str(fake_gigacode)])

                committed = subprocess.run(
                    ["git", "log", "--name-only", "--format=%s", "-1"],
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                ).stdout
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertIn("docs: add plan 202", committed)
            self.assertIn("docs/plans/", committed)
            self.assertIn("add-demo-feature.md", committed)
            self.assertTrue((tmp_path / ".gigalphex/config").exists())
            self.assertTrue((tmp_path / ".gigalphex/prompts/make_plan.txt").exists())


if __name__ == "__main__":
    unittest.main()
