from crawler.models import DiscoveredItem, Source
from crawler.robots import (
    FetchPolicy,
    access_log_entry,
    evaluate_access,
    make_headers,
    rate_limit_seconds,
    robots_url,
)


ROBOTS_TEXT = """User-agent: *
Allow: /public/
Disallow: /private/
"""


def source(**overrides):
    values = {
        "source_id": "example-source",
        "name": "Example Source",
        "tier": "tier_1",
        "publisher_type": "reference",
        "base_url": "https://example.org",
        "access_method": "sitemap",
        "rate_limit_seconds": 1.5,
        "robots_required": True,
        "allowed_paths": [],
        "blocked_paths": [],
    }
    values.update(overrides)
    return Source(**values)


def item(url: str = "https://example.org/public/report") -> DiscoveredItem:
    return DiscoveredItem(
        item_id="item-001",
        source_id="example-source",
        url=url,
        discovery_method="manual_seed",
        discovered_at="2026-06-03T00:00:00Z",
    )


def test_evaluate_access_allows_robots_permitted_url() -> None:
    decision = evaluate_access(
        item(),
        source(),
        robots_text=ROBOTS_TEXT,
        checked_at="2026-06-03T00:00:00Z",
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert decision.rate_limit_seconds == 1.5
    assert decision.user_agent == "webcrawler/0.1"


def test_evaluate_access_blocks_robots_disallowed_url() -> None:
    decision = evaluate_access(
        item("https://example.org/private/report"),
        source(),
        robots_text=ROBOTS_TEXT,
        checked_at="2026-06-03T00:00:00Z",
    )

    assert decision.allowed is False
    assert decision.reason == "disallowed_by_robots_txt"
    assert decision.metadata["robots_url"] == "https://example.org/robots.txt"


def test_evaluate_access_blocks_when_robots_required_but_missing() -> None:
    decision = evaluate_access(
        item(),
        source(),
        checked_at="2026-06-03T00:00:00Z",
    )

    assert decision.allowed is False
    assert decision.reason == "robots_required_but_not_loaded"


def test_evaluate_access_honors_explicit_source_paths() -> None:
    explicit_source = source(
        robots_required=False,
        allowed_paths=["/reports"],
        blocked_paths=["/reports/private"],
    )

    allowed = evaluate_access(
        item("https://example.org/reports/public"),
        explicit_source,
        checked_at="2026-06-03T00:00:00Z",
    )
    outside = evaluate_access(
        item("https://example.org/news/public"),
        explicit_source,
        checked_at="2026-06-03T00:00:00Z",
    )
    blocked = evaluate_access(
        item("https://example.org/reports/private/a"),
        explicit_source,
        checked_at="2026-06-03T00:00:00Z",
    )

    assert allowed.allowed is True
    assert outside.reason == "outside_allowed_source_paths"
    assert blocked.reason == "blocked_by_source_path:/reports/private"


def test_fetch_policy_requires_timeout_and_user_agent() -> None:
    try:
        FetchPolicy(timeout_seconds=0)
    except ValueError as error:
        assert "timeout_seconds" in str(error)
    else:
        raise AssertionError("expected timeout validation error")

    try:
        FetchPolicy(user_agent=" ")
    except ValueError as error:
        assert "user_agent" in str(error)
    else:
        raise AssertionError("expected user agent validation error")


def test_helpers_return_headers_rate_limit_robots_url_and_log_entry() -> None:
    policy = FetchPolicy(user_agent="example-agent/1.0", timeout_seconds=5)
    decision = evaluate_access(
        item(),
        source(rate_limit_seconds=None, robots_required=False),
        policy=policy,
        checked_at="2026-06-03T00:00:00Z",
    )

    assert make_headers(policy) == {"User-Agent": "example-agent/1.0"}
    assert rate_limit_seconds(source(rate_limit_seconds=None), policy) == 2.0
    assert robots_url("https://example.org/path") == "https://example.org/robots.txt"
    assert access_log_entry(decision)["reason"] == "allowed"
