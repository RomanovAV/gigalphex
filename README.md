# gigalphex

Python autonomous plan runner for GigaCode CLI.

This is a small standalone rewrite of the useful ralphex core:

- parse English and Russian markdown plans with `### Task N:` /
  `### Iteration N:` / `### Задача N:` / `### Итерация N:`
- run one task section per agent iteration
- stream output to terminal and progress logs
- detect gigalphex completion signals
- run review and a default finalize pass
- run five specialist review agents in parallel, then synthesize/fix findings
- create/switch a git branch from the plan filename
- optionally run a plan in an isolated git worktree
- guard against dirty working trees
- move completed plans into `completed/`
- call `gigacode` through a configurable CLI boundary

Current assumption: GigaCode CLI is available in `PATH`. Task, review,
finalize, and quick-plan sessions use one-shot mode by default:

```bash
gigacode -p '<generated prompt>' --approval-mode=auto-edit --allowed-tools run_shell_command
```

The default argument template is
`-p {prompt} --approval-mode=auto-edit --allowed-tools run_shell_command`.
`gigalphex` replaces `{prompt}` with the generated prompt before invoking
GigaCode. If custom `gigacode_args` do not include `{prompt}`, GigaLphex adds
`-p <generated prompt>`. GigaCode marks `-p/--prompt` as deprecated in favor of
the positional query, but its variadic `query..` parser consumes options placed
after the query, while array-valued options can consume a query placed after
them. The explicit `-p` form is therefore the reliable non-interactive contract
for GigaCode 26.5.17 and is also the form recommended by its runtime approval
error. `--approval-mode=auto-edit` allows edit/write tools, while shell commands
such as tests and `git commit` also require
`--allowed-tools run_shell_command`. Output is streamed from combined
stdout/stderr back to the terminal and progress log.

Interactive plan creation is different. When stdin and stdout are attached to
a terminal, `--plan` launches GigaCode with
`--prompt-interactive '<generated prompt>' --approval-mode=auto-edit` and
inherits the current terminal. Unlike a positional prompt or `-p`, the
`--prompt-interactive` flag executes the planning request and keeps the TUI
open so the user can answer the planning skill's questions. Auto-edit lets the
skill create the requested plan file. Use `--quick` to force the one-shot plan
prompt. Non-TTY sessions, including CI, automatically use quick mode.

Install the bundled planning skill once:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --install-planning-skill
```

The default destination is `~/.gigacode/skills/planning/SKILL.md`. Existing
customized content is preserved; use `--force-skill-install` to replace it
with the bundled version. For a GigaCode version using another skills
directory, pass `--skill-dir PATH` or configure `gigacode_skills_dir`.

Specialist and single-review sessions use `review_model`, remove the configured
`--approval-mode` argument, and receive an explicit inspect-only prompt. The
synthesis session uses `task_model`, keeps the normal editable invocation, and
is the only review stage allowed to fix files or create commits.

Observed GigaCode constraints:

- GigaCode edits only inside its configured workspace. To let it work across
  sibling project directories, pass the appropriate GigaCode flag as, for
  example, `--gigacode-arg=--include-directories=/path/to/shared`. Extra
  GigaCode arguments are applied to both one-shot and interactive planning
  invocations. They can also be placed directly in `gigacode_args` and
  `gigacode_interactive_args`.
- GigaCode exposes administrative subcommands such as `mcp`, `extensions`,
  `auth`, `sandbox`, and `hooks`, but no task-execution subcommand.
  GigaLphex therefore uses the default `gigacode [query..]` command and does
  not assume a `gigacode task` command, JSON/REST API, or Python SDK.
- Non-interactive runs fail if GigaCode asks for shell approval without the
  shell tool being explicitly allowed. Real logs and GigaCode help indicate that
  `--approval-mode=auto-edit` must be paired with
  `--allowed-tools run_shell_command`; `gigalphex` includes both by default and
  still detects the warning if it appears.
- There is no `IN_PROGRESS` signal. Progress is inferred from process lifetime,
  terminal output, and the progress log.
- GigaCode runs on Node.js, so Node warnings such as
  `MaxListenersExceededWarning` may appear in combined output.

Run from this directory:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --dry-run ../e2e/testdata/test-plan.md
PYTHONPATH=python python3 -m gigalphex.cli docs/plans/my-feature.md
```

Diagnose differences between direct GigaCode and GigaLphex execution by running
this Python module from the affected project directory:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.diagnose
```

For colleagues testing `gigalphex` on real tasks, see the short Russian guide:
[`docs/real-task-testing-guide.md`](docs/real-task-testing-guide.md).

Run a plan in a separate git worktree, close to ralphex `--worktree`
behavior:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --worktree docs/plans/my-feature.md
PYTHONPATH=python python3 -m gigalphex.cli --worktree --branch=my-feature docs/plans/tasks.md
```

Initialize local project config:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --init
```

If you skip `--init`, the first real plan creation or plan execution initializes
the local `.gigalphex/config` automatically. Dry runs and review-only runs do
not auto-create it. Local prompt templates are not created automatically,
because their presence overrides the global prompt with the same filename.
Initialization also creates or updates `.gitignore` with `.DS_Store` and
`.gigalphex/progress/`, so local progress logs stay out of normal commits.

Create editable project-specific prompt overrides only when needed:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --init-prompts
```

Initialize git automatically when creating or running a plan in a fresh folder:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --plan "add user authentication" --init-git
```

Without `--init-git`, `gigalphex` does not create a git repository for you. Plan
creation still works, but the created plan is left uncommitted outside git.
When `--init-git` creates a new repository, it commits the current files first
as `chore: initialize repository`, then continues with plan creation or
execution.

Create a new executable plan:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --plan "add user authentication"
```

The default interactive mode requires the GigaCode `planning` skill. The skill
creates the requested file under `docs/plans/`; after the GigaCode session
exits, `gigalphex` verifies the file and commits it when configured to do so.
If the installed GigaCode version needs different interactive CLI arguments,
set `gigacode_interactive_args` while keeping a `{prompt}` placeholder.

Create a plan without the skill or from automation:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --plan "add user authentication" --quick
```

Generated plans are requested entirely in the same language as the `--plan`
text, including structural headings. Russian plans may use `# План`,
`## Обзор`, `## Контекст`, `### Задача N:`, and `## Проверка`; they are parsed
and executed exactly like their English equivalents.
By default, a newly created plan is committed as `docs: add plan <name>` when
the current directory is inside a git repository. Use `--no-commit-plan` or
`commit_plan_on_creation = false` to leave the plan uncommitted.
When a full run finishes and moves the plan into `docs/plans/completed/`, that
move is committed as `docs: complete plan <name>`.

Run review with a different GigaCode model:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --review --review-model <model-name>
PYTHONPATH=python python3 -m gigalphex.cli docs/plans/my-feature.md --review-model <model-name>
```

Review the current `HEAD` against an explicit branch or other Git ref:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --review --base-ref develop
```

Run tests:

```bash
PYTHONPATH=python python3 -m unittest discover -s tests
```

Review behavior:

- default: parallel review with `quality`, `implementation`, `testing`,
  `simplification`, and `documentation` agents
- reviewers return machine-validated `<FINDING>` blocks with severity,
  category, file, evidence, impact, and a minimal suggested fix
- malformed review output is rejected instead of being forwarded to synthesis
- synthesis receives normalized findings inside an explicit untrusted-data
  boundary and independently verifies every claim against the repository
- pass `--base-ref REF` to compare `REF...HEAD`; without it, the default branch
  is auto-detected
- reviewers only inspect and report findings; they do not edit or commit
- synthesis uses `task_model`, verifies reported findings, and is the only
  stage that may fix, test, and commit changes
- finalize runs after a successful review by default; pass `--no-finalize` to
  skip the final validation/cleanup pass
- fallback: pass `--no-parallel-review` to use one read-only reviewer followed
  by the same synthesis stage
- limit fan-out with `--review-workers N`
- kill stuck sessions with `--session-timeout SECONDS`
- kill silent sessions with `--idle-timeout SECONDS`
- retry failed sessions with `--retry-count N --retry-delay SECONDS`
- classify transient failures with `retry_patterns`
- classify rate limits with `rate_limit_patterns`; pass
  `--wait-on-rate-limit SECONDS` to wait longer before retrying those failures

Configure GigaCode:

```ini
[gigalphex]
gigacode_command = gigacode
gigacode_args = -p {prompt} --approval-mode=auto-edit --allowed-tools run_shell_command
gigacode_interactive_args = --prompt-interactive {prompt} --approval-mode=auto-edit
gigacode_skills_dir = ~/.gigacode/skills
task_model =
review_model =
default_branch =
prompts_dir = .gigalphex/prompts
session_timeout = 1800
idle_timeout = 900
retry_count = 1
retry_delay = 5
retry_patterns = FYA_TRANSIENT_TIMEOUT,API Error: 529,API Error: 502,API Error: 503,API Error: 504,502 Bad Gateway,503 Service Unavailable,504 Gateway Timeout
rate_limit_patterns = Rate limit exceeded,rate limit reached,429 Too Many Requests,quota exceeded,insufficient_quota,You've hit your usage limit
wait_on_rate_limit =
review_workers = 5
finalize_enabled = true
create_branch = true
worktree = false
move_plan_on_completion = true
commit_plan_on_creation = true
allow_dirty = false
```

Configuration loading priority, from lowest to highest:

1. embedded defaults
2. global config at `~/.config/gigalphex/config`
3. project config at `.gigalphex/config`
4. a file passed with `--config`
5. supported `GIGALPHEX_*` environment variables
6. CLI arguments

The global directory `~/.config/gigalphex/`, a commented
`~/.config/gigalphex/config` template, and all seven prompt templates under
`~/.config/gigalphex/prompts/` are created automatically when the CLI starts.
Existing global config files and customized prompts are never overwritten.
Global prompts that still match an earlier installed default are upgraded to
the current embedded default automatically.

Git behavior:

- plan runs create/switch to a branch derived from the plan filename
- `--worktree` runs full and tasks-only plan execution in
  `.gigalphex/worktrees/<branch>` instead of switching the current checkout
- `--branch` overrides the branch name for normal branch switching and
  worktree runs
- review-only mode does not switch branches
- `--review --base-ref REF` validates the ref and compares it with the current
  `HEAD`
- dirty working trees are rejected unless `--allow-dirty` is passed
- completed full runs move the plan file to `completed/`
- use `--no-branch` or `--no-move-plan` to disable those steps

Prompt customization:

- global editable defaults are created automatically in
  `~/.config/gigalphex/prompts/`
- `--init-prompts` creates project-specific overrides in
  `.gigalphex/prompts/`
- both directories use `make_plan.txt`, `plan_skill.txt`, `task.txt`, `review.txt`,
  `review_agent.txt`, `review_synthesis.txt`, and `finalize.txt`
- loading priority is local prompts directory, then `~/.config/gigalphex/prompts`, then embedded defaults

Planning skill:

- `--install-planning-skill` installs the bundled skill globally
- `--skill-dir PATH` overrides the configured GigaCode skills directory
- `--force-skill-install` replaces an existing modified skill
- interactive `--plan` checks for `<skills-dir>/planning/SKILL.md` before
  launching GigaCode and suggests `--quick` when the skill is unavailable

Model selection:

- GigaCode exposes model selection as `-m/--model`, separate from the one-shot
  `-p/--prompt` option and `--prompt-interactive`.
- `plan_model`, `task_model`, `review_model`, and `finalize_model` add
  `--model <name>` to the GigaCode invocation for their phases.
- review agents use `review_model`, falling back to `task_model`.
- synthesis/fixes always use `task_model`, the same model as task execution.
- `plan_model` falls back to `task_model`, and `finalize_model` falls back to
  `review_model`/`task_model`.
# gigalphex
