ALL_TASKS_DONE = "<<<RALPHEX:ALL_TASKS_DONE>>>"
TASK_FAILED = "<<<RALPHEX:TASK_FAILED>>>"
REVIEW_DONE = "<<<RALPHEX:REVIEW_DONE>>>"


def detect_signal(text: str) -> str:
    if ALL_TASKS_DONE in text:
        return ALL_TASKS_DONE
    if TASK_FAILED in text:
        return TASK_FAILED
    if REVIEW_DONE in text:
        return REVIEW_DONE
    return ""
