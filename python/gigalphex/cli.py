from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

from .config import init_project_config, load_config
from .executor import GigaCodeExecutor
from .git import GitError, GitService, branch_name_from_plan, move_plan_to_completed
from .planner import clean_plan_output, next_plan_path
from .progress import ProgressLog
from .prompts import load_prompt_templates, render_make_plan
from .runner import RunOptions, Runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gigalphex")
    parser.add_argument("plan_file", nargs="?", help="path to markdown plan file")
    parser.add_argument("--config", type=Path, help="config file path")
    parser.add_argument("--init", action="store_true", help="create local .gigalphex config and prompt templates")
    parser.add_argument("--init-git", action="store_true", help="run git init first when current directory is not a git repository")
    parser.add_argument("--plan", help="create a markdown execution plan for this request")
    parser.add_argument("--gigacode-command", help="command to run, default: gigacode")
    parser.add_argument("--gigacode-arg", action="append", default=[], help="extra arg for gigacode; repeatable")
    parser.add_argument("--plan-model", help="GigaCode model for plan creation; falls back to task model")
    parser.add_argument("--task-model", help="GigaCode model for task execution")
    parser.add_argument("--review-model", help="GigaCode model for review agents and synthesis; falls back to task model")
    parser.add_argument("--finalize-model", help="GigaCode model for finalize; falls back to review/task model")
    parser.add_argument("--tasks-only", action="store_true", help="run task phase only")
    parser.add_argument("--review", action="store_true", help="skip tasks and run review phase")
    parser.add_argument("--max-iterations", type=int, help="maximum task iterations")
    parser.add_argument("--review-iterations", type=int, help="maximum review iterations")
    parser.add_argument("--session-timeout", type=int, help="seconds before killing one gigacode session")
    parser.add_argument("--retry-count", type=int, help="retry failed gigacode sessions N times")
    parser.add_argument("--retry-delay", type=float, help="seconds between gigacode retries")
    parser.add_argument("--review-workers", type=int, help="maximum parallel review agents")
    parser.add_argument("--default-branch", help="default branch for diffs")
    parser.add_argument("--branch", help="branch to create/switch to before running a plan")
    parser.add_argument("--no-branch", action="store_true", help="do not create/switch branches")
    parser.add_argument("--allow-dirty", action="store_true", help="allow starting with uncommitted changes")
    parser.add_argument("--no-move-plan", action="store_true", help="do not move completed plan to completed/")
    parser.add_argument("--no-commit-plan", action="store_true", help="do not commit newly created plans")
    parser.add_argument("--finalize", action="store_true", help="run finalize prompt after review")
    parser.add_argument("--no-parallel-review", action="store_true", help="use a single review prompt instead of parallel agents")
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


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.init:
        written = init_project_config()
        if written:
            print("initialized gigalphex files:")
            for path in written:
                print(f"- {path}")
        else:
            print("gigalphex config already initialized")
        return 0

    if should_auto_init(args):
        written = init_project_config()
        if written:
            print(f"initialized local gigalphex config: {Path('.gigalphex/config')}")

    if args.init_git and not args.dry_run:
        git = GitService(Path("."))
        if git.init_repo_if_missing():
            print("initialized git repository")

    cfg = load_config(args.config)
    prompts = load_prompt_templates(cfg.prompt_dirs)

    if args.gigacode_command:
        cfg.gigacode_command = args.gigacode_command
    if args.gigacode_arg:
        cfg.gigacode_args = [*cfg.resolved_args, *args.gigacode_arg]
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
    if args.retry_count is not None:
        cfg.retry_count = args.retry_count
    if args.retry_delay is not None:
        cfg.retry_delay = args.retry_delay
    if args.review_workers is not None:
        cfg.review_workers = args.review_workers
    if args.default_branch:
        cfg.default_branch = args.default_branch
    if args.no_branch:
        cfg.create_branch = False
    if args.allow_dirty:
        cfg.allow_dirty = True
    if args.no_move_plan:
        cfg.move_plan_on_completion = False
    if args.no_commit_plan:
        cfg.commit_plan_on_creation = False
    if args.finalize:
        cfg.finalize_enabled = True

    if args.plan:
        progress_file = cfg.progress_dir / "progress-plan.txt"
        log = ProgressLog(progress_file)
        executor = GigaCodeExecutor(
            command=cfg.gigacode_command,
            args=cfg.args_for_phase("plan"),
            timeout=cfg.session_timeout,
            retry_count=cfg.retry_count,
            retry_delay=cfg.retry_delay,
            max_workers=cfg.review_workers,
            output=log.stream,
        )
        prompt = render_make_plan(prompts.make_plan, args.plan)
        if args.dry_run:
            log.section("make plan prompt")
            log.stream(prompt)
            log.stream("\n")
            print(f"progress log: {progress_file}")
            return 0
        try:
            log.section("make plan")
            log.write(f"gigacode command: {executor.command_line()}\n")
            result = executor.run(prompt)
            if not result.ok:
                raise RuntimeError(f"gigacode plan session exited with status {result.returncode}")
            plan_path = next_plan_path(cfg.plans_dir, args.plan)
            plan_path.write_text(clean_plan_output(result.output), encoding="utf-8")
            log.write(f"created plan: {plan_path}\n")
            if cfg.commit_plan_on_creation:
                git = GitService(Path("."))
                if git.is_repo():
                    message = plan_commit_message(plan_path)
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

    progress_base = plan_file.stem if plan_file else "review"
    progress_file = cfg.progress_dir / f"progress-{progress_base}.txt"
    log = ProgressLog(progress_file)
    task_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("task"),
        timeout=cfg.session_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    review_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("review"),
        timeout=cfg.session_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    finalize_executor = GigaCodeExecutor(
        command=cfg.gigacode_command,
        args=cfg.args_for_phase("finalize"),
        timeout=cfg.session_timeout,
        retry_count=cfg.retry_count,
        retry_delay=cfg.retry_delay,
        max_workers=cfg.review_workers,
        output=log.stream,
    )
    git = GitService(Path("."))
    if not args.dry_run:
        try:
            git.ensure_repo()
            cfg.default_branch = git.default_branch(cfg.default_branch)
            git.ensure_clean(cfg.allow_dirty)
            if cfg.create_branch and plan_file is not None and not args.review:
                branch = args.branch or branch_name_from_plan(plan_file)
                git.switch_or_create_branch(branch)
        except GitError as exc:
            hint = "; pass --init-git to initialize this directory first" if str(exc) == "not inside a git repository" else ""
            print(f"error: {exc}{hint}", file=sys.stderr)
            return 1

    if not args.dry_run:
        log.section("startup")
        log.write(f"gigacode command: {task_executor.command_line()}\n")
        if review_executor.command_line() != task_executor.command_line():
            log.write(f"review gigacode command: {review_executor.command_line()}\n")
        if cfg.finalize_enabled and finalize_executor.command_line() != review_executor.command_line():
            log.write(f"finalize gigacode command: {finalize_executor.command_line()}\n")
        if cfg.session_timeout:
            log.write(f"session timeout: {cfg.session_timeout}s\n")
        if cfg.retry_count:
            log.write(f"retry count: {cfg.retry_count}, retry delay: {cfg.retry_delay}s\n")
        log.write(f"review workers: {cfg.review_workers}\n")
        log.write(f"default branch: {cfg.default_branch}\n")
        if cfg.create_branch and plan_file is not None and not args.review:
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
        Runner(options, task_executor, log, review_executor=review_executor, finalize_executor=finalize_executor).run()
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
