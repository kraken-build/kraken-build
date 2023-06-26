from __future__ import annotations

import enum
from typing import Callable, Iterable, TypeVar

__all__ = [
    "exactly_one",
    "flatten",
    "not_none",
    "one",
]

T = TypeVar("T")


def get_message(message: str | Callable[[], str] | None) -> str | None:
    if callable(message):
        return message()
    return message


def flatten(it: Iterable[Iterable[T]]) -> Iterable[T]:
    """
    Flatten a nested iterable into a single iterable.
    """

    for item in it:
        yield from item


def not_none(v: "T | None", message: str | Callable[[], str] = "expected not-None") -> T:
    """
    Raise a :class:`RuntimeError` if *v* is `None`, otherwise return *v*.
    """

    if v is None:
        raise RuntimeError(get_message(message))
    return v


def one(it: Iterable[T], message: str | Callable[[], str] | None = None) -> T | None:
    iterator = iter(it)
    try:
        item = next(iterator)
    except StopIteration:
        return None
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise ValueError(f"expected exactly one item, got more than one {get_message(message)}")
    return item


def exactly_one(it: Iterable[T], message: str | Callable[[], str] | None = None) -> T:
    item = one(it, message)
    if item is None:
        raise ValueError(f"expected exactly one item, got zero (message: {get_message(message)})")
    return item


class NotSet(enum.Enum):
    Value = 1
