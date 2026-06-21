from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.diagnose import _argv


class DiagnoseTest(unittest.TestCase):
    def test_uses_confirmed_gigacode_arguments(self) -> None:
        self.assertEqual(
            [
                "gigacode",
                "-p",
                "check shell",
                "--approval-mode=auto-edit",
                "--allowed-tools",
                "run_shell_command",
            ],
            _argv("check shell"),
        )


if __name__ == "__main__":
    unittest.main()
