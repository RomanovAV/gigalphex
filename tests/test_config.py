from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import Config


class ConfigTest(unittest.TestCase):
    def test_default_args_enable_noninteractive_auto_edit(self) -> None:
        self.assertEqual(
            ["-p", "{prompt}", "--approval-mode=auto-edit", "--allowed-tools", "run_shell_command"],
            Config().resolved_args,
        )

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
