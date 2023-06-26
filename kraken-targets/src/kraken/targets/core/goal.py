from dataclasses import dataclass
from typing import ClassVar


class GoalSubsystem:
    """
    The GoalSubsystem represents the external API for a goal.
    """

    name: str
    help: str


@dataclass(frozen=True)
class Goal:
    """
    A goal is a type that is returned by a rule that orchestrates the execution of other rules.
    """

    subsystem_cls: ClassVar[type[GoalSubsystem]]
    exit_code: int
