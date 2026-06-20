from pathlib import Path
import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.cli import build_parser, main, should_auto_init


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class CliTest(unittest.TestCase):
    def test_main_creates_global_config_and_prompt_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            project = tmp_path / "project"
            project.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(project)
                with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(io.StringIO()):
                    code = main(["--init"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            config = home / ".config/gigalphex/config"
            self.assertTrue(config.is_file())
            self.assertIn("# task_model =", config.read_text(encoding="utf-8"))
            self.assertTrue((home / ".config/gigalphex/prompts/task.txt").is_file())
            self.assertTrue((home / ".config/gigalphex/prompts/review_synthesis.txt").is_file())
            self.assertFalse((project / ".gigalphex/prompts").exists())

    def test_init_prompts_creates_local_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            project = tmp_path / "project"
            project.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(project)
                with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(io.StringIO()):
                    code = main(["--init-prompts"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertTrue((project / ".gigalphex/prompts/task.txt").is_file())
            self.assertTrue((project / ".gigalphex/prompts/review_synthesis.txt").is_file())
            self.assertFalse((project / ".gigalphex/config").exists())

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
            self.assertFalse((tmp_path / ".gigalphex/prompts").exists())

    def test_plan_execution_outside_git_repo_returns_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
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
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main([str(plan)])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(1, code)
            self.assertIn("not inside a git repository", stderr.getvalue())
            self.assertIn("--init-git", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_auto_init_does_not_make_clean_plan_execution_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                """#!/usr/bin/env python3
import sys
sys.stdin.read()
print("<<<GIGALPHEX:ALL_TASKS_DONE>>>")
""",
            )
            plan = repo / "docs/plans/20260612-smoke.md"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                """# Plan: Smoke

### Task 1: Already done
- [x] Nothing left to do
""",
                encoding="utf-8",
            )

            code = -1
            try:
                os.chdir(repo)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "config", "user.name", "GigaLphex Test"], check=True)
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", "initial"], check=True, stdout=subprocess.PIPE)

                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(
                        [
                            str(plan),
                            "--gigacode-command",
                            str(fake_gigacode),
                            "--tasks-only",
                            "--no-move-plan",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertEqual("", stderr.getvalue())
            self.assertTrue((repo / ".gigalphex/config").exists())

    def test_plan_execution_init_git_commits_initial_state_before_dirty_check(self) -> None:
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
                stdout = io.StringIO()
                git_env = {
                    "GIT_AUTHOR_NAME": "GigaLphex Test",
                    "GIT_AUTHOR_EMAIL": "test@example.com",
                    "GIT_COMMITTER_NAME": "GigaLphex Test",
                    "GIT_COMMITTER_EMAIL": "test@example.com",
                }
                with patch.dict(os.environ, git_env), contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            str(plan),
                            "--init-git",
                            "--gigacode-command",
                            str(fake_gigacode),
                            "--tasks-only",
                            "--no-move-plan",
                        ]
                    )

                log = subprocess.run(
                    ["git", "log", "--oneline", "--decorate"],
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                ).stdout
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertIn("initialized git repository", stdout.getvalue())
            self.assertIn("committed initial repository state", stdout.getvalue())
            self.assertIn("chore: initialize repository", log)

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
            self.assertIn(".gigalphex/config", committed)
            self.assertIn(".gitignore", committed)
            self.assertIn("docs/plans/", committed)
            self.assertIn("add-demo-feature.md", committed)
            self.assertTrue((tmp_path / ".gigalphex/config").exists())
            self.assertFalse((tmp_path / ".gigalphex/prompts").exists())

    def test_plan_creation_can_initialize_git_repository_before_commit(self) -> None:
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
print("### Task 1: Build")
print("- [ ] Do it")
""",
            )

            try:
                os.chdir(tmp_path)
                stdout = io.StringIO()
                git_env = {
                    "GIT_AUTHOR_NAME": "GigaLphex Test",
                    "GIT_AUTHOR_EMAIL": "test@example.com",
                    "GIT_COMMITTER_NAME": "GigaLphex Test",
                    "GIT_COMMITTER_EMAIL": "test@example.com",
                }
                with patch.dict(os.environ, git_env), contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            "--plan",
                            "add demo feature",
                            "--init-git",
                            "--gigacode-command",
                            str(fake_gigacode),
                        ]
                    )

                committed = subprocess.run(
                    ["git", "log", "--name-only", "--format=%s", "-1"],
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                ).stdout
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertTrue((tmp_path / ".git").exists())
            self.assertIn("docs: add plan 202", committed)
            self.assertIn("docs/plans/", committed)

    def test_review_autodetects_default_branch_when_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            capture = tmp_path / "prompt.txt"
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import sys
Path({str(capture)!r}).write_text("\\n".join(sys.argv[1:]) + "\\nSTDIN\\n" + sys.stdin.read())
print("<<<GIGALPHEX:REVIEW_DONE>>>")
""",
            )

            try:
                os.chdir(repo)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "config", "user.name", "GigaLphex Test"], check=True)
                Path("README.md").write_text("# Demo\n", encoding="utf-8")
                subprocess.run(["git", "add", "README.md"], check=True)
                subprocess.run(["git", "commit", "-m", "initial"], check=True, stdout=subprocess.PIPE)
                subprocess.run(["git", "branch", "-m", "master"], check=True)

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["--review", "--no-parallel-review", "--gigacode-command", str(fake_gigacode)])
            finally:
                os.chdir(original_cwd)

            captured_prompt = capture.read_text(encoding="utf-8")
            self.assertEqual(0, code)
            self.assertIn("git diff master...HEAD", captured_prompt)
            self.assertNotIn("git diff main...HEAD", captured_prompt)

    def test_successful_plan_run_commits_completed_plan_move_and_ignores_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                """#!/usr/bin/env python3
import sys
prompt = " ".join(sys.argv[1:]) + sys.stdin.read()
if "specialist review agents" in prompt:
    print("<<<GIGALPHEX:REVIEW_DONE>>>")
elif "You are the" in prompt:
    print("NO FINDINGS")
else:
    print("<<<GIGALPHEX:ALL_TASKS_DONE>>>")
""",
            )

            try:
                os.chdir(tmp_path)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "config", "user.name", "GigaLphex Test"], check=True)

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, main(["--init"]))

                plan = tmp_path / "docs/plans/20260612-smoke.md"
                plan.parent.mkdir(parents=True)
                plan.write_text(
                    """# Plan: Smoke

### Task 1: Already done
- [x] Nothing left to do
""",
                    encoding="utf-8",
                )
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", "initial"], check=True, stdout=subprocess.PIPE)

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main([str(plan), "--gigacode-command", str(fake_gigacode), "--no-branch"])

                latest = subprocess.run(
                    ["git", "log", "--name-only", "--format=%s", "-1"],
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                ).stdout
                status = subprocess.run(
                    ["git", "status", "--short"],
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                ).stdout
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertIn("docs: complete plan 20260612-smoke", latest)
            self.assertIn("docs/plans/completed/20260612-smoke.md", latest)
            self.assertEqual("", status)

    def test_plan_run_can_use_isolated_worktree_branch(self) -> None:
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

            try:
                os.chdir(tmp_path)
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "config", "user.name", "GigaLphex Test"], check=True)

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, main(["--init"]))

                plan = tmp_path / "docs/plans/20260612-smoke.md"
                plan.parent.mkdir(parents=True)
                plan.write_text(
                    """# Plan: Smoke

### Task 1: Already done
- [x] Nothing left to do
""",
                    encoding="utf-8",
                )
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", "initial"], check=True, stdout=subprocess.PIPE)

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            str(plan),
                            "--worktree",
                            "--gigacode-command",
                            str(fake_gigacode),
                            "--tasks-only",
                            "--no-move-plan",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            worktree = tmp_path / ".gigalphex/worktrees/smoke"
            branch = subprocess.run(
                ["git", "-C", str(worktree), "branch", "--show-current"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            main_branch = subprocess.run(
                ["git", "-C", str(tmp_path), "branch", "--show-current"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            self.assertEqual(0, code)
            self.assertEqual("smoke", branch)
            self.assertNotEqual("smoke", main_branch)
            self.assertTrue((worktree / "docs/plans/20260612-smoke.md").exists())
            self.assertIn("progress log:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
