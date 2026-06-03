"""Access and politeness checks for candidate URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from crawler.models import AccessDecision, DiscoveredItem, Source


DEFAULT_USER_AGENT = "webcrawler/0.1"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RATE_LIMIT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    """Network safety defaults required before later fetch code can run."""

    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    default_rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("user_agent is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.default_rate_limit_seconds < 0:
            raise ValueError("default_rate_limit_seconds cannot be negative")


def robots_url(base_url: str) -> str:
    """Return the robots.txt URL for a source base URL."""
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"base_url must be absolute: {base_url!r}")
    return urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")


def make_headers(policy: FetchPolicy) -> dict[str, str]:
    """Return polite default headers for later fetch requests."""
    return {"User-Agent": policy.user_agent}


def rate_limit_seconds(
    source: Source,
    policy: FetchPolicy = FetchPolicy(),
) -> float:
    """Resolve the per-source delay before future fetches."""
    if source.rate_limit_seconds is None:
        return policy.default_rate_limit_seconds
    if source.rate_limit_seconds < 0:
        raise ValueError("source rate_limit_seconds cannot be negative")
    return source.rate_limit_seconds


def evaluate_access(
    item: DiscoveredItem,
    source: Source,
    *,
    policy: FetchPolicy = FetchPolicy(),
    robots_text: str | None = None,
    checked_at: str | None = None,
) -> AccessDecision:
    """Decide whether a discovered item may proceed to fetching."""
    timestamp = checked_at or datetime.now(UTC).isoformat()
    path = _url_path(item.url)

    blocked_prefix = _matching_prefix(path, source.blocked_paths)
    if blocked_prefix is not None:
        return _decision(
            item,
            source,
            policy,
            timestamp,
            allowed=False,
            reason=f"blocked_by_source_path:{blocked_prefix}",
        )

    if source.allowed_paths and _matching_prefix(path, source.allowed_paths) is None:
        return _decision(
            item,
            source,
            policy,
            timestamp,
            allowed=False,
            reason="outside_allowed_source_paths",
        )

    if source.robots_required:
        if robots_text is None:
            return _decision(
                item,
                source,
                policy,
                timestamp,
                allowed=False,
                reason="robots_required_but_not_loaded",
                metadata={"robots_url": robots_url(source.base_url)},
            )
        parser = _robots_parser(source.base_url, robots_text)
        if not parser.can_fetch(policy.user_agent, item.url):
            return _decision(
                item,
                source,
                policy,
                timestamp,
                allowed=False,
                reason="disallowed_by_robots_txt",
                metadata={"robots_url": robots_url(source.base_url)},
            )

    return _decision(
        item,
        source,
        policy,
        timestamp,
        allowed=True,
        reason="allowed",
    )


def access_log_entry(decision: AccessDecision) -> dict[str, object]:
    """Create a structured log entry for allowed or skipped URLs."""
    return {
        "stage": "check_access",
        "item_id": decision.item_id,
        "source_id": decision.source_id,
        "url": decision.url,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "checked_at": decision.checked_at,
    }


def _decision(
    item: DiscoveredItem,
    source: Source,
    policy: FetchPolicy,
    checked_at: str,
    *,
    allowed: bool,
    reason: str,
    metadata: Mapping[str, object] | None = None,
) -> AccessDecision:
    return AccessDecision(
        item_id=item.item_id,
        source_id=source.source_id,
        url=item.url,
        allowed=allowed,
        reason=reason,
        checked_at=checked_at,
        robots_required=source.robots_required,
        user_agent=policy.user_agent,
        rate_limit_seconds=rate_limit_seconds(source, policy),
        metadata=dict(metadata or {}),
    )


def _robots_parser(base_url: str, robots_text: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(robots_url(base_url))
    parser.parse(robots_text.splitlines())
    return parser


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"url must be absolute: {url!r}")
    return parsed.path or "/"


def _matching_prefix(path: str, prefixes: list[str]) -> str | None:
    for prefix in prefixes:
        normalized = prefix if prefix.startswith("/") else f"/{prefix}"
        if path == normalized or path.startswith(normalized.rstrip("/") + "/"):
            return prefix
    return None
