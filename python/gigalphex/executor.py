from __future__ import annotations

import codecs
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import threading
import time
from typing import Callable, Optional

from .defaults import DEFAULT_GIGACODE_ARGS
from .signals import detect_signal


APPROVAL_UNAVAILABLE_TEXT = (
    "requires user approval but cannot execute in non-interactive mode"
)


DEFAULT_TRANSIENT_RETRY_PATTERNS = [
    "FYA_TRANSIENT_TIMEOUT",
    "API Error: 529",
    "API Error: 502",
    "API Error: 503",
    "API Error: 504",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
]

DEFAULT_RATE_LIMIT_PATTERNS = [
    "Rate limit exceeded",
    "rate limit reached",
    "429 Too Many Requests",
    "quota exceeded",
    "insufficient_quota",
    "You've hit your usage limit",
]


@dataclass
class ExecResult:
    output: str
    signal: str = ""
    returncode: int = 0
    timed_out: bool = False
    idle_timed_out: bool = False
    transient_error: bool = False
    rate_limited: bool = False
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return (
            self.returncode == 0
            and not self.timed_out
            and not self.idle_timed_out
            and not self.transient_error
            and not self.rate_limited
            and not self.approval_unavailable
        )

    @property
    def approval_unavailable(self) -> bool:
        return APPROVAL_UNAVAILABLE_TEXT in self.output


RetryGuard = Callable[[ExecResult], bool]


class GigaCodeExecutor:
    def __init__(
        self,
        command: str = "gigacode",
        args: Optional[list[str]] = None,
        timeout: Optional[int] = None,
        idle_timeout: Optional[int] = None,
        retry_count: int = 0,
        retry_delay: float = 2.0,
        retry_patterns: Optional[list[str]] = None,
        rate_limit_patterns: Optional[list[str]] = None,
        wait_on_rate_limit: Optional[float] = None,
        max_workers: int = 5,
        output: Optional[Callable[[str], None]] = None,
        diagnostic: Optional[Callable[[str], None]] = None,
        name: str = "gigacode",
    ) -> None:
        self.command = command
        self.args = args if args is not None else DEFAULT_GIGACODE_ARGS.copy()
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.retry_count = max(0, retry_count)
        self.retry_delay = max(0.0, retry_delay)
        self.retry_patterns = retry_patterns if retry_patterns is not None else DEFAULT_TRANSIENT_RETRY_PATTERNS.copy()
        self.rate_limit_patterns = (
            rate_limit_patterns if rate_limit_patterns is not None else DEFAULT_RATE_LIMIT_PATTERNS.copy()
        )
        self.wait_on_rate_limit = wait_on_rate_limit
        self.max_workers = max(1, max_workers)
        self.output = output or (lambda line: print(line, end=""))
        self.diagnostic = diagnostic or (lambda _line: None)
        self.name = name

    def run(
        self,
        prompt: str,
        *,
        retry_guard: Optional[RetryGuard] = None,
    ) -> ExecResult:
        return self._run_with_retries(
            prompt,
            self.output,
            self.name,
            retry_guard=retry_guard,
        )

    def run_interactive(self, prompt: str) -> ExecResult:
        session = self.name
        started = time.monotonic()
        argv, stdin_prompt = self._build_invocation(
            prompt,
            require_placeholder=True,
        )
        if stdin_prompt:
            raise ValueError(
                "interactive GigaCode args must include {prompt}; "
                "configure gigacode_interactive_args"
            )
        self._event(
            session,
            "prepared",
            mode="interactive",
            command=self._safe_command(argv, prompt),
            prompt_chars=len(prompt),
            prompt_transport="argv",
            cwd=Path.cwd(),
            stdin_tty=sys.stdin.isatty(),
            stdout_tty=sys.stdout.isatty(),
        )
        try:
            self._event(session, "launching")
            proc = subprocess.run(
                argv,
                timeout=self.timeout if self.timeout and self.timeout > 0 else None,
            )
        except FileNotFoundError as exc:
            self._event(session, "launch_failed", error="command_not_found")
            raise RuntimeError(f"gigacode command not found: {self.command}") from exc
        except subprocess.TimeoutExpired:
            self._event(
                session,
                "finished",
                returncode=-1,
                duration_ms=_elapsed_ms(started),
                timed_out=True,
            )
            return ExecResult(output="", returncode=-1, timed_out=True)
        self._event(
            session,
            "finished",
            returncode=proc.returncode,
            duration_ms=_elapsed_ms(started),
            timed_out=False,
        )
        return ExecResult(output="", returncode=proc.returncode)

    def run_batch(self, prompts: dict[str, str]) -> dict[str, ExecResult]:
        if not prompts:
            return {}
        results: dict[str, ExecResult] = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(prompts))) as pool:
            futures = {
                pool.submit(
                    self._run_with_retries,
                    prompt,
                    lambda _line: None,
                    f"{self.name}:{name}",
                ): name
                for name, prompt in prompts.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()
        return results

    def command_line(self) -> str:
        safe_args = [arg.replace("{prompt}", "<prompt>") for arg in self.args]
        if not any("{prompt}" in arg for arg in self.args):
            safe_args.extend(["-p", "<prompt>"])
        return shlex.join([self.command, *safe_args])

    def _run_with_retries(
        self,
        prompt: str,
        output: Callable[[str], None],
        session: str,
        retry_guard: Optional[RetryGuard] = None,
    ) -> ExecResult:
        attempts = self.retry_count + 1
        last: Optional[ExecResult] = None
        for attempt in range(1, attempts + 1):
            self._event(session, "attempt_started", attempt=attempt, attempts=attempts)
            if attempt > 1:
                output(f"retrying gigacode command, attempt {attempt}/{attempts}\n")
            result = self._run_once(prompt, output, session)
            result.attempts = attempt
            if result.ok:
                self._event(session, "attempt_succeeded", attempt=attempt)
                return result
            if result.approval_unavailable:
                self._event(
                    session,
                    "retry_stopped",
                    attempt=attempt,
                    reason="approval_unavailable",
                )
                return result
            last = result
            if attempt < attempts:
                if retry_guard is not None and not retry_guard(result):
                    self._event(
                        session,
                        "retry_stopped",
                        attempt=attempt,
                        reason="retry_guard_rejected",
                    )
                    return result
                delay = self._retry_delay(result)
                self._event(
                    session,
                    "retry_scheduled",
                    next_attempt=attempt + 1,
                    delay_seconds=delay,
                    reason=_failure_reason(result),
                )
                if result.rate_limited and delay > 0:
                    output(f"rate limit detected; waiting {delay:g}s before retry\n")
                elif result.transient_error and delay > 0:
                    output(f"transient error detected; waiting {delay:g}s before retry\n")
                time.sleep(delay)
        assert last is not None
        self._event(
            session,
            "attempts_exhausted",
            attempts=attempts,
            reason=_failure_reason(last),
        )
        return last

    def _run_once(
        self,
        prompt: str,
        output: Callable[[str], None],
        session: str,
    ) -> ExecResult:
        return self._run(prompt, output, session)

    def _retry_delay(self, result: ExecResult) -> float:
        if result.rate_limited and self.wait_on_rate_limit is not None:
            return max(0.0, self.wait_on_rate_limit)
        return self.retry_delay

    def _run(
        self,
        prompt: str,
        output: Callable[[str], None],
        session: str,
    ) -> ExecResult:
        started = time.monotonic()
        argv, stdin_prompt = self._build_invocation(prompt)
        pipe_stdin = bool(stdin_prompt)
        self._event(
            session,
            "prepared",
            mode="noninteractive",
            command=self._safe_command(argv, prompt),
            prompt_chars=len(prompt),
            prompt_transport="stdin" if pipe_stdin else "argv",
            cwd=Path.cwd(),
            stdin_tty=sys.stdin.isatty(),
            stdout_tty=sys.stdout.isatty(),
            stdout_capture=True,
            timeout_seconds=self.timeout or 0,
            idle_timeout_seconds=self.idle_timeout or 0,
        )
        try:
            self._event(session, "launching")
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if pipe_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            self._event(session, "launch_failed", error="command_not_found")
            raise RuntimeError(f"gigacode command not found: {self.command}") from exc

        self._event(session, "started", pid=getattr(proc, "pid", "unknown"))
        assert proc.stdout is not None
        if pipe_stdin:
            assert proc.stdin is not None
            proc.stdin.write(stdin_prompt.encode("utf-8"))
            proc.stdin.close()
            self._event(session, "stdin_sent", chars=len(stdin_prompt))

        chunks: list[str] = []
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        approval_scan_tail = ""
        timed_out = False
        idle_timed_out = False
        first_output_seen = False

        def kill_process(reason: str) -> None:
            if proc.poll() is None:
                self._event(session, "terminating", reason=reason)
                proc.kill()

        def kill_on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            kill_process("session_timeout")

        def kill_on_idle_timeout() -> None:
            nonlocal idle_timed_out
            idle_timed_out = True
            kill_process("idle_timeout")

        timer: Optional[threading.Timer] = None
        idle_timer: Optional[threading.Timer] = None

        def reset_idle_timer() -> None:
            nonlocal idle_timer
            if self.idle_timeout is None or self.idle_timeout <= 0:
                return
            if idle_timer is not None:
                idle_timer.cancel()
            idle_timer = threading.Timer(self.idle_timeout, kill_on_idle_timeout)
            idle_timer.daemon = True
            idle_timer.start()

        if self.timeout is not None and self.timeout > 0:
            timer = threading.Timer(self.timeout, kill_on_timeout)
            timer.daemon = True
            timer.start()
        reset_idle_timer()
        try:
            for raw_chunk in _read_output_chunks(proc.stdout):
                reset_idle_timer()
                if not first_output_seen:
                    first_output_seen = True
                    self._event(
                        session,
                        "first_output",
                        elapsed_ms=_elapsed_ms(started),
                    )
                chunk = (
                    raw_chunk
                    if isinstance(raw_chunk, str)
                    else decoder.decode(raw_chunk)
                )
                if chunk:
                    chunks.append(chunk)
                    output(chunk)
                approval_scan = approval_scan_tail + chunk
                approval_scan_tail = approval_scan[-len(APPROVAL_UNAVAILABLE_TEXT):]
                if APPROVAL_UNAVAILABLE_TEXT in approval_scan:
                    self._event(session, "approval_warning_detected")
                    kill_process("approval_unavailable")
            final_chunk = decoder.decode(b"", final=True)
            if final_chunk:
                chunks.append(final_chunk)
                output(final_chunk)
            returncode = proc.wait()
        except KeyboardInterrupt:
            self._event(session, "interrupted")
            proc.kill()
            proc.wait()
            raise
        finally:
            if timer is not None:
                timer.cancel()
            if idle_timer is not None:
                idle_timer.cancel()
            proc.stdout.close()

        if chunks and not chunks[-1].endswith("\n"):
            chunks.append("\n")
            output("\n")

        text = "".join(chunks)
        failed = returncode != 0 or timed_out or idle_timed_out
        result = ExecResult(
            output=text,
            signal=detect_signal(text),
            returncode=returncode,
            timed_out=timed_out,
            idle_timed_out=idle_timed_out,
            transient_error=failed and matches_any(text, self.retry_patterns),
            rate_limited=failed and matches_any(text, self.rate_limit_patterns),
        )
        self._event(
            session,
            "finished",
            returncode=returncode,
            duration_ms=_elapsed_ms(started),
            output_chars=len(text),
            signal=result.signal or "none",
            timed_out=timed_out,
            idle_timed_out=idle_timed_out,
            transient_error=result.transient_error,
            rate_limited=result.rate_limited,
            approval_unavailable=result.approval_unavailable,
        )
        return result

    def _build_invocation(
        self,
        prompt: str,
        *,
        require_placeholder: bool = False,
    ) -> tuple[list[str], str]:
        used_placeholder = False
        args: list[str] = []
        for arg in self.args:
            if "{prompt}" in arg:
                args.append(arg.replace("{prompt}", prompt))
                used_placeholder = True
            else:
                args.append(arg)
        if not used_placeholder:
            if require_placeholder:
                return [self.command, *args], prompt
            args.extend(["-p", prompt])
        return [self.command, *args], ""

    def _safe_command(self, argv: list[str], prompt: str) -> str:
        safe_args = [
            arg.replace(prompt, "<prompt>") if prompt and prompt in arg else arg
            for arg in argv
        ]
        return shlex.join(safe_args)

    def _event(self, session: str, event: str, **fields: object) -> None:
        details = " ".join(
            f"{key}={_diagnostic_value(value)}"
            for key, value in fields.items()
        )
        suffix = f" {details}" if details else ""
        self.diagnostic(f"session={session} event={event}{suffix}")


def matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern and pattern.lower() in lowered for pattern in patterns)


def _read_output_chunks(
    stream: io.BufferedReader,
):
    if isinstance(stream, io.BufferedReader):
        file_descriptor = stream.fileno()
        while chunk := os.read(file_descriptor, 4096):
            yield chunk
        return

    # Test doubles and unusual stream wrappers may only support iteration.
    yield from stream


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _failure_reason(result: ExecResult) -> str:
    if result.approval_unavailable:
        return "approval_unavailable"
    if result.timed_out:
        return "session_timeout"
    if result.idle_timed_out:
        return "idle_timeout"
    if result.rate_limited:
        return "rate_limited"
    if result.transient_error:
        return "transient_error"
    return f"exit_{result.returncode}"


def _diagnostic_value(value: object) -> str:
    text = str(value)
    if text and all(char.isalnum() or char in "._:/-+" for char in text):
        return text
    return json.dumps(text, ensure_ascii=False)


class DryRunExecutor:
    def __init__(self, output: Optional[Callable[[str], None]] = None) -> None:
        self.output = output or (lambda line: sys.stdout.write(line))
        self.prompts: list[str] = []

    def run(
        self,
        prompt: str,
        *,
        retry_guard: Optional[RetryGuard] = None,
    ) -> ExecResult:
        self.prompts.append(prompt)
        self.output("--- DRY RUN PROMPT ---\n")
        self.output(prompt)
        self.output("\n--- END PROMPT ---\n")
        return ExecResult(output="", returncode=0)
