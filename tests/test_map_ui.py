import json
from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.map_ui import (
    build_map_data,
    load_map_records,
    map_ui_log_entry,
    render_map_html,
    write_map_ui,
)
from crawler.models import Claim, FetchedDocument, Source, TrustScore
from crawler.storage import append_jsonl


def test_build_map_data_includes_operational_layers_and_source_coverage() -> None:
    sources = [
        Source(
            "source-1",
            "Global Witness Gas Flaring Azerbaijan",
            "tier_3",
            "ngo",
            "https://example.org/flaring",
            "manual_seed",
            notes="gas flaring pollution near Sangachal terminal",
            metadata={"domain_tags": ["gas_flaring", "ecology", "Azerbaijan"]},
        ),
        Source(
            "source-2",
            "Caspian Oil Pollution Study",
            "tier_4",
            "academic",
            "https://example.org/oil",
            "manual_seed",
            notes="oil pollution and oil spills in the Caspian Sea",
            metadata={"domain_tags": ["oil_pollution", "oil_spills", "ecology"]},
        ),
    ]

    data = build_map_data(sources=sources, include_demo_overlays=True)
    features = data["features"]["features"]
    layers = {feature["properties"]["layer"] for feature in features}

    assert {"opportunity", "environmental", "political", "coverage"} <= layers
    assert data["summary"]["crawler_sources"] == 2
    assert any(
        feature["properties"]["name"] == "Sangachal Compliance Pressure"
        for feature in features
    )
    assert any(
        feature["properties"].get("source_count", 0) >= 1
        for feature in features
        if feature["properties"]["layer"] == "coverage"
    )


def test_build_map_data_attaches_claim_evidence() -> None:
    source = Source(
        "source-1",
        "Example Source",
        "tier_1",
        "government",
        "https://example.org",
        "manual_seed",
    )
    document = FetchedDocument("doc-1", "source-1", "https://example.org/report")
    claim = Claim(
        "claim-1",
        "doc-1",
        "Gas flaring pollution was reported near Sangachal terminal.",
        "environmental_risk",
        evidence_excerpt="Gas flaring pollution was reported.",
        confidence=0.7,
    )
    score = TrustScore("claim-1", final_score=0.812)

    data = build_map_data(
        sources=[source],
        claims=[claim],
        trust_scores=[score],
        documents=[document],
    )
    claim_features = [
        feature
        for feature in data["features"]["features"]
        if feature["properties"]["layer"] == "claim"
    ]

    assert len(claim_features) == 1
    assert claim_features[0]["properties"]["confidence"] == 0.812
    assert claim_features[0]["properties"]["evidence"][0]["url"] == document.url


def test_render_map_html_embeds_maplibre_and_map_data() -> None:
    data = build_map_data(include_demo_overlays=True)
    rendered = render_map_html(
        data,
        api_base_url="http://127.0.0.1:8000",
        run_id="run-1",
    )

    assert "maplibre-gl" in rendered
    assert "basemaps.cartocdn.com" in rendered
    assert "Azerbaijan Energy Intelligence" in rendered
    assert "Sangachal Compliance Pressure" in rendered
    assert '<script type="application/json" id="map-data">' in rendered
    assert '<script type="application/json" id="api-config">' in rendered
    assert "/runs/${encodeURIComponent(apiConfig.run_id)}/map-data" in rendered
    assert "http://127.0.0.1:8000" in rendered


def test_write_map_ui_and_log_entry() -> None:
    with TemporaryDirectory() as tmp_dir:
        result = write_map_ui(Path(tmp_dir) / "ui" / "map.html")
        content = result.path.read_text(encoding="utf-8")
        payload = content.split('<script type="application/json" id="map-data">')[1]
        payload = payload.split("</script>", 1)[0]
        decoded = json.loads(payload)

    assert result.feature_count == len(decoded["features"]["features"])
    assert result.source_count == 0
    assert map_ui_log_entry(result)["stage"] == "build_map_ui"


def test_build_map_data_uses_pipeline_records_without_demo_overlays() -> None:
    source = Source(
        "source-1",
        "Example Source",
        "tier_1",
        "government",
        "https://example.org",
        "manual_seed",
    )
    document = FetchedDocument("doc-1", "source-1", "https://example.org/report")
    claim = Claim(
        "claim-1",
        "doc-1",
        "Oil pollution was reported near Oil Rocks.",
        "environmental_risk",
        evidence_excerpt="Oil pollution was reported.",
        confidence=0.7,
    )

    data = build_map_data(sources=[source], claims=[claim], documents=[document])
    layers = {feature["properties"]["layer"] for feature in data["features"]["features"]}

    assert "claim" in layers
    assert "coverage" in layers
    assert "opportunity" not in layers
    assert "environmental" not in layers
    assert data["summary"]["data_mode"] == "pipeline_records"


def test_load_map_records_and_write_ui_from_records_dir() -> None:
    source = Source(
        "source-1",
        "Example Source",
        "tier_1",
        "government",
        "https://example.org",
        "manual_seed",
    )
    document = FetchedDocument("doc-1", "source-1", "https://example.org/report")
    claim = Claim(
        "claim-1",
        "doc-1",
        "Gas flaring pollution was reported near Sangachal terminal.",
        "environmental_risk",
        evidence_excerpt="Gas flaring pollution was reported.",
        confidence=0.7,
    )
    score = TrustScore("claim-1", final_score=0.812)

    with TemporaryDirectory() as tmp_dir:
        records_dir = Path(tmp_dir) / "records"
        append_jsonl(records_dir / "sources.jsonl", [source])
        append_jsonl(records_dir / "fetched_documents.jsonl", [document])
        append_jsonl(records_dir / "claims.jsonl", [claim])
        append_jsonl(records_dir / "trust_scores.jsonl", [score])

        records = load_map_records(records_dir)
        result = write_map_ui(
            Path(tmp_dir) / "ui" / "map.html",
            records_dir=records_dir,
            api_base_url="http://127.0.0.1:8000",
            run_id="run-1",
        )
        content = result.path.read_text(encoding="utf-8")
        payload = content.split('<script type="application/json" id="map-data">')[1]
        data = json.loads(payload.split("</script>", 1)[0])

    assert len(records.claims) == 1
    assert data["summary"]["claims"] == 1
    assert '"run_id": "run-1"' in content
    assert data["summary"]["trust_scores"] == 1
    assert any(
        feature["properties"]["layer"] == "claim"
        and feature["properties"]["confidence"] == 0.812
        for feature in data["features"]["features"]
    )
