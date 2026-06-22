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

    def test_parses_fully_localized_russian_plan(self) -> None:
        plan = parse_plan(
            """# План: Демо

## Обзор
Добавить новую возможность.

## Контекст
Сначала изучить существующую реализацию.

### Задача 1: Реализация
- [x] Готовый шаг
- [ ] Добавить код

### Итерация №2: Проверка
- [ ] Запустить тесты

## Проверка
- выполнить полный набор тестов
"""
        )

        self.assertEqual("План: Демо", plan.title)
        self.assertEqual([1, 2], [task.number for task in plan.tasks])
        self.assertEqual(["Реализация", "Проверка"], [task.title for task in plan.tasks])
        self.assertEqual(1, plan.first_uncompleted_task_index())

    def test_russian_task_header_is_case_insensitive(self) -> None:
        plan = parse_plan("### задача 1: Сделать\n- [ ] Шаг\n")

        self.assertEqual(1, len(plan.tasks))
        self.assertEqual(1, plan.tasks[0].number)

    def test_preserves_complete_task_section_text(self) -> None:
        plan = parse_plan(
            """# Plan: Demo

### Task 7: Build parser
Explain the approach.
- [ ] Implement it
```text
example
```

### Task 8: Follow-up
- [ ] Later work
"""
        )

        self.assertEqual(
            """### Task 7: Build parser
Explain the approach.
- [ ] Implement it
```text
example
```""",
            plan.tasks[0].section,
        )
        self.assertEqual(plan.tasks[0], plan.first_uncompleted_task())
        self.assertEqual([plan.tasks[0]], plan.tasks_matching(7, "Build parser"))


if __name__ == "__main__":
    unittest.main()
