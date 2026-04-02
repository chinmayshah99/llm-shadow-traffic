from __future__ import annotations

from time import perf_counter


def elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)
