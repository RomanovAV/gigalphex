# Python rewrite notes

## Core functions preserved

- Parse markdown plans with `### Task N:` / `### Iteration N:` sections and actionable checkboxes.
- Create gigalphex-compatible plans from a free-form request.
- Commit newly created plan files by default when running inside a git
  repository.
- Commit completed plan moves after a successful full run.
- Install `.gitignore` entries for `.DS_Store` and `.gigalphex/progress/`
  during project initialization.
- Optionally initialize a missing git repository with `--init-git` and commit
  the initial working tree before execution.
- Run one task section per agent iteration.
- Stream agent output to terminal and a progress log.
- Detect gigalphex completion signals.
- Run a review loop after tasks.
- Run five specialist review agents in parallel, then synthesize/fix findings.
- Optionally run a finalize prompt.
- Configure the agent command as `gigacode` plus arbitrary CLI args.
- Select GigaCode models per phase with `plan_model`, `task_model`,
  `review_model`, and `finalize_model`, mapped to GigaCode's `--model` flag.
- Initialize local `.gigalphex/` config and editable prompt templates, including
  automatic initialization on first real plan creation or execution.
- Bound executor runs with session timeout, retry count, retry delay, and review worker limit.
- Validate git repository state, detect default branch, create/switch plan branch, and move completed plans.
- Run full and tasks-only plan execution in an isolated git worktree with
  `--worktree`.

## Intentionally deferred

- Web dashboard.
- Notifications.
- External second-model review.
- Docker wrapper.

The Python version is intentionally small first. It launches `gigacode` in
one-shot mode with
`-p {prompt} --approval-mode=auto-edit --allowed-tools run_shell_command` by
default and substitutes the generated prompt into `{prompt}` before invoking
GigaCode. GigaCode 26.5.17 needs `--allowed-tools run_shell_command` for tests
and git commands; `--approval-mode=auto-edit` only covers edit/write tools. If
custom args omit `{prompt}`, the executor falls back to sending the generated
prompt on stdin. If the CLI later needs a subcommand or different flags, the
executor boundary is `GigaCodeExecutor`, so adapting the invocation should be
one local change.

GigaCode model selection is a CLI concern, not a prompt concern. The CLI exposes
`-m/--model`, so gigalphex adds `--model <name>` to the phase invocation instead
of embedding model names in the `-p` prompt text.

## Observed GigaCode behavior

- Prompts are plain text instructions. The task prompt tells GigaCode to read a
  markdown plan, find the first unchecked `### Task N:` or `### Iteration N:`
  section, complete it, test it, commit it, mark checkboxes as `[x]`, and emit a
  completion signal.
- One task section is expected per GigaCode launch. The prompt explicitly says:
  `Do not continue to the next task section.`
- Workspace guard is enforced by GigaCode. Files outside its workspace cannot be
  edited unless the GigaCode invocation includes the needed
  `--include-directories` values.
- Approval mode must be explicit in non-interactive runs. Real logs show
  `Warning: Tool "run_shell_command" requires user approval but cannot execute
  in non-interactive mode`; GigaCode help shows that shell execution additionally
  requires `--allowed-tools run_shell_command`.
- GigaCode appears to run on Node.js; `MaxListenersExceededWarning` can surface
  in its output.
- There are no observed CLI subcommands, JSON/REST API, official Python SDK, or
  `IN_PROGRESS` signal. `gigalphex` therefore treats the CLI process and output
  stream as the integration boundary.

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
gigacode_args = -p {prompt} --approval-mode=auto-edit --allowed-tools run_shell_command
default_branch = main
```

Create local config and prompt templates:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --init
```

Create a new plan:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --plan "add user authentication"
```
