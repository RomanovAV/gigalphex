from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Optional

from .config import (
    init_global_config,
    init_global_prompt_templates,
    init_project_config,
    init_project_prompt_templates,
    load_config,
)
from .executor import GigaCodeExecutor
from .git import GitError, GitService, branch_name_from_plan, move_plan_to_completed
from .planner import clean_plan_output, next_plan_path
from .progress import ProgressLog
from .prompts import load_prompt_templates, render_make_plan, render_plan_skill
from .runner import RunOptions, Runner
from .skills import install_planning_skill, planning_skill_installed, planning_skill_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gigalphex")
    parser.add_argument("plan_file", nargs="?", help="path to markdown plan file")
    parser.add_argument("--config", type=Path, help="config file path")
    parser.add_argument("--init", action="store_true", help="create local .gigalphex config")
    parser.add_argument(
        "--init-prompts",
        action="store_true",
        help="create local .gigalphex prompt templates that override global prompts",
    )
    parser.add_argument("--init-git", action="store_true", help="run git init first when current directory is not a git repository")
    parser.add_argument(
        "--install-planning-skill",
        action="store_true",
        help="install the bundled planning skill for GigaCode",
    )
    parser.add_argument(
        "--force-skill-install",
        action="store_true",
        help="overwrite an existing modified planning skill",
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        help="GigaCode skills directory, default: ~/.gigacode/skills",
    )
    parser.add_argument("--plan", help="create a markdown execution plan for this request")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="create a plan non-interactively with the one-shot plan prompt",
    )
    parser.add_argument("--gigacode-command", help="command to run, default: gigacode")
    parser.add_argument(
        "--gigacode-arg",
        action="append",
        default=[],
        help="extra arg for all gigacode invocations; repeatable",
    )
    parser.add_argument("--plan-model", help="GigaCode model for plan creation; falls back to task model")
    parser.add_argument("--task-model", help="GigaCode model for task execution")
    parser.add_argument("--review-model", help="GigaCode model for read-only review agents; falls back to task model")
    parser.add_argument("--finalize-model", help="GigaCode model for finalize; falls back to review/task model")
    parser.add_argument("--tasks-only", action="store_true", help="run task phase only")
    parser.add_argument("--review", action="store_true", help="skip tasks and run review phase")
    parser.add_argument("--max-iterations", type=int, help="maximum task iterations")
    parser.add_argument("--review-iterations", type=int, help="maximum review iterations")
    parser.add_argument("--session-timeout", type=int, help="seconds before killing one gigacode session")
    parser.add_argument("--idle-timeout", type=int, help="seconds of no output before killing one gigacode session")
    parser.add_argument("--retry-count", type=int, help="retry failed gigacode sessions N times")
    parser.add_argument("--retry-delay", type=float, help="seconds between gigacode retries")
    parser.add_argument("--retry-pattern", action="append", default=[], help="transient error text to treat as retryable")
    parser.add_argument("--rate-limit-pattern", action="append", default=[], help="rate-limit text to detect in failed sessions")
    parser.add_argument("--wait-on-rate-limit", type=float, help="seconds to wait before retrying a rate-limited session")
    parser.add_argument("--review-workers", type=int, help="maximum parallel review agents")
    parser.add_argument("--default-branch", help="default branch for diffs")
    parser.add_argument("--base-ref", help="branch or git ref to compare with HEAD in --review mode")
    parser.add_argument("--branch", help="branch to create/switch to before running a plan")
    parser.add_argument("--no-branch", action="store_true", help="do not create/switch branches")
    parser.add_argument("--worktree", action="store_true", help="run the plan in an isolated git worktree")
    parser.add_argument("--allow-dirty", action="store_true", help="allow starting with uncommitted changes")
    parser.add_argument("--no-move-plan", action="store_true", help="do not move completed plan to completed/")
    parser.add_argument("--no-commit-plan", action="store_true", help="do not commit newly created plans")
    finalize_group = parser.add_mutually_exclusive_group()
    finalize_group.add_argument(
        "--finalize",
        action="store_true",
        dest="finalize",
        default=None,
        help="run finalize prompt after review (enabled by default)",
    )
    finalize_group.add_argument(
        "--no-finalize",
        action="store_false",
        dest="finalize",
        help="skip the finalize prompt after review",
    )
    parser.add_argument(
        "--no-parallel-review",
        action="store_true",
        help="use one read-only reviewer before synthesis instead of parallel agents",
    )
    parser.add_argument("--dry-run", action="store_true", help="print prompts instead of invoking gigacode")
    return parser


def should_auto_init(args: argparse.Namespace) -> bool:
    if args.dry_run or args.review or args.config is not None or Path(".gigalphex/config").exists():
        return False
    if args.plan:
        return True
    return bool(args.plan_file and Path(args.plan_file).exists())


def plan_commit_message(plan_path: Path) -> str:
    return f"docs: add plan {plan_path.stem}"


def completed_plan_commit_message(plan_path: Path) -> str:
    return f"docs: complete plan {plan_path.stem}"


def add_gigacode_args(base_args: list[str], extra_args: list[str]) -> list[str]:
    for index, arg in enumerate(base_args):
        if "{prompt}" in arg:
            insertion_index = index
            if (
                arg == "{prompt}"
                and index > 0
                and base_args[index - 1]
                in {"-p", "--prompt", "-i", "--prompt-interactive"}
            ):
                insertion_index = index - 1
            return [
                *base_args[:insertion_index],
                *extra_args,
                *base_args[insertion_index:],
            ]
    return [*base_args, *extra_args]


def should_use_interactive_plan(args: argparse.Namespace) -> bool:
    return bool(
        args.plan
        and not args.quick
        and not args.dry_run
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def find_interactively_created_plan(
    expected_path: Path,
    existing_paths: set[Path],
) -> Path:
    if expected_path.is_file():
        return expected_path
    created = sorted(
        path
        for path in expected_path.parent.glob("*.md")
        if path not in existing_paths
    )
    if len(created) == 1:
        return created[0]
    if not created:
        raise RuntimeError(
            f"interactive planning finished without creating the expected plan: {expected_path}"
        )
    joined = ", ".join(str(path) for path in created)
    raise RuntimeError(f"interactive planning created multiple plan files: {joined}")


def main(argv: Optional[list[str]] = None) -> int:
    try:
        init_global_config()
        init_global_prompt_templates()
    except OSError as exc:
        print(f"warning: could not initialize global gigalphex files: {exc}", file=sys.stderr)

    args = build_parser().parse_args(argv)
    if args.force_skill_install and not args.install_planning_skill:
        print("error: --force-skill-install requires --install-planning-skill", file=sys.stderr)
        return 2
    if args.quick and not args.plan:
        print("error: --quick requires --plan", file=sys.stderr)
        return 2
    if args.base_ref and not args.review:
        print("error: --base-ref requires --review", file=sys.stderr)
        return 2
    if args.base_ref and args.default_branch:
        print("error: --base-ref and --default-branch cannot be used together", file=sys.stderr)
        return 2
    if args.init or args.init_prompts:
        written: list[Path] = []
        if args.init:
            written.extend(init_project_config())
        if args.init_prompts:
            written.extend(init_project_prompt_templates())
        if written:
            print("initialized gigalphex files:")
            for path in written:
                print(f"- {path}")
        else:
            print("requested gigalphex files already initialized")
        return 0

    if should_use_interactive_plan(args):
        planning_cfg = load_config(args.config)
        if args.skill_dir:
            planning_cfg.gigacode_skills_dir = args.skill_dir.expanduser()
        if not planning_skill_installed(planning_cfg.gigacode_skills_dir):
            expected_skill = planning_skill_path(planning_cfg.gigacode_skills_dir)
            print(f"error: GigaCode planning skill not found: {expected_skill}", file=sys.stderr)
            install_command = "gigalphex --install-planning-skill"
            if args.skill_dir:
                install_command += f" --skill-dir {planning_cfg.gigacode_skills_dir}"
            print(f"install it with: {install_command}", file=sys.stderr)
            print("or use --quick for non-interactive plan creation", file=sys.stderr)
            return 2

    auto_init_written: list[Path] = []
    auto_init_started_clean = False
    if should_auto_init(args):
        auto_init_git = GitService(Path("."))
        auto_init_started_clean = auto_init_git.is_repo() and not auto_init_git.is_dirty()
        auto_init_written = init_project_config()
        if auto_init_written:
            print(f"initialized local gigalphex config: {Path('.gigalphex/config')}")

    if args.init_git and not args.dry_run:
        git = GitService(Path("."))
        if git.init_repo_if_missing():
            print("initialized git repository")
        if not git.has_commits() and git.commit_all_if_dirty("chore: initialize repository"):
            print("committed initial repository state")

    cfg = load_config(args.config)
    prompts = load_prompt_templates(cfg.prompt_dirs)

    if args.gigacode_command:
        cfg.gigacode_command = args.gigacode_command
    if args.skill_dir:
        cfg.gigacode_skills_dir = args.skill_dir.expanduser()
    if args.gigacode_arg:
        cfg.gigacode_args = add_gigacode_args(
            cfg.resolved_args,
            args.gigacode_arg,
        )
        cfg.gigacode_interactive_args = add_gigacode_args(
            cfg.resolved_interactive_args,
            args.gigacode_arg,
        )
    if args.plan_model:
        cfg.plan_model = args.plan_model
    if args.task_model:
        cfg.task_model = args.task_model
    if args.review_model:
        cfg.review_model = args.review_model
    if args.finalize_model:
        cfg.finalize_model = args.finalize_model
    if args.max_iterations is not None:
        cfg.max_iterations = args.max_iterations
    if args.review_iterations is not None:
        cfg.review_iterations = args.review_iterations
    if args.session_timeout is not None:
        cfg.session_timeout = args.session_timeout
    if args.idle_timeout is not None:
        cfg.idle_timeout = args.idle_timeout
    if args.retry_count is not None:
        cfg.retry_count = args.retry_count
    if args.retry_delay is not None:
        cfg.retry_delay = args.retry_delay
    if args.retry_pattern:
        cfg.retry_patterns = [*cfg.retry_patterns, *args.retry_pattern]
    if args.rate_limit_pattern:
        cfg.rate_limit_patterns = [*cfg.rate_limit_patterns, *args.rate_limit_pattern]
    if args.wait_on_rate_limit is not None:
        cfg.wait_on_rate_limit = args.wait_on_rate_limit
    if args.review_workers is not None:
        cfg.review_workers = args.review_workers
    if args.default_branch:
        cfg.default_branch = args.default_branch
    if args.base_ref:
        cfg.default_branch = args.base_ref
    if args.no_branch:
        cfg.create_branch = False
    if args.worktree:
        cfg.worktree = True
    if args.allow_dirty:
        cfg.allow_dirty = True
    if args.no_move_plan:
        cfg.move_plan_on_completion = False
    if args.no_commit_plan:
        cfg.commit_plan_on_creation = False
    if args.finalize is not None:
        cfg.finalize_enabled = args.finalize

    if args.install_planning_skill:
        try:
            skill_path, written = install_planning_skill(
                cfg.gigacode_skills_dir,
                force=args.force_skill_install,
            )
        except FileExistsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("re-run with --force-skill-install to overwrite it", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"error: could not install planning skill: {exc}", file=sys.stderr)
            return 1
        if written:
            print(f"installed planning skill: {skill_path}")
        else:
            print(f"planning skill already installed: {skill_path}")
        return 0

    if args.plan:
        progress_file = cfg.progress_dir / "progress-plan.txt"
        log = ProgressLog(progress_file)
        interactive = should_use_interactive_plan(args)
        plan_path = next_plan_path(cfg.plans_dir, args.plan)
        existing_plan_paths = set(cfg.plans_dir.glob("*.md"))
        executor = GigaCodeExecutor(
            command=cfg.gigacode_command,
            args=(
                cfg.args_for_interactive_plan()
                if interactive
                else cfg.args_for_phase("plan")
            ),
            timeout=cfg.session_timeout,
            idle_timeout=cfg.idle_timeout,
            retry_count=cfg.retry_count,
            retry_delay=cfg.retry_delay,
            retry_patterns=cfg.retry_patterns,
            rate_limit_patterns=cfg.rate_limit_patterns,
            wait_on_rate_limit=cfg.wait_on_rate_limit,
            max_workers=cfg.review_workers,
            output=log.stream,
        )
        prompt = (
            render_plan_skill(prompts.plan_skill, args.plan, plan_path)
            if interactive
            else render_make_plan(prompts.make_plan, args.plan)
        )
        if args.dry_run:
            log.section("make plan prompt")
            log.stream(prompt)
            log.stream("\n")
            print(f"progress log: {progress_file}")
            return 0
        try:
            log.section("make plan")
            log.write(f"gigacode command: {executor.command_line()}\n")
            if interactive:
                log.write(f"interactive plan target: {plan_path}\n")
                print(f"starting interactive GigaCode planning session for: {plan_path}")
                print("exit GigaCode after the planning skill creates the plan file")
                result = executor.run_interactive(prompt)
            else:
                result = executor.run(prompt)
            if not result.ok:
                raise RuntimeError(f"gigacode plan session exited with status {result.returncode}")
            if interactive:
                created_path = find_interactively_created_plan(plan_path, existing_plan_paths)
                if created_path != plan_path:
                    log.write(
                        f"interactive skill used a different plan path: {created_path}\n"
                    )
                plan_path = created_path
            else:
                plan_path.write_text(clean_plan_output(result.output), encoding="utf-8")
            log.write(f"created plan: {plan_path}\n")
            if cfg.commit_plan_on_creation:
                git = GitService(Path("."))
                if git.is_repo():
                    message = plan_commit_message(plan_path)
                    if auto_init_written:
                        git.commit_paths([*auto_init_written, plan_path], message)
                    else:
                        git.commit_file(plan_path, message)
                    log.write(f"committed plan: {message}\n")
                else:
                    log.write("skipped plan commit: not inside a git repository\n")
        except KeyboardInterrupt:
            print("\ninterrupted", file=sys.stderr)
            return 130
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"created plan: {plan_path}")
        print(f"progress log: {progress_file}")
        return 0

    plan_file = Path(args.plan_file).resolve() if args.plan_file else None
    if plan_file is not None and not plan_file.exists():
        print(f"error: plan file not found: {plan_file}", file=sys.stderr)
        return 2
    if plan_file is None and not args.review:
        print("error: plan file is required unless --review is used", file=sys.stderr)
        return 2

    git = GitService(Path("."))
    worktree_path: Optional[Path] = None
    if not args.dry_run:
        try:
            git.ensure_repo()
            cfg.default_branch = git.default_branch(cfg.default_branch)
            if args.review:
                git.ensure_ref_exists(cfg.default_branch)
            ignored_dirty_paths = auto_init_written if auto_init_started_clean else []
            git.ensure_clean(cfg.allow_dirty, ignored_dirty_paths)
            if cfg.worktree and plan_file is not None and not args.review:
                branch = args.branch or branch_name_from_plan(plan_file)
                repo_root = git.repo_root()
                try:
                    plan_relative = plan_file.relative_to(repo_root)
                except ValueError as exc:
                    raise GitError(f"plan file must be inside the git repository for --worktree: {plan_file}") from exc
                worktree_path = git.ensure_worktree(branch)
                plan_file = worktree_path / plan_relative
                if not plan_file.exists():
                    raise GitError(f"plan file is not available in worktree; commit it first: {plan_relative}")
                os.chdir(worktree_path)
                git = GitService(Path("."))
            elif cfg.create_branch and plan_file is not None and not args.review:
                branch = args.branch or branch_name_from_plan(plan_file)
                git.switch_or_create_branch(branch)
        except GitError as exc:
            hint = "; pass --init-git to initialize this directory first" if str(exc) == "not inside a git repository" else ""
            print(f"error: {exc}{hint}", file=sys.stderr)
            return 1

    progress_base = plan_file.stem if plan_file else "review"
    progress_file = cfg.progress_dir / f"progress-{progress_base}.txt"
    log = ProgressLog(progress_file)
    task_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("task"),
        timeout=cfg.session_timeout,
        idle_timeout=cfg.idle_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        retry_patterns=cfg.retry_patterns,
        rate_limit_patterns=cfg.rate_limit_patterns,
        wait_on_rate_limit=cfg.wait_on_rate_limit,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    synthesis_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("synthesis"),
        timeout=cfg.session_timeout,
        idle_timeout=cfg.idle_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        retry_patterns=cfg.retry_patterns,
        rate_limit_patterns=cfg.rate_limit_patterns,
        wait_on_rate_limit=cfg.wait_on_rate_limit,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    review_agent_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_review_agent(),
        timeout=cfg.session_timeout,
        idle_timeout=cfg.idle_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        retry_patterns=cfg.retry_patterns,
        rate_limit_patterns=cfg.rate_limit_patterns,
        wait_on_rate_limit=cfg.wait_on_rate_limit,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    finalize_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("finalize"),
        timeout=cfg.session_timeout,
        idle_timeout=cfg.idle_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        retry_patterns=cfg.retry_patterns,
        rate_limit_patterns=cfg.rate_limit_patterns,
        wait_on_rate_limit=cfg.wait_on_rate_limit,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    if not args.dry_run:
        log.section("startup")
        log.write(f"gigacode command: {task_executor.command_line()}\n")
        if review_agent_executor.command_line() != task_executor.command_line():
            log.write(f"review agent gigacode command: {review_agent_executor.command_line()}\n")
        if synthesis_executor.command_line() != task_executor.command_line():
            log.write(f"review synthesis gigacode command: {synthesis_executor.command_line()}\n")
        if cfg.finalize_enabled and finalize_executor.command_line() != synthesis_executor.command_line():
            log.write(f"finalize gigacode command: {finalize_executor.command_line()}\n")
        if cfg.session_timeout:
            log.write(f"session timeout: {cfg.session_timeout}s\n")
        if cfg.idle_timeout:
            log.write(f"idle timeout: {cfg.idle_timeout}s\n")
        if cfg.retry_count:
            log.write(f"retry count: {cfg.retry_count}, retry delay: {cfg.retry_delay}s\n")
        if cfg.wait_on_rate_limit is not None:
            log.write(f"rate limit wait: {cfg.wait_on_rate_limit}s\n")
        log.write(f"review workers: {cfg.review_workers}\n")
        if args.review:
            log.write(f"review base ref: {cfg.default_branch}\n")
        else:
            log.write(f"default branch: {cfg.default_branch}\n")
        if worktree_path is not None:
            log.write(f"worktree: {worktree_path}\n")
            log.write(f"branch: {args.branch or branch_name_from_plan(plan_file)}\n")
        elif cfg.create_branch and plan_file is not None and not args.review:
            log.write(f"branch: {args.branch or branch_name_from_plan(plan_file)}\n")
    options = RunOptions(
        plan_file=plan_file,
        progress_file=progress_file,
        default_branch=cfg.default_branch,
        max_iterations=cfg.max_iterations,
        review_iterations=cfg.review_iterations,
        tasks_only=args.tasks_only,
        review_only=args.review,
        finalize_enabled=cfg.finalize_enabled,
        dry_run=args.dry_run,
        parallel_review=not args.no_parallel_review,
        prompts=prompts,
    )

    try:
        Runner(
            options,
            task_executor,
            log,
            synthesis_executor=synthesis_executor,
            review_agent_executor=review_agent_executor,
            finalize_executor=finalize_executor,
        ).run()
        if (
            not args.dry_run
            and cfg.move_plan_on_completion
            and plan_file is not None
            and not args.review
            and not args.tasks_only
        ):
            moved_to = move_plan_to_completed(plan_file)
            log.section("plan")
            log.write(f"moved completed plan to {moved_to}\n")
            if git.is_repo():
                message = completed_plan_commit_message(plan_file)
                git.commit_paths([plan_file, moved_to], message)
                log.write(f"committed completed plan move: {message}\n")
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"progress log: {progress_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
