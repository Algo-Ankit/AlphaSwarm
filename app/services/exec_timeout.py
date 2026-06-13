"""
Wall-clock budget for user strategy code.

The RestrictedPython sandbox blocks `while` and the `iter(int, 1)` trick, but it
cannot stop every CPU-exhaustion vector — `for i in range(10**18): ...` hangs
just as hard, and the AST prescan can't catch it. This puts a hard ceiling on
how long a single strategy evaluation may run.

Mechanism: SIGALRM. It fires inside the running thread and raises StrategyTimeout
mid-call, so it interrupts even a single hung on_bar() (a deadline you only check
between calls cannot). SIGALRM is POSIX-only and main-thread-only — exactly the
case for Celery prefork workers (Linux/Docker), where strategy code runs. When
unavailable (Windows dev, eager mode, a non-main thread) this degrades to a
no-op and Celery's task_time_limit hard kill remains the backstop.
"""
from __future__ import annotations

import signal
import threading
from contextlib import contextmanager


class StrategyTimeout(Exception):
    """Strategy code exceeded its wall-clock execution budget."""


def _can_use_sigalrm() -> bool:
    return (
        hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )


@contextmanager
def time_limit(seconds: float):
    """
    Raise StrategyTimeout if the wrapped block runs longer than `seconds`.
    A no-op when seconds <= 0 or SIGALRM is unavailable on this platform/thread.
    """
    if seconds <= 0 or not _can_use_sigalrm():
        yield
        return

    def _handler(signum, frame):
        raise StrategyTimeout(
            f"strategy execution exceeded its {seconds:g}s budget"
        )

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
