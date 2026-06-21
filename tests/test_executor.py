from pathlib import Path
import json
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.executor import ExecResult, GigaCodeExecutor


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ExecutorTest(unittest.TestCase):
    def test_default_gigacode_args_use_explicit_prompt_option(self) -> None:
        with patch("subprocess.Popen") as popen:
            process = popen.return_value
            process.stdout = MagicMock()
            process.stdout.__iter__.return_value = iter(["ok\n"])
            process.wait.return_value = 0
            process.poll.return_value = 0

            result = GigaCodeExecutor(
                command="gigacode",
                output=lambda _line: None,
            ).run("prompt body")

        self.assertTrue(result.ok)
        popen.assert_called_once()
        self.assertEqual(
            [
                "gigacode",
                "--approval-mode=auto-edit",
                "--allowed-tools",
                "run_shell_command",
                "-p",
                "prompt body",
            ],
            popen.call_args.args[0],
        )
        self.assertIsNone(popen.call_args.kwargs["stdin"])

    def test_command_line_quotes_empty_prompt_arg(self) -> None:
        executor = GigaCodeExecutor(command="gigacode")

        self.assertEqual(
            "gigacode --approval-mode=auto-edit "
            "--allowed-tools run_shell_command -p '<prompt>'",
            executor.command_line(),
        )

    def test_prompt_remains_one_exact_argv_value_after_policy_options(self) -> None:
        prompt = "first line\nsecond line with 'quotes' and \"double quotes\""
        with patch("subprocess.Popen") as popen:
            process = popen.return_value
            process.stdout = MagicMock()
            process.stdout.__iter__.return_value = iter([])
            process.wait.return_value = 0
            process.poll.return_value = 0

            result = GigaCodeExecutor(
                command="gigacode",
                output=lambda _line: None,
            ).run(prompt)

        self.assertTrue(result.ok)
        argv = popen.call_args.args[0]
        self.assertEqual("-p", argv[-2])
        self.assertEqual(prompt, argv[-1])
        self.assertEqual(1, argv.count(prompt))
        self.assertIsNone(popen.call_args.kwargs["stdin"])

    def test_diagnostics_record_stages_without_prompt_contents(self) -> None:
        prompt = "SECRET PROMPT\nwith multiple lines"
        diagnostics: list[str] = []
        with patch("subprocess.Popen") as popen:
            process = popen.return_value
            process.pid = 12345
            process.stdout = MagicMock()
            process.stdout.__iter__.return_value = iter(["ok\n"])
            process.wait.return_value = 0
            process.poll.return_value = 0

            result = GigaCodeExecutor(
                command="gigacode",
                output=lambda _line: None,
                diagnostic=diagnostics.append,
                name="task",
            ).run(prompt)

        self.assertTrue(result.ok)
        joined = "\n".join(diagnostics)
        self.assertIn("session=task event=attempt_started", joined)
        self.assertIn("session=task event=prepared", joined)
        self.assertIn("prompt_transport=argv", joined)
        self.assertIn(f"prompt_chars={len(prompt)}", joined)
        self.assertIn("session=task event=started pid=12345", joined)
        self.assertIn("session=task event=first_output", joined)
        self.assertIn("session=task event=finished", joined)
        self.assertIn("session=task event=attempt_succeeded", joined)
        self.assertNotIn(prompt, joined)
        self.assertNotIn("SECRET PROMPT", joined)

    def test_batch_diagnostics_identify_each_session(self) -> None:
        diagnostics: list[str] = []
        executor = GigaCodeExecutor(
            diagnostic=diagnostics.append,
            name="review-agent",
            max_workers=2,
        )
        success = ExecResult(output="NO FINDINGS\n", returncode=0)

        with patch.object(executor, "_run_once", return_value=success):
            results = executor.run_batch(
                {
                    "quality": "quality prompt",
                    "testing": "testing prompt",
                }
            )

        self.assertEqual({"quality", "testing"}, set(results))
        joined = "\n".join(diagnostics)
        self.assertIn("session=review-agent:quality event=attempt_started", joined)
        self.assertIn("session=review-agent:testing event=attempt_started", joined)

    def test_custom_args_without_prompt_placeholder_append_prompt_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "capture.json"
            script = write_script(
                Path(tmp) / "capture.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import json
import sys
Path({str(output_file)!r}).write_text(json.dumps({{"argv": sys.argv[1:]}}))
print("ok")
""",
            )

            result = GigaCodeExecutor(
                command=str(script),
                args=["--debug"],
                output=lambda _line: None,
            ).run("prompt body")
            captured = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(["--debug", "-p", "prompt body"], captured["argv"])

    def test_command_line_shows_appended_prompt_option(self) -> None:
        executor = GigaCodeExecutor(command="gigacode", args=["--debug"])

        self.assertEqual("gigacode --debug -p '<prompt>'", executor.command_line())

    def test_legacy_prompt_flag_can_embed_prompt_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "capture.json"
            script = write_script(
                Path(tmp) / "capture.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import json
import sys
Path({str(output_file)!r}).write_text(json.dumps({{"argv": sys.argv[1:]}}))
print("ok")
""",
            )

            result = GigaCodeExecutor(
                command=str(script),
                args=["--prompt={prompt}"],
                output=lambda _line: None,
            ).run("prompt body")
            captured = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(["--prompt=prompt body"], captured["argv"])

    def test_interactive_run_passes_initial_prompt_as_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "capture.json"
            script = write_script(
                Path(tmp) / "capture.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import json
import sys
Path({str(output_file)!r}).write_text(json.dumps({{"argv": sys.argv[1:]}}))
""",
            )

            result = GigaCodeExecutor(
                command=str(script),
                args=["--prompt-interactive", "{prompt}"],
            ).run_interactive("use planning skill")
            captured = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(
                ["--prompt-interactive", "use planning skill"],
                captured["argv"],
            )

    def test_interactive_run_requires_prompt_placeholder(self) -> None:
        executor = GigaCodeExecutor(command="gigacode", args=["--prompt-interactive"])

        with self.assertRaisesRegex(ValueError, "must include \\{prompt\\}"):
            executor.run_interactive("use planning skill")

    def test_adds_trailing_newline_to_streamed_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = write_script(
                Path(tmp) / "no_newline.py",
                """#!/usr/bin/env python3
import sys
sys.stdin.read()
sys.stdout.write("no newline")
""",
            )
            chunks = []

            result = GigaCodeExecutor(command=str(script), output=chunks.append).run("prompt")

            self.assertTrue(result.ok)
            self.assertEqual("no newline\n", result.output)
            self.assertEqual(["no newline", "\n"], chunks)

    def test_detects_noninteractive_approval_warning(self) -> None:
        result = ExecResult(
            output='Warning: Tool "write_file" requires user approval but cannot execute in non-interactive mode\n',
            returncode=0,
        )

        self.assertTrue(result.approval_unavailable)
        self.assertFalse(result.ok)

    def test_does_not_retry_noninteractive_approval_failure(self) -> None:
        executor = GigaCodeExecutor(
            retry_count=3,
            retry_delay=0,
            output=lambda _line: None,
        )
        approval_failure = ExecResult(
            output=(
                'Warning: Tool "run_shell_command" requires user approval '
                "but cannot execute in non-interactive mode\n"
            ),
            returncode=0,
        )

        with patch.object(executor, "_run_once", return_value=approval_failure) as run_once:
            result = executor.run("prompt")

        self.assertFalse(result.ok)
        self.assertTrue(result.approval_unavailable)
        self.assertEqual(1, result.attempts)
        run_once.assert_called_once()

    def test_kills_session_on_first_noninteractive_approval_warning(self) -> None:
        warning = (
            'Warning: Tool "run_shell_command" requires user approval '
            "but cannot execute in non-interactive mode.\n"
        )
        with patch("subprocess.Popen") as popen:
            process = popen.return_value
            process.stdout = MagicMock()
            process.stdout.__iter__.return_value = iter([warning])
            process.poll.return_value = None
            process.wait.return_value = -9

            result = GigaCodeExecutor(
                command="gigacode",
                output=lambda _line: None,
            ).run("prompt")

        process.kill.assert_called_once_with()
        self.assertTrue(result.approval_unavailable)
        self.assertFalse(result.ok)

    def test_diagnostics_record_approval_stop_reason(self) -> None:
        diagnostics: list[str] = []
        warning = (
            'Warning: Tool "run_shell_command" requires user approval '
            "but cannot execute in non-interactive mode.\n"
        )
        with patch("subprocess.Popen") as popen:
            process = popen.return_value
            process.pid = 77
            process.stdout = MagicMock()
            process.stdout.__iter__.return_value = iter([warning])
            process.poll.return_value = None
            process.wait.return_value = -9

            result = GigaCodeExecutor(
                command="gigacode",
                output=lambda _line: None,
                diagnostic=diagnostics.append,
                name="task",
                retry_count=2,
            ).run("prompt")

        self.assertFalse(result.ok)
        joined = "\n".join(diagnostics)
        self.assertIn("event=approval_warning_detected", joined)
        self.assertIn("event=terminating reason=approval_unavailable", joined)
        self.assertIn(
            "event=retry_stopped attempt=1 reason=approval_unavailable",
            joined,
        )
        self.assertNotIn("event=retry_scheduled", joined)

    def test_retries_failed_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            marker = tmp_path / "attempts"
            script = write_script(
                tmp_path / "flaky.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import sys
marker = Path({str(marker)!r})
attempt = int(marker.read_text() or "0") if marker.exists() else 0
marker.write_text(str(attempt + 1))
sys.stdin.read()
if attempt == 0:
    print("temporary failure")
    raise SystemExit(7)
print("ok")
""",
            )

            result = GigaCodeExecutor(
                command=str(script),
                retry_count=1,
                retry_delay=0,
                output=lambda _line: None,
            ).run("prompt")

            self.assertTrue(result.ok)
            self.assertEqual(2, result.attempts)
            self.assertIn("ok", result.output)

    def test_marks_transient_retry_pattern_on_failed_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = write_script(
                Path(tmp) / "transient.py",
                """#!/usr/bin/env python3
import sys
sys.stdin.read()
print("API Error: 503")
raise SystemExit(7)
""",
            )

            result = GigaCodeExecutor(
                command=str(script),
                retry_count=0,
                output=lambda _line: None,
            ).run("prompt")

            self.assertTrue(result.transient_error)
            self.assertFalse(result.ok)

    def test_rate_limit_uses_configured_wait_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            marker = tmp_path / "attempts"
            script = write_script(
                tmp_path / "rate_limited.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import sys
marker = Path({str(marker)!r})
attempt = int(marker.read_text() or "0") if marker.exists() else 0
marker.write_text(str(attempt + 1))
sys.stdin.read()
if attempt == 0:
    print("429 Too Many Requests")
    raise SystemExit(1)
print("ok")
""",
            )

            start = time.monotonic()
            result = GigaCodeExecutor(
                command=str(script),
                retry_count=1,
                retry_delay=0,
                wait_on_rate_limit=0.02,
                output=lambda _line: None,
            ).run("prompt")

            self.assertGreaterEqual(time.monotonic() - start, 0.02)
            self.assertTrue(result.ok)
            self.assertEqual(2, result.attempts)
            self.assertIn("ok", result.output)

    def test_timeout_marks_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = write_script(
                Path(tmp) / "slow.py",
                """#!/usr/bin/env python3
import sys
import time
sys.stdin.read()
time.sleep(5)
""",
            )

            start = time.monotonic()
            result = GigaCodeExecutor(
                command=str(script),
                timeout=1,
                output=lambda _line: None,
            ).run("prompt")

            self.assertLess(time.monotonic() - start, 3)
            self.assertTrue(result.timed_out)
            self.assertFalse(result.ok)

    def test_idle_timeout_marks_result_after_silent_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = write_script(
                Path(tmp) / "silent.py",
                """#!/usr/bin/env python3
import sys
import time
sys.stdin.read()
print("working", flush=True)
time.sleep(5)
""",
            )

            start = time.monotonic()
            result = GigaCodeExecutor(
                command=str(script),
                timeout=5,
                idle_timeout=1,
                output=lambda _line: None,
            ).run("prompt")

            self.assertLess(time.monotonic() - start, 3)
            self.assertTrue(result.idle_timed_out)
            self.assertFalse(result.timed_out)
            self.assertFalse(result.ok)
            self.assertIn("working", result.output)


if __name__ == "__main__":
    unittest.main()
