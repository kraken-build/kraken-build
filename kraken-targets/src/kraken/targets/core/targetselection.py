from typing import Iterable

from kraken.core.address import Address


class TargetSelection(tuple[Address]):
    """
    Represents a collection of targets.
    """

    def __new__(self, targets: Iterable[str | Address]) -> None:
        return tuple.__new__(self, map(Address, targets))
