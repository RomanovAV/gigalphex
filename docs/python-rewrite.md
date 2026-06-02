# Python rewrite notes

## Core functions preserved

- Parse markdown plans with `### Task N:` / `### Iteration N:` sections and actionable checkboxes.
- Run one task section per agent iteration.
- Stream agent output to terminal and a progress log.
- Detect ralphex-compatible completion signals.
- Run a review loop after tasks.
- Run five specialist review agents in parallel, then synthesize/fix findings.
- Optionally run a finalize prompt.
- Configure the agent command as `gigacode` plus arbitrary CLI args.
- Bound executor runs with session timeout, retry count, retry delay, and review worker limit.
- Validate git repository state, detect default branch, create/switch plan branch, and move completed plans.

## Intentionally deferred

- Web dashboard.
- Git worktree isolation.
- Notifications.
- External second-model review.
- Docker wrapper.

The Python version is intentionally small first. For now it assumes `gigacode`
is launched as a plain terminal command and receives the prompt on stdin. If the
real CLI later needs a subcommand or flags, the executor boundary is
`GigaCodeExecutor`, so adapting the invocation should be one local change.

## Usage

Run without installing:

```bash
PYTHONPATH=python python3 -m gigalphex.cli docs/plans/my-feature.md
```

Inspect prompts without invoking GigaCode:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --dry-run docs/plans/my-feature.md
```

Configure command shape:

```ini
[gigalphex]
gigacode_command = gigacode
gigacode_args = --some --flags
default_branch = main
```
