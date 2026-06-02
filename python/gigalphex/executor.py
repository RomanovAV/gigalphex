from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from .signals import detect_signal


@dataclass
class ExecResult:
    output: str
    signal: str = ""
    returncode: int = 0
    timed_out: bool = False
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class GigaCodeExecutor:
    def __init__(
        self,
        command: str = "gigacode",
        args: Optional[list[str]] = None,
        timeout: Optional[int] = None,
        retry_count: int = 0,
        retry_delay: float = 2.0,
        max_workers: int = 5,
        output: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.timeout = timeout
        self.retry_count = max(0, retry_count)
        self.retry_delay = max(0.0, retry_delay)
        self.max_workers = max(1, max_workers)
        self.output = output or (lambda line: print(line, end=""))

    def run(self, prompt: str) -> ExecResult:
        return self._run_with_retries(prompt, self.output)

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
        return " ".join([self.command, *self.args])

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
                time.sleep(self.retry_delay)
        assert last is not None
        return last

    def _run_once(self, prompt: str, output: Callable[[str], None]) -> ExecResult:
        return self._run(prompt, output)

    def _run(self, prompt: str, output: Callable[[str], None]) -> ExecResult:
        argv = [self.command, *self.args]
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"gigacode command not found: {self.command}") from exc

        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(prompt)
        proc.stdin.close()

        chunks: list[str] = []
        timed_out = False

        def kill_on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            proc.kill()

        timer: Optional[threading.Timer] = None
        if self.timeout is not None and self.timeout > 0:
            timer = threading.Timer(self.timeout, kill_on_timeout)
            timer.daemon = True
            timer.start()
        try:
            for line in proc.stdout:
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
            proc.stdout.close()

        text = "".join(chunks)
        return ExecResult(output=text, signal=detect_signal(text), returncode=returncode, timed_out=timed_out)


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
