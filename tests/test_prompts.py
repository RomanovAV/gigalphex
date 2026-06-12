from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import init_project_config
from gigalphex.prompts import DEFAULT_PROMPTS, load_prompt_templates


class PromptTemplatesTest(unittest.TestCase):
    def test_loads_local_prompt_over_embedded_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp) / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "task.txt").write_text("custom task {plan_file}", encoding="utf-8")

            prompts = load_prompt_templates([prompt_dir])

            self.assertEqual("custom task {plan_file}", prompts.task)
            self.assertEqual(DEFAULT_PROMPTS.review, prompts.review)

    def test_init_project_config_writes_templates_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / ".gigalphex"
            prompt_dir = base_dir / "prompts"
            prompt_dir.mkdir(parents=True)
            existing = prompt_dir / "task.txt"
            existing.write_text("keep me", encoding="utf-8")

            written = init_project_config(base_dir)

            self.assertTrue((base_dir / "config").exists())
            self.assertEqual("keep me", existing.read_text(encoding="utf-8"))
            self.assertTrue((prompt_dir / "review.txt").exists())
            self.assertNotIn(existing, written)


if __name__ == "__main__":
    unittest.main()
