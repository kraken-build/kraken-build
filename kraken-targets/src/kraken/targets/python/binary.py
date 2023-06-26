import shutil
from dataclasses import dataclass
from pathlib import Path

from adjudicator import collect_rules, rule
from kraken.common import findpython

from kraken.targets.core.rulerunner import RuleRunner


@dataclass(frozen=True)
class PythonBinaryRequest:
    """
    A request to find a Python interpreter binary.
    """

    interpreter_constraint: str | None = None


@dataclass(frozen=True)
class PythonBinary:
    """
    A Python interpreter binary.
    """

    path: Path
    version: str
    md5sum: str


@rule
def get_python_binary(request: PythonBinaryRequest) -> PythonBinary:
    cache = findpython.InterpreterVersionCache()
    python_bin: findpython.Interpreter | None = None

    if not request.interpreter_constraint:
        python_bin_path = shutil.which("python") or shutil.which("python3")
        if not python_bin_path:
            raise RuntimeError("No Python interpreter found on PATH (checked 'python' and 'python3').")
        version = cache.get_version(Path(python_bin_path))
        if not version:
            version = findpython.get_python_interpreter_version(python_bin_path)
        python_bin = {"path": python_bin_path, "version": version}

    else:
        candidates = findpython.get_candidates()

        # For some candidates we may already know an exact version, so let's try them first.
        if candidate := next(
            (
                x
                for x in candidates
                if x.get("exact_version")
                and findpython.match_version_constraint(request.interpreter_constraint, x["exact_version"])  # type: ignore[arg-type]  # noqa: E501
            ),
            None,
        ):
            python_bin = {"path": candidate["path"], "version": candidate["exact_version"]}  # type: ignore[typeddict-item]  # noqa: E501
        else:
            evaluated = findpython.evaluate_candidates(candidates, cache)
            python_bin = next(
                (
                    x
                    for x in evaluated
                    if findpython.match_version_constraint(request.interpreter_constraint, x["version"])
                ),
                None,
            )

        if not python_bin:
            raise RuntimeError(f"No Python interpreter found matching constraint '{request.interpreter_constraint}'.")

    return PythonBinary(
        path=Path(python_bin["path"]),
        version=python_bin["version"],
        md5sum=cache._hash_file(Path(python_bin["path"])),
    )


def register(runner: RuleRunner) -> None:
    runner.engine.add_rules(collect_rules())
