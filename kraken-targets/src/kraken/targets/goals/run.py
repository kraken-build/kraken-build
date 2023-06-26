from typing import ClassVar

from adjudicator import collect_rules, get, rule
from kraken.common import one

from kraken.targets.core.goal import Goal, GoalSubsystem
from kraken.targets.core.resolve_targets import ResolvedTargets, ResolveTargetsRequest
from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.subtypes import SubtypesRegistry
from kraken.targets.core.targetselection import TargetSelection


class RunGoalSubsystem(GoalSubsystem):
    name = "run"
    help = "Run an executable."


class RunGoal(Goal):
    subsystem_cls = RunGoalSubsystem
    requirements: ClassVar[tuple[type, ...]] = ()


@rule
def do_run(
    system: RunGoalSubsystem,
    subtypes: SubtypesRegistry,
    selection: TargetSelection,
) -> RunGoal:
    from kraken.targets.python.venv import PythonExecutableRunGoal

    targets = get(ResolvedTargets, ResolveTargetsRequest(selection)).targets
    for target in targets:
        dependencies = get(ResolvedTargets, ResolveTargetsRequest(tuple(target.dependencies))).targets
        inputs = list(
            filter(
                None,
                (
                    one(x.data for x in dependencies if isinstance(x.data, req_type))
                    for req_type in PythonExecutableRunGoal.requirements
                ),
            )
        )
        print(inputs, PythonExecutableRunGoal.requirements, dependencies)
        result = get(PythonExecutableRunGoal, target.data, *inputs)
        if result.exit_code != 0:
            return RunGoal(exit_code=result.exit_code)

    return RunGoal(exit_code=0)


def register(runner: RuleRunner) -> None:
    runner.load("kraken.targets.core.resolve_targets")
    runner.engine.add_rules(collect_rules())
