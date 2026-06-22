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

from gigalphex.cli import (
    add_gigacode_args,
    build_parser,
    find_interactively_created_plan,
    main,
    should_auto_init,
    should_use_interactive_plan,
)


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class CliTest(unittest.TestCase):
    def test_extra_gigacode_args_are_inserted_before_prompt_option(self) -> None:
        self.assertEqual(
            [
                "--include-directories=/workspace/shared",
                "-p",
                "{prompt}",
                "--approval-mode=auto-edit",
                "--allowed-tools",
                "run_shell_command",
            ],
            add_gigacode_args(
                [
                    "-p",
                    "{prompt}",
                    "--approval-mode=auto-edit",
                    "--allowed-tools",
                    "run_shell_command",
                ],
                ["--include-directories=/workspace/shared"],
            ),
        )

    def test_extra_gigacode_args_do_not_split_legacy_prompt_flag_and_value(self) -> None:
        self.assertEqual(
            [
                "--include-directories=/workspace/shared",
                "-p",
                "{prompt}",
            ],
            add_gigacode_args(
                ["-p", "{prompt}"],
                ["--include-directories=/workspace/shared"],
            ),
        )

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
            self.assertTrue((home / ".config/gigalphex/prompts/plan_skill.txt").is_file())
            self.assertTrue((home / ".config/gigalphex/prompts/review_synthesis.txt").is_file())
            self.assertFalse((project / ".gigalphex/prompts").exists())

    def test_regular_command_falls_back_to_local_files_when_global_config_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.write_text("not a writable directory", encoding="utf-8")
            project = tmp_path / "project"
            project.mkdir()
            skills_dir = tmp_path / "skills"
            stdout = io.StringIO()
            stderr = io.StringIO()
            original_cwd = Path.cwd()

            try:
                os.chdir(project)
                with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(
                    stdout
                ), contextlib.redirect_stderr(stderr):
                    code = main(["--install-planning-skill", "--skill-dir", str(skills_dir)])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(0, code)
            self.assertTrue((skills_dir / "planning/SKILL.md").is_file())
            self.assertTrue((project / ".gigalphex/config").is_file())
            self.assertTrue((project / ".gigalphex/prompts/task.txt").is_file())
            self.assertTrue((project / ".gigalphex/prompts/plan_skill.txt").is_file())
            self.assertIn("installed planning skill", stdout.getvalue())
            self.assertEqual("", stderr.getvalue())

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

    def test_finalize_cli_defaults_to_config_and_can_be_disabled(self) -> None:
        parser = build_parser()

        self.assertIsNone(parser.parse_args([]).finalize)
        self.assertTrue(parser.parse_args(["--finalize"]).finalize)
        self.assertFalse(parser.parse_args(["--no-finalize"]).finalize)

    def test_quick_requires_plan(self) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            code = main(["--quick"])

        self.assertEqual(2, code)
        self.assertIn("--quick requires --plan", stderr.getvalue())

    def test_force_skill_install_requires_install_command(self) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            code = main(["--force-skill-install"])

        self.assertEqual(2, code)
        self.assertIn("--force-skill-install requires", stderr.getvalue())

    def test_interactive_plan_requires_tty_and_can_be_forced_quick(self) -> None:
        interactive_args = build_parser().parse_args(["--plan", "add demo"])
        quick_args = build_parser().parse_args(["--plan", "add demo", "--quick"])

        with patch("sys.stdin.isatty", return_value=True), patch(
            "sys.stdout.isatty",
            return_value=True,
        ):
            self.assertTrue(should_use_interactive_plan(interactive_args))
            self.assertFalse(should_use_interactive_plan(quick_args))

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
            self.assertTrue((tmp_path / ".gigalphex/prompts/task.txt").is_file())
            progress = (
                tmp_path / ".gigalphex/progress/progress-20260612-smoke.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("session=task event=prepared", progress)
            self.assertIn("session=task event=started", progress)
            self.assertIn("session=task event=first_output", progress)
            self.assertIn("session=task event=finished", progress)
            self.assertIn("prompt_transport=argv", progress)

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
            home = tmp_path / "home"
            home.write_text("not a writable directory", encoding="utf-8")
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
                with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(
                    stdout
                ), contextlib.redirect_stderr(stderr):
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
            self.assertTrue((tmp_path / ".gigalphex/prompts/task.txt").is_file())

    def test_interactive_plan_uses_planning_skill_and_existing_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            capture = tmp_path / "prompt.txt"
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import sys
prompt = "\\n".join(sys.argv[1:])
Path({str(capture)!r}).write_text(prompt)
marker = "Create exactly this plan file:\\n"
target = Path(prompt.split(marker, 1)[1].splitlines()[0])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("# Plan: Demo\\n\\n### Task 1: Build\\n- [ ] Do it\\n")
""",
            )
            installed_skill = home / ".gigacode/skills/planning/SKILL.md"
            installed_skill.parent.mkdir(parents=True)
            installed_skill.write_text("---\nname: planning\n---\n", encoding="utf-8")

            try:
                os.chdir(tmp_path)
                stdout = io.StringIO()
                with patch.dict(os.environ, {"HOME": str(home)}), patch(
                    "gigalphex.cli.should_use_interactive_plan",
                    return_value=True,
                ), contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            "--plan",
                            "add demo feature",
                            "--gigacode-command",
                            str(fake_gigacode),
                            "--gigacode-arg=--include-directories=/workspace/shared",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            plans = list((tmp_path / "docs/plans").glob("*.md"))
            prompt = capture.read_text(encoding="utf-8")
            self.assertEqual(0, code)
            self.assertEqual(1, len(plans))
            self.assertIn("--prompt-interactive", prompt)
            self.assertIn("--approval-mode=auto-edit", prompt)
            self.assertIn("--include-directories=/workspace/shared", prompt)
            self.assertIn("installed `planning` skill", prompt)
            self.assertIn("add demo feature", prompt)
            self.assertIn(str(plans[0].relative_to(tmp_path)), prompt)
            self.assertIn(f"created plan: {plans[0].relative_to(tmp_path)}", stdout.getvalue())

    def test_interactive_plan_reports_missing_planning_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                stderr = io.StringIO()
                with patch.dict(os.environ, {"HOME": str(home)}), patch(
                    "gigalphex.cli.should_use_interactive_plan",
                    return_value=True,
                ), contextlib.redirect_stderr(stderr):
                    code = main(["--plan", "add demo feature"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(2, code)
            self.assertIn("planning skill not found", stderr.getvalue())
            self.assertIn("--install-planning-skill", stderr.getvalue())
            self.assertIn("--quick", stderr.getvalue())
            self.assertFalse((tmp_path / ".gigalphex").exists())

    def test_install_planning_skill_to_explicit_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            skills_dir = tmp_path / "skills"
            stdout = io.StringIO()

            with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(stdout):
                code = main(["--install-planning-skill", "--skill-dir", str(skills_dir)])

            skill = skills_dir / "planning/SKILL.md"
            self.assertEqual(0, code)
            self.assertTrue(skill.is_file())
            self.assertIn("name: planning", skill.read_text(encoding="utf-8"))
            self.assertIn(f"installed planning skill: {skill}", stdout.getvalue())

    def test_install_planning_skill_preserves_modified_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            skills_dir = tmp_path / "skills"
            skill = skills_dir / "planning/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("custom skill\n", encoding="utf-8")
            stderr = io.StringIO()

            with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stderr(stderr):
                code = main(["--install-planning-skill", "--skill-dir", str(skills_dir)])

            self.assertEqual(1, code)
            self.assertEqual("custom skill\n", skill.read_text(encoding="utf-8"))
            self.assertIn("--force-skill-install", stderr.getvalue())

    def test_interactive_plan_accepts_one_new_file_when_skill_changes_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plans_dir = Path(tmp) / "docs/plans"
            plans_dir.mkdir(parents=True)
            existing = plans_dir / "existing.md"
            existing.write_text("# Existing\n", encoding="utf-8")
            expected = plans_dir / "expected.md"
            actual = plans_dir / "actual.md"
            actual.write_text("# Actual\n", encoding="utf-8")

            found = find_interactively_created_plan(expected, {existing})

            self.assertEqual(actual, found)

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
prompt = "\\n".join(sys.argv[1:]) + "\\nSTDIN\\n" + sys.stdin.read()
with Path({str(capture)!r}).open("a") as fh:
    fh.write(prompt)
if "specialist review agents have returned" in prompt:
    print("<<<GIGALPHEX:REVIEW_DONE>>>")
elif "Phase: final verification" in prompt:
    print("<<<GIGALPHEX:FINALIZE_DONE>>>")
else:
    print("NO FINDINGS")
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

    def test_review_uses_explicit_base_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            repo.mkdir()
            capture = tmp_path / "prompt.txt"
            home = tmp_path / "home"
            original_cwd = Path.cwd()
            fake_gigacode = write_script(
                tmp_path / "fake_gigacode.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import sys
prompt = "\\n".join(sys.argv[1:]) + "\\nSTDIN\\n" + sys.stdin.read()
with Path({str(capture)!r}).open("a") as fh:
    fh.write(prompt)
if "specialist review agents have returned" in prompt:
    print("<<<GIGALPHEX:REVIEW_DONE>>>")
elif "Phase: final verification" in prompt:
    print("<<<GIGALPHEX:FINALIZE_DONE>>>")
else:
    print("NO FINDINGS")
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
                subprocess.run(["git", "branch", "release"], check=True)

                stdout = io.StringIO()
                with patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stdout(stdout):
                    code = main(
                        [
                            "--review",
                            "--base-ref",
                            "release",
                            "--no-parallel-review",
                            "--gigacode-command",
                            str(fake_gigacode),
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            captured_prompt = capture.read_text(encoding="utf-8")
            self.assertEqual(0, code)
            self.assertIn("git diff release...HEAD", captured_prompt)
            self.assertIn("current branch vs release", captured_prompt)

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
elif "Phase: final verification" in prompt:
    print("<<<GIGALPHEX:FINALIZE_DONE>>>")
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
