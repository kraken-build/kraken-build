from dataclasses import dataclass
from typing import Any

from adjudicator import collect_rules, get, rule
from kraken.core import Context
from kraken.core.address import Address
from kraken.core.system.errors import ProjectNotFoundError

from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.target import Target, TargetNotFoundError, get_target


@dataclass(frozen=True)
class ResolveTargetsRequest:
    addresses: tuple[Address, ...]
    transitive: bool = False


@dataclass(frozen=True)
class ResolvedTargets:
    targets: tuple[Target[Any], ...]


class ResolveAddressError(Exception):
    pass


@rule
def resolve_targets(request: ResolveTargetsRequest) -> ResolvedTargets:
    """
    Resolve the given targets.
    """

    context = get(Context)
    results = []

    for address in request.addresses:
        if not address.is_absolute():
            raise ValueError(f"Cannot resolve relative address {address!r}")
        try:
            project = context.get_project(address.parent)
        except ProjectNotFoundError:
            raise ResolveAddressError(address)
        try:
            results.append(get_target(project, address.name))
        except TargetNotFoundError:
            raise ResolveAddressError(address)

    return ResolvedTargets(tuple(results))


def register(runner: RuleRunner) -> None:
    runner.engine.add_rules(collect_rules())
