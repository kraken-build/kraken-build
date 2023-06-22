import subprocess
from pathlib import Path

from kraken.core import Project, TaskStatus

from kraken.std.git.tasks.check_file_task import CheckFileTask


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=path)


def _git_add(path: Path, files: list[Path]) -> None:
    subprocess.run(["git", "add", *map(str, files)], check=True, cwd=path)


def _git_commit(path: Path, message: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=John Doe <john@doe.com>", "commit", "--allow-empty", "-m", message],
        check=True,
        cwd=path,
    )


def test__CheckFileTask__file_does_not_exist(kraken_project: Project) -> None:
    task = kraken_project.do("check_file", CheckFileTask)
    task.file_to_check.set(Path("warbl.garbl"))
    status = task.execute()
    assert status == TaskStatus.failed("'warbl.garbl' does not exist")

    task.state.set("absent")
    status = task.execute()
    assert status == TaskStatus.succeeded("'warbl.garbl' does not exist")


def test__CheckFileTask__file_exists_but_is_not_committed(kraken_project: Project) -> None:
    _git_init(kraken_project.directory)
    _git_commit(kraken_project.directory, "Initial commit")
    file_name = Path("warbl.garbl")
    (kraken_project.directory / file_name).touch()

    task = kraken_project.do("check_file", CheckFileTask)
    task.file_to_check.set(file_name)
    status = task.execute()
    assert status == TaskStatus.failed("'warbl.garbl' exists but is not committed")

    task.state.set("absent")
    assert status == TaskStatus.failed("'warbl.garbl' exists but is not committed")


def test__file_exists_and_is_committed(kraken_project: Project) -> None:
    _git_init(kraken_project.directory)
    file_name = Path("warbl.garbl")
    (kraken_project.directory / file_name).touch()
    _git_add(kraken_project.directory, [file_name])
    _git_commit(kraken_project.directory, "Initial commit")

    task = kraken_project.do("check_file", CheckFileTask)
    task.file_to_check.set(file_name)
    status = task.execute()
    assert status == TaskStatus.succeeded("'warbl.garbl' exists and is committed")

    task.state.set("absent")
    status = task.execute()
    assert status == TaskStatus.failed("'warbl.garbl' exists and is committed")
