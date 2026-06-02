from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.executor import GigaCodeExecutor


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ExecutorTest(unittest.TestCase):
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
