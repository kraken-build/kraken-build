import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from kraken.common import findpython
from kraken.core import Project

from kraken.targets.core.goal import Goal
from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.core.targetselection import TargetSelection
from kraken.targets.goals.install import InstallGoal
from kraken.targets.goals.run import RunGoal
from kraken.targets.python.executable import python_executable
from kraken.targets.python.requirements import python_requirement, python_requirements
from kraken.targets.python.venv import CreateVenvRequest, ExistingVenv, python_venv


@pytest.fixture
def runner() -> RuleRunner:
    return RuleRunner(["kraken.targets.python.binary", "kraken.targets.python.venv"])


def test__create_venv(runner: RuleRunner) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        request = CreateVenvRequest(path=Path(tmpdir) / "venv", interpreter_constraint=">=3.10")
        response = runner.get(ExistingVenv, [request])

        python_bin = response.scripts_dir / ("python.exe" if os.name == "nt" else "python")
        assert response.python.path == python_bin
        assert findpython.get_python_interpreter_version(response.python.path) == response.python.version


@pytest.mark.parametrize(
    argnames=["goal_type", "target"],
    argvalues=[
        (InstallGoal, ":venv"),
        (RunGoal, ":main"),
        # (InstallGoal, ":"),
        # (RunGoal, ":"),
    ],
)
def test__python_venv__install__with_requirements(
    kraken_project: Project, runner: RuleRunner, goal_type: type[Goal], target: str
) -> None:
    """
    Tests the installation of a Python virtual environment with requirements from multiple requirement source
    targets and the subsequent execution of a Python script using an entrypoint target.
    """

    runner.engine.assert_facts([kraken_project.context])

    with tempfile.TemporaryDirectory() as tmpdir:
        venv_dir = Path(tmpdir) / "venv"

        python_requirements(name="req-multi", requirements=["nr-stream==1.1.5"])
        python_requirement(name="req-single", requirement="termcolor==2.3.0")
        python_venv(
            name="venv", dependencies=["req-multi", "req-single"], path=venv_dir, interpreter_constraint=">=3.10"
        )
        python_executable(name="main", entry_point="termcolor", dependencies=["venv"])

        goal = runner.run(goal_type, [TargetSelection([target])])
        assert goal.exit_code == 0
        assert venv_dir.is_dir(), "venv directory was not created"

        python_bin = (
            venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        )
        assert python_bin.is_file()

        proc = subprocess.run([python_bin, "-c", "from nr.stream import Stream"])
        assert proc.returncode == 0
        proc = subprocess.run([python_bin, "-c", "import termcolor"])
        assert proc.returncode == 0
