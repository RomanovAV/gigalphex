from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.config import init_project_config, init_project_prompt_templates
from gigalphex.prompts import (
    DEFAULT_PROMPTS,
    PromptContext,
    load_prompt_templates,
    render_make_plan,
    render_plan_skill,
    render_review_prompt,
    render_review_synthesis_prompt,
    render_task_prompt,
)


class PromptTemplatesTest(unittest.TestCase):
    def test_make_plan_prompt_preserves_request_language(self) -> None:
        self.assertIn("Write the entire plan in the same language as the user's request.", DEFAULT_PROMPTS.make_plan)

    def test_make_plan_render_allows_fully_localized_russian_template(self) -> None:
        prompt = render_make_plan("Создай план для запроса:\n{plan_request}", "добавить поиск")

        self.assertIn("добавить поиск", prompt)
        self.assertIn("`### Задача N:`", prompt)
        self.assertIn("`## Обзор`", prompt)

    def test_plan_skill_prompt_includes_request_and_exact_target(self) -> None:
        prompt = render_plan_skill(
            DEFAULT_PROMPTS.plan_skill,
            "добавить поиск",
            Path("docs/plans/20260620-search.md"),
        )

        self.assertIn("installed `planning` skill", prompt)
        self.assertIn("добавить поиск", prompt)
        self.assertIn("docs/plans/20260620-search.md", prompt)
        self.assertIn("Do not implement", prompt)

    def test_task_render_supports_russian_headings_for_custom_templates(self) -> None:
        prompt = render_task_prompt(
            "Выполни план {plan_file}.",
            PromptContext(Path("docs/plans/demo.md"), Path("progress.txt"), "main"),
        )

        self.assertIn("Выполни план docs/plans/demo.md.", prompt)
        self.assertIn("`### Задача N:`", prompt)
        self.assertIn("`Контекст`", prompt)

    def test_loads_local_prompt_over_embedded_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp) / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "task.txt").write_text("custom task {plan_file}", encoding="utf-8")

            prompts = load_prompt_templates([prompt_dir])

            self.assertEqual("custom task {plan_file}", prompts.task)
            self.assertEqual(DEFAULT_PROMPTS.review, prompts.review)

    def test_local_prompt_overrides_global_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "local"
            global_dir = tmp_path / "global"
            local_dir.mkdir()
            global_dir.mkdir()
            (local_dir / "task.txt").write_text("local task {plan_file}", encoding="utf-8")
            (global_dir / "task.txt").write_text("global task {plan_file}", encoding="utf-8")
            (global_dir / "review.txt").write_text("global review {goal}", encoding="utf-8")

            prompts = load_prompt_templates([local_dir, global_dir])

            self.assertEqual("local task {plan_file}", prompts.task)
            self.assertEqual("global review {goal}", prompts.review)

    def test_review_synthesis_template_gets_full_context(self) -> None:
        prompt = render_review_synthesis_prompt(
            "{default_branch} {base_ref} {progress_file} {goal}",
            {"quality": "NO FINDINGS"},
            PromptContext(None, Path("progress.txt"), "master"),
        )

        self.assertEqual("master master progress.txt current branch vs master", prompt)

    def test_review_prompt_appends_read_only_guard_to_custom_templates(self) -> None:
        prompt = render_review_prompt(
            "Review {goal}. Fix issues and commit them.",
            PromptContext(None, Path("progress.txt"), "develop"),
        )

        self.assertTrue(prompt.startswith("Review current branch vs develop. Fix issues and commit them."))
        self.assertIn("ignore any earlier template instruction", prompt)
        self.assertIn("Only the later synthesis session is allowed to apply fixes.", prompt)

    def test_init_project_config_does_not_create_local_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / ".gigalphex"

            written = init_project_config(base_dir)

            self.assertTrue((base_dir / "config").exists())
            self.assertTrue((Path(tmp) / ".gitignore").exists())
            self.assertIn(".DS_Store", (Path(tmp) / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn(".gigalphex/progress/", (Path(tmp) / ".gitignore").read_text(encoding="utf-8"))
            self.assertFalse((base_dir / "prompts").exists())
            self.assertNotIn(base_dir / "prompts", written)

    def test_init_project_prompts_writes_templates_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / ".gigalphex"
            prompt_dir = base_dir / "prompts"
            prompt_dir.mkdir(parents=True)
            existing = prompt_dir / "task.txt"
            existing.write_text("keep me", encoding="utf-8")

            written = init_project_prompt_templates(base_dir)

            self.assertEqual("keep me", existing.read_text(encoding="utf-8"))
            self.assertTrue((prompt_dir / "make_plan.txt").exists())
            self.assertTrue((prompt_dir / "plan_skill.txt").exists())
            self.assertIn(
                "Write the entire plan in the same language as the user's request.",
                (prompt_dir / "make_plan.txt").read_text(encoding="utf-8"),
            )
            self.assertTrue((prompt_dir / "review.txt").exists())
            self.assertNotIn(existing, written)

    def test_init_project_config_appends_missing_gitignore_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / ".gigalphex"
            gitignore = Path(tmp) / ".gitignore"
            gitignore.write_text("build/\n", encoding="utf-8")

            init_project_config(base_dir)

            self.assertEqual(
                "build/\n.DS_Store\n.gigalphex/progress/\n.gigalphex/worktrees/\n",
                gitignore.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
