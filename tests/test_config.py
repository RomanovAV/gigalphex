from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import Config, init_global_config, init_global_prompt_templates, load_config


class ConfigTest(unittest.TestCase):
    def test_default_args_enable_noninteractive_auto_edit(self) -> None:
        self.assertEqual(
            ["-p", "{prompt}", "--approval-mode=auto-edit", "--allowed-tools", "run_shell_command"],
            Config().resolved_args,
        )

    def test_created_plans_are_committed_by_default(self) -> None:
        self.assertTrue(Config().commit_plan_on_creation)

    def test_worktree_is_disabled_by_default(self) -> None:
        self.assertFalse(Config().worktree)

    def test_default_branch_is_auto_detected_by_default(self) -> None:
        self.assertEqual("", Config().default_branch)

    def test_idle_timeout_defaults_to_fifteen_minutes(self) -> None:
        self.assertEqual(900, Config().idle_timeout)

    def test_retry_count_defaults_to_one_retry(self) -> None:
        self.assertEqual(1, Config().retry_count)

    def test_retry_delay_defaults_to_five_seconds(self) -> None:
        self.assertEqual(5.0, Config().retry_delay)

    def test_retry_patterns_include_transient_http_errors(self) -> None:
        self.assertIn("API Error: 503", Config().retry_patterns)

    def test_rate_limit_patterns_include_429(self) -> None:
        self.assertIn("429 Too Many Requests", Config().rate_limit_patterns)

    def test_load_config_reads_retry_pattern_lists_and_rate_limit_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            config.write_text(
                """[gigalphex]
retry_patterns = temporary one, temporary two
rate_limit_patterns = limit one, limit two
wait_on_rate_limit = 12.5
""",
                encoding="utf-8",
            )

            cfg = load_config(config)

            self.assertEqual(["temporary one", "temporary two"], cfg.retry_patterns)
            self.assertEqual(["limit one", "limit two"], cfg.rate_limit_patterns)
            self.assertEqual(12.5, cfg.wait_on_rate_limit)

    def test_local_config_overrides_global_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            project = tmp_path / "project"
            global_dir = home / ".config/gigalphex"
            local_dir = project / ".gigalphex"
            global_dir.mkdir(parents=True)
            local_dir.mkdir(parents=True)
            (global_dir / "config").write_text(
                "[gigalphex]\ntask_model = global-task\nreview_workers = 2\n",
                encoding="utf-8",
            )
            (local_dir / "config").write_text(
                "[gigalphex]\ntask_model = local-task\n",
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            try:
                os.chdir(project)
                with patch.dict(os.environ, {"HOME": str(home)}):
                    cfg = load_config()
            finally:
                os.chdir(original_cwd)

            self.assertEqual("local-task", cfg.task_model)
            self.assertEqual(2, cfg.review_workers)

    def test_explicit_config_overrides_local_and_global_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            project = tmp_path / "project"
            explicit = tmp_path / "explicit-config"
            global_dir = home / ".config/gigalphex"
            local_dir = project / ".gigalphex"
            global_dir.mkdir(parents=True)
            local_dir.mkdir(parents=True)
            (global_dir / "config").write_text(
                "[gigalphex]\ntask_model = global-task\n",
                encoding="utf-8",
            )
            (local_dir / "config").write_text(
                "[gigalphex]\ntask_model = local-task\n",
                encoding="utf-8",
            )
            explicit.write_text(
                "[gigalphex]\ntask_model = explicit-task\n",
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            try:
                os.chdir(project)
                with patch.dict(os.environ, {"HOME": str(home)}):
                    cfg = load_config(explicit)
            finally:
                os.chdir(original_cwd)

            self.assertEqual("explicit-task", cfg.task_model)

    def test_init_global_config_creates_commented_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with patch.dict(os.environ, {"HOME": str(home)}):
                written = init_global_config()

            config = home / ".config/gigalphex/config"
            self.assertEqual([config], written)
            self.assertTrue(config.is_file())
            text = config.read_text(encoding="utf-8")
            self.assertIn("[gigalphex]", text)
            self.assertIn("# task_model =", text)
            self.assertIn("# review_workers = 5", text)

    def test_init_global_config_does_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config = home / ".config/gigalphex/config"
            config.parent.mkdir(parents=True)
            config.write_text("[gigalphex]\ntask_model = keep-me\n", encoding="utf-8")

            with patch.dict(os.environ, {"HOME": str(home)}):
                written = init_global_config()

            self.assertEqual([], written)
            self.assertEqual(
                "[gigalphex]\ntask_model = keep-me\n",
                config.read_text(encoding="utf-8"),
            )

    def test_init_global_prompts_creates_templates_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            prompt_dir = home / ".config/gigalphex/prompts"
            prompt_dir.mkdir(parents=True)
            existing = prompt_dir / "task.txt"
            existing.write_text("keep global task", encoding="utf-8")

            with patch.dict(os.environ, {"HOME": str(home)}):
                written = init_global_prompt_templates()

            self.assertEqual("keep global task", existing.read_text(encoding="utf-8"))
            self.assertTrue((prompt_dir / "make_plan.txt").is_file())
            self.assertTrue((prompt_dir / "review_agent.txt").is_file())
            self.assertNotIn(existing, written)

    def test_resolved_default_args_are_copied(self) -> None:
        first = Config().resolved_args
        first.append("--include-directories")

        self.assertEqual(
            ["-p", "{prompt}", "--approval-mode=auto-edit", "--allowed-tools", "run_shell_command"],
            Config().resolved_args,
        )

    def test_phase_args_add_model_flag_before_prompt_args(self) -> None:
        cfg = Config(task_model="fast-task", review_model="strong-review")

        self.assertEqual(
            [
                "--model",
                "strong-review",
                "-p",
                "{prompt}",
                "--approval-mode=auto-edit",
                "--allowed-tools",
                "run_shell_command",
            ],
            cfg.args_for_phase("review"),
        )

    def test_review_model_falls_back_to_task_model(self) -> None:
        cfg = Config(task_model="shared-model")

        self.assertEqual(
            [
                "--model",
                "shared-model",
                "-p",
                "{prompt}",
                "--approval-mode=auto-edit",
                "--allowed-tools",
                "run_shell_command",
            ],
            cfg.args_for_phase("review"),
        )


if __name__ == "__main__":
    unittest.main()
