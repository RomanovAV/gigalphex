#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gigalphex-diagnostic.XXXXXX")"
PROMPT="${GIGALPHEX_DIAGNOSTIC_PROMPT:-выполни pwd через run_shell_command}"
PYTHONPATH_VALUE="${REPO_ROOT}/python"

if [[ -n "${PYTHONPATH:-}" ]]; then
  PYTHONPATH_VALUE="${PYTHONPATH_VALUE}:${PYTHONPATH}"
fi

run_test() {
  local label="$1"
  local logfile="$2"
  shift 2

  printf '\n=== %s ===\n' "${label}"
  "$@" 2>&1 | tee "${logfile}"
  local status="${PIPESTATUS[0]}"
  printf '\nexit status: %s\n' "${status}"
  return "${status}"
}

run_inherited_test() {
  local label="$1"
  local logfile="$2"
  shift 2

  printf '\n=== %s ===\n' "${label}"
  "$@"
  local status="$?"
  printf '\nexit status: %s\n' "${status}"
  printf 'exit status: %s\n' "${status}" >"${logfile}"
  return "${status}"
}

has_approval_warning() {
  grep -q "requires user approval but cannot execute in non-interactive mode" "$1"
}

printf 'GigaCode/GigaLphex diagnostic\n'
printf 'working directory: %s\n' "${PWD}"
printf 'gigalphex repository: %s\n' "${REPO_ROOT}"
printf 'log directory: %s\n' "${LOG_DIR}"
printf 'gigacode executable: %s\n' "$(command -v gigacode 2>/dev/null || printf 'NOT FOUND')"
printf 'python executable: %s\n' "$(command -v python3 2>/dev/null || printf 'NOT FOUND')"
printf 'stdin is a terminal: %s\n' "$([[ -t 0 ]] && printf yes || printf no)"
printf 'stdout is a terminal: %s\n' "$([[ -t 1 ]] && printf yes || printf no)"

if ! command -v gigacode >/dev/null 2>&1; then
  printf '\nERROR: gigacode is not available in PATH.\n'
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf '\nERROR: python3 is not available in PATH.\n'
  exit 2
fi

printf '\n=== versions ===\n'
gigacode --version 2>&1 || true
python3 --version 2>&1 || true

printf '\n=== active overrides ===\n'
env | grep -E '^(GIGALPHEX|GIGACODE)_' | sort || printf '(none)\n'

printf '\n=== relevant configuration files ===\n'
for candidate in \
  "${PWD}/.gigalphex/config" \
  "${HOME}/.config/gigalphex/config" \
  "${HOME}/.gigacode/settings.json" \
  "${HOME}/.gigacode/hooks.json"
do
  if [[ -f "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
  fi
done
find "${PWD}" -maxdepth 3 -type f \
  \( -name settings.json -o -name hooks.json -o -name '*.hook.json' \) \
  -print 2>/dev/null | sort || true

printf '\n=== loaded GigaLphex implementation ===\n'
env PYTHONPATH="${PYTHONPATH_VALUE}" python3 -c '
from gigalphex import defaults, executor
print("executor:", executor.__file__)
print("default args:", defaults.DEFAULT_GIGACODE_ARGS)
' 2>&1 | tee "${LOG_DIR}/implementation.log"

DIRECT_LOG="${LOG_DIR}/direct.log"
PYTHON_RUN_LOG="${LOG_DIR}/python-run.log"
PYTHON_CAPTURE_LOG="${LOG_DIR}/python-capture.log"
EXECUTOR_LOG="${LOG_DIR}/executor.log"

run_inherited_test \
  "1. direct gigacode" \
  "${DIRECT_LOG}" \
  gigacode \
  -p "${PROMPT}" \
  --approval-mode=auto-edit \
  --allowed-tools run_shell_command
DIRECT_STATUS="$?"

run_inherited_test \
  "2. python subprocess.run with inherited terminal" \
  "${PYTHON_RUN_LOG}" \
  env DIAG_PROMPT="${PROMPT}" python3 -c '
import os
import subprocess
import sys

argv = [
    "gigacode",
    "-p", os.environ["DIAG_PROMPT"],
    "--approval-mode=auto-edit",
    "--allowed-tools", "run_shell_command",
]
raise SystemExit(subprocess.run(argv).returncode)
'
PYTHON_RUN_STATUS="$?"

run_test \
  "3. python Popen with captured stdout" \
  "${PYTHON_CAPTURE_LOG}" \
  env DIAG_PROMPT="${PROMPT}" python3 -c '
import os
import subprocess

argv = [
    "gigacode",
    "-p", os.environ["DIAG_PROMPT"],
    "--approval-mode=auto-edit",
    "--allowed-tools", "run_shell_command",
]
proc = subprocess.Popen(
    argv,
    stdin=None,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
)
assert proc.stdout is not None
for line in proc.stdout:
    print(line, end="")
raise SystemExit(proc.wait())
'
PYTHON_CAPTURE_STATUS="$?"

run_test \
  "4. GigaCodeExecutor smoke test" \
  "${EXECUTOR_LOG}" \
  env \
  PYTHONPATH="${PYTHONPATH_VALUE}" \
  DIAG_PROMPT="${PROMPT}" \
  python3 -c '
import os
from gigalphex.executor import GigaCodeExecutor

result = GigaCodeExecutor(retry_count=0).run(os.environ["DIAG_PROMPT"])
raise SystemExit(0 if result.ok else result.returncode or 1)
'
EXECUTOR_STATUS="$?"

printf '\n=== diagnosis ===\n'
printf 'direct: %s\n' "${DIRECT_STATUS}"
printf 'python inherited: %s\n' "${PYTHON_RUN_STATUS}"
printf 'python captured: %s\n' "${PYTHON_CAPTURE_STATUS}"
printf 'GigaCodeExecutor: %s\n' "${EXECUTOR_STATUS}"

if (( DIRECT_STATUS != 0 )); then
  printf 'Result: GigaCode or project-level policy/configuration fails even without GigaLphex.\n'
elif (( PYTHON_RUN_STATUS != 0 )); then
  printf 'Result: launching GigaCode as a Python child process changes its approval behavior.\n'
elif (( PYTHON_CAPTURE_STATUS != 0 )) || has_approval_warning "${PYTHON_CAPTURE_LOG}"; then
  printf 'Result: capturing GigaCode stdout triggers the failure; a PTY or inherited stdout is required.\n'
elif (( EXECUTOR_STATUS != 0 )) || has_approval_warning "${EXECUTOR_LOG}"; then
  printf 'Result: the problem is inside GigaCodeExecutor or its loaded configuration.\n'
else
  printf 'Result: all minimal checks pass. The failure depends on the full task prompt or project operations.\n'
fi

printf 'Attach this directory if further analysis is needed: %s\n' "${LOG_DIR}"
