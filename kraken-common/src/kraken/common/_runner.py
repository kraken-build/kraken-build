"""
Implements build script runners.
"""

import re
import types
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterable, NamedTuple, Sequence

import builddsl

from ._buildscript import BuildscriptMetadata, buildscript
from ._generic import NotSet

##
# Data classes
##


class ProjectInfo(NamedTuple):
    script: Path
    runner: "ScriptRunner"


##
# Interfaces
##


class ScriptRunner(ABC):
    """
    Abstract class for script runners. Implementations of this class are used to detect a script in a directory
    and to actually run it. The Kraken wrapper and build system both use this to run a build script, which for
    the wrapper is needed to extract the build script metadata.
    """

    @abstractmethod
    def find_script(self, directory: Path) -> "Path | None":
        raise NotImplementedError(self)

    @abstractmethod
    def execute_script(self, script: Path, scope: Dict[str, Any]) -> None:
        raise NotImplementedError(self)

    @abstractmethod
    def has_buildscript_call(self, script: Path) -> bool:
        """
        Implement a heuristic to check if the script implements a call to the :func:`buildscript` function.
        """

        raise NotImplementedError(self)

    @abstractmethod
    def get_buildscript_call_recommendation(self, metadata: BuildscriptMetadata) -> str:
        """
        Make a recommendation to the user for the code the user should put into their build script for the
        :func:`buildscript` call that is required by Kraken wrapper.
        """

        raise NotImplementedError(self)


class ProjectFinder(ABC):
    """
    Base class for finding a Kraken project starting from any directory.
    """

    @abstractmethod
    def find_project(self, directory: Path) -> "ProjectInfo | None":
        ...


##
# ScriptRunner Implementations
##


class ScriptPicker(ScriptRunner):
    """
    Base class for picking the right script file in a directory based on a few criteria.
    """

    def __init__(self, filenames: Sequence[str]) -> None:
        self.filenames = list(filenames)

    def find_script(self, directory: Path) -> "Path | None":
        for filename in self.filenames:
            script = directory / filename
            if script.is_file():
                return script
        return None


class PythonScriptRunner(ScriptPicker):
    """
    A finder and runner for Python based Kraken build scripts called `.kraken.py`.

    !!! note

        We can't call the script `kraken.py` (without the leading dot), as otherwise under most circumstances the
        script will try to import itself when doing `import kraken` or `from kraken import ...`.
    """

    def __init__(self, filenames: Sequence[str] = (".kraken.py",)) -> None:
        super().__init__(filenames)

    def execute_script(self, script: Path, scope: Dict[str, Any]) -> None:
        module = types.ModuleType(str(script.parent))
        module.__file__ = str(script)

        try:
            code = compile(script.read_text(), script, "exec")
        except BaseException as err:
            raise ValueError("Script failed to compile the build script") from err
        exec(code, vars(module))

    def has_buildscript_call(self, script: Path) -> bool:
        code = script.read_text()
        if not re.search(r"^from kraken.common import buildscript", code, re.M):
            return False
        if not re.search(r"^buildscript\s*\(", code, re.M):
            return False
        return True

    def get_buildscript_call_recommendation(self, metadata: BuildscriptMetadata) -> str:
        code = "from kraken.common import buildscript\nbuildscript("
        if metadata.index_url:
            code += f"\n    index_url={metadata.index_url!r},"
        if metadata.extra_index_urls:
            if len(metadata.extra_index_urls) == 1:
                code += f"\n    extra_index_urls={metadata.extra_index_urls!r},"
            else:
                code += "\n    extra_index_urls=["
                for url in metadata.extra_index_urls:
                    code += f"\n        {url!r},"
                code += "\n    ],"
        if metadata.requirements:
            if sum(map(len, metadata.requirements)) < 50:
                code += f"\n    requirements={metadata.requirements!r},"
            else:
                code += "\n    requirements=["
                for req in metadata.requirements:
                    code += f"\n        {req!r},"
                code += "\n    ],"
        if not code.endswith("("):
            code += "\n"
        code += ")"
        return code


class BuildDslScriptRunner(ScriptPicker):
    """
    A finder and runner for BuildDSL based Kraken build scripts called `kraken.build` (optionally prefixed with `.`).
    """

    def __init__(self, filenames: Sequence[str] = ("kraken.build", ".kraken.build")) -> None:
        super().__init__(filenames)

    def execute_script(self, script: Path, scope: Dict[str, Any]) -> None:
        code = script.read_text()
        scope = {"buildscript": buildscript, **scope}
        builddsl.Closure.from_map(scope).run_code(code, str(script))

    def has_buildscript_call(self, script: Path) -> bool:
        code = script.read_text()
        if re.match(r"^buildscript\s*(\(|\{})", code, re.M):
            return False
        return True

    def get_buildscript_call_recommendation(self, metadata: BuildscriptMetadata) -> str:
        code = "buildscript {"
        if metadata.index_url:
            code += f"\n    index_url = {metadata.index_url!r}"
        if metadata.extra_index_urls:
            for url in metadata.extra_index_urls:
                code += f"\n    extra_index_url {url!r}"
        if metadata.requirements:
            for req in metadata.requirements:
                code += f"        requires {req!r}"
        code += "}"
        return code


##
# ProjectFinder Implementations
##


class CurrentDirectoryProjectFinder(ProjectFinder):
    """
    Goes through a list of script finders and returns the first one matching.
    """

    def __init__(self, script_runners: Iterable[ScriptRunner]) -> None:
        self.script_runners = list(script_runners)

    def find_project(self, directory: Path) -> "ProjectInfo | None":
        for runner in self.script_runners:
            script = runner.find_script(directory)
            if script is not None:
                return ProjectInfo(script, runner)

        return None

    @classmethod
    def default(cls) -> "CurrentDirectoryProjectFinder":
        """
        Returns the default instance that contains the known :class:`ScriptRunner` implementations.
        """

        return cls(
            (
                PythonScriptRunner(),
                BuildDslScriptRunner(),
            )
        )


class GitAwareProjectFinder(ProjectFinder):
    """
    Finds the root of a project by picking the highest-up build script that does not cross a Git repository boundary
    or a home directory boundary. Starts from a directory and works it's way up until a stop condition is encountered.

    If any build script contains the string `# ::krakenw-root`, then the directory containing that build script is
    considered the root of the project. This is useful for projects that have multiple build scripts in different
    directories, but they should not be considered part of the same project.
    """

    def __init__(self, delegate: ProjectFinder, home_boundary: "Path | None | NotSet" = None) -> None:
        """
        :param delegate: The project finder to delegate to in any of the directories that this class
            looks through. The first project returned by this finder in any of the directories is used.
        :param home_boundary: A directory which contains a boundary that should not be crossed when
            searching for projects. For example, if this is `/home/foo`, then this class will stop searching
            for projects as soon as it reaches `/home/foo` or any sibling directory (such as `/home/bar`).
            If a path does not live within the home boundary or any of its siblings, the boundary is not
            taken into account.

            When the parameter is set to :const:`NotSet.Value`, it will default to the user's home directory.
            The value can be set to :const:`None` to disable the home boundary check all together.
        """
        self.delegate = delegate
        self.home_boundary = (
            Path("~").expanduser().parent.absolute() if home_boundary is NotSet.Value else home_boundary
        )

    def find_project(self, directory: Path) -> "ProjectInfo | None":
        highest_script: "ProjectInfo | None" = None
        directory = directory.absolute()
        while directory != Path(directory.root):
            # If we're in any directory that could be a home directory, we stop searching.
            if directory.parent == self.home_boundary:
                break

            script = self.delegate.find_project(directory)
            if script is not None:
                highest_script = script
                if script.script.read_text().find("# ::krakenw-root") != -1:
                    break

            # If in the next loop we would cross a Git repository boundary, we stop searching.
            if (directory / ".git").exists():
                break

            directory = directory.parent

        return highest_script

    @classmethod
    def default(cls) -> "GitAwareProjectFinder":
        """
        Returns the default instance that contains a default :class:`CurrentDirectoryProjectFinder`.
        """

        return cls(CurrentDirectoryProjectFinder.default())
