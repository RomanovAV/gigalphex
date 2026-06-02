from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.plan import file_has_uncompleted_checkbox, parse_plan


class PlanParserTest(unittest.TestCase):
    def test_parses_tasks_and_ignores_fenced_checkboxes(self) -> None:
        plan = parse_plan(
            """# Plan: Demo

```md
- [ ] ignored
```

### Task 1: Build
- [x] done
- [ ] todo

## Notes
- [ ] not task

### Iteration 2: Verify
- [X] checked
"""
        )

        self.assertEqual("Plan: Demo", plan.title)
        self.assertEqual(2, len(plan.tasks))
        self.assertEqual(1, plan.first_uncompleted_task_index())
        self.assertTrue(plan.has_uncompleted_tasks())

    def test_file_has_uncompleted_checkbox_ignores_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text("- [ ] literal format [ ] example\n- [x] done\n", encoding="utf-8")
            self.assertFalse(file_has_uncompleted_checkbox(path))


if __name__ == "__main__":
    unittest.main()
