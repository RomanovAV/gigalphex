from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import Config, load_config


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
