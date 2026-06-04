"""Deployment configuration for the crawler API and analyst UI.

The local proof of concept uses ``outputs/runs`` and open local development
ports. Milestone 22 keeps that workflow, but lets deployments move run artifacts
to a shared path, restrict CORS to known UI origins, and require an API bearer
token without changing the crawler record contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
SUPPORTED_STORAGE_BACKENDS = {"local_jsonl", "shared_filesystem", "sqlite"}


@dataclass(frozen=True, slots=True)
class DeploymentSettings:
    """Environment-specific settings for deployed API instances.

    Attributes:
        environment (str): Human-readable environment name, for example
            ``local``, ``staging``, or ``production``.
        run_storage_path (Path): Directory containing run folders with
            ``run_summary.json`` and ``records/*.jsonl`` artifacts.
        audit_log_path (Path): JSONL file where analyst audit events are
            appended.
        storage_backend (str): Name of the storage adapter. Milestone 22
            supports local JSONL and shared filesystem paths; Milestone 27 adds
            SQLite-backed production metadata and record storage.
        run_db_path (Path): SQLite database used when
            ``storage_backend='sqlite'``.
        cors_origins (tuple[str, ...]): Exact browser origins allowed to call
            the FastAPI service.
        cors_origin_regex (str | None): Optional regex for controlled preview
            origins.
        api_token (str | None): Bearer token expected by protected API
            endpoints.
        auth_required (bool): Whether protected API endpoints must reject
            requests without the configured token.
    """

    environment: str = "local"
    run_storage_path: Path = Path("outputs/runs")
    audit_log_path: Path = Path("outputs/audit/audit_events.jsonl")
    storage_backend: str = "local_jsonl"
    run_db_path: Path = Path("outputs/storage/webcrawler.sqlite")
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    cors_origin_regex: str | None = None
    api_token: str | None = None
    auth_required: bool = False

    def public_dict(self) -> dict[str, object]:
        """Return non-secret settings for health checks and documentation.

        Returns:
            dict[str, object]: JSON-safe settings with secret values replaced by
                booleans.
        """

        return {
            "environment": self.environment,
            "run_storage_path": str(self.run_storage_path),
            "audit_log_path": str(self.audit_log_path),
            "storage_backend": self.storage_backend,
            "run_db_path": str(self.run_db_path),
            "cors_origins": list(self.cors_origins),
            "cors_origin_regex": self.cors_origin_regex,
            "auth_required": self.auth_required,
            "api_token_configured": bool(self.api_token),
        }


def load_deployment_settings(environ: dict[str, str] | None = None) -> DeploymentSettings:
    """Load deployment settings from environment variables.

    Args:
        environ (dict[str, str] | None): Optional environment mapping used by
            tests. When omitted, ``os.environ`` is read.

    Returns:
        DeploymentSettings: Parsed settings for the API process.
    """

    values = environ if environ is not None else os.environ
    api_token = _optional_text(values.get("CRAWLER_API_TOKEN"))
    auth_required = _bool_value(
        values.get("CRAWLER_AUTH_REQUIRED"),
        default=bool(api_token),
    )
    return DeploymentSettings(
        environment=values.get("CRAWLER_ENV", "local").strip() or "local",
        run_storage_path=Path(
            values.get("CRAWLER_RUN_STORAGE_PATH", "outputs/runs"),
        ),
        audit_log_path=Path(
            values.get("CRAWLER_AUDIT_LOG_PATH", "outputs/audit/audit_events.jsonl"),
        ),
        storage_backend=values.get("CRAWLER_STORAGE_BACKEND", "local_jsonl").strip()
        or "local_jsonl",
        run_db_path=Path(
            values.get("CRAWLER_RUN_DB_PATH", "outputs/storage/webcrawler.sqlite"),
        ),
        cors_origins=_csv_values(
            values.get("CRAWLER_CORS_ORIGINS"),
            default=DEFAULT_CORS_ORIGINS,
        ),
        cors_origin_regex=_optional_text(values.get("CRAWLER_CORS_ORIGIN_REGEX")),
        api_token=api_token,
        auth_required=auth_required,
    )


def validate_deployment_settings(settings: DeploymentSettings) -> None:
    """Validate deployment settings before the API starts serving requests.

    Args:
        settings (DeploymentSettings): Settings loaded from environment or
            passed by tests.

    Raises:
        ValueError: Raised when auth or storage settings are internally
            inconsistent.
    """

    if settings.storage_backend not in SUPPORTED_STORAGE_BACKENDS:
        allowed = ", ".join(sorted(SUPPORTED_STORAGE_BACKENDS))
        raise ValueError(f"unsupported storage backend; allowed: {allowed}")
    if settings.auth_required and not settings.api_token:
        raise ValueError("CRAWLER_AUTH_REQUIRED requires CRAWLER_API_TOKEN")


def _csv_values(value: str | None, *, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse comma-separated environment values.

    Args:
        value (str | None): Raw environment string.
        default (tuple[str, ...]): Values used when the environment variable is
            not set.

    Returns:
        tuple[str, ...]: Trimmed values with empty entries removed.
    """

    if value is None:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _optional_text(value: str | None) -> str | None:
    """Normalize blank environment values to ``None``.

    Args:
        value (str | None): Raw value from the environment.

    Returns:
        str | None: Trimmed text or ``None`` when the value is blank.
    """

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _bool_value(value: str | None, *, default: bool) -> bool:
    """Parse a boolean environment flag.

    Args:
        value (str | None): Raw environment value such as ``true`` or ``0``.
        default (bool): Value used when the environment variable is unset.

    Returns:
        bool: Parsed boolean value.

    Raises:
        ValueError: Raised when the value is not a recognized boolean spelling.
    """

    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean environment value: {value!r}")
