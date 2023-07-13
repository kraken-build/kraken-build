from __future__ import annotations

import datetime
import hashlib
import logging
import platform
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from kraken.common import EnvironmentType, RequirementSpec, not_none, safe_rmpath

from ._buildend_venv import VenvBuildEnv
from ._buildenv import BuildEnv, BuildEnvMetadata, BuildEnvMetadataStore
from ._config import AuthModel
from ._lockfile import Lockfile

logger = logging.getLogger(__name__)


class BuildEnvManager:
    def __init__(
        self,
        path: Path,
        auth: AuthModel,
        default_type: EnvironmentType = EnvironmentType.VENV,
        default_hash_algorithm: str = "sha256",
        incremental: bool = False,
        show_install_logs: bool = False,
    ) -> None:
        assert (
            default_hash_algorithm in hashlib.algorithms_available
        ), f"hash algoritm {default_hash_algorithm!r} is not available"

        self._path = path
        self._auth = auth
        self._metadata_store = BuildEnvMetadataStore(path.parent / (path.name + ".meta"))
        self._default_type = default_type
        self._default_hash_algorithm = default_hash_algorithm
        self._incremental = incremental
        self._show_install_logs = show_install_logs

    def _inject_auth(self, url: str) -> str:
        parsed_url = urlparse(url)
        credentials = self._auth.get_credentials(parsed_url.netloc)
        if credentials is None:
            return url

        logger.info('Injecting username and password into index url "%s"', url)
        domain = parsed_url.netloc.rpartition("@")[-1]
        parsed_url = parsed_url._replace(netloc=f"{quote(credentials.username)}:{quote(credentials.password)}@{domain}")
        url = urlunparse(parsed_url)
        return url

    def exists(self) -> bool:
        if self._metadata_store.get() is None:
            return False  # If we don't have metadata, we assume the environment does not exist.
        return self.get_environment(None).get_path().exists()

    def remove(self) -> None:
        safe_rmpath(self._metadata_store.path)
        safe_rmpath(self.get_environment(None).get_path())

    def install(
        self,
        requirements: RequirementSpec,
        env_type: EnvironmentType | None = None,
        transitive: bool = True,
    ) -> None:
        """
        :param requirements: The requirements to build the environment with.
        :param env_type: The environment type to use. If not specified, falls back to the last used or default.
        :param transitive: If set to `False`, it indicates that the *requirements* are fully resolved and the
            build environment installer does not need to resolve transitve dependencies.
        """

        if env_type is None:
            metadata = self._metadata_store.get()
            env_type = metadata.environment_type if metadata else self._default_type

        # Inject credentials into the requirements.
        requirements = RequirementSpec(
            requirements=requirements.requirements,
            index_url=self._inject_auth(requirements.index_url) if requirements.index_url else None,
            extra_index_urls=tuple(self._inject_auth(url) for url in requirements.extra_index_urls),
            interpreter_constraint=requirements.interpreter_constraint,
            pythonpath=requirements.pythonpath,
        )

        env = self.get_environment(env_type)
        env.build(requirements, transitive)
        hash_algorithm = self.get_hash_algorithm()
        metadata = BuildEnvMetadata(
            datetime.datetime.utcnow(),
            env.get_type(),
            requirements.to_hash(hash_algorithm),
            hash_algorithm,
        )
        self._metadata_store.set(metadata)

    def get_metadata_file(self) -> Path:
        return self._metadata_store.path

    def get_metadata(self) -> BuildEnvMetadata:
        return not_none(self._metadata_store.get(), "metadata does not exist")

    def get_hash_algorithm(self) -> str:
        metadata = self._metadata_store.get()
        return metadata.hash_algorithm if metadata else self._default_hash_algorithm

    def get_environment(self, env_type: EnvironmentType | None = None) -> BuildEnv:
        if env_type is None:
            metadata = self._metadata_store.get()
            env_type = self._default_type if metadata is None else metadata.environment_type
        return _get_environment_for_type(env_type, self._path, self._incremental, self._show_install_logs)

    def set_locked(self, lockfile: Lockfile) -> None:
        metadata = self._metadata_store.get()
        assert metadata is not None
        metadata = BuildEnvMetadata(
            metadata.created_at,
            metadata.environment_type,
            lockfile.to_pinned_requirement_spec().to_hash(metadata.hash_algorithm),
            metadata.hash_algorithm,
        )
        self._metadata_store.set(metadata)


def _get_environment_for_type(
    environment_type: EnvironmentType, base_path: Path, incremental: bool, show_install_logs: bool
) -> BuildEnv:
    platform_name = platform.system().lower()
    if platform_name != "windows":
        from ._buildenv_pex import PexBuildEnv

        if environment_type in PexBuildEnv.STYLES:
            if incremental:
                logger.warning("incremental installation mode not supported for Pex")
            if show_install_logs:
                # We could support it if we were to hide the install logs in the first place.
                logger.warning("`show_install_logs` not supported for Pex")
            return PexBuildEnv(environment_type, base_path.parent / (base_path.name + ".pex"))

    if environment_type == EnvironmentType.VENV:
        return VenvBuildEnv(
            base_path,
            incremental=incremental,
            show_pip_logs=show_install_logs,
        )
    else:
        raise RuntimeError(f"unsupported environment type {environment_type!r} on platform {platform_name!r}")
