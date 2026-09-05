"""Small shared helpers for the application."""

from functools import wraps
from time import sleep
from typing import Callable, ParamSpec, TypeVar


P = ParamSpec("P")
T = TypeVar("T")


def retry(max_retries: int = 3, delay_seconds: float = 1.0) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry a function after exceptions, then re-raise its final error.

    ``max_retries=3`` means one initial attempt plus up to three retries.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be zero or greater")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_retries:
                        raise
                    sleep(delay_seconds)

            raise RuntimeError("Retry loop ended unexpectedly")  # pragma: no cover

        return wrapper

    return decorator
