import inspect

import pytest
from kraken.core import Context, Project
from kraken.core.address import Address

from kraken.targets.core.resolve_targets import ResolvedTargets, ResolveTargetsRequest
from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.target import Target, create_target


@pytest.fixture
def runner() -> RuleRunner:
    return RuleRunner(["kraken.targets.core.resolve_targets"])


def test__resolve_targets(kraken_ctx: Context, kraken_project: Project, runner: RuleRunner) -> None:
    context = kraken_ctx
    project = kraken_project

    runner.engine.assert_facts([context])
    target = create_target("mytarget", project, Target.Data(), inspect.currentframe())

    request = ResolveTargetsRequest(addresses=(Address(project.address.append("mytarget")),), transitive=False)
    response = runner.get(ResolvedTargets, [request])
    assert response.targets == (target,)
