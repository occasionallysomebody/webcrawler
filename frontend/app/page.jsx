"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import {
  AlertTriangle,
  Braces,
  CheckCircle2,
  Database,
  Download,
  Filter,
  Layers,
  RefreshCw,
  ShieldCheck
} from "lucide-react";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api/crawler").replace(/\/$/, "");
const ANALYST_ID = process.env.NEXT_PUBLIC_ANALYST_ID || "local-analyst";
const BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const LAYER_COLORS = {
  opportunity: "#1f73d1",
  environmental: "#bf2e2e",
  political: "#a46100",
  coverage: "#147d64",
  claim: "#6b55c8"
};

export default function Home() {
  const mapNode = useRef(null);
  const mapRef = useRef(null);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [summary, setSummary] = useState(null);
  const [mapData, setMapData] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);
  const [claimType, setClaimType] = useState("");
  const [minTrust, setMinTrust] = useState("0.4");
  const [layerState, setLayerState] = useState({
    coverage: true,
    claim: true,
    opportunity: true,
    environmental: true,
    political: true
  });
  const [status, setStatus] = useState("Loading runs");
  const [error, setError] = useState("");
  const [exportStatus, setExportStatus] = useState("");

  const features = mapData?.features?.features || [];
  const claims = useMemo(
    () => features.filter((feature) => feature.properties.layer === "claim"),
    [features]
  );
  const coverage = useMemo(
    () => features.filter((feature) => feature.properties.layer === "coverage"),
    [features]
  );

  useEffect(() => {
    loadRuns();
  }, []);

  useEffect(() => {
    if (!selectedRun) return;
    loadRunData(selectedRun);
  }, [selectedRun, claimType, minTrust]);

  useEffect(() => {
    if (!mapNode.current || mapRef.current || !mapData) return;
    const map = new maplibregl.Map({
      container: mapNode.current,
      style: BASEMAP_STYLE,
      center: mapData.center,
      zoom: mapData.zoom,
      attributionControl: true
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.on("load", () => {
      map.resize();
      installMapLayers(map);
      syncMapData(map, features);
      syncLayerVisibility(map, layerState);
    });
    requestAnimationFrame(() => map.resize());
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [mapData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    syncMapData(map, features);
    syncLayerVisibility(map, layerState);
  }, [features, layerState]);

  async function loadRuns() {
    try {
      setError("");
      const response = await apiFetch("/runs");
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const payload = await response.json();
      const sortedRuns = [...payload.runs].sort(
        (a, b) => (b.claims_extracted || 0) - (a.claims_extracted || 0)
      );
      setRuns(sortedRuns);
      setSelectedRun(sortedRuns[0]?.run_id || "");
      setStatus(sortedRuns.length ? "Connected" : "No runs available");
    } catch (loadError) {
      setError(loadError.message);
      setStatus("API unavailable");
    }
  }

  async function loadRunData(runId) {
    const params = new URLSearchParams();
    if (claimType) params.set("claim_type", claimType);
    if (minTrust) params.set("min_trust", minTrust);
    try {
      setError("");
      const [summaryResponse, mapResponse] = await Promise.all([
        apiFetch(`/runs/${encodeURIComponent(runId)}/summary`),
        apiFetch(`/runs/${encodeURIComponent(runId)}/map-data?${params}`)
      ]);
      if (!summaryResponse.ok || !mapResponse.ok) {
        throw new Error("Run data request failed");
      }
      const nextSummary = await summaryResponse.json();
      const nextMapData = await mapResponse.json();
      setSummary(nextSummary);
      setMapData(nextMapData);
      setSelectedFeature(nextMapData.features.features[0] || null);
      setStatus("Connected");
      setExportStatus("");
      void sendAuditEvent("run_selected", {
        run_id: runId,
        metadata: { claim_type: claimType || "all", min_trust: minTrust || "none" }
      });
    } catch (loadError) {
      setError(loadError.message);
      setStatus("API error");
    }
  }

  function installMapLayers(map) {
    for (const layer of ["environmental", "political", "coverage", "opportunity", "claim"]) {
      if (!map.getSource(layer)) {
        map.addSource(layer, emptyFeatureCollection());
      }
    }
    for (const layer of ["environmental", "political"]) {
      map.addLayer({
        id: `${layer}-fill`,
        type: "fill",
        source: layer,
        paint: {
          "fill-color": LAYER_COLORS[layer],
          "fill-opacity": 0.18
        }
      });
      map.addLayer({
        id: `${layer}-outline`,
        type: "line",
        source: layer,
        paint: {
          "line-color": LAYER_COLORS[layer],
          "line-width": 1.5,
          "line-opacity": 0.72
        }
      });
    }
    map.addLayer({
      id: "coverage-circle",
      type: "circle",
      source: "coverage",
      paint: {
        "circle-color": LAYER_COLORS.coverage,
        "circle-radius": ["interpolate", ["linear"], ["get", "source_count"], 1, 7, 12, 22],
        "circle-opacity": 0.32,
        "circle-stroke-color": LAYER_COLORS.coverage,
        "circle-stroke-width": 1
      }
    });
    map.addLayer({
      id: "opportunity-circle",
      type: "circle",
      source: "opportunity",
      paint: {
        "circle-color": LAYER_COLORS.opportunity,
        "circle-radius": ["interpolate", ["linear"], ["get", "value_index"], 50, 10, 95, 28],
        "circle-opacity": 0.72,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2
      }
    });
    map.addLayer({
      id: "claim-circle",
      type: "circle",
      source: "claim",
      paint: {
        "circle-color": LAYER_COLORS.claim,
        "circle-radius": 7,
        "circle-opacity": 0.74,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5
      }
    });
    for (const id of [
      "environmental-fill",
      "political-fill",
      "coverage-circle",
      "opportunity-circle",
      "claim-circle"
    ]) {
      map.on("click", id, (event) => {
        const feature = event.features?.[0];
        if (feature) setSelectedFeature(feature);
      });
      map.on("mouseenter", id, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", id, () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }

  function selectFeature(feature) {
    setSelectedFeature(feature);
    setExportStatus("");
    const props = feature?.properties || {};
    if (props.layer === "claim") {
      void sendAuditEvent("evidence_selected", {
        run_id: selectedRun,
        claim_id: props.claim_id,
        document_id: props.document_id,
        source_id: props.source_id,
        metadata: { feature_id: props.id, layer: props.layer }
      });
    }
    const map = mapRef.current;
    if (!map || feature.geometry.type !== "Point") return;
    map.easeTo({ center: feature.geometry.coordinates, zoom: Math.max(map.getZoom(), 8) });
  }

  async function sendAuditEvent(eventType, details = {}) {
    try {
      await apiFetch("/audit-events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, ...details })
      });
    } catch {
      return null;
    }
    return null;
  }

  async function exportEvidence() {
    if (!selectedRun || !selectedFeature) return;
    const claimId = selectedProps.claim_id;
    const query = claimId ? `?claim_id=${encodeURIComponent(claimId)}` : "";
    try {
      setExportStatus("Exporting");
      const response = await apiFetch(
        `/runs/${encodeURIComponent(selectedRun)}/evidence-export${query}`
      );
      if (!response.ok) throw new Error(`Export failed with ${response.status}`);
      const payload = await response.json();
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json"
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${selectedRun}-evidence${claimId ? `-${claimId}` : ""}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setExportStatus("Exported");
    } catch (exportError) {
      setExportStatus(exportError.message);
    }
  }

  const selectedProps = selectedFeature?.properties || {};
  const evidence = selectedProps.evidence || [];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Azerbaijan Energy Intelligence</h1>
          <p>API-backed analyst map for source coverage, extracted claims, and evidence review.</p>
        </div>
        <div className="top-actions">
          <StatusPill status={status} error={error} />
          <button className="icon-button" onClick={loadRuns} title="Refresh runs">
            <RefreshCw size={18} />
            Refresh
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="left-panel">
          <section className="panel-section">
            <h2>Run Control</h2>
            <label className="field">
              <span>Run</span>
              <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.run_id}
                  </option>
                ))}
              </select>
            </label>
            <div className="summary-grid">
              <Metric label="Sources" value={summary?.sources_loaded || 0} />
              <Metric label="Fetched" value={summary?.documents_fetched || 0} />
              <Metric label="Claims" value={summary?.claims_extracted || 0} />
              <Metric label="Retries" value={summary?.retry_candidates || 0} />
            </div>
          </section>

          <section className="panel-section">
            <h2><Filter size={15} /> Filters</h2>
            <label className="field">
              <span>Claim type</span>
              <select value={claimType} onChange={(event) => setClaimType(event.target.value)}>
                <option value="">All claim types</option>
                <option value="environmental_risk">Environmental risk</option>
                <option value="operational_context">Operational context</option>
                <option value="labor_human_rights_risk">Labor / human rights</option>
                <option value="governance_risk">Governance risk</option>
              </select>
            </label>
            <label className="field">
              <span>Minimum trust</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={minTrust}
                onChange={(event) => setMinTrust(event.target.value)}
              />
              <strong>{Math.round(Number(minTrust) * 100)}%</strong>
            </label>
          </section>

          <section className="panel-section">
            <h2><Layers size={15} /> Layers</h2>
            {Object.keys(layerState).map((layer) => (
              <label className="toggle" key={layer}>
                <input
                  type="checkbox"
                  checked={layerState[layer]}
                  onChange={() => setLayerState((current) => ({ ...current, [layer]: !current[layer] }))}
                />
                <span style={{ background: LAYER_COLORS[layer] }} />
                {layer.replace("_", " ")}
              </label>
            ))}
          </section>

          <section className="panel-section list-section">
            <h2><Database size={15} /> Live Claims</h2>
            <div className="feature-list">
              {claims.slice(0, 24).map((feature) => (
                <button key={feature.properties.id} onClick={() => selectFeature(feature)}>
                  <span className="dot" />
                  <span>
                    <strong>{feature.properties.name}</strong>
                    <small>{feature.properties.summary}</small>
                  </span>
                  <em>{scoreText(feature)}</em>
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section className="map-area">
          <div ref={mapNode} className="map" />
          {!mapData || error ? (
            <div className="map-empty">
              <span>{error ? `Map unavailable: ${error}` : "Loading map data..."}</span>
            </div>
          ) : null}
          <div className="map-footer">
            <ShieldCheck size={16} />
            <span>{coverage.length} coverage markers</span>
            <span>{claims.length} filtered claim markers</span>
          </div>
        </section>

        <aside className="right-panel">
          <section className="panel-section detail-section">
            <h2>Evidence Ledger</h2>
            {selectedFeature ? (
              <>
                <h3>{selectedProps.name}</h3>
                <div className="tag-row">
                  {[selectedProps.layer, selectedProps.status, selectedProps.agreement_status].filter(Boolean).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                <p className="detail-summary">{selectedProps.summary}</p>
                <p className="muted">Confidence: {scoreText(selectedFeature) || "unscored"}</p>
                <div className="detail-actions">
                  <button className="icon-button" onClick={exportEvidence}>
                    <Download size={16} />
                    Export Evidence
                  </button>
                  {exportStatus ? <span>{exportStatus}</span> : null}
                </div>
                <div className="evidence-list">
                  {evidence.map((item, index) => (
                    <article key={`${item.url}-${index}`}>
                      <strong>{item.label}</strong>
                      <p>{item.excerpt || "No excerpt supplied."}</p>
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.url}
                      </a>
                    </article>
                  ))}
                </div>
                <div className="gap-box">
                  <AlertTriangle size={16} />
                  <span>{selectedProps.gaps || "Analyst validation required."}</span>
                </div>
              </>
            ) : (
              <p className="muted">Select a marker or claim to inspect evidence.</p>
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function StatusPill({ status, error }) {
  const ok = status === "Connected";
  return (
    <div className={`status-pill ${ok ? "ok" : "warn"}`}>
      {ok ? <CheckCircle2 size={16} /> : <Braces size={16} />}
      <span>{error || status}</span>
    </div>
  );
}

function scoreText(feature) {
  const value = feature?.properties?.confidence ?? feature?.properties?.score ?? feature?.properties?.coverage_score;
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "";
}

function syncMapData(map, features) {
  for (const layer of ["environmental", "political", "coverage", "opportunity", "claim"]) {
    const source = map.getSource(layer);
    if (source) {
      source.setData({
        type: "FeatureCollection",
        features: features.filter((feature) => feature.properties.layer === layer)
      });
    }
  }
}

function syncLayerVisibility(map, layerState) {
  const layerIds = {
    opportunity: ["opportunity-circle"],
    environmental: ["environmental-fill", "environmental-outline"],
    political: ["political-fill", "political-outline"],
    coverage: ["coverage-circle"],
    claim: ["claim-circle"]
  };
  for (const [layer, ids] of Object.entries(layerIds)) {
    const visibility = layerState[layer] ? "visible" : "none";
    ids.forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
    });
  }
}

function emptyFeatureCollection() {
  return { type: "geojson", data: { type: "FeatureCollection", features: [] } };
}

function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Analyst-Id", ANALYST_ID);
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store"
  });
}
