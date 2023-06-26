from collections import defaultdict
from typing import Any, Collection, DefaultDict


class SubtypesRegistry:
    """
    This class is a registry that keeps track of types and their known subtypes. It is used by goal rules to
    dispatch to the appropriate rules.
    """

    def __init__(self) -> None:
        self._subtypes: DefaultDict[type[Any], set[type[Any]]] = defaultdict(set)

    def members(self, type_: type[Any]) -> Collection[type[Any]]:
        return self._subtypes[type_]

    def register(self, type_: type[Any], subtype: type[Any]) -> None:
        self._subtypes[type_].add(subtype)
