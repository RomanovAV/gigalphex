ALL_TASKS_DONE = "<<<GIGALPHEX:ALL_TASKS_DONE>>>"
TASK_FAILED = "<<<GIGALPHEX:TASK_FAILED>>>"
REVIEW_DONE = "<<<GIGALPHEX:REVIEW_DONE>>>"
FINALIZE_DONE = "<<<GIGALPHEX:FINALIZE_DONE>>>"
FINALIZE_FAILED = "<<<GIGALPHEX:FINALIZE_FAILED>>>"


def detect_signal(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    last_line = lines[-1]
    known_signals = {
        ALL_TASKS_DONE,
        TASK_FAILED,
        REVIEW_DONE,
        FINALIZE_DONE,
        FINALIZE_FAILED,
    }
    return last_line if last_line in known_signals else ""
