""" Implements Poetry as a build system for kraken-std. """

from __future__ import annotations

import logging
import os
import shutil
import subprocess as sp
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kraken.common import NotSet
from kraken.common.path import is_relative_to
from kraken.common.pyenv import get_current_venv
from kraken.core import TaskStatus

from kraken.std.python.buildsystem.helpers import update_python_version_str_in_source_files
from kraken.std.python.pyproject import PoetryPyproject, Pyproject, SpecializedPyproject
from kraken.std.python.settings import PythonSettings

from . import ManagedEnvironment, PythonBuildSystem

logger = logging.getLogger(__name__)


class PoetryPythonBuildSystem(PythonBuildSystem):
    name = "Poetry"

    def __init__(self, project_directory: Path) -> None:
        self.project_directory = project_directory

    def get_pyproject_reader(self, pyproject: Pyproject) -> SpecializedPyproject:
        return PoetryPyproject(pyproject)

    def supports_managed_environments(self) -> bool:
        return True

    def get_managed_environment(self) -> ManagedEnvironment:
        return PoetryManagedEnvironment(self.project_directory)

    def update_pyproject(self, settings: PythonSettings, pyproject: Pyproject) -> None:
        poetry_pyproj = PoetryPyproject(pyproject)
        for source in poetry_pyproj.get_sources():
            poetry_pyproj.delete_source(source["name"])
        for index in settings.package_indexes.values():
            if index.is_package_source:
                poetry_pyproj.upsert_source(index.alias, index.index_url, index.priority)

    def update_lockfile(self, settings: PythonSettings, pyproject: Pyproject) -> TaskStatus:
        command = ["poetry", "update"]
        sp.check_call(command, cwd=self.project_directory)
        return TaskStatus.succeeded()

    def requires_login(self) -> bool:
        return True

    def login(self, settings: PythonSettings) -> None:
        for index in settings.package_indexes.values():
            if index.is_package_source and index.credentials:
                command = ["poetry", "config", "http-basic." + index.alias, index.credentials[0], index.credentials[1]]
                safe_command = ["poetry", "config", "http-basic." + index.alias, index.credentials[0], "MASKED"]
                logger.info("$ %s", safe_command)
                code = sp.call(command)
                if code != 0:
                    raise RuntimeError(f"command {safe_command!r} failed with exit code {code}")

    def build(self, output_directory: Path, as_version: str | None = None) -> list[Path]:
        previous_version: str | None = None
        revert_version_paths: list[Path] = []
        if as_version is not None:
            # Bump the in-source version number.
            pyproject = Pyproject.read(self.project_directory / "pyproject.toml")
            poetry_pyproj = PoetryPyproject(pyproject)
            poetry_pyproj.update_relative_packages(as_version)
            previous_version = poetry_pyproj.set_version(as_version)
            poetry_pyproj.save()
            for package in poetry_pyproj.get_packages(fallback=True):
                package_dir = self.project_directory / (package.from_ or "") / package.include
                n_replaced = update_python_version_str_in_source_files(as_version, package_dir)
                if n_replaced > 0:
                    revert_version_paths.append(package_dir)
                    print(
                        f"Bumped {n_replaced} version reference(s) in "
                        f"{package_dir.relative_to(self.project_directory)} to {as_version}"
                    )

        # Poetry does not allow configuring the output folder, so it's always going to be "dist/".
        # We remove the contents of that folder to make sure we know what was produced.
        dist_dir = self.project_directory / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)

        command = ["poetry", "build"]
        logger.info("%s", command)
        sp.check_call(command, cwd=self.project_directory)
        src_files = list(dist_dir.iterdir())
        dst_files = [output_directory / path.name for path in src_files]
        for src, dst in zip(src_files, dst_files):
            shutil.move(str(src), dst)

        # Unless the output directory is a subdirectory of the dist_dir, we remove the dist dir again.
        if not is_relative_to(output_directory, dist_dir):
            shutil.rmtree(dist_dir)

        # Roll back the previously updated in-source version numbers.
        if previous_version is not None:
            poetry_pyproj.set_version(previous_version)
            poetry_pyproj.save()
            for package_dir in revert_version_paths:
                update_python_version_str_in_source_files(previous_version, package_dir)

        return dst_files


class PoetryManagedEnvironment(ManagedEnvironment):
    def __init__(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self._env_path: Path | None | NotSet = NotSet.Value

    def _get_current_poetry_environment_path(self) -> Path | None:
        """Uses `poetry env info -p`. This will not work if Poetry has to fall back to a compatible Python
        version if the version that Poetry is installed into is not compatible."""

        # Ensure we de-activate any environment that might be active when Kraken is invoked. Otherwise,
        # Poetry would fall back to that environment.
        environ = os.environ.copy()
        venv = get_current_venv(environ)
        if venv:
            venv.deactivate(environ)

        command = ["poetry", "env", "info", "-p"]
        try:
            response = sp.check_output(command, cwd=self.project_directory, env=environ).decode().strip()
        except sp.CalledProcessError as exc:
            if exc.returncode != 1:
                raise
            return None
        else:
            return Path(response)

    def _get_all_poetry_known_environment_paths(self) -> list[Path]:
        """Uses `poetry env list --full-path` to get the path to all relevant virtual environments that are known
        to Poetry for the project. We fall back to this method if `poetry env info -p` fails us."""

        command = ["poetry", "env", "list", "--full-path"]
        try:
            response = sp.check_output(command, cwd=self.project_directory).decode().strip().splitlines()
        except sp.CalledProcessError as exc:
            if exc.returncode != 1:
                raise
            return []
        else:
            return [Path(line.replace(" (Activated)", "").strip()) for line in response if line]

    def _get_poetry_environment_path(self) -> Path | None:
        # Run the two Poetry commands we need to run in parallel to improve load times.
        with ThreadPoolExecutor() as executor:
            venv_path_future = executor.submit(self._get_current_poetry_environment_path)
            known_venvs_future = executor.submit(self._get_all_poetry_known_environment_paths)
            venv_path = venv_path_future.result()
            if venv_path is not None:
                return venv_path
            known_venvs = known_venvs_future.result()
            if known_venvs:
                if len(known_venvs) > 1:
                    logger.warning(
                        "This project has multiple Poetry environments. Picking the first one (%s)", known_venvs[0]
                    )
                return known_venvs[0]
            return None

    # ManagedEnvironment

    def exists(self) -> bool:
        try:
            self.get_path()
            return True
        except RuntimeError:
            return False

    def get_path(self) -> Path:
        if self._env_path is NotSet.Value:
            self._env_path = self._get_poetry_environment_path()
        if self._env_path is None:
            raise RuntimeError("managed environment does not exist")
        return self._env_path

    def install(self, settings: PythonSettings) -> None:
        command = ["poetry", "install", "--no-interaction"]
        logger.info("%s", command)
        sp.check_call(command, cwd=self.project_directory)
