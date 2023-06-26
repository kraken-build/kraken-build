import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import databind.json
from adjudicator import collect_rules, get, rule

from kraken.targets.core.resolve_targets import ResolvedTargets, ResolveTargetsRequest
from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.target import Target, make_target_factory
from kraken.targets.goals.install import InstallGoal
from kraken.targets.goals.run import RunGoal
from kraken.targets.python.binary import PythonBinary, PythonBinaryRequest
from kraken.targets.python.executable import PythonExecutable
from kraken.targets.python.requirements import PythonRequirement, PythonRequirementSet

logger = logging.getLogger(__name__)

##
# CreateVenv Rule
##


@dataclass(frozen=True)
class CreateVenvRequest:
    """
    A request for creating a Python virtual environment.
    """

    #: The path where the virtual environment should be created.
    path: Path

    #: A constraint for the Python interpreter to use when creating the virtual environment.
    #: This is ignored if a #python is specified.
    interpreter_constraint: str | None = None

    #: The Python binary to create the virtual environment with.
    python: PythonBinary | None = None


@dataclass(frozen=True)
class ExistingVenv:
    """
    A response for creating a Python virtual environment.
    """

    #: The path to the Python binary of the virtual environment.
    python: PythonBinary

    #: Path to the virtual environment's bin/Scripts folder.
    scripts_dir: Path

    def get_bin(self, name: str) -> Path:
        return self.scripts_dir / (name + ".exe" if os.name == "nt" else name)


@rule
def create_venv(request: CreateVenvRequest) -> ExistingVenv:
    python = request.python or get(
        PythonBinary,
        PythonBinaryRequest(interpreter_constraint=request.interpreter_constraint),
    )

    path = request.path
    metadata_file = path / ".metadata"

    if path.is_dir():
        # Check if the virtual environment was created using the correct PythonBinary.
        metadata: PythonBinary | None = None
        if metadata_file.is_file():
            try:
                metadata = databind.json.loads(metadata_file.read_text(), PythonBinary)
            except Exception:
                logger.warning(
                    f"Failed to read metadata file {metadata_file}. The virtual environment at "
                    f"{path} will be recreated."
                )

        if not metadata:
            recreate = True
            logger.info(
                f"Recreating virtual environment at {path} because it was created with an unknown Python version."
            )
        elif metadata != python:
            recreate = True
            logger.info(
                f"Recreating virtual environment at {path} because it was created with a different " f"Python binary."
            )
        else:
            recreate = False

        if recreate:
            shutil.rmtree(path)

    if not path.is_dir():
        logger.info("Creating virtual environment at %s using %s", path, python.path)
        subprocess.check_call([python.path, "-m", "venv", str(path)])
        metadata_file.write_text(databind.json.dumps(python, PythonBinary))

    scripts_dir = path / "Scripts" if os.name == "nt" else path / "bin"
    return ExistingVenv(
        python=PythonBinary(
            path=scripts_dir / "python",
            version=python.version,
            md5sum=python.md5sum,
        ),
        scripts_dir=scripts_dir,
    )


@dataclass(frozen=True)
class RequirementsInstalled:
    venv: ExistingVenv


@rule
def install_requirements(venv: ExistingVenv, requirements: PythonRequirementSet) -> RequirementsInstalled:
    pip_bin = venv.get_bin("pip")
    command = [str(pip_bin), "install"] + [req.requirement for req in requirements]
    subprocess.check_call(command)
    return RequirementsInstalled(venv)


##
# PythonVenv Target
##


@dataclass(frozen=True)
class PythonVenv(Target.Data):
    #: The path where the virtual environment should be created.
    path: Path

    #: A constraint for the Python interpreter to use when creating the virtual environment.
    interpreter_constraint: str | None = None


@dataclass(frozen=True)
class PythonVenvInstallGoal(InstallGoal):
    venv: ExistingVenv


@dataclass(frozen=True)
class PythonExecutableRunGoal(RunGoal):
    requirements = (PythonVenv,)


python_venv = make_target_factory("python_venv", PythonVenv)


@rule
def make_create_venv_request(venv: PythonVenv) -> CreateVenvRequest:
    return CreateVenvRequest(
        path=venv.path,
        interpreter_constraint=venv.interpreter_constraint,
    )


@rule
def install_python_venv(venv: PythonVenv) -> PythonVenvInstallGoal:
    dependencies = get(ResolvedTargets, ResolveTargetsRequest(tuple(venv.target.dependencies))).targets

    # Find requirements to install from the venv's parent directory.
    requirements: set[PythonRequirement] = set()
    for dep in dependencies:
        requirements.update(get(PythonRequirementSet, dep.data))

    # Install the requirements into the virtual environment.
    response = get(RequirementsInstalled, venv, PythonRequirementSet(requirements))

    return PythonVenvInstallGoal(exit_code=0, venv=response.venv)


@rule
def run_python_executable_in_venv(venv: PythonVenv, executable: PythonExecutable) -> PythonExecutableRunGoal:
    if ":" in executable.entry_point:
        module, func = executable.entry_point.split(":")
        code = (
            "from importlib import import_module\n"
            f"mod = import_module({module!r})\n"
            f"main = getattr(mod, {func!r})\n"
            "main()"
        )
    else:
        module = executable.entry_point
        code = "from runpy import run_module\n" f'run_module({module!r}, run_name="__main__")\n'

    installed_venv = get(PythonVenvInstallGoal, venv).venv
    command = [str(installed_venv.python.path), "-c", code]
    exit_code = subprocess.call(command)
    return PythonExecutableRunGoal(exit_code=exit_code)


def register(runner: RuleRunner) -> None:
    runner.load("kraken.targets.goals.install")
    runner.load("kraken.targets.goals.run")
    runner.load("kraken.targets.python.requirements")
    runner.engine.add_rules(collect_rules())
    runner.subtypes.register(InstallGoal, PythonVenvInstallGoal)
