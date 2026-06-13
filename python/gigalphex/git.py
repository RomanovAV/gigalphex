from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess


DATE_PREFIX_RE = re.compile(r"^[\d-]+")


class GitError(RuntimeError):
    pass


@dataclass
class GitService:
    cwd: Path = Path(".")

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(self.cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return proc

    def ensure_repo(self) -> None:
        proc = self.run("rev-parse", "--is-inside-work-tree", check=False)
        if proc.returncode != 0 or proc.stdout.strip() != "true":
            raise GitError("not inside a git repository")

    def is_repo(self) -> bool:
        proc = self.run("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def init_repo_if_missing(self) -> bool:
        if self.is_repo():
            return False
        self.run("init")
        return True

    def default_branch(self, configured: str = "") -> str:
        if configured:
            return configured

        origin_head = self.run("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
        if origin_head.returncode == 0:
            value = origin_head.stdout.strip()
            if value.startswith("origin/"):
                return value.split("/", 1)[1]
            if value:
                return value

        for branch in ("main", "master", "trunk"):
            exists = self.run("rev-parse", "--verify", "--quiet", branch, check=False)
            if exists.returncode == 0:
                return branch

        current = self.current_branch()
        if current:
            return current
        raise GitError("could not detect default branch; pass --default-branch")

    def current_branch(self) -> str:
        proc = self.run("branch", "--show-current", check=False)
        return proc.stdout.strip()

    def is_dirty(self) -> bool:
        proc = self.run("status", "--porcelain", check=True)
        return bool(proc.stdout.strip())

    def ensure_clean(self, allow_dirty: bool) -> None:
        if not allow_dirty and self.is_dirty():
            raise GitError("working tree has uncommitted changes; commit/stash them or pass --allow-dirty")

    def branch_exists(self, branch: str) -> bool:
        proc = self.run("rev-parse", "--verify", "--quiet", branch, check=False)
        return proc.returncode == 0

    def switch_or_create_branch(self, branch: str) -> None:
        if not branch:
            return
        if self.current_branch() == branch:
            return
        if self.branch_exists(branch):
            self.run("switch", branch)
            return
        self.run("switch", "-c", branch)

    def commit_file(self, path: Path, message: str) -> None:
        self.run("add", "--", str(path))
        self.run("commit", "--only", "-m", message, "--", str(path))


def branch_name_from_plan(plan_file: Path) -> str:
    name = plan_file.name
    if name.endswith(".md"):
        name = name[:-3]
    branch = DATE_PREFIX_RE.sub("", name).strip("-")
    return branch or name


def move_plan_to_completed(plan_file: Path) -> Path:
    completed_dir = plan_file.parent / "completed"
    completed_dir.mkdir(parents=True, exist_ok=True)
    target = completed_dir / plan_file.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        index = 2
        while target.exists():
            target = completed_dir / f"{stem}-{index}{suffix}"
            index += 1
    shutil.move(str(plan_file), str(target))
    return target
