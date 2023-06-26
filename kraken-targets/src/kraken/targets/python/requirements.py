from dataclasses import dataclass

from adjudicator import collect_rules, rule

from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.target import Target, make_target_factory


@dataclass(frozen=True)
class PythonRequirements(Target.Data):
    requirements: tuple[str]


@dataclass(frozen=True)
class PythonRequirement(Target.Data):
    requirement: str


python_requirement = make_target_factory("python_requirement", PythonRequirement)
python_requirements = make_target_factory("python_requirements", PythonRequirements)


class PythonRequirementSet(frozenset[PythonRequirement]):
    pass


@rule
def fan_out_python_requirement(req: PythonRequirement) -> PythonRequirementSet:
    return PythonRequirementSet([req])


@rule
def fan_out_python_requirements(reqs: PythonRequirements) -> PythonRequirementSet:
    return PythonRequirementSet(PythonRequirement(req) for req in reqs.requirements)


def register(runner: RuleRunner) -> None:
    runner.engine.add_rules(collect_rules())
