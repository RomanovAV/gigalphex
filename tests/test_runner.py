from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.executor import ExecResult
from gigalphex.progress import ProgressLog
from gigalphex.runner import RunOptions, Runner
from gigalphex.signals import REVIEW_DONE


class FakeExecutor:
    def __init__(self) -> None:
        self.batch_prompts = []
        self.single_prompts = []

    def run_batch(self, prompts):
        self.batch_prompts.append(prompts)
        return {
            name: ExecResult(output=f"{name}: NO FINDINGS\n", returncode=0)
            for name in prompts
        }

    def run(self, prompt):
        self.single_prompts.append(prompt)
        return ExecResult(output=REVIEW_DONE, signal=REVIEW_DONE, returncode=0)


class RunnerTest(unittest.TestCase):
    def test_parallel_review_runs_agents_then_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            executor = FakeExecutor()
            runner = Runner(
                RunOptions(
                    plan_file=None,
                    progress_file=tmp_path / "progress.txt",
                    review_only=True,
                    parallel_review=True,
                ),
                executor,  # type: ignore[arg-type]
                ProgressLog(tmp_path / "progress.txt"),
            )

            runner.run()

            self.assertEqual(1, len(executor.batch_prompts))
            self.assertEqual(
                {"quality", "implementation", "testing", "simplification", "documentation"},
                set(executor.batch_prompts[0]),
            )
            self.assertEqual(1, len(executor.single_prompts))
            self.assertIn("specialist review agents", executor.single_prompts[0])


class FailureDescriptionTest(unittest.TestCase):
    def test_describes_timeout_and_attempts(self) -> None:
        from gigalphex.runner import describe_failure

        message = describe_failure(
            "gigacode review agent quality",
            ExecResult(output="", returncode=-9, timed_out=True, attempts=3),
        )

        self.assertEqual("gigacode review agent quality timed out after 3 attempts", message)

    def test_describes_noninteractive_approval_failure(self) -> None:
        from gigalphex.runner import describe_failure

        message = describe_failure(
            "gigacode task session",
            ExecResult(
                output='Warning: Tool "run_shell_command" requires user approval but cannot execute in non-interactive mode\n',
                returncode=1,
            ),
        )

        self.assertEqual(
            "gigacode task session exited with status 1 "
            "(GigaCode requested shell approval in non-interactive mode)",
            message,
        )


if __name__ == "__main__":
    unittest.main()
