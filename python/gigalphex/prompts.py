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


TASK_PROMPT = """Read the plan file at {plan_file}. Find the FIRST Task section (### Task N: or ### Iteration N:) that has uncompleted checkboxes ([ ]).

Complete exactly one Task/Iteration section per run:
- read Overview and Context
- implement all unchecked items in the selected section
- add or update tests
- run validation commands from the plan
- mark completed checkboxes as [x]
- commit code and plan updates with message: feat: <brief task description>

If no unchecked Task/Iteration checkboxes remain, output exactly:
<<<RALPHEX:ALL_TASKS_DONE>>>

If the task cannot be completed after reasonable fixes, output exactly:
<<<RALPHEX:TASK_FAILED>>>

Progress log: {progress_file}
Default branch: {default_branch}

Plain text output only. Do not continue to the next task section.
"""

REVIEW_PROMPT = """Review {goal}.

Run:
- git log {default_branch}..HEAD --oneline
- git diff {default_branch}...HEAD

Find real issues only: bugs, broken requirements, missing tests, regressions, security problems, and unnecessary complexity.
Verify each finding in code before fixing it.

If confirmed issues exist:
- fix them
- run tests
- commit with message: fix: address code review findings
- stop without a completion signal

If no confirmed issues exist, output exactly:
<<<RALPHEX:REVIEW_DONE>>>

Progress log: {progress_file}
Plain text output only.
"""

REVIEW_AGENT_PROMPT = """You are the {agent_name} review agent.

Review {goal}.

Agent focus:
{agent_focus}

Run these commands first:
- git diff {default_branch}...HEAD --stat
- git diff {default_branch}...HEAD

Read changed files in full context before reporting findings.
Report confirmed findings only. Do not fix code. Do not make commits.

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
<<<RALPHEX:REVIEW_DONE>>>

Reject false positives explicitly and briefly.
Progress log: {progress_file}
Plain text output only.
"""

FINALIZE_PROMPT = """Finalize the branch for {goal}.

Check git status, run the validation commands from the plan if available, and leave the branch in a clean state.
Do not rewrite history unless the plan explicitly asks for it.

Progress log: {progress_file}
Plain text output only.
"""


def render(template: str, context: PromptContext) -> str:
    return template.format(
        plan_file=context.plan_file or "(no plan file)",
        progress_file=context.progress_file,
        default_branch=context.default_branch,
        goal=context.goal,
    )


REVIEW_AGENTS = {
    "quality": "bugs, security issues, race conditions, data loss, error handling, and edge cases",
    "implementation": "whether the implementation actually satisfies the plan and preserves existing behavior",
    "testing": "missing tests, weak assertions, brittle tests, and validation gaps",
    "simplification": "unnecessary complexity, over-engineering, duplication, and clearer simpler alternatives",
    "documentation": "user-facing docs, comments, examples, migration notes, and stale documentation",
}


def render_review_agent(agent_name: str, agent_focus: str, context: PromptContext) -> str:
    return REVIEW_AGENT_PROMPT.format(
        agent_name=agent_name,
        agent_focus=agent_focus,
        default_branch=context.default_branch,
        goal=context.goal,
    )


def render_review_synthesis(findings: dict[str, str], context: PromptContext) -> str:
    blocks = []
    for name, text in findings.items():
        blocks.append(f"=== {name} ===\n{text.strip() or 'NO OUTPUT'}")
    return REVIEW_SYNTHESIS_PROMPT.format(
        agent_findings="\n\n".join(blocks),
        progress_file=context.progress_file,
        goal=context.goal,
    )
