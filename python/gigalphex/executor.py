from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import shlex
import sys
import threading
import time
from typing import Callable, Optional

from .defaults import DEFAULT_GIGACODE_ARGS
from .signals import detect_signal


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
        )

    @property
    def approval_unavailable(self) -> bool:
        return "requires user approval but cannot execute in non-interactive mode" in self.output


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

    def run(self, prompt: str) -> ExecResult:
        return self._run_with_retries(prompt, self.output)

    def run_interactive(self, prompt: str) -> ExecResult:
        argv, stdin_prompt = self._build_invocation(
            prompt,
            require_placeholder=True,
        )
        if stdin_prompt:
            raise ValueError(
                "interactive GigaCode args must include {prompt}; "
                "configure gigacode_interactive_args"
            )
        try:
            proc = subprocess.run(
                argv,
                timeout=self.timeout if self.timeout and self.timeout > 0 else None,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"gigacode command not found: {self.command}") from exc
        except subprocess.TimeoutExpired:
            return ExecResult(output="", returncode=-1, timed_out=True)
        return ExecResult(output="", returncode=proc.returncode)

    def run_batch(self, prompts: dict[str, str]) -> dict[str, ExecResult]:
        if not prompts:
            return {}
        results: dict[str, ExecResult] = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(prompts))) as pool:
            futures = {
                pool.submit(self._run_with_retries, prompt, lambda _line: None): name
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

    def _run_with_retries(self, prompt: str, output: Callable[[str], None]) -> ExecResult:
        attempts = self.retry_count + 1
        last: Optional[ExecResult] = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                output(f"retrying gigacode command, attempt {attempt}/{attempts}\n")
            result = self._run_once(prompt, output)
            result.attempts = attempt
            if result.ok:
                return result
            last = result
            if attempt < attempts:
                delay = self._retry_delay(result)
                if result.rate_limited and delay > 0:
                    output(f"rate limit detected; waiting {delay:g}s before retry\n")
                elif result.transient_error and delay > 0:
                    output(f"transient error detected; waiting {delay:g}s before retry\n")
                time.sleep(delay)
        assert last is not None
        return last

    def _run_once(self, prompt: str, output: Callable[[str], None]) -> ExecResult:
        return self._run(prompt, output)

    def _retry_delay(self, result: ExecResult) -> float:
        if result.rate_limited and self.wait_on_rate_limit is not None:
            return max(0.0, self.wait_on_rate_limit)
        return self.retry_delay

    def _run(self, prompt: str, output: Callable[[str], None]) -> ExecResult:
        argv, stdin_prompt = self._build_invocation(prompt)
        pipe_stdin = bool(stdin_prompt)
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if pipe_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"gigacode command not found: {self.command}") from exc

        assert proc.stdout is not None
        if pipe_stdin:
            assert proc.stdin is not None
            proc.stdin.write(stdin_prompt)
            proc.stdin.close()

        chunks: list[str] = []
        timed_out = False
        idle_timed_out = False

        def kill_process() -> None:
            if proc.poll() is None:
                proc.kill()

        def kill_on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            kill_process()

        def kill_on_idle_timeout() -> None:
            nonlocal idle_timed_out
            idle_timed_out = True
            kill_process()

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
            for line in proc.stdout:
                reset_idle_timer()
                chunks.append(line)
                output(line)
            returncode = proc.wait()
        except KeyboardInterrupt:
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
        return ExecResult(
            output=text,
            signal=detect_signal(text),
            returncode=returncode,
            timed_out=timed_out,
            idle_timed_out=idle_timed_out,
            transient_error=failed and matches_any(text, self.retry_patterns),
            rate_limited=failed and matches_any(text, self.rate_limit_patterns),
        )

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


def matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern and pattern.lower() in lowered for pattern in patterns)


class DryRunExecutor:
    def __init__(self, output: Optional[Callable[[str], None]] = None) -> None:
        self.output = output or (lambda line: sys.stdout.write(line))
        self.prompts: list[str] = []

    def run(self, prompt: str) -> ExecResult:
        self.prompts.append(prompt)
        self.output("--- DRY RUN PROMPT ---\n")
        self.output(prompt)
        self.output("\n--- END PROMPT ---\n")
        return ExecResult(output="", returncode=0)
