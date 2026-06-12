# gigalphex

Python autonomous plan runner for GigaCode CLI.

This is a small standalone rewrite of the useful ralphex core:

- parse markdown plans with `### Task N:` / `### Iteration N:`
- run one task section per agent iteration
- stream output to terminal and progress logs
- detect ralphex-compatible completion signals
- run review and optional finalize loops
- run five specialist review agents in parallel, then synthesize/fix findings
- create/switch a git branch from the plan filename
- guard against dirty working trees
- move completed plans into `completed/`
- call `gigacode` through a configurable CLI boundary

Current assumption: GigaCode CLI is available in `PATH`. By default
`gigalphex` starts it in one-shot mode with:

```bash
gigacode --prompt '' --approval-mode=auto-edit
```

The empty `--prompt` flag selects non-interactive execution for the current
GigaCode CLI, while `gigalphex` sends the generated prompt through stdin.
`--approval-mode=auto-edit` enables automatic shell/tool execution for
non-interactive runs. Output is streamed from combined stdout/stderr back to the
terminal and progress log.

Observed GigaCode constraints:

- GigaCode edits only inside its configured workspace. To let it work across
  sibling project directories, pass the appropriate GigaCode
  `--include-directories` flags through repeated `--gigacode-arg` entries or
  `gigacode_args`.
- GigaCode currently exposes a plain CLI invocation only. This runner does not
  assume subcommands such as `gigacode task`, a JSON/REST API, or a Python SDK.
- Non-interactive runs fail if GigaCode asks for shell approval without
  automatic approval enabled. Real logs recommend `--approval-mode=auto-edit`;
  `gigalphex` includes it by default and still detects the warning if it appears.
- There is no `IN_PROGRESS` signal. Progress is inferred from process lifetime,
  terminal output, and the progress log.
- GigaCode runs on Node.js, so Node warnings such as
  `MaxListenersExceededWarning` may appear in combined output.

Run from this directory:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --dry-run ../e2e/testdata/test-plan.md
PYTHONPATH=python python3 -m gigalphex.cli docs/plans/my-feature.md
```

Initialize local project config and editable prompt templates:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --init
```

Run tests:

```bash
PYTHONPATH=python python3 -m unittest discover -s tests
```

Review behavior:

- default: parallel review with `quality`, `implementation`, `testing`,
  `simplification`, and `documentation` agents
- fallback: pass `--no-parallel-review` to use a single review prompt
- limit fan-out with `--review-workers N`
- kill stuck sessions with `--session-timeout SECONDS`
- retry failed sessions with `--retry-count N --retry-delay SECONDS`

Configure GigaCode:

```ini
[gigalphex]
gigacode_command = gigacode
gigacode_args = --prompt "" --approval-mode=auto-edit
default_branch = main
prompts_dir = .gigalphex/prompts
session_timeout = 1800
retry_count = 1
retry_delay = 5
review_workers = 5
create_branch = true
move_plan_on_completion = true
allow_dirty = false
```

Git behavior:

- plan runs create/switch to a branch derived from the plan filename
- review-only mode does not switch branches
- dirty working trees are rejected unless `--allow-dirty` is passed
- completed full runs move the plan file to `completed/`
- use `--no-branch` or `--no-move-plan` to disable those steps

Prompt customization:

- `--init` creates `.gigalphex/prompts/task.txt`
- `--init` creates `.gigalphex/prompts/review.txt`
- `--init` creates `.gigalphex/prompts/review_agent.txt`
- `--init` creates `.gigalphex/prompts/review_synthesis.txt`
- `--init` creates `.gigalphex/prompts/finalize.txt`
- loading priority is local prompts directory, then `~/.config/gigalphex/prompts`, then embedded defaults
# gigalphex
