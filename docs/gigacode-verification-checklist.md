# GigaCode Verification Checklist

Use this checklist on a machine where `gigacode` is installed. Add notes,
outputs, and failures under each section as you test.

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

## 2. Run Unit Tests

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

## 3. Verify `--init` in a Clean Directory

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

Notes:

```text

```

## 4. Verify `--plan --dry-run`

From the repository root:

```bash
cd /path/to/gigalphex
PYTHONPATH=python python3 -m gigalphex.cli --plan "add health check endpoint" --dry-run
```

Expected:

- Prints the plan-generation prompt.
- Does not invoke `gigacode`.
- Prints `progress log: .gigalphex/progress/progress-plan.txt`.

Notes:

```text

```

## 5. Verify Real Plan Generation

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

## 6. Verify Repeated Plan Generation Does Not Overwrite

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

## 7. Verify Custom `make_plan.txt`

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

## 8. Verify Small Task Execution

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
cd /path/to/gigalphex
PYTHONPATH=python python3 -m gigalphex.cli docs/plans/20260612-smoke.md --allow-dirty --tasks-only --no-move-plan
```

Expected:

- `SMOKE_TEST.md` is created.
- The checkbox in the plan is marked `[x]`.
- A commit is created.
- A progress log appears under `.gigalphex/progress/`.

Notes:

```text

```

## Things to Watch Closely

- Does `gigacode` accept prompts through stdin?
- Does `--approval-mode=auto-edit` avoid non-interactive approval failures?
- Does any run hang without output?
- Does generated markdown contain extra commentary or code fences?
- Does task execution emit one of the expected signals when done?
- Does the progress log contain enough detail to debug failures?

Notes:

```text

```
