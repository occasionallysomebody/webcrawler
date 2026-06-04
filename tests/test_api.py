import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import pytest

from crawler.api import create_app
from crawler.config import DeploymentSettings, load_deployment_settings
from crawler.models import Claim, FetchedDocument, Source, TrustScore
from crawler.review import create_claim_review
from crawler.storage import (
    append_jsonl,
    fetch_audit_events,
    initialize_sqlite,
    mirror_run_to_sqlite,
    read_jsonl,
)


def test_api_lists_runs_and_serves_summary_records_and_map_data() -> None:
    with TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "run-1"
        records_dir = run_dir / "records"
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "status": "success",
                    "started_at": "2026-06-04T00:00:00+00:00",
                    "finished_at": "2026-06-04T00:01:00+00:00",
                    "sources_loaded": 1,
                    "claims_extracted": 1,
                }
            ),
            encoding="utf-8",
        )
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
            "Gas flaring pollution was reported.",
            "environmental_risk",
            evidence_excerpt="Gas flaring pollution was reported.",
        )
        score = TrustScore("claim-1", final_score=0.812)
        append_jsonl(records_dir / "sources.jsonl", [source])
        append_jsonl(records_dir / "fetched_documents.jsonl", [document])
        append_jsonl(records_dir / "claims.jsonl", [claim])
        append_jsonl(records_dir / "trust_scores.jsonl", [score])

        client = TestClient(create_app(tmp_dir))

        assert client.get("/").json()["docs"] == "/docs"
        assert client.get("/health").json() == {"status": "ok"}
        cors_response = client.get(
            "/health",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        assert cors_response.headers["access-control-allow-origin"] == (
            "http://127.0.0.1:3000"
        )
        assert client.get("/runs").json()["runs"][0]["run_id"] == "run-1"
        assert client.get("/runs/run-1/summary").json()["status"] == "success"
        assert (
            client.get("/runs/run-1/records/claims").json()["records"][0]["claim_id"]
            == "claim-1"
        )
        map_data = client.get("/runs/run-1/map-data").json()
        map_html = client.get("/runs/run-1/map")
        filtered = client.get(
            "/runs/run-1/map-data",
            params={"claim_type": "environmental_risk", "min_trust": 0.8},
        ).json()

    assert map_data["summary"]["claims"] == 1
    assert map_html.status_code == 200
    assert "/runs/${encodeURIComponent(apiConfig.run_id)}/map-data" in map_html.text
    assert '"run_id": "run-1"' in map_html.text
    assert filtered["summary"]["trust_scores"] == 1
    assert any(
        feature["properties"]["layer"] == "claim"
        for feature in filtered["features"]["features"]
    )


def test_api_rejects_unknown_runs_and_record_names() -> None:
    with TemporaryDirectory() as tmp_dir:
        client = TestClient(create_app(tmp_dir))

        assert client.get("/runs/missing/summary").status_code == 404

        run_dir = Path(tmp_dir) / "run-1"
        run_dir.mkdir()
        (run_dir / "run_summary.json").write_text("{}", encoding="utf-8")

        assert client.get("/runs/run-1/records/../../secret").status_code == 404
        assert client.get("/runs/run-1/records/unknown").status_code == 404


def test_api_rejects_unauthorized_data_routes_when_auth_is_enabled() -> None:
    with TemporaryDirectory() as tmp_dir:
        settings = DeploymentSettings(
            run_storage_path=Path(tmp_dir),
            audit_log_path=Path(tmp_dir) / "audit_events.jsonl",
            api_token="secret-token",
            auth_required=True,
            cors_origins=("https://analyst.example",),
        )
        client = TestClient(create_app(settings=settings))

        unauthorized = client.get("/runs")
        authorized = client.get(
            "/runs",
            headers={
                "Authorization": "Bearer secret-token",
                "Origin": "https://analyst.example",
                "X-Analyst-Id": "analyst-a",
            },
        )

    assert client.get("/health").json() == {"status": "ok"}
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.headers["access-control-allow-origin"] == (
        "https://analyst.example"
    )


def test_api_records_audit_events_and_exports_claim_evidence() -> None:
    with TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "run-1"
        records_dir = run_dir / "records"
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps({"run_id": "run-1", "status": "success"}),
            encoding="utf-8",
        )
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
            "Gas flaring pollution was reported.",
            "environmental_risk",
            evidence_excerpt="Gas flaring pollution was reported.",
        )
        score = TrustScore("claim-1", final_score=0.75)
        append_jsonl(records_dir / "sources.jsonl", [source])
        append_jsonl(records_dir / "fetched_documents.jsonl", [document])
        append_jsonl(records_dir / "claims.jsonl", [claim])
        append_jsonl(records_dir / "trust_scores.jsonl", [score])
        review = create_claim_review(
            run_id="run-1",
            claim_id="claim-1",
            review_status="confirmed",
            reviewer="analyst-a",
            notes="Reviewed against cited source.",
            source_id="source-1",
            document_id="doc-1",
            reviewed_at="2026-06-04T12:00:00+00:00",
        )
        append_jsonl(records_dir / "claim_reviews.jsonl", [review])

        audit_path = Path(tmp_dir) / "audit" / "audit_events.jsonl"
        settings = DeploymentSettings(
            run_storage_path=Path(tmp_dir),
            audit_log_path=audit_path,
            api_token="secret-token",
            auth_required=True,
        )
        client = TestClient(create_app(settings=settings))
        headers = {
            "Authorization": "Bearer secret-token",
            "X-Analyst-Id": "analyst-a",
        }

        recorded = client.post(
            "/audit-events",
            headers=headers,
            json={
                "event_type": "run_selected",
                "run_id": "run-1",
                "metadata": {"min_trust": "0.4"},
            },
        )
        exported = client.get(
            "/runs/run-1/evidence-export",
            params={"claim_id": "claim-1"},
            headers=headers,
        )
        audit_events = read_jsonl(audit_path)

    assert recorded.status_code == 200
    assert exported.status_code == 200
    assert exported.json()["claims"][0]["claim_id"] == "claim-1"
    assert exported.json()["review_notes"][0]["review_status"] == "confirmed"
    assert exported.json()["review_notes"][0]["notes"] == "Reviewed against cited source."
    assert exported.json()["map_features"]
    assert exported.json()["audit_event_id"].startswith("audit-")
    assert [event["event_type"] for event in audit_events] == [
        "run_selected",
        "evidence_exported",
    ]
    assert {event["actor"] for event in audit_events} == {"analyst-a"}


def test_api_saves_claim_review_without_mutating_claim_record() -> None:
    with TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "run-1"
        records_dir = run_dir / "records"
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps({"run_id": "run-1", "status": "success"}),
            encoding="utf-8",
        )
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
            "Gas flaring pollution was reported.",
            "environmental_risk",
            evidence_excerpt="Gas flaring pollution was reported.",
        )
        append_jsonl(records_dir / "sources.jsonl", [source])
        append_jsonl(records_dir / "fetched_documents.jsonl", [document])
        append_jsonl(records_dir / "claims.jsonl", [claim])

        audit_path = Path(tmp_dir) / "audit" / "audit_events.jsonl"
        settings = DeploymentSettings(
            run_storage_path=Path(tmp_dir),
            audit_log_path=audit_path,
            api_token="secret-token",
            auth_required=True,
        )
        client = TestClient(create_app(settings=settings))
        headers = {
            "Authorization": "Bearer secret-token",
            "X-Analyst-Id": "analyst-a",
        }

        saved = client.post(
            "/runs/run-1/claim-reviews",
            headers=headers,
            json={
                "claim_id": "claim-1",
                "review_status": "watchlisted",
                "notes": "Monitor this claim in the next crawl.",
            },
        )
        reviews = client.get(
            "/runs/run-1/claim-reviews",
            headers=headers,
            params={"claim_id": "claim-1"},
        )
        claim_record = client.get(
            "/runs/run-1/records/claims",
            headers=headers,
        )
        map_data = client.get("/runs/run-1/map-data", headers=headers).json()
        audit_events = read_jsonl(audit_path)

    assert saved.status_code == 200
    assert saved.json()["review"]["review_status"] == "watchlisted"
    assert reviews.json()["reviews"][0]["notes"] == "Monitor this claim in the next crawl."
    assert "review_status" not in claim_record.json()["records"][0]
    claim_features = [
        feature
        for feature in map_data["features"]["features"]
        if feature["properties"].get("claim_id") == "claim-1"
    ]
    assert claim_features[0]["properties"]["review_status"] == "watchlisted"
    assert audit_events[0]["event_type"] == "claim_reviewed"


def test_api_serves_runs_records_and_reviews_from_sqlite_storage() -> None:
    with TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "runs" / "run-1"
        records_dir = run_dir / "records"
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "status": "success",
                    "sources_loaded": 1,
                    "claims_extracted": 1,
                }
            ),
            encoding="utf-8",
        )
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
            "Gas flaring pollution was reported.",
            "environmental_risk",
            evidence_excerpt="Gas flaring pollution was reported.",
        )
        score = TrustScore("claim-1", final_score=0.8)
        append_jsonl(records_dir / "sources.jsonl", [source])
        append_jsonl(records_dir / "fetched_documents.jsonl", [document])
        append_jsonl(records_dir / "claims.jsonl", [claim])
        append_jsonl(records_dir / "trust_scores.jsonl", [score])
        db_path = Path(tmp_dir) / "storage" / "crawler.sqlite"
        mirror_run_to_sqlite(db_path=db_path, run_dir=run_dir)

        settings = DeploymentSettings(
            run_storage_path=Path(tmp_dir) / "missing-file-root",
            audit_log_path=Path(tmp_dir) / "audit" / "events.jsonl",
            storage_backend="sqlite",
            run_db_path=db_path,
            api_token="secret-token",
            auth_required=True,
        )
        client = TestClient(create_app(settings=settings))
        headers = {
            "Authorization": "Bearer secret-token",
            "X-Analyst-Id": "analyst-a",
        }

        listed = client.get("/runs", headers=headers)
        records = client.get("/runs/run-1/records/claims", headers=headers)
        map_data = client.get("/runs/run-1/map-data", headers=headers)
        saved_review = client.post(
            "/runs/run-1/claim-reviews",
            headers=headers,
            json={
                "claim_id": "claim-1",
                "review_status": "confirmed",
                "notes": "Reviewed from SQLite-backed API.",
            },
        )
        reviews = client.get("/runs/run-1/claim-reviews", headers=headers)
        connection = initialize_sqlite(db_path)
        audit_events = fetch_audit_events(connection, run_id="run-1")
        stored_reviews = client.get(
            "/runs/run-1/records/claim_reviews",
            headers=headers,
        )
        connection.close()

    assert listed.status_code == 200
    assert listed.json()["runs"][0]["run_id"] == "run-1"
    assert records.json()["records"][0]["claim_id"] == "claim-1"
    assert map_data.json()["summary"]["claims"] == 1
    assert saved_review.status_code == 200
    assert reviews.json()["reviews"][0]["review_status"] == "confirmed"
    assert stored_reviews.json()["records"][0]["notes"] == "Reviewed from SQLite-backed API."
    assert audit_events[0]["event_type"] == "claim_reviewed"


def test_deployment_settings_load_environment_and_validate_auth() -> None:
    settings = load_deployment_settings(
        {
            "CRAWLER_ENV": "staging",
            "CRAWLER_RUN_STORAGE_PATH": "Z:/shared/runs",
            "CRAWLER_AUDIT_LOG_PATH": "Z:/shared/audit/events.jsonl",
            "CRAWLER_STORAGE_BACKEND": "shared_filesystem",
            "CRAWLER_CORS_ORIGINS": "https://ui.example,https://preview.example",
            "CRAWLER_API_TOKEN": "secret-token",
        }
    )

    assert settings.environment == "staging"
    assert settings.auth_required is True
    assert settings.storage_backend == "shared_filesystem"
    assert settings.cors_origins == ("https://ui.example", "https://preview.example")

    with pytest.raises(ValueError, match="CRAWLER_AUTH_REQUIRED"):
        create_app(settings=DeploymentSettings(auth_required=True))
