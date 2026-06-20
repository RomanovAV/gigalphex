from __future__ import annotations

from importlib import resources
from pathlib import Path


PLANNING_SKILL_NAME = "planning"
PLANNING_SKILL_RESOURCE = "assets/planning/SKILL.md"


def planning_skill_path(skills_dir: Path) -> Path:
    return skills_dir.expanduser() / PLANNING_SKILL_NAME / "SKILL.md"


def planning_skill_text() -> str:
    resource = resources.files("gigalphex")
    for part in PLANNING_SKILL_RESOURCE.split("/"):
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


def planning_skill_installed(skills_dir: Path) -> bool:
    return planning_skill_path(skills_dir).is_file()


def install_planning_skill(skills_dir: Path, force: bool = False) -> tuple[Path, bool]:
    target = planning_skill_path(skills_dir)
    content = planning_skill_text()
    if target.exists():
        if target.read_text(encoding="utf-8") == content:
            return target, False
        if not force:
            raise FileExistsError(
                f"planning skill already exists and differs from the bundled version: {target}"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target, True
