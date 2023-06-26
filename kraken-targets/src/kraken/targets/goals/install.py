from adjudicator import collect_rules, get, rule

from kraken.targets.core.goal import Goal, GoalSubsystem
from kraken.targets.core.resolve_targets import ResolvedTargets, ResolveTargetsRequest
from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.subtypes import SubtypesRegistry
from kraken.targets.core.targetselection import TargetSelection


class InstallGoalSubsystem(GoalSubsystem):
    name = "install"
    help = "Install the project."


class InstallGoal(Goal):
    subsystem_cls = InstallGoalSubsystem


@rule
def do_install(
    system: InstallGoalSubsystem,
    subtypes: SubtypesRegistry,
    selection: TargetSelection,
) -> InstallGoal:
    from kraken.targets.python.venv import PythonVenvInstallGoal

    targets = get(ResolvedTargets, ResolveTargetsRequest(selection)).targets
    for target in targets:
        result = get(PythonVenvInstallGoal, target.data)
        if result.exit_code != 0:
            return InstallGoal(exit_code=result.exit_code)

    return InstallGoal(exit_code=0)


def register(runner: RuleRunner) -> None:
    runner.load("kraken.targets.core.resolve_targets")
    runner.engine.add_rules(collect_rules())
