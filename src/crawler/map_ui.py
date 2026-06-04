"""Azerbaijan energy intelligence map data and static HTML rendering.

The map is an analyst-facing view over pipeline records. It converts sources,
claims, trust scores, and optional demo overlays into GeoJSON so the static map,
FastAPI endpoint, and Next UI can share the same evidence-backed contract.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import html
import json
from pathlib import Path
from typing import Any

from crawler.models import Claim, FetchedDocument, Source, TrustScore


DEFAULT_CENTER = [49.45, 40.15]
DEFAULT_ZOOM = 6.2
MAPLIBRE_CSS_URL = "https://unpkg.com/maplibre-gl@5.6.0/dist/maplibre-gl.css"
MAPLIBRE_JS_URL = "https://unpkg.com/maplibre-gl@5.6.0/dist/maplibre-gl.js"
BASEMAP_STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"


@dataclass(slots=True)
class MapUiResult:
    """Result of writing a static map UI artifact."""

    path: Path
    feature_count: int
    source_count: int


@dataclass(slots=True)
class MapUiRecords:
    """Pipeline records available for map UI generation."""

    sources: list[Source]
    claims: list[Claim]
    trust_scores: list[TrustScore]
    documents: list[FetchedDocument]


def build_map_data(
    *,
    sources: list[Source] | None = None,
    claims: list[Claim] | None = None,
    trust_scores: list[TrustScore] | None = None,
    documents: list[FetchedDocument] | None = None,
    include_demo_overlays: bool = False,
) -> dict[str, Any]:
    """Build map-ready operational intelligence from pipeline records."""
    sources = sources or []
    claims = claims or []
    trust_scores = trust_scores or []
    documents = documents or []
    source_count_by_topic = _source_counts_by_topic(sources)

    features = []
    if include_demo_overlays:
        features.extend(_opportunity_features())
        features.extend(_environmental_pressure_features(source_count_by_topic))
        features.extend(_political_pressure_features())
    features.extend(_source_coverage_features(sources, source_count_by_topic))
    features.extend(_claim_features(claims, trust_scores, documents, sources))
    data_mode = "demo_plus_pipeline" if include_demo_overlays else "pipeline_records"
    summary = {
        "opportunities": sum(
            1 for feature in features if feature["properties"]["layer"] == "opportunity"
        ),
        "environmental_zones": sum(
            1 for feature in features if feature["properties"]["layer"] == "environmental"
        ),
        "political_zones": sum(
            1 for feature in features if feature["properties"]["layer"] == "political"
        ),
        "source_coverage_points": sum(
            1 for feature in features if feature["properties"]["layer"] == "coverage"
        ),
        "crawler_sources": len(sources),
        "claims": len(claims),
        "documents": len(documents),
        "trust_scores": len(trust_scores),
        "data_mode": data_mode,
    }
    return {
        "title": "Azerbaijan Energy Intelligence",
        "generated_from": data_mode,
        "center": DEFAULT_CENTER,
        "zoom": DEFAULT_ZOOM,
        "summary": summary,
        "features": {"type": "FeatureCollection", "features": features},
    }


def load_map_records(records_dir: str | Path) -> MapUiRecords:
    """Load map UI inputs from a pipeline records directory."""
    base = Path(records_dir)
    return MapUiRecords(
        sources=_records_from_jsonl(base / "sources.jsonl", Source, "source_id"),
        claims=_records_from_jsonl(base / "claims.jsonl", Claim, "claim_id"),
        trust_scores=_records_from_jsonl(
            base / "trust_scores.jsonl",
            TrustScore,
            "claim_id",
        ),
        documents=[
            *_records_from_jsonl(
                base / "fetched_documents.jsonl",
                FetchedDocument,
                "document_id",
            ),
            *_records_from_jsonl(base / "documents.jsonl", FetchedDocument, "document_id"),
        ],
    )


def render_map_html(
    map_data: dict[str, Any],
    *,
    api_base_url: str | None = None,
    run_id: str | None = None,
) -> str:
    """Render a self-contained HTML dashboard with embedded GeoJSON."""
    payload = _json_for_script(map_data)
    api_payload = _json_for_script(
        {
            "api_base_url": api_base_url or "",
            "run_id": run_id or "",
        }
    )
    title = html.escape(str(map_data.get("title", "Energy Intelligence Map")))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{MAPLIBRE_CSS_URL}">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f5;
      --panel: #ffffff;
      --border: #deded9;
      --text: #171717;
      --muted: #5f6368;
      --soft: #f0f1ee;
      --blue: #1f73d1;
      --green: #147d64;
      --amber: #a46100;
      --red: #bf2e2e;
      --purple: #6b55c8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .shell {{ min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }}
    header {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--bg);
    }}
    h1 {{
      margin: 0;
      font-size: 34px;
      line-height: 1.05;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .subtitle {{ margin-top: 6px; color: var(--muted); font-size: 15px; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 10px;
      align-items: center;
    }}
    .control, .button {{
      min-height: 42px;
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 7px;
      padding: 0 12px;
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--text);
      font-size: 14px;
    }}
    select, button {{ border: 0; background: transparent; font: inherit; color: inherit; }}
    button {{ cursor: pointer; }}
    .main {{
      display: grid;
      grid-template-columns: 340px minmax(420px, 1fr) 360px;
      min-height: 0;
    }}
    aside {{ border-right: 1px solid var(--border); background: var(--panel); overflow: auto; }}
    .drawer {{ border-left: 1px solid var(--border); border-right: 0; }}
    .panel-section {{ padding: 16px 18px; border-bottom: 1px solid var(--border); }}
    .panel-title {{
      margin: 0 0 11px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .metric {{ border: 1px solid var(--border); border-radius: 7px; padding: 10px; background: #fbfbfa; }}
    .metric strong {{ display: block; font-size: 22px; line-height: 1; }}
    .metric span {{ display: block; margin-top: 5px; color: var(--muted); font-size: 12px; }}
    .item {{
      width: 100%;
      text-align: left;
      display: grid;
      grid-template-columns: 10px 1fr auto;
      gap: 10px;
      align-items: start;
      padding: 11px 0;
      border-top: 1px solid var(--soft);
    }}
    .item:first-of-type {{ border-top: 0; }}
    .dot {{ width: 8px; height: 8px; margin-top: 6px; border-radius: 999px; background: var(--blue); }}
    .item small, .muted {{ color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .item strong {{ display: block; font-size: 14px; line-height: 1.25; font-weight: 650; }}
    .score {{ color: var(--text); font-variant-numeric: tabular-nums; font-size: 13px; }}
    #map-wrap {{ position: relative; min-width: 0; min-height: 0; }}
    #map {{ position: absolute; inset: 0; }}
    #map:after {{
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background-image: radial-gradient(#111 0.8px, transparent 0.8px);
      background-size: 9px 9px;
      opacity: .08;
      mix-blend-mode: multiply;
    }}
    .legend {{
      position: absolute;
      left: 18px;
      bottom: 18px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      max-width: min(680px, calc(100% - 36px));
      padding: 9px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: rgba(255, 255, 255, .92);
      backdrop-filter: blur(8px);
      z-index: 2;
    }}
    .legend label {{ display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; white-space: nowrap; }}
    input[type="checkbox"] {{ accent-color: var(--blue); }}
    .detail h2 {{ margin: 0; font-size: 22px; line-height: 1.15; letter-spacing: 0; }}
    .tag-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 11px; }}
    .tag {{ border: 1px solid var(--border); background: var(--soft); border-radius: 999px; padding: 4px 8px; font-size: 12px; color: #333; }}
    .evidence {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--soft); }}
    .evidence a {{ color: var(--blue); overflow-wrap: anywhere; }}
    @media (max-width: 1080px) {{
      .main {{ grid-template-columns: 310px 1fr; }}
      .drawer {{ grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--border); min-height: 220px; }}
    }}
    @media (max-width: 780px) {{
      header {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
      .main {{ grid-template-columns: 1fr; grid-template-rows: auto 58vh auto; }}
      aside {{ border-right: 0; border-bottom: 1px solid var(--border); max-height: 42vh; }}
      .drawer {{ border-top: 1px solid var(--border); }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>Azerbaijan Energy Intelligence</h1>
        <div class="subtitle">Recommended drillsite opportunities, EPA-relevant environmental pressure, and political/regulatory context.</div>
      </div>
      <div class="controls" aria-label="Map controls">
        <div class="control" title="Select the analysis time window">
          <span aria-hidden="true">Cal</span>
          <select id="time-window">
            <option>Last 12 months</option>
            <option>Last 90 days</option>
            <option>Last 30 days</option>
          </select>
        </div>
        <button class="button" id="fit-azerbaijan" title="Fit map to Azerbaijan and the Caspian operating area">Fit Azerbaijan</button>
        <button class="button" id="export-json" title="Download embedded map intelligence as JSON">Export JSON</button>
      </div>
    </header>
    <main class="main">
      <aside aria-label="Operational intelligence list">
        <section class="panel-section">
          <p class="panel-title">Run Summary</p>
          <div class="metric-grid" id="metric-grid"></div>
        </section>
        <section class="panel-section">
          <p class="panel-title">Ranked Opportunities</p>
          <div id="opportunity-list"></div>
        </section>
        <section class="panel-section">
          <p class="panel-title">Active Pressure Zones</p>
          <div id="pressure-list"></div>
        </section>
      </aside>
      <section id="map-wrap" aria-label="Azerbaijan map">
        <div id="map"></div>
        <div class="legend">
          <label><input type="checkbox" data-layer="opportunity" checked> Drillsites</label>
          <label><input type="checkbox" data-layer="environmental" checked> Environmental</label>
          <label><input type="checkbox" data-layer="political" checked> Political</label>
          <label><input type="checkbox" data-layer="coverage" checked> Source coverage</label>
          <label><input type="checkbox" data-layer="claim" checked> Claims</label>
        </div>
      </section>
      <aside class="drawer detail" aria-label="Evidence details">
        <section class="panel-section" id="detail-panel"></section>
      </aside>
    </main>
  </div>
  <script type="application/json" id="map-data">{payload}</script>
  <script type="application/json" id="api-config">{api_payload}</script>
  <script src="{MAPLIBRE_JS_URL}"></script>
  <script>
    let mapData = JSON.parse(document.getElementById("map-data").textContent);
    const apiConfig = JSON.parse(document.getElementById("api-config").textContent);
    let features = mapData.features.features;
    const colors = {{ opportunity: "#1f73d1", environmental: "#bf2e2e", political: "#a46100", coverage: "#147d64", claim: "#6b55c8" }};
    function layerFeatures(layer) {{
      return {{ type: "FeatureCollection", features: features.filter((feature) => feature.properties.layer === layer) }};
    }}
    function scoreText(feature) {{
      const value = feature.properties.confidence ?? feature.properties.score ?? feature.properties.coverage_score;
      return Number.isFinite(value) ? Math.round(value * 100) + "%" : "";
    }}
    function renderMetrics() {{
      const summary = mapData.summary;
      const metrics = [["Sites", summary.opportunities], ["Zones", summary.environmental_zones + summary.political_zones], ["Sources", summary.crawler_sources], ["Claims", summary.claims]];
      document.getElementById("metric-grid").innerHTML = metrics.map(([label, value]) => `<div class="metric"><strong>${{value}}</strong><span>${{label}}</span></div>`).join("");
    }}
    function itemButton(feature) {{
      const layer = feature.properties.layer;
      const color = colors[layer] || "#1f73d1";
      return `<button class="item" data-feature-id="${{feature.properties.id}}"><span class="dot" style="background:${{color}}"></span><span><strong>${{feature.properties.name}}</strong><small>${{feature.properties.summary}}</small></span><span class="score">${{scoreText(feature)}}</span></button>`;
    }}
    function renderLists() {{
      const opportunities = features.filter((feature) => feature.properties.layer === "opportunity").sort((a, b) => (b.properties.score || 0) - (a.properties.score || 0));
      const pressure = features.filter((feature) => ["environmental", "political"].includes(feature.properties.layer)).sort((a, b) => (b.properties.severity || 0) - (a.properties.severity || 0));
      document.getElementById("opportunity-list").innerHTML = opportunities.length ? opportunities.map(itemButton).join("") : `<p class="muted">No live drillsite recommendation records are available yet.</p>`;
      document.getElementById("pressure-list").innerHTML = pressure.length ? pressure.map(itemButton).join("") : `<p class="muted">No live environmental or political zone records are available yet.</p>`;
      document.querySelectorAll("[data-feature-id]").forEach((button) => button.addEventListener("click", () => selectFeature(features.find((candidate) => candidate.properties.id === button.dataset.featureId))));
    }}
    function renderDetail(feature) {{
      if (!feature) return;
      const evidence = feature.properties.evidence || [];
      const tags = [feature.properties.layer, feature.properties.status, feature.properties.asset_type].filter(Boolean);
      document.getElementById("detail-panel").innerHTML = `<p class="panel-title">Selected Intelligence</p><h2>${{feature.properties.name}}</h2><div class="tag-row">${{tags.map((tag) => `<span class="tag">${{tag}}</span>`).join("")}}</div><p>${{feature.properties.summary}}</p><p class="muted">Confidence: ${{scoreText(feature) || "unscored"}}. Freshness: ${{feature.properties.freshness || "mixed"}}.</p><div class="evidence"><p class="panel-title">Evidence Ledger</p>${{evidence.length ? evidence.map((item) => `<p><strong>${{item.label}}</strong><br><span class="muted">${{item.excerpt || "No excerpt supplied."}}</span><br><a href="${{item.url}}" target="_blank" rel="noreferrer">${{item.url}}</a></p>`).join("") : `<p class="muted">No cited evidence attached to this feature.</p>`}}</div><div class="evidence"><p class="panel-title">Known Gaps</p><p class="muted">${{feature.properties.gaps || "Needs analyst review before capital allocation or compliance action."}}</p></div>`;
    }}
    function selectFeature(feature) {{
      if (!feature) return;
      renderDetail(feature);
      const geometry = feature.geometry;
      if (geometry.type === "Point") {{
        map.easeTo({{ center: geometry.coordinates, zoom: Math.max(map.getZoom(), 8), duration: 650 }});
      }} else {{
        const coords = geometry.type === "Polygon" ? geometry.coordinates.flat() : geometry.coordinates.flat(2);
        const bounds = coords.reduce((box, coord) => box.extend(coord), new maplibregl.LngLatBounds(coords[0], coords[0]));
        map.fitBounds(bounds, {{ padding: 90, duration: 650 }});
      }}
    }}
    function updateMapSources() {{
      for (const layer of ["environmental", "political", "coverage", "opportunity", "claim"]) {{
        const source = map.getSource(layer);
        if (source) source.setData(layerFeatures(layer));
      }}
    }}
    function apiMapDataUrl() {{
      if (!apiConfig.run_id) return null;
      const base = (apiConfig.api_base_url || "").replace(/\\/$/, "");
      return `${{base}}/runs/${{encodeURIComponent(apiConfig.run_id)}}/map-data`;
    }}
    async function refreshFromApi() {{
      const url = apiMapDataUrl();
      if (!url) return;
      try {{
        const response = await fetch(url);
        if (!response.ok) return;
        mapData = await response.json();
        features = mapData.features.features;
        renderMetrics();
        renderLists();
        renderDetail(features[0]);
        updateMapSources();
      }} catch (error) {{
        console.warn("Map API refresh failed; using embedded fallback.", error);
      }}
    }}
    renderMetrics();
    renderLists();
    renderDetail(features[0]);
    const map = new maplibregl.Map({{ container: "map", style: "{BASEMAP_STYLE_URL}", center: mapData.center, zoom: mapData.zoom, attributionControl: true }});
    map.addControl(new maplibregl.NavigationControl({{ showCompass: true }}), "top-right");
    map.on("load", () => {{
      for (const layer of ["environmental", "political", "coverage", "opportunity", "claim"]) map.addSource(layer, {{ type: "geojson", data: layerFeatures(layer) }});
      for (const layer of ["environmental", "political"]) {{
        map.addLayer({{ id: `${{layer}}-fill`, type: "fill", source: layer, paint: {{ "fill-color": colors[layer], "fill-opacity": .18 }} }});
        map.addLayer({{ id: `${{layer}}-outline`, type: "line", source: layer, paint: {{ "line-color": colors[layer], "line-width": 1.5, "line-opacity": .72 }} }});
      }}
      map.addLayer({{ id: "coverage-circle", type: "circle", source: "coverage", paint: {{ "circle-color": colors.coverage, "circle-radius": ["interpolate", ["linear"], ["get", "source_count"], 1, 6, 12, 20], "circle-opacity": .28, "circle-stroke-color": colors.coverage, "circle-stroke-width": 1 }} }});
      map.addLayer({{ id: "opportunity-circle", type: "circle", source: "opportunity", paint: {{ "circle-color": colors.opportunity, "circle-radius": ["interpolate", ["linear"], ["get", "value_index"], 50, 10, 95, 28], "circle-opacity": .72, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 }} }});
      map.addLayer({{ id: "claim-circle", type: "circle", source: "claim", paint: {{ "circle-color": colors.claim, "circle-radius": 7, "circle-opacity": .72, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 }} }});
      for (const id of ["environmental-fill", "political-fill", "coverage-circle", "opportunity-circle", "claim-circle"]) {{
        map.on("click", id, (event) => selectFeature(event.features[0]));
        map.on("mouseenter", id, () => map.getCanvas().style.cursor = "pointer");
        map.on("mouseleave", id, () => map.getCanvas().style.cursor = "");
      }}
      refreshFromApi();
    }});
    document.querySelectorAll("[data-layer]").forEach((checkbox) => {{
      checkbox.addEventListener("change", () => {{
        const visibility = checkbox.checked ? "visible" : "none";
        const ids = {{ opportunity: ["opportunity-circle"], environmental: ["environmental-fill", "environmental-outline"], political: ["political-fill", "political-outline"], coverage: ["coverage-circle"], claim: ["claim-circle"] }}[checkbox.dataset.layer];
        ids.forEach((id) => {{ if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility); }});
      }});
    }});
    document.getElementById("fit-azerbaijan").addEventListener("click", () => map.fitBounds([[44.65, 38.1], [52.4, 42.1]], {{ padding: 42, duration: 700 }}));
    document.getElementById("export-json").addEventListener("click", () => {{
      const blob = new Blob([JSON.stringify(mapData, null, 2)], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "azerbaijan-energy-intelligence-map.json";
      link.click();
      URL.revokeObjectURL(url);
    }});
  </script>
</body>
</html>
"""


def write_map_ui(
    path: str | Path,
    *,
    map_data: dict[str, Any] | None = None,
    records_dir: str | Path | None = None,
    sources: list[Source] | None = None,
    claims: list[Claim] | None = None,
    trust_scores: list[TrustScore] | None = None,
    documents: list[FetchedDocument] | None = None,
    include_demo_overlays: bool = False,
    api_base_url: str | None = None,
    run_id: str | None = None,
) -> MapUiResult:
    """Write a static HTML map dashboard and return metadata."""
    target = Path(path)
    if records_dir is not None:
        records = load_map_records(records_dir)
        sources = records.sources or sources
        claims = records.claims or claims
        trust_scores = records.trust_scores or trust_scores
        documents = records.documents or documents
    data = map_data or build_map_data(
        sources=sources,
        claims=claims,
        trust_scores=trust_scores,
        documents=documents,
        include_demo_overlays=include_demo_overlays,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_map_html(data, api_base_url=api_base_url, run_id=run_id),
        encoding="utf-8",
    )
    return MapUiResult(
        path=target,
        feature_count=len(data["features"]["features"]),
        source_count=data["summary"]["crawler_sources"],
    )


def map_ui_log_entry(result: MapUiResult) -> dict[str, object]:
    """Create a structured log entry for UI generation."""
    return {
        "stage": "build_map_ui",
        "output_path": str(result.path),
        "format": "html",
        "feature_count": result.feature_count,
        "source_count": result.source_count,
    }


def _json_for_script(data: dict[str, Any]) -> str:
    """Serialize JSON safely for a script data block without HTML entities."""
    return (
        json.dumps(data, indent=2, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _records_from_jsonl(
    path: Path,
    record_type: type[Source] | type[Claim] | type[TrustScore] | type[FetchedDocument],
    id_field: str,
) -> list[Any]:
    """Support the module's public workflow by computing records from jsonl.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        path (Path): Filesystem path used by this step. It may be a string or a ``Path``
            depending on the caller.
        record_type (type[Source] | type[Claim] | type[TrustScore] | type[FetchedDocument]): V
            alue named ``record_type`` supplied by the caller for this pipeline step.
        id_field (str): Value named ``id_field`` supplied by the caller for this
            pipeline step.
    
    Returns:
        list[Any]: Result produced for the next pipeline step or caller.
    
    Raises:
        ValueError: Raised when validation or downstream access fails and the caller
            should stop or return an explicit error.
    """
    if not path.exists():
        return []
    records: dict[str, Any] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {error}") from error
            record_id = payload.get(id_field)
            if not record_id:
                continue
            records[str(record_id)] = record_type(**payload)
    return list(records.values())


def _opportunity_features() -> list[dict[str, Any]]:
    """Support the module's public workflow by computing opportunity features.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Returns:
        list[dict[str, Any]]: Result produced for the next pipeline step or caller.
    """
    return [
        _point(
            "opp-absheron-deepwater",
            [50.05, 40.42],
            "Absheron Deepwater Stepout",
            "High-value offshore prospect near existing Caspian infrastructure.",
            "opportunity",
            score=0.84,
            confidence=0.76,
            value_index=91,
            asset_type="offshore prospect",
            status="recommended",
            freshness="current demo layer",
            evidence=[
                {
                    "label": "Operational context",
                    "url": "https://www.bp.com/en_az/azerbaijan/home.html",
                    "excerpt": "Existing offshore development and export infrastructure reduce tieback uncertainty.",
                },
            ],
            gaps="Requires licensed seismic, reservoir, and partner economics review.",
        ),
        _point(
            "opp-shafag-asiman",
            [49.83, 39.78],
            "Shafag-Asiman Appraisal Watch",
            "Large offshore structure with upside, but timing and appraisal evidence remain uncertain.",
            "opportunity",
            score=0.78,
            confidence=0.68,
            value_index=85,
            asset_type="offshore appraisal",
            status="watchlist",
            freshness="mixed",
            evidence=[
                {
                    "label": "Field context",
                    "url": "https://www.bp.com/en_az/azerbaijan/home.html",
                    "excerpt": "Public operator materials identify major Azerbaijan upstream assets and infrastructure.",
                },
            ],
            gaps="Needs updated appraisal status and commercial threshold validation.",
        ),
        _point(
            "opp-gobustan-onshore",
            [49.42, 40.08],
            "Gobustan Onshore Rework",
            "Lower-capex onshore candidate close to Baku service base and export routes.",
            "opportunity",
            score=0.64,
            confidence=0.61,
            value_index=62,
            asset_type="onshore rework",
            status="screening",
            freshness="stale",
            evidence=[
                {
                    "label": "Regional context",
                    "url": "https://www.worldbank.org/en/publication/macro-poverty-outlook/mpo_eca",
                    "excerpt": "Macro and policy context informs capital timing and country risk assumptions.",
                },
            ],
            gaps="Requires current acreage, license status, and reservoir decline analysis.",
        ),
    ]


def _environmental_pressure_features(topic_counts: Counter[str]) -> list[dict[str, Any]]:
    """Support the module's public workflow by computing environmental pressure
    features.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        topic_counts (Counter[str]): Counts of source coverage topics used to size or
            explain map layers.
    
    Returns:
        list[dict[str, Any]]: Result produced for the next pipeline step or caller.
    """
    return [
        _polygon(
            "env-sangachal-flaring",
            [[49.28, 39.98], [49.55, 39.98], [49.60, 40.18], [49.35, 40.27], [49.18, 40.14], [49.28, 39.98]],
            "Sangachal Compliance Pressure",
            "Gas flaring and public health scrutiny near terminal infrastructure.",
            "environmental",
            severity=0.88,
            confidence=0.78,
            status="elevated",
            freshness="2025 source coverage",
            evidence=[
                {
                    "label": "Global Witness source coverage",
                    "url": "https://globalwitness.org/en/campaigns/fossil-fuels/hundreds-of-thousands-in-cop29-host-country-at-risk-from-gas-flaring-pollution/",
                    "excerpt": f"{topic_counts['gas_flaring']} crawler source(s) reference gas flaring or related emissions.",
                },
            ],
            gaps="Needs operator facility-level emissions measurements and current flare event chronology.",
        ),
        _polygon(
            "env-oil-rocks-slicks",
            [[50.15, 39.76], [50.95, 39.75], [51.12, 40.35], [50.55, 40.62], [49.98, 40.29], [50.15, 39.76]],
            "Oil Rocks Surface Slick Risk",
            "Satellite-observed oil pollution and natural seep ambiguity in the central Caspian.",
            "environmental",
            severity=0.81,
            confidence=0.73,
            status="monitor",
            freshness="annual to monthly coverage",
            evidence=[
                {
                    "label": "Caspian satellite monitoring",
                    "url": "https://www.biotaxa.org/em/article/download/86052/80833/361146",
                    "excerpt": f"{topic_counts['oil_pollution'] + topic_counts['oil_spills']} crawler source(s) reference Caspian oil pollution or slicks.",
                },
            ],
            gaps="Needs separation of natural seeps, vessel discharge, and production-related slicks.",
        ),
        _polygon(
            "env-kura-delta-water",
            [[48.52, 39.12], [49.12, 39.06], [49.30, 39.42], [48.82, 39.66], [48.35, 39.48], [48.52, 39.12]],
            "Kura Delta Water Quality Watch",
            "Sensitive coastal and delta area where water-quality claims should gate onshore expansion.",
            "environmental",
            severity=0.62,
            confidence=0.55,
            status="screen",
            freshness="limited direct coverage",
            evidence=[
                {
                    "label": "Caspian ecology source coverage",
                    "url": "https://link.springer.com/article/10.1007/s11356-024-32653-y",
                    "excerpt": f"{topic_counts['ecology']} crawler source(s) reference ecological or biological sampling topics.",
                },
            ],
            gaps="Needs direct water-quality datasets and seasonal baseline measurements.",
        ),
    ]


def _political_pressure_features() -> list[dict[str, Any]]:
    """Support the module's public workflow by computing political pressure features.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Returns:
        list[dict[str, Any]]: Result produced for the next pipeline step or caller.
    """
    return [
        _polygon(
            "pol-baku-regulatory",
            [[49.55, 40.24], [50.10, 40.22], [50.22, 40.55], [49.78, 40.78], [49.42, 40.52], [49.55, 40.24]],
            "Baku Regulatory And Export Nexus",
            "Permitting, export, and stakeholder scrutiny concentrate around Baku and Absheron assets.",
            "political",
            severity=0.74,
            confidence=0.66,
            status="managed risk",
            freshness="current operating context",
            evidence=[
                {
                    "label": "Regulatory and ESG source set",
                    "url": "https://globalreporting.org/standards/",
                    "excerpt": "Disclosure and ESG standards shape analyst review of emissions and operating risk.",
                },
            ],
            gaps="Needs Azerbaijan-specific permitting calendar and stakeholder map.",
        ),
        _polygon(
            "pol-western-corridor",
            [[45.30, 39.85], [46.55, 39.70], [46.88, 40.35], [45.75, 40.78], [44.95, 40.38], [45.30, 39.85]],
            "Western Corridor Political Pressure",
            "Pipeline and border-adjacent operating areas require political-condition monitoring.",
            "political",
            severity=0.69,
            confidence=0.6,
            status="monitor",
            freshness="analyst-maintained",
            evidence=[
                {
                    "label": "Macro context",
                    "url": "https://www.worldbank.org/en/publication/macro-poverty-outlook/mpo_eca",
                    "excerpt": "Country and regional macro context informs exposure monitoring.",
                },
            ],
            gaps="Needs live security, sanctions, and transport disruption feeds.",
        ),
    ]


def _source_coverage_features(
    sources: list[Source],
    topic_counts: Counter[str],
) -> list[dict[str, Any]]:
    """Support the module's public workflow by computing source coverage features.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        sources (list[Source]): Source registry entries available to the current
            pipeline step.
        topic_counts (Counter[str]): Counts of source coverage topics used to size or
            explain map layers.
    
    Returns:
        list[dict[str, Any]]: Result produced for the next pipeline step or caller.
    """
    coverage_points = [
        ("coverage-caspian-ecology", [50.55, 40.2], "Caspian Environmental Evidence", "ecology"),
        ("coverage-gas-flaring", [49.42, 40.12], "Gas Flaring Evidence", "gas_flaring"),
        ("coverage-regulatory", [49.86, 40.38], "Regulatory And ESG Evidence", "regulatory"),
    ]
    features = []
    for feature_id, coordinates, name, topic in coverage_points:
        count = topic_counts[topic]
        features.append(
            _point(
                feature_id,
                coordinates,
                name,
                f"{count} enabled source(s) in the crawler registry mention this topic.",
                "coverage",
                source_count=count,
                coverage_score=min(1.0, count / max(1, len(sources) * 0.25)),
                confidence=0.7 if count else 0.35,
                status="covered" if count else "gap",
                freshness="source registry derived",
                evidence=[
                    {
                        "label": "Crawler source registry",
                        "url": "data/sources.csv",
                        "excerpt": "Coverage is counted from enabled registry metadata tags and notes.",
                    },
                ],
                gaps="Coverage does not mean each source has been fetched in the current run.",
            )
        )
    return features


def _claim_features(
    claims: list[Claim],
    trust_scores: list[TrustScore],
    documents: list[FetchedDocument],
    sources: list[Source],
) -> list[dict[str, Any]]:
    """Support the module's public workflow by computing claim features.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        claims (list[Claim]): Claim records extracted from cleaned and redacted
            documents.
        trust_scores (list[TrustScore]): Trust score records keyed to extracted claims.
        documents (list[FetchedDocument]): Fetched or extracted documents available to
            the current pipeline step.
        sources (list[Source]): Source registry entries available to the current
            pipeline step.
    
    Returns:
        list[dict[str, Any]]: Result produced for the next pipeline step or caller.
    """
    score_by_claim = {score.claim_id: score for score in trust_scores}
    doc_by_id = {document.document_id: document for document in documents}
    source_by_id = {source.source_id: source for source in sources}
    positions = {
        "environmental_risk": [49.56, 40.12],
        "governance_risk": [49.86, 40.38],
        "labor_human_rights_risk": [49.75, 40.42],
        "operational_context": [50.08, 40.28],
    }
    features = []
    for index, claim in enumerate(claims[:20], start=1):
        document = doc_by_id.get(claim.document_id)
        source = source_by_id.get(document.source_id) if document else None
        score = score_by_claim.get(claim.claim_id)
        coordinates = positions.get(claim.claim_type, [49.86 + index * 0.015, 40.38])
        confidence = score.final_score if score and score.final_score is not None else claim.confidence
        agreement_status = claim.metadata.get("corroboration_status", "unclustered")
        agreement_summary = claim.metadata.get(
            "corroboration_summary",
            "No corroboration cluster is available for this claim.",
        )
        features.append(
            _point(
                f"claim-{index}-{claim.claim_id}",
                coordinates,
                f"Claim: {claim.claim_type.replace('_', ' ')}",
                claim.claim_text[:180],
                "claim",
                claim_id=claim.claim_id,
                document_id=claim.document_id,
                source_id=document.source_id if document else None,
                confidence=confidence or 0.4,
                status="extracted",
                agreement_status=agreement_status,
                agreement_summary=agreement_summary,
                corroborating_source_count=claim.metadata.get(
                    "corroborating_source_count",
                    0,
                ),
                independent_publisher_count=claim.metadata.get(
                    "independent_publisher_count",
                    0,
                ),
                conflicting_claim_ids=claim.metadata.get("conflicting_claim_ids", []),
                freshness="pipeline claim",
                evidence=[
                    {
                        "label": source.name if source else "Pipeline document",
                        "url": document.url if document else "#",
                        "excerpt": claim.evidence_excerpt or claim.claim_text,
                    },
                ],
                gaps=(
                    f"{agreement_summary} Automated claim extraction requires "
                    "analyst validation."
                ),
            )
        )
    return features


def _source_counts_by_topic(sources: list[Source]) -> Counter[str]:
    """Support the module's public workflow by computing source counts by topic.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        sources (list[Source]): Source registry entries available to the current
            pipeline step.
    
    Returns:
        Counter[str]: Result produced for the next pipeline step or caller.
    """
    counter: Counter[str] = Counter()
    for source in sources:
        text = " ".join(
            [
                source.name,
                source.notes,
                " ".join(source.metadata.get("domain_tags", [])),
                str(source.metadata.get("country", "")),
            ]
        ).casefold()
        for topic in ("gas_flaring", "oil_pollution", "oil_spills", "ecology", "regulatory"):
            needles = {topic, topic.replace("_", " ")}
            if topic == "regulatory":
                needles.update({"regulator", "compliance", "esg", "disclosure"})
            if any(needle in text for needle in needles):
                counter[topic] += 1
    return counter


def _point(
    feature_id: str,
    coordinates: list[float],
    name: str,
    summary: str,
    layer: str,
    **properties: Any,
) -> dict[str, Any]:
    """Support the module's public workflow by computing point.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        feature_id (str): Value named ``feature_id`` supplied by the caller for this
            pipeline step.
        coordinates (list[float]): Value named ``coordinates`` supplied by the caller
            for this pipeline step.
        name (str): Value named ``name`` supplied by the caller for this pipeline step.
        summary (str): Value named ``summary`` supplied by the caller for this pipeline
            step.
        layer (str): Value named ``layer`` supplied by the caller for this pipeline
            step.
        properties (Any): Value named ``properties`` supplied by the caller for this
            pipeline step.
    
    Returns:
        dict[str, Any]: Dictionary response that FastAPI serializes to JSON for the
            frontend or caller.
    """
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {
            "id": feature_id,
            "name": name,
            "summary": summary,
            "layer": layer,
            **properties,
        },
    }


def _polygon(
    feature_id: str,
    coordinates: list[list[float]],
    name: str,
    summary: str,
    layer: str,
    **properties: Any,
) -> dict[str, Any]:
    """Support the module's public workflow by computing polygon.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        feature_id (str): Value named ``feature_id`` supplied by the caller for this
            pipeline step.
        coordinates (list[list[float]]): Value named ``coordinates`` supplied by the
            caller for this pipeline step.
        name (str): Value named ``name`` supplied by the caller for this pipeline step.
        summary (str): Value named ``summary`` supplied by the caller for this pipeline
            step.
        layer (str): Value named ``layer`` supplied by the caller for this pipeline
            step.
        properties (Any): Value named ``properties`` supplied by the caller for this
            pipeline step.
    
    Returns:
        dict[str, Any]: Dictionary response that FastAPI serializes to JSON for the
            frontend or caller.
    """
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
        "properties": {
            "id": feature_id,
            "name": name,
            "summary": summary,
            "layer": layer,
            **properties,
        },
    }
