# GigaCode Verification Checklist

Use this checklist on a machine where `gigacode` is installed. Add notes,
outputs, and failures under each section as you test.

## Historical Baseline

These checks passed in prior verification runs with GigaCode `26.5.17`:

- `gigacode` is available at `/Users/19268765/.gigacode/bin/gigacode`.
- Unit tests passed from the repository root: `19/19`, then `20/20` after the
  prompt-placeholder fix.
- `--init` created config and all prompt templates.
- `--plan --dry-run` printed the plan-generation prompt and did not invoke
  `gigacode`.
- Real `--plan` created markdown plans under `docs/plans/`.
- Generated plans were not wrapped in markdown code fences.
- Repeated `--plan` did not overwrite the first file; it created `-2.md`.
- Custom `.gigalphex/prompts/make_plan.txt` overrode the embedded prompt.
- The previous newline fix worked: `created plan:` and `progress log:` no
  longer stick to the last line of GigaCode output.
- Small task execution passed end-to-end on 2026-06-12 with the default
  `gigacode -p '<prompt>' --approval-mode=auto-edit --allowed-tools run_shell_command`
  invocation. GigaCode created `SMOKE_TEST.md`, marked the task checkboxes,
  committed the changes, and emitted the completion signal.

The formerly unresolved item was small task execution. When the prompt was sent
through stdin, GigaCode warned that `run_shell_command` needed approval and the
task failed before commit. Passing the prompt through `-p {prompt}` fixed the
invocation shape but did not allow shell commands by itself. GigaCode help for
26.5.17 says `--approval-mode=auto-edit` allows edit/write tools, while shell
commands require `--allowed-tools run_shell_command`. The current default uses
that full invocation and the 2026-06-12 smoke run confirmed autonomous commits
without a manual follow-up.

## Current Retest Scope

Run these checks after updating to the latest code. The first two are quick
sanity checks; the third is the real regression test.

## 1. Check GigaCode Availability

```bash
command -v gigacode
gigacode --version
```

Expected:

- `gigacode` is found in `PATH`.
- Version command returns successfully.

Notes:

```text

```

## 2. Run Unit Tests From Repository Root

From the repository root, not from `/tmp`:

```bash
cd /path/to/gigalphex
PYTHONPATH=python python3 -m unittest discover -s tests
```

Expected:

- All tests pass.

Notes:

```text

```

## 3. Verify Small Task Execution With Shell Tool Allowed

Use a clean temporary git repository so the smoke test cannot disturb real work:

```bash
mkdir -p /tmp/gigalphex-task-check
cd /tmp/gigalphex-task-check
git init
git config user.email "test@example.com"
git config user.name "GigaLphex Test"
mkdir -p docs/plans
cat > README.md <<'EOF'
# Smoke Repo
EOF
git add README.md
git commit -m "initial commit"
```

Create `docs/plans/20260612-smoke.md`:

```md
# Plan: Smoke test

## Overview
Add a tiny smoke-test artifact.

## Context
This checks that gigalphex can run GigaCode non-interactively.

### Task 1: Add smoke file
- [ ] Create `SMOKE_TEST.md` with one short sentence.
- [ ] Mark this task complete.
- [ ] Commit the change.

## Validation
- git status --short
```

Run:

```bash
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli docs/plans/20260612-smoke.md --allow-dirty --tasks-only --no-move-plan
```

Expected:

- No warning like `Tool "run_shell_command" requires user approval`.
- The startup section logs
  `gigacode -p '<prompt>' --approval-mode=auto-edit --allowed-tools run_shell_command`,
  not the full prompt text.
- `SMOKE_TEST.md` is created and contains a non-empty sentence.
- The checkbox in the plan is marked `[x]`.
- A new commit is created after `initial commit`.
- The command exits successfully and prints `progress log: ...`.
- The progress log contains `<<<GIGALPHEX:ALL_TASKS_DONE>>>` or a clear success
  path, not `<<<GIGALPHEX:TASK_FAILED>>>`.

Collect:

```bash
git log --oneline --decorate -5
git status --short
cat docs/plans/20260612-smoke.md
cat SMOKE_TEST.md
cat .gigalphex/progress/progress-20260612-smoke.txt
```

Notes:

```text
Verified on 2026-06-12 in /tmp/gigalphex-task-check.

Command:
PYTHONPATH=/Users/19268765/IdeaProjects/gigalphex-new/python:$PYTHONPATH python3 -m gigalphex.cli docs/plans/20260612-smoke.md --allow-dirty --tasks-only --no-move-plan

Observed:
- No non-interactive shell approval warning.
- Startup logged: gigacode -p '<prompt>' --approval-mode=auto-edit --allowed-tools run_shell_command
- Created SMOKE_TEST.md with a non-empty sentence.
- Marked all three Task 1 checkboxes as [x].
- Created commits:
  81796c9 feat: mark smoke-task checkboxes complete
  e84517b feat: add smoke-test artifact
- Emitted the completion signal and exited successfully.
- Left only untracked .gigalphex/ progress files in the smoke repository.
```

## Optional Regression Checks

The following already passed historically. Re-run only if related code changed.

## 4. Verify `--init` in a Clean Directory

```bash
mkdir -p /tmp/gigalphex-init-check
cd /tmp/gigalphex-init-check
PYTHONPATH=/path/to/gigalphex/python python3 -m gigalphex.cli --init
find .gigalphex -type f | sort
```

Expected files:

```text
.gigalphex/config
.gigalphex/prompts/finalize.txt
.gigalphex/prompts/make_plan.txt
.gigalphex/prompts/review.txt
.gigalphex/prompts/review_agent.txt
.gigalphex/prompts/review_synthesis.txt
.gigalphex/prompts/task.txt
```

## 5. Verify `--plan --dry-run`

```bash
cd /path/to/gigalphex
PYTHONPATH=python python3 -m gigalphex.cli --plan "add health check endpoint" --dry-run
```

Expected:

- Prints the plan-generation prompt.
- Does not invoke `gigacode`.
- Prints `progress log: .gigalphex/progress/progress-plan.txt`.

## 6. Verify Real Plan Generation

From the repository root:

```bash
cd /path/to/gigalphex
PYTHONPATH=python python3 -m gigalphex.cli --plan "add health check endpoint"
```

Expected:

- Creates a file like `docs/plans/YYYYMMDD-add-health-check-endpoint.md`.
- The file contains a markdown plan.
- The plan includes `# Plan:`, `## Overview`, `## Context`, and at least one `### Task 1:` section.
- Task items use checkbox format: `- [ ] ...`.
- The saved file does not wrap the whole plan in markdown code fences.

Notes:

```text

```

## 7. Verify Repeated Plan Generation Does Not Overwrite

Run the same command again:

```bash
PYTHONPATH=python python3 -m gigalphex.cli --plan "add health check endpoint"
```

Expected:

- Creates a second file with a numeric suffix, such as
  `docs/plans/YYYYMMDD-add-health-check-endpoint-2.md`.
- The first generated plan remains unchanged.

Notes:

```text

```

## 8. Verify Custom `make_plan.txt`

From the repository root:

```bash
cd /path/to/gigalphex
PYTHONPATH=python python3 -m gigalphex.cli --init
printf 'CUSTOM PLAN PROMPT: {plan_request}\n' > .gigalphex/prompts/make_plan.txt
PYTHONPATH=python python3 -m gigalphex.cli --plan "demo request" --dry-run
```

Expected:

- Output contains `CUSTOM PLAN PROMPT: demo request`.
- This confirms local prompt templates override embedded defaults.

Notes:

```text

```

## Things to Watch Closely

- Does `gigacode` accept the generated prompt through `-p {prompt}`?
- Does `--approval-mode=auto-edit --allowed-tools run_shell_command` avoid
  non-interactive approval failures?
- Does any run hang without output?
- Does generated markdown contain extra commentary or code fences?
- Does task execution emit one of the expected signals when done?
- Does the progress log contain enough detail to debug failures?

Notes:

```text

```
