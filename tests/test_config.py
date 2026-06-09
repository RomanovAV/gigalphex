from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import Config


class ConfigTest(unittest.TestCase):
    def test_default_args_enable_noninteractive_auto_edit(self) -> None:
        self.assertEqual(
            ["--prompt", "", "--approval-mode=auto-edit"],
            Config().resolved_args,
        )

    def test_resolved_default_args_are_copied(self) -> None:
        first = Config().resolved_args
        first.append("--include-directories")

        self.assertEqual(
            ["--prompt", "", "--approval-mode=auto-edit"],
            Config().resolved_args,
        )


if __name__ == "__main__":
    unittest.main()
