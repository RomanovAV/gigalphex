from pathlib import Path
import json
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.executor import ExecResult, GigaCodeExecutor


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ExecutorTest(unittest.TestCase):
    def test_default_gigacode_args_force_one_shot_auto_edit_prompt_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "capture.json"
            script = write_script(
                Path(tmp) / "capture.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import json
import sys
Path({str(output_file)!r}).write_text(json.dumps({{"argv": sys.argv[1:], "stdin": sys.stdin.read()}}))
print("ok")
""",
            )

            result = GigaCodeExecutor(command=str(script), output=lambda _line: None).run("prompt body")
            captured = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(
                ["-p", "prompt body", "--approval-mode=auto-edit", "--allowed-tools", "run_shell_command"],
                captured["argv"],
            )
            self.assertEqual("", captured["stdin"])

    def test_command_line_quotes_empty_prompt_arg(self) -> None:
        executor = GigaCodeExecutor(command="gigacode")

        self.assertEqual(
            "gigacode -p '<prompt>' --approval-mode=auto-edit --allowed-tools run_shell_command",
            executor.command_line(),
        )

    def test_custom_args_without_prompt_placeholder_use_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "capture.json"
            script = write_script(
                Path(tmp) / "capture.py",
                f"""#!/usr/bin/env python3
from pathlib import Path
import json
import sys
Path({str(output_file)!r}).write_text(json.dumps({{"argv": sys.argv[1:], "stdin": sys.stdin.read()}}))
print("ok")
""",
            )

            result = GigaCodeExecutor(command=str(script), args=["--plain"], output=lambda _line: None).run("prompt body")
            captured = json.loads(output_file.read_text(encoding="utf-8"))

            self.assertTrue(result.ok)
            self.assertEqual(["--plain"], captured["argv"])
            self.assertEqual("prompt body", captured["stdin"])

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
            output='Warning: Tool "run_shell_command" requires user approval but cannot execute in non-interactive mode\n',
            returncode=1,
        )

        self.assertTrue(result.approval_unavailable)

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


if __name__ == "__main__":
    unittest.main()
