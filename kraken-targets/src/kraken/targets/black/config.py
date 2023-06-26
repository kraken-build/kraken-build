from dataclasses import dataclass

from kraken.targets.core.target import Target, make_target_factory


@dataclass
class BlackConfig(Target.Data):
    """
    Represents a configuration for the Black linter.
    """

    line_length: int | None = None


black_config = make_target_factory("black_config", BlackConfig)
