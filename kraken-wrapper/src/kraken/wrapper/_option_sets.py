from __future__ import annotations

import argparse
import dataclasses
import os

from kraken.common import EnvironmentType


@dataclasses.dataclass(frozen=True)
class EnvOptions:
    status: bool
    upgrade: bool
    reinstall: bool
    uninstall: bool
    use: EnvironmentType | None
    incremental: bool
    show_install_logs: bool
    no_keyring: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        group = parser.add_argument_group("build environment")
        group.add_argument(
            "--use",
            choices=[v.name for v in EnvironmentType if v.is_wrapped()],
            default=os.getenv("KRAKENW_USE"),
            help="use the specified environment type. If the environment type changes it will trigger a reinstall.\n"
            "Defaults to the value of the KRAKENW_USE environment variable. If that variable is unset, and\nif a build "
            "environment already exists, that environment's type will be used. The default\nenvironment type that is "
            "used for new environments is VENV. [env: KRAKENW_USE=...]",
        )
        group.add_argument(
            "--status",
            action="store_true",
            help="print the status of the build environment and exit",
        )
        group.add_argument(
            "--upgrade",
            action="store_true",
            help="reinstall the build environment from the original requirements",
        )
        group.add_argument(
            "--reinstall",
            action="store_true",
            default=os.getenv("KRAKENW_REINSTALL") == "1",
            help="reinstall the build environment from the lock file [env: KRAKENW_REINSTALL=1]",
        )
        group.add_argument(
            "--uninstall",
            action="store_true",
            help="uninstall the build environment",
        )
        group.add_argument(
            "--incremental",
            action="store_true",
            default=os.getenv("KRAKENW_INCREMENTAL") == "1",
            help="re-use an existing build environment. Improves installation time after an update to the buildscript\n"
            "dependencies, but does not upgrade all packages to latest. [env: KRAKENW_INCREMENTAL=1]",
        )
        group.add_argument(
            "--show-install-logs",
            action="store_true",
            default=os.getenv("KARKENW_SHOW_INSTALL_LOGS") == "1",
            help="show Pip install logs instead of piping them to the build/.venv.log/ directory.\n"
            "[env: KARKENW_SHOW_INSTALL_LOGS=1]",
        )

        group = parser.add_argument_group("authentication")
        group.add_argument(
            "--no-keyring",
            action="store_true",
            default=os.getenv("KRAKENW_NO_KEYRING") == "1",
            help="disable the use of the keyring package for loading and storing credentials. "
            "[env: KRAKENW_NO_KEYRING=1]",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> EnvOptions:
        return cls(
            status=args.status,
            upgrade=args.upgrade,
            reinstall=args.reinstall,
            uninstall=args.uninstall,
            use=EnvironmentType[args.use] if args.use else None,
            incremental=args.incremental,
            show_install_logs=args.show_install_logs,
            no_keyring=args.no_keyring,
        )

    def any(self) -> bool:
        return bool(self.status or self.upgrade or self.reinstall or self.uninstall or self.use)


@dataclasses.dataclass(frozen=True)
class AuthOptions:
    host: str
    username: str | None
    password: str | None
    password_stdin: bool
    remove: bool
    list: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("host", nargs="?", help="the host to add the credentials for")
        parser.add_argument(
            "-u",
            "--username",
            help="the username to use when accessing resources on the given host",
        )
        parser.add_argument(
            "-p",
            "--password",
            help="the password to use when accessing resources on the given host (use --password-stdin when possible)",
        )
        parser.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
        parser.add_argument(
            "-r",
            "--remove",
            action="store_true",
            help="remove credentials for the given host",
        )
        parser.add_argument(
            "-l",
            "--list",
            action="store_true",
            help="list configured credentials for the given host",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> AuthOptions:
        return cls(
            host=args.host,
            username=args.username,
            password=args.password,
            password_stdin=args.password_stdin,
            remove=args.remove,
            list=args.list,
        )
