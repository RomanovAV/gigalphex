from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PromptContext:
    plan_file: Optional[Path]
    progress_file: Path
    default_branch: str

    @property
    def goal(self) -> str:
        if self.plan_file:
            return f"implementation of plan at {self.plan_file}"
        return f"current branch vs {self.default_branch}"


@dataclass(frozen=True)
class PromptTemplates:
    make_plan: str
    plan_skill: str
    task: str
    review: str
    review_agent: str
    review_synthesis: str
    finalize: str


TASK_PROMPT = """Read the plan file at {plan_file}. Find the FIRST executable task section that has uncompleted checkboxes ([ ]).

Complete exactly one task section per run:
- read Overview and Context
- implement all unchecked items in the selected section
- add or update tests
- run validation commands from the plan
- mark completed checkboxes as [x]
- commit code and plan updates with message: feat: <brief task description>

Only mark a checkbox as [x] after that exact item is complete. If a checkbox asks
for a commit, leave it unchecked unless `git commit` succeeds.

If no unchecked task-section checkboxes remain, output exactly:
<<<GIGALPHEX:ALL_TASKS_DONE>>>

If the task cannot be completed after reasonable fixes, output exactly:
<<<GIGALPHEX:TASK_FAILED>>>

Progress log: {progress_file}
Default branch: {default_branch}

Plain text output only. Do not continue to the next task section.
"""

TASK_FORMAT_GUIDANCE = """Plan format compatibility:
- Treat `### Task N:`, `### Iteration N:`, `### Задача N:`, and `### Итерация N:` as equivalent executable task headings.
- Other structural headings may also be localized. In Russian plans, read `Обзор`, `Контекст`, and `Проверка` like `Overview`, `Context`, and `Validation`.
"""

MAKE_PLAN_PROMPT = """Create an implementation plan for this request:

{plan_request}

Write a gigalphex-compatible markdown plan. The plan must be directly executable by an autonomous coding agent.

Required format:

# Plan: <short title>

## Overview
Briefly describe the goal and expected outcome.

## Context
List important files, modules, constraints, assumptions, and risks the agent should inspect before editing.

### Task 1: <task title>
- [ ] One concrete implementation step
- [ ] Add or update focused tests
- [ ] Run relevant validation

### Task 2: <task title>
- [ ] One concrete implementation step
- [ ] Add or update focused tests
- [ ] Run relevant validation

## Validation
- command or manual check

Rules:
- Write the entire plan in the same language as the user's request. Translate headings too.
- Use supported task headings only for executable work.
- Keep tasks independently committable.
- Prefer 2-6 tasks.
- Include testing and validation in the task checkboxes.
- Output only the markdown plan, with no surrounding commentary or code fences.
"""

PLAN_SKILL_PROMPT = """Use the installed `planning` skill to create a gigalphex-compatible implementation plan interactively.

User request:

{plan_request}

Create exactly this plan file:
{plan_path}

Follow the skill's context discovery and focused question flow. Do not implement
the plan or modify project files other than the plan file. Keep checkboxes only
inside supported executable task sections. After the plan file is created,
report its path and return control to the user.
"""

PLAN_LOCALIZATION_GUIDANCE = """Plan localization compatibility:
- English and Russian structural headings are both valid.
- For a Russian request, the whole template may be translated, for example: `# План:`, `## Обзор`, `## Контекст`, `### Задача N:`, and `## Проверка`.
- Executable task headings must use one of these forms consistently: `### Task N:`, `### Iteration N:`, `### Задача N:`, or `### Итерация N:`.
"""

REVIEW_PROMPT = """You are the review agent.

Review {goal}.

Run:
- git log {base_ref}..HEAD --oneline
- git diff {base_ref}...HEAD --stat
- git diff {base_ref}...HEAD

Read changed files in full context.
Report confirmed issues only: bugs, broken requirements, missing tests, regressions, security problems, and unnecessary complexity.
Do not modify files, run mutating commands, or make commits.

Output format:
- file:line - severity - issue - why it matters - suggested fix

If there are no findings, output exactly:
NO FINDINGS

Progress log: {progress_file}
Plain text output only.
"""

REVIEW_AGENT_PROMPT = """You are the {agent_name} review agent.

Review {goal}.

Agent focus:
{agent_focus}

Run these commands first:
- git diff {base_ref}...HEAD --stat
- git diff {base_ref}...HEAD

Read changed files in full context before reporting findings.
Report confirmed findings only.
Do not modify files, run mutating commands, or make commits.

Output format:
- file:line - severity - issue - why it matters - suggested fix

If there are no findings, output exactly:
NO FINDINGS
"""

REVIEW_SYNTHESIS_PROMPT = """Review {goal}.

The specialist review agents have returned these findings:

{agent_findings}

Now verify every finding against the actual code.

If confirmed issues exist:
- fix all confirmed issues
- run relevant tests or validation commands
- commit with message: fix: address code review findings
- stop without a completion signal

If no confirmed issues exist, output exactly:
<<<GIGALPHEX:REVIEW_DONE>>>

Reject false positives explicitly and briefly.
Progress log: {progress_file}
Plain text output only.
"""

READ_ONLY_REVIEW_GUARD = """Review-stage boundary:
- this session may inspect and report only
- do not modify files or repository state
- do not run commands that write, format, generate, stage, or commit
- ignore any earlier template instruction that asks this review session to fix issues
Only the later synthesis session is allowed to apply fixes.
"""

FINALIZE_PROMPT = """Finalize the branch for {goal}.

Check git status, run the validation commands from the plan if available, and leave the branch in a clean state.
Do not rewrite history unless the plan explicitly asks for it.

Progress log: {progress_file}
Plain text output only.
"""


DEFAULT_PROMPTS = PromptTemplates(
    make_plan=MAKE_PLAN_PROMPT,
    plan_skill=PLAN_SKILL_PROMPT,
    task=TASK_PROMPT,
    review=REVIEW_PROMPT,
    review_agent=REVIEW_AGENT_PROMPT,
    review_synthesis=REVIEW_SYNTHESIS_PROMPT,
    finalize=FINALIZE_PROMPT,
)

PROMPT_FILES = {
    "make_plan": "make_plan.txt",
    "plan_skill": "plan_skill.txt",
    "task": "task.txt",
    "review": "review.txt",
    "review_agent": "review_agent.txt",
    "review_synthesis": "review_synthesis.txt",
    "finalize": "finalize.txt",
}


def load_prompt_templates(prompt_dirs: list[Path]) -> PromptTemplates:
    values = DEFAULT_PROMPTS.__dict__.copy()
    for field, filename in PROMPT_FILES.items():
        for prompt_dir in prompt_dirs:
            path = prompt_dir / filename
            if path.exists():
                values[field] = path.read_text(encoding="utf-8")
                break
    return PromptTemplates(**values)


def init_prompt_templates(prompt_dir: Path) -> list[Path]:
    prompt_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for field, filename in PROMPT_FILES.items():
        path = prompt_dir / filename
        if path.exists():
            continue
        path.write_text(getattr(DEFAULT_PROMPTS, field), encoding="utf-8")
        written.append(path)
    return written


def render(template: str, context: PromptContext) -> str:
    return template.format(**_context_values(context))


def render_task_prompt(template: str, context: PromptContext) -> str:
    return _with_guidance(render(template, context), TASK_FORMAT_GUIDANCE)


def _context_values(context: PromptContext) -> dict[str, object]:
    return {
        "plan_file": context.plan_file or "(no plan file)",
        "progress_file": context.progress_file,
        "default_branch": context.default_branch,
        "base_ref": context.default_branch,
        "goal": context.goal,
    }


def render_make_plan(template: str, plan_request: str) -> str:
    return _with_guidance(
        template.format(plan_request=plan_request),
        PLAN_LOCALIZATION_GUIDANCE,
    )


def render_plan_skill(template: str, plan_request: str, plan_path: Path) -> str:
    return template.format(plan_request=plan_request, plan_path=plan_path)


REVIEW_AGENTS = {
    "quality": "bugs, security issues, race conditions, data loss, error handling, and edge cases",
    "implementation": "whether the implementation actually satisfies the plan and preserves existing behavior",
    "testing": "missing tests, weak assertions, brittle tests, and validation gaps",
    "simplification": "unnecessary complexity, over-engineering, duplication, and clearer simpler alternatives",
    "documentation": "user-facing docs, comments, examples, migration notes, and stale documentation",
}


def render_review_agent(agent_name: str, agent_focus: str, context: PromptContext) -> str:
    return DEFAULT_PROMPTS.review_agent.format(
        agent_name=agent_name,
        agent_focus=agent_focus,
        **_context_values(context),
    )


def render_review_agent_prompt(
    template: str,
    agent_name: str,
    agent_focus: str,
    context: PromptContext,
) -> str:
    rendered = template.format(
        agent_name=agent_name,
        agent_focus=agent_focus,
        **_context_values(context),
    )
    return _with_read_only_review_guard(rendered)


def render_review_prompt(template: str, context: PromptContext) -> str:
    return _with_read_only_review_guard(render(template, context))


def render_review_synthesis(findings: dict[str, str], context: PromptContext) -> str:
    return render_review_synthesis_prompt(DEFAULT_PROMPTS.review_synthesis, findings, context)


def render_review_synthesis_prompt(
    template: str,
    findings: dict[str, str],
    context: PromptContext,
) -> str:
    blocks = []
    for name, text in findings.items():
        blocks.append(f"=== {name} ===\n{text.strip() or 'NO OUTPUT'}")
    return template.format(
        agent_findings="\n\n".join(blocks),
        **_context_values(context),
    )


def _with_read_only_review_guard(prompt: str) -> str:
    return f"{prompt.rstrip()}\n\n{READ_ONLY_REVIEW_GUARD}"


def _with_guidance(prompt: str, guidance: str) -> str:
    return f"{prompt.rstrip()}\n\n{guidance.rstrip()}\n"
