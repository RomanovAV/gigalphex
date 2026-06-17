from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
import os
import shlex
from typing import Optional

from .defaults import DEFAULT_GIGACODE_ARGS
from .prompts import init_prompt_templates


@dataclass
class Config:
    gigacode_command: str = "gigacode"
    gigacode_args: Optional[list[str]] = None
    plan_model: Optional[str] = None
    task_model: Optional[str] = None
    review_model: Optional[str] = None
    finalize_model: Optional[str] = None
    plans_dir: Path = Path("docs/plans")
    progress_dir: Path = Path(".gigalphex/progress")
    prompts_dir: Path = Path(".gigalphex/prompts")
    default_branch: str = "main"
    max_iterations: int = 50
    review_iterations: int = 5
    finalize_enabled: bool = False
    session_timeout: Optional[int] = None
    idle_timeout: Optional[int] = 900
    retry_count: int = 1
    retry_delay: float = 2.0
    review_workers: int = 5
    create_branch: bool = True
    worktree: bool = False
    move_plan_on_completion: bool = True
    commit_plan_on_creation: bool = True
    allow_dirty: bool = False

    @property
    def resolved_args(self) -> list[str]:
        return self.gigacode_args if self.gigacode_args is not None else DEFAULT_GIGACODE_ARGS.copy()

    def args_for_phase(self, phase: str) -> list[str]:
        model = self.model_for_phase(phase)
        args = self.resolved_args
        if model:
            return ["--model", model, *args]
        return args

    def model_for_phase(self, phase: str) -> Optional[str]:
        if phase == "plan":
            return self.plan_model or self.task_model
        if phase == "task":
            return self.task_model
        if phase == "review":
            return self.review_model or self.task_model
        if phase == "finalize":
            return self.finalize_model or self.review_model or self.task_model
        raise ValueError(f"unknown phase: {phase}")

    @property
    def prompt_dirs(self) -> list[Path]:
        return [self.prompts_dir, Path.home() / ".config/gigalphex/prompts"]


def load_config(path: Optional[Path] = None) -> Config:
    cfg = Config()
    candidates = []
    if path is not None:
        candidates.append(path)
    candidates.extend([Path(".gigalphex/config"), Path.home() / ".config/gigalphex/config"])

    parser = ConfigParser()
    parser.optionxform = str
    read_files = parser.read([str(p) for p in candidates if p.exists()], encoding="utf-8")
    if not read_files:
        return _apply_env(cfg)

    section = parser["gigalphex"] if parser.has_section("gigalphex") else parser["DEFAULT"]
    cfg.gigacode_command = section.get("gigacode_command", cfg.gigacode_command)
    if "gigacode_args" in section:
        cfg.gigacode_args = shlex.split(section.get("gigacode_args", ""))
    cfg.plan_model = _optional_str(section.get("plan_model", cfg.plan_model))
    cfg.task_model = _optional_str(section.get("task_model", cfg.task_model))
    cfg.review_model = _optional_str(section.get("review_model", cfg.review_model))
    cfg.finalize_model = _optional_str(section.get("finalize_model", cfg.finalize_model))
    cfg.plans_dir = Path(section.get("plans_dir", str(cfg.plans_dir)))
    cfg.progress_dir = Path(section.get("progress_dir", str(cfg.progress_dir)))
    cfg.prompts_dir = Path(section.get("prompts_dir", str(cfg.prompts_dir)))
    cfg.default_branch = section.get("default_branch", cfg.default_branch)
    cfg.max_iterations = section.getint("max_iterations", cfg.max_iterations)
    cfg.review_iterations = section.getint("review_iterations", cfg.review_iterations)
    cfg.finalize_enabled = section.getboolean("finalize_enabled", cfg.finalize_enabled)
    if "session_timeout" in section:
        cfg.session_timeout = section.getint("session_timeout")
    if "idle_timeout" in section:
        cfg.idle_timeout = section.getint("idle_timeout")
    cfg.retry_count = section.getint("retry_count", cfg.retry_count)
    cfg.retry_delay = section.getfloat("retry_delay", cfg.retry_delay)
    cfg.review_workers = section.getint("review_workers", cfg.review_workers)
    cfg.create_branch = section.getboolean("create_branch", cfg.create_branch)
    cfg.worktree = section.getboolean("worktree", cfg.worktree)
    cfg.move_plan_on_completion = section.getboolean("move_plan_on_completion", cfg.move_plan_on_completion)
    cfg.commit_plan_on_creation = section.getboolean("commit_plan_on_creation", cfg.commit_plan_on_creation)
    cfg.allow_dirty = section.getboolean("allow_dirty", cfg.allow_dirty)
    return _apply_env(cfg)


def _apply_env(cfg: Config) -> Config:
    if command := os.getenv("GIGALPHEX_GIGACODE_COMMAND"):
        cfg.gigacode_command = command
    if args := os.getenv("GIGALPHEX_GIGACODE_ARGS"):
        cfg.gigacode_args = shlex.split(args)
    if model := os.getenv("GIGALPHEX_TASK_MODEL"):
        cfg.task_model = model
    if model := os.getenv("GIGALPHEX_REVIEW_MODEL"):
        cfg.review_model = model
    return cfg


def _optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


DEFAULT_CONFIG_TEXT = """[gigalphex]
# gigacode_command = gigacode
# gigacode_args = -p {prompt} --approval-mode=auto-edit --allowed-tools run_shell_command
# plan_model =
# task_model =
# review_model =
# finalize_model =
# plans_dir = docs/plans
# progress_dir = .gigalphex/progress
# prompts_dir = .gigalphex/prompts
# default_branch = main
# max_iterations = 50
# review_iterations = 5
# finalize_enabled = false
# session_timeout = 1800
# idle_timeout = 900
# retry_count = 1
# retry_delay = 5
# review_workers = 5
# create_branch = true
# worktree = false
# move_plan_on_completion = true
# commit_plan_on_creation = true
# allow_dirty = false
"""


DEFAULT_GITIGNORE_LINES = [
    ".DS_Store",
    ".gigalphex/progress/",
    ".gigalphex/worktrees/",
]


def init_project_config(base_dir: Path = Path(".gigalphex")) -> list[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    config_path = base_dir / "config"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        written.append(config_path)

    gitignore_path = base_dir.parent / ".gitignore"
    if _ensure_gitignore_lines(gitignore_path, DEFAULT_GITIGNORE_LINES):
        written.append(gitignore_path)

    written.extend(init_prompt_templates(base_dir / "prompts"))
    return written


def _ensure_gitignore_lines(path: Path, lines: list[str]) -> bool:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    missing = [line for line in lines if line not in existing]
    if not missing:
        return False

    content = "\n".join(existing)
    if content:
        content += "\n"
    content += "\n".join(missing) + "\n"
    path.write_text(content, encoding="utf-8")
    return True
