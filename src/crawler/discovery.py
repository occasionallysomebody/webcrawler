"""Discovery helpers that produce normalized candidate records."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, build_opener

from crawler.models import DiscoveredItem, Source
from crawler.robots import FetchPolicy, make_headers
from crawler.source_registry import load_source_registry


MANUAL_SEED_METHOD = "manual_seed"
SITEMAP_METHOD = "sitemap"
RSS_METHOD = "rss"
API_METHOD = "api"


def discover_from_source_registry(
    path: str | Path = "data/sources.csv",
    *,
    include_disabled: bool = False,
    discovered_at: str | None = None,
) -> list[DiscoveredItem]:
    """Load enabled sources and discover their registry URLs as manual seeds."""
    registry = load_source_registry(path, include_disabled=include_disabled)
    return discover_manual_seed_urls(
        registry.sources,
        discovered_at=discovered_at,
    )


def discover_manual_seed_urls(
    sources: list[Source],
    *,
    discovered_at: str | None = None,
) -> list[DiscoveredItem]:
    """Create one discovered item per unique source registry URL.

    This discovery method is intentionally network-free. It treats curated
    source registry URLs as manual seeds for later access checks and fetching.
    """
    timestamp = discovered_at or datetime.now(UTC).isoformat()
    items_by_url: dict[str, DiscoveredItem] = {}

    for source in sources:
        normalized_url = normalize_url(source.base_url)
        existing = items_by_url.get(normalized_url)
        if existing is not None:
            duplicate_source_ids = existing.metadata.setdefault(
                "duplicate_source_ids",
                [],
            )
            if isinstance(duplicate_source_ids, list):
                duplicate_source_ids.append(source.source_id)
            continue

        item = DiscoveredItem(
            item_id=discovered_item_id(
                source.source_id,
                normalized_url,
                MANUAL_SEED_METHOD,
            ),
            source_id=source.source_id,
            url=normalized_url,
            discovery_method=MANUAL_SEED_METHOD,
            discovered_at=timestamp,
            title=source.name,
            content_type_hint=content_type_hint(source, normalized_url),
            metadata={
                "source_name": source.name,
                "source_tier": source.tier,
                "publisher_type": source.publisher_type,
                "access_method": source.access_method,
            },
        )
        items_by_url[normalized_url] = item

    return list(items_by_url.values())


def discover_expanded_source_urls(
    sources: list[Source],
    *,
    discovered_at: str | None = None,
    policy: FetchPolicy = FetchPolicy(),
    opener=None,
) -> list[DiscoveredItem]:
    """Discover manual seeds plus approved sitemap, feed, and API URLs."""
    timestamp = discovered_at or datetime.now(UTC).isoformat()
    items_by_url: dict[str, DiscoveredItem] = {
        item.url: item
        for item in discover_manual_seed_urls(sources, discovered_at=timestamp)
    }

    for source in sources:
        for method, registry_url, urls in _expanded_urls(source, policy, opener):
            for url in urls:
                normalized_url = normalize_url(url)
                if normalized_url in items_by_url:
                    continue
                items_by_url[normalized_url] = _discovered_item(
                    source,
                    normalized_url,
                    method,
                    timestamp,
                    registry_url=registry_url,
                )

    return list(items_by_url.values())


def normalize_url(url: str) -> str:
    """Normalize a seed URL for stable discovery and deduplication."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"url must be absolute: {url!r}")

    scheme = parsed.scheme.lower()
    netloc = _normalize_netloc(parsed.netloc, scheme)
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def discovered_item_id(
    source_id: str,
    normalized_url: str,
    discovery_method: str,
) -> str:
    """Return a stable item ID for a discovered source URL."""
    digest = hashlib.sha256(
        f"{source_id}\n{discovery_method}\n{normalized_url}".encode("utf-8"),
    ).hexdigest()
    return f"item-{digest[:16]}"


def content_type_hint(source: Source, url: str) -> str | None:
    """Infer a coarse content-type hint without fetching the URL."""
    method = source.access_method.lower()
    path = urlparse(url).path.lower()

    if method == "public_pdf" or path.endswith(".pdf"):
        return "application/pdf"
    if method == "api" or path.endswith(".json"):
        return "application/json"
    if method in {"public_html", "manual_seed", "sitemap", "rss"}:
        return "text/html"
    return None


def _expanded_urls(
    source: Source,
    policy: FetchPolicy,
    opener,
) -> list[tuple[str, str, list[str]]]:
    expanded: list[tuple[str, str, list[str]]] = []
    for method, metadata_key, parser in (
        (SITEMAP_METHOD, "sitemap_url", _parse_sitemap_urls),
        (RSS_METHOD, "rss_url", _parse_feed_urls),
        (API_METHOD, "api_url", _parse_api_urls),
    ):
        registry_url = source.metadata.get(metadata_key)
        if not isinstance(registry_url, str) or not registry_url:
            continue
        text = _fetch_discovery_text(registry_url, policy, opener)
        if text is None:
            continue
        expanded.append((method, registry_url, parser(text)))
    return expanded


def _fetch_discovery_text(
    url: str,
    policy: FetchPolicy,
    opener,
) -> str | None:
    request_opener = opener or build_opener()
    request = Request(url, headers=make_headers(policy), method="GET")
    try:
        response = request_opener.open(request, timeout=policy.timeout_seconds)
        try:
            return response.read().decode("utf-8", errors="replace")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except OSError:
        return None


def _parse_sitemap_urls(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) == "loc" and element.text:
            urls.append(element.text.strip())
    return urls


def _parse_feed_urls(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "link" and element.text and element.text.strip().startswith("http"):
            urls.append(element.text.strip())
        if name == "link" and element.attrib.get("href"):
            urls.append(element.attrib["href"].strip())
    return urls


def _parse_api_urls(text: str) -> list[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    return list(_walk_urls(payload))


def _walk_urls(value) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "link", "href"} and isinstance(item, str):
                urls.append(item)
            else:
                urls.extend(_walk_urls(item))
    if isinstance(value, list):
        for item in value:
            urls.extend(_walk_urls(item))
    return urls


def _discovered_item(
    source: Source,
    normalized_url: str,
    discovery_method: str,
    discovered_at: str,
    *,
    registry_url: str,
) -> DiscoveredItem:
    return DiscoveredItem(
        item_id=discovered_item_id(
            source.source_id,
            normalized_url,
            discovery_method,
        ),
        source_id=source.source_id,
        url=normalized_url,
        discovery_method=discovery_method,
        discovered_at=discovered_at,
        title=source.name,
        content_type_hint=content_type_hint(source, normalized_url),
        metadata={
            "source_name": source.name,
            "source_tier": source.tier,
            "publisher_type": source.publisher_type,
            "access_method": source.access_method,
            "registry_url": registry_url,
        },
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _normalize_netloc(netloc: str, scheme: str) -> str:
    lowered = netloc.lower()
    if scheme == "http" and lowered.endswith(":80"):
        return lowered[:-3]
    if scheme == "https" and lowered.endswith(":443"):
        return lowered[:-4]
    return lowered
