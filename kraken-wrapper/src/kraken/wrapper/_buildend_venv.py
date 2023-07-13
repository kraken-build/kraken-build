from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import List, NoReturn

from kraken.common import EnvironmentType, RequirementSpec, findpython, safe_rmpath
from kraken.common.pyenv import VirtualEnvInfo
from typing_extensions import Literal

from ._buildenv import KRAKEN_MAIN_IMPORT_SNIPPET, BuildEnv, BuildEnvError, general_get_installed_distributions
from ._lockfile import Distribution

logger = logging.getLogger(__name__)


def find_python_interpreter(constraint: str) -> str:
    """
    Finds a Python interpreter that matches the given constraint. We rely on the order of candidates returned by
    #findpython.get_candidates() and return the first matching Python version.
    """

    interpreters = findpython.evaluate_candidates(findpython.get_candidates(), findpython.InterpreterVersionCache())
    for interpreter in interpreters:
        if findpython.match_version_constraint(constraint, interpreter["version"]):
            return interpreter["path"]

    raise RuntimeError(f"Could not find a Python interpreter that matches the constraint {constraint!r}.")


class VenvBuildEnv(BuildEnv):
    """
    Installs the Kraken build environment into a Python virtual environment.
    """

    def __init__(self, path: Path, incremental: bool = False, show_pip_logs: bool = False) -> None:
        self._path = path
        self._venv = VirtualEnvInfo(self._path)
        self._incremental = incremental
        self._show_pip_logs = show_pip_logs

    def _run_command(
        self, command: List[str], operation_name: str, log_file: Path | None, mode: Literal["a", "w"] = "w"
    ) -> None:
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)

        offset: int | None = None
        exc: Exception | None = None

        with ExitStack() as stack:
            if log_file is not None:
                fp = stack.enter_context(log_file.open(mode))
                offset = fp.tell()
            else:
                fp = None
                offset = 0
            try:
                subprocess.check_call(command, stdout=fp, stderr=fp)
                return
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                exc = e

        assert exc is not None
        exit_code = exc.returncode if isinstance(exc, subprocess.CalledProcessError) else -1
        command_str = "$ " + " ".join(map(shlex.quote, command))

        if log_file:
            assert offset is not None
            with log_file.open() as fp:
                fp.seek(offset)
                logger.error(
                    "'%s' failed (exit code: %d, command: %s). Output:\n\n%s",
                    operation_name,
                    exit_code,
                    command_str,
                    fp.read(),
                )
        else:
            logger.error(
                "'%s' failed (exit code: %d, command: %d). Check the output above for more information.",
                operation_name,
                exc.returncode if isinstance(exc, subprocess.CalledProcessError) else -1,
                "$ " + " ".join(map(shlex.quote, command)),
            )

        raise BuildEnvError(f"The command {command} failed.") from exc

    # BuildEnv

    def get_path(self) -> Path:
        return self._path

    def get_type(self) -> EnvironmentType:
        return EnvironmentType.VENV

    def get_installed_distributions(self) -> List[Distribution]:
        python = self._venv.get_bin("python")
        return general_get_installed_distributions([str(python), "-c", f"{KRAKEN_MAIN_IMPORT_SNIPPET}\nmain()"])

    def build(self, requirements: RequirementSpec, transitive: bool) -> None:
        if self._show_pip_logs:
            create_log: Path | None = self._path.with_name(self._path.name + ".log") / "create.txt"
            install_log: Path | None = self._path.with_name(self._path.name + ".log") / "install.txt"
        else:
            create_log = install_log = None

        if not self._incremental and self._path.exists():
            logger.debug("Removing existing virtual environment at %s", self._path)
            safe_rmpath(self._path)

        python_bin = str(self._venv.get_bin("python"))

        # If a virtual environment already exists, we should ensure that it matches the given interpreter constraint.
        if os.path.isfile(python_bin):
            try:
                current_python_version = findpython.get_python_interpreter_version(python_bin)
            except (subprocess.CalledProcessError, RuntimeError) as e:
                logger.warning("Could not determine the version of the current Python build environment: %s", e)
                logger.info("Destroying existing environment at %s", self._path)
                safe_rmpath(self._path)
            else:
                if requirements.interpreter_constraint and not findpython.match_version_constraint(
                    requirements.interpreter_constraint, current_python_version
                ):
                    logger.info(
                        "Existing Python interpreter at %s does not match constraint %s because its Python version "
                        "is %s. The environment will be recreated with the correct interpreter.",
                        python_bin,
                        requirements.interpreter_constraint,
                        current_python_version,
                    )
                    safe_rmpath(self._path)

        if not self._path.exists():
            # Find a Python interpreter that matches the given interpreter constraint.
            if requirements.interpreter_constraint is not None:
                logger.info("Using Python interpreter constraint: %s", requirements.interpreter_constraint)
                python_origin_bin = find_python_interpreter(requirements.interpreter_constraint)
                logger.info("Using Python interpreter at %s", python_origin_bin)
            else:
                logger.info(
                    "No interpreter constraint specified, using current Python interpreter (%s)", sys.executable
                )
                python_origin_bin = sys.executable

            command = [python_origin_bin, "-m", "venv", str(self._path)]
            logger.info("Creating virtual environment at %s", os.path.relpath(self._path))
            self._run_command(command, operation_name="Create virtual environment", log_file=create_log)

            # Upgrade Pip.
            command = [python_bin, "-m", "pip", "install", "--upgrade", "pip"]
            logger.info("Upgrading Pip in virtual environment.")
            self._run_command(command, operation_name="Upgrade Pip", log_file=create_log, mode="a")

        else:
            logger.info("Reusing virtual environment at %s", self._path)

        # Install requirements.
        command = [
            python_bin,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-python-version-warning",
            "--no-input",
        ]
        # Must enable transitive resolution because lock files are not currently cross platform (see kraken-wrapper#2).
        # if not transitive:
        #     command += ["--no-deps"]
        # TODO (@NiklasRosenstein): Handle requirements interpreter constraint (see kraken-wrapper#5).
        command += requirements.to_args()
        logger.info("Installing dependencies.")
        logger.debug("Installing into build environment with Pip: %s", " ".join(command))
        self._run_command(command, operation_name="Install dependencies", log_file=install_log)

        # Make sure the pythonpath from the requirements is encoded into the enviroment.
        command = [python_bin, "-c", "from sysconfig import get_path; print(get_path('purelib'))"]
        site_packages = Path(subprocess.check_output(command).decode().strip())
        pth_file = site_packages / "krakenw.pth"
        if requirements.pythonpath:
            logger.debug("Writing .pth file at %s", pth_file)
            pth_file.write_text("\n".join(str(Path(path).absolute()) for path in requirements.pythonpath))
        elif pth_file.is_file():
            logger.debug("Removing .pth file at %s", pth_file)
            pth_file.unlink()

    def dispatch_to_kraken_cli(self, argv: List[str]) -> NoReturn:
        python = self._venv.get_bin("python")
        command = [str(python), "-c", f"{KRAKEN_MAIN_IMPORT_SNIPPET}\nmain()", *argv]
        env = os.environ.copy()
        self.get_type().set(env)
        env["PATH"] = str(self._venv.get_bin_directory()) + os.pathsep + env.get("PATH", "")
        sys.exit(subprocess.call(command, env=env))
