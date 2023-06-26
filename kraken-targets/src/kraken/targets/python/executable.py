from dataclasses import dataclass

from kraken.targets.core.target import Target, make_target_factory


@dataclass(frozen=True)
class PythonExecutable(Target.Data):
    """
    Represents a Python executable entrypoint.
    """

    entry_point: str


python_executable = make_target_factory("python_executable", PythonExecutable)
