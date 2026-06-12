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
    plans_dir: Path = Path("docs/plans")
    progress_dir: Path = Path(".gigalphex/progress")
    prompts_dir: Path = Path(".gigalphex/prompts")
    default_branch: str = "main"
    max_iterations: int = 50
    review_iterations: int = 5
    finalize_enabled: bool = False
    session_timeout: Optional[int] = None
    retry_count: int = 0
    retry_delay: float = 2.0
    review_workers: int = 5
    create_branch: bool = True
    move_plan_on_completion: bool = True
    allow_dirty: bool = False

    @property
    def resolved_args(self) -> list[str]:
        return self.gigacode_args if self.gigacode_args is not None else DEFAULT_GIGACODE_ARGS.copy()

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
    cfg.plans_dir = Path(section.get("plans_dir", str(cfg.plans_dir)))
    cfg.progress_dir = Path(section.get("progress_dir", str(cfg.progress_dir)))
    cfg.prompts_dir = Path(section.get("prompts_dir", str(cfg.prompts_dir)))
    cfg.default_branch = section.get("default_branch", cfg.default_branch)
    cfg.max_iterations = section.getint("max_iterations", cfg.max_iterations)
    cfg.review_iterations = section.getint("review_iterations", cfg.review_iterations)
    cfg.finalize_enabled = section.getboolean("finalize_enabled", cfg.finalize_enabled)
    if "session_timeout" in section:
        cfg.session_timeout = section.getint("session_timeout")
    cfg.retry_count = section.getint("retry_count", cfg.retry_count)
    cfg.retry_delay = section.getfloat("retry_delay", cfg.retry_delay)
    cfg.review_workers = section.getint("review_workers", cfg.review_workers)
    cfg.create_branch = section.getboolean("create_branch", cfg.create_branch)
    cfg.move_plan_on_completion = section.getboolean("move_plan_on_completion", cfg.move_plan_on_completion)
    cfg.allow_dirty = section.getboolean("allow_dirty", cfg.allow_dirty)
    return _apply_env(cfg)


def _apply_env(cfg: Config) -> Config:
    if command := os.getenv("GIGALPHEX_GIGACODE_COMMAND"):
        cfg.gigacode_command = command
    if args := os.getenv("GIGALPHEX_GIGACODE_ARGS"):
        cfg.gigacode_args = shlex.split(args)
    return cfg


DEFAULT_CONFIG_TEXT = """[gigalphex]
# gigacode_command = gigacode
# gigacode_args = -p {prompt} --approval-mode=auto-edit
# plans_dir = docs/plans
# progress_dir = .gigalphex/progress
# prompts_dir = .gigalphex/prompts
# default_branch = main
# max_iterations = 50
# review_iterations = 5
# finalize_enabled = false
# session_timeout = 1800
# retry_count = 1
# retry_delay = 5
# review_workers = 5
# create_branch = true
# move_plan_on_completion = true
# allow_dirty = false
"""


def init_project_config(base_dir: Path = Path(".gigalphex")) -> list[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    config_path = base_dir / "config"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        written.append(config_path)

    written.extend(init_prompt_templates(base_dir / "prompts"))
    return written
