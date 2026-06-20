from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional


TASK_HEADER_RE = re.compile(
    r"^###\s+(?:Task|Iteration|Задача|Итерация)\s+(?:№\s*)?([^:]+?):\s*(.*)$",
    re.IGNORECASE,
)
CHECKBOX_RE = re.compile(r"^\s*-\s+\[([ xX])\]\s*(.*)$")
TITLE_RE = re.compile(r"^#\s+(.*)$")
FORMAT_IN_TEXT_RE = re.compile(r"\[\s*[ xX]?\s*\]")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*\r?$")


@dataclass(frozen=True)
class Checkbox:
    text: str
    checked: bool

    @property
    def actionable(self) -> bool:
        return FORMAT_IN_TEXT_RE.search(self.text) is None


@dataclass
class Task:
    number: int
    title: str
    checkboxes: list[Checkbox] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.has_uncompleted_actionable_work()

    def has_uncompleted_actionable_work(self) -> bool:
        return any(not cb.checked and cb.actionable for cb in self.checkboxes)


@dataclass
class Plan:
    title: str = ""
    tasks: list[Task] = field(default_factory=list)

    def first_uncompleted_task_index(self) -> Optional[int]:
        for index, task in enumerate(self.tasks, start=1):
            if task.has_uncompleted_actionable_work():
                return index
        return None

    def has_uncompleted_tasks(self) -> bool:
        return self.first_uncompleted_task_index() is not None


class FenceTracker:
    def __init__(self) -> None:
        self.open_marker = ""

    def skip(self, line: str) -> bool:
        if not self.open_marker:
            match = FENCE_OPEN_RE.match(line)
            if not match:
                return False
            self.open_marker = match.group(1)
            return True

        match = FENCE_CLOSE_RE.match(line)
        if match and len(match.group(1)) >= len(self.open_marker) and match.group(1)[0] == self.open_marker[0]:
            self.open_marker = ""
        return True


def parse_task_number(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return 0


def parse_plan(content: str) -> Plan:
    plan = Plan()
    current: Optional[Task] = None
    fence = FenceTracker()

    for line in content.splitlines():
        if fence.skip(line):
            continue

        if not plan.title:
            title_match = TITLE_RE.match(line)
            if title_match:
                plan.title = title_match.group(1).strip()
                continue

        task_match = TASK_HEADER_RE.match(line)
        if task_match:
            if current is not None:
                plan.tasks.append(current)
            current = Task(number=parse_task_number(task_match.group(1)), title=task_match.group(2).strip())
            continue

        is_h2 = line.startswith("##") and not line.startswith("###")
        is_h1_after_title = line.startswith("#") and plan.title and not line.startswith("##")
        if current is not None and (is_h2 or is_h1_after_title):
            plan.tasks.append(current)
            current = None
            continue

        if current is not None:
            checkbox_match = CHECKBOX_RE.match(line)
            if checkbox_match:
                current.checkboxes.append(
                    Checkbox(
                        text=checkbox_match.group(2).strip(),
                        checked=checkbox_match.group(1).lower() == "x",
                    )
                )

    if current is not None:
        plan.tasks.append(current)
    return plan


def parse_plan_file(path: Path) -> Plan:
    return parse_plan(path.read_text(encoding="utf-8"))


def file_has_uncompleted_checkbox(path: Path) -> bool:
    fence = FenceTracker()
    for line in path.read_text(encoding="utf-8").splitlines():
        if fence.skip(line):
            continue
        match = CHECKBOX_RE.match(line)
        if not match:
            continue
        checkbox = Checkbox(text=match.group(2).strip(), checked=match.group(1).lower() == "x")
        if not checkbox.checked and checkbox.actionable:
            return True
    return False
