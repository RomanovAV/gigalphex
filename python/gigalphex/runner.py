from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Optional

from .executor import ExecResult, GigaCodeExecutor
from .plan import file_has_uncompleted_checkbox, parse_plan_file
from .progress import ProgressLog
from .prompts import (
    DEFAULT_PROMPTS,
    REVIEW_AGENTS,
    PromptContext,
    PromptTemplates,
    render,
    render_review_agent_prompt,
    render_review_synthesis_prompt,
)
from .signals import ALL_TASKS_DONE, REVIEW_DONE, TASK_FAILED


@dataclass
class RunOptions:
    plan_file: Optional[Path]
    progress_file: Path
    default_branch: str = "main"
    max_iterations: int = 50
    review_iterations: int = 5
    tasks_only: bool = False
    review_only: bool = False
    finalize_enabled: bool = False
    dry_run: bool = False
    parallel_review: bool = True
    delay_seconds: float = 1.0
    prompts: PromptTemplates = field(default_factory=lambda: DEFAULT_PROMPTS)


class Runner:
    def __init__(self, options: RunOptions, executor: GigaCodeExecutor, log: ProgressLog) -> None:
        self.options = options
        self.executor = executor
        self.log = log

    def run(self) -> None:
        if self.options.dry_run:
            self.print_prompts()
            return
        if not self.options.review_only:
            self.run_tasks()
        if self.options.tasks_only:
            self.log.section("done")
            self.log.write("task execution completed\n")
            return
        self.run_review()
        if self.options.finalize_enabled:
            self.run_finalize()

    def run_tasks(self) -> None:
        if self.options.plan_file is None:
            raise ValueError("plan file is required for task execution")
        self._validate_plan_has_tasks()
        context = self._context()
        prompt = render(self.options.prompts.task, context)

        for iteration in range(1, self.options.max_iterations + 1):
            task_index = parse_plan_file(self.options.plan_file).first_uncompleted_task_index() or iteration
            self.log.section(f"task iteration {task_index}")
            result = self.executor.run(prompt)
            if not result.ok:
                raise RuntimeError(describe_failure("gigacode task session", result))
            if result.signal == TASK_FAILED:
                raise RuntimeError("task failed")
            if result.signal == ALL_TASKS_DONE and not self._has_uncompleted_work():
                return
            if not self._has_uncompleted_work():
                return
            time.sleep(self.options.delay_seconds)
        raise RuntimeError(f"max task iterations reached: {self.options.max_iterations}")

    def run_review(self) -> None:
        if self.options.parallel_review:
            self.run_parallel_review()
            return

        context = self._context()
        prompt = render(self.options.prompts.review, context)
        for iteration in range(1, self.options.review_iterations + 1):
            self.log.section(f"review iteration {iteration}")
            result = self.executor.run(prompt)
            if not result.ok:
                raise RuntimeError(describe_failure("gigacode review session", result))
            if result.signal == TASK_FAILED:
                raise RuntimeError("review failed")
            if result.signal == REVIEW_DONE:
                return
            time.sleep(self.options.delay_seconds)
        raise RuntimeError(f"max review iterations reached: {self.options.review_iterations}")

    def run_parallel_review(self) -> None:
        context = self._context()
        for iteration in range(1, self.options.review_iterations + 1):
            self.log.section(f"parallel review iteration {iteration}")
            prompts = {
                name: render_review_agent_prompt(self.options.prompts.review_agent, name, focus, context)
                for name, focus in REVIEW_AGENTS.items()
            }
            results = self.executor.run_batch(prompts)
            findings: dict[str, str] = {}
            for name in REVIEW_AGENTS:
                result = results[name]
                self.log.section(f"review agent: {name}")
                self.log.write(result.output)
                findings[name] = result.output
                if not result.ok:
                    raise RuntimeError(describe_failure(f"gigacode review agent {name}", result))

            self.log.section("review synthesis")
            synthesis = self.executor.run(
                render_review_synthesis_prompt(self.options.prompts.review_synthesis, findings, context)
            )
            if not synthesis.ok:
                raise RuntimeError(describe_failure("gigacode review synthesis", synthesis))
            if synthesis.signal == TASK_FAILED:
                raise RuntimeError("review failed")
            if synthesis.signal == REVIEW_DONE:
                return
            time.sleep(self.options.delay_seconds)
        raise RuntimeError(f"max review iterations reached: {self.options.review_iterations}")

    def run_finalize(self) -> None:
        self.log.section("finalize")
        result = self.executor.run(render(self.options.prompts.finalize, self._context()))
        if not result.ok:
            raise RuntimeError(describe_failure("gigacode finalize session", result))

    def print_prompts(self) -> None:
        context = self._context()
        if not self.options.review_only:
            self.log.section("task prompt")
            self.log.stream(render(self.options.prompts.task, context))
            self.log.stream("\n")
        if not self.options.tasks_only:
            self.log.section("review prompt")
            if self.options.parallel_review:
                for name, focus in REVIEW_AGENTS.items():
                    self.log.stream(f"\n--- review agent: {name} ---\n")
                    self.log.stream(
                        render_review_agent_prompt(self.options.prompts.review_agent, name, focus, context)
                    )
                self.log.stream("\n--- review synthesis prompt uses collected agent findings ---\n")
            else:
                self.log.stream(render(self.options.prompts.review, context))
                self.log.stream("\n")
        if self.options.finalize_enabled:
            self.log.section("finalize prompt")
            self.log.stream(render(self.options.prompts.finalize, context))
            self.log.stream("\n")

    def _context(self) -> PromptContext:
        return PromptContext(
            plan_file=self.options.plan_file,
            progress_file=self.options.progress_file,
            default_branch=self.options.default_branch,
        )

    def _validate_plan_has_tasks(self) -> None:
        assert self.options.plan_file is not None
        plan = parse_plan_file(self.options.plan_file)
        if not plan.tasks:
            raise ValueError(f"plan file has no executable task sections: {self.options.plan_file}")

    def _has_uncompleted_work(self) -> bool:
        assert self.options.plan_file is not None
        plan = parse_plan_file(self.options.plan_file)
        if plan.tasks:
            return plan.has_uncompleted_tasks()
        return file_has_uncompleted_checkbox(self.options.plan_file)


def describe_failure(label: str, result: ExecResult) -> str:
    parts = [label]
    if result.timed_out:
        parts.append("timed out")
    else:
        parts.append(f"exited with status {result.returncode}")
    if result.approval_unavailable:
        parts.append("(GigaCode requested shell approval in non-interactive mode)")
    if result.attempts > 1:
        parts.append(f"after {result.attempts} attempts")
    return " ".join(parts)
