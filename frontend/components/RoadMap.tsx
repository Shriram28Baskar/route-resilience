"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Marker, useMapEvents, GeoJSON } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { centralityColor, findNearestNodeId } from "@/lib/utils";
import type { CriticalityResponse, HospitalAccessibility, RouteResponse, EquityResponse } from "@/lib/api";

interface RoadMapProps {
  centrality: CriticalityResponse | null;
  hospitals: HospitalAccessibility | null;
  equity: EquityResponse | null;
  activeLayer: "centrality" | "hospitals" | "topology" | "route" | "simulate" | "equity";
  graphGeojson: GeoJSON.FeatureCollection | null;
  routeResult?: RouteResponse | null;
  srcNodeId?: string;
  tgtNodeId?: string;
  selectedNodes?: string[];
  onMapClick?: (nodeId: string) => void;
  floodNodes?: string[];
  reliefCamps?: Array<{ id: string; lat: number; lng: number }>;
}

// Bengaluru AOI center
const MAP_CENTER: [number, number] = [12.955, 77.605];
const MAP_ZOOM = 13;

function MapEvents({ geojson, onMapClick }: { geojson: GeoJSON.FeatureCollection | null, onMapClick?: (id: string) => void }) {
  useMapEvents({
    click(e) {
      if (onMapClick && geojson) {
        const id = findNearestNodeId(e.latlng.lat, e.latlng.lng, geojson);
        if (id) onMapClick(id);
      }
    }
  });
  return null;
}

export default function RoadMap({ centrality, hospitals, equity, activeLayer, graphGeojson, routeResult, srcNodeId, tgtNodeId, selectedNodes, onMapClick, floodNodes, reliefCamps }: RoadMapProps) {
  const [theme, setTheme] = useState<"dark" | "light" | "satellite">("dark");

  const tileUrls = {
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    light: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    satellite: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
  };

  const attributions = {
    dark: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    light: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    satellite: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
  };

  const roadLines = graphGeojson
    ? {
        type: "FeatureCollection",
        features: graphGeojson.features.filter((f) => f.geometry.type === "LineString")
      }
    : null;

  return (
    <div style={{ height: "100%", width: "100%", position: "relative" }}>
      <MapContainer
        center={MAP_CENTER}
        zoom={MAP_ZOOM}
        style={{ height: "100%", width: "100%", background: theme === "light" ? "#F3F4F6" : "#0B0F1A" }}
        zoomControl={true}
      >
        <MapEvents geojson={graphGeojson} onMapClick={onMapClick} />
        
        <TileLayer
          key={theme}
          url={tileUrls[theme]}
          attribution={attributions[theme]}
          maxZoom={19}
        />

        {roadLines && (
          <GeoJSON
            key={String(roadLines.features.length) + theme}
            data={roadLines as any}
            style={() => ({
              color: theme === "dark" ? "rgba(255,255,255,0.12)" : theme === "light" ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.35)",
              weight: 1.5,
              opacity: 0.9,
            })}
          />
        )}

        {/* Selected nodes for ablation/cascade */}
        {selectedNodes && selectedNodes.length > 0 && graphGeojson && (
          <SelectedNodesLayer selectedNodes={selectedNodes} graphGeojson={graphGeojson} />
        )}

        {/* Route visualization */}
        {routeResult && <RouteLayer routeResult={routeResult} />}

        {/* Source/Target markers */}
        {srcNodeId && graphGeojson && <NodeMarker nodeId={srcNodeId} label="S" color="#00E5B4" graphGeojson={graphGeojson} />}
        {tgtNodeId && graphGeojson && <NodeMarker nodeId={tgtNodeId} label="T" color="#FFB400" graphGeojson={graphGeojson} />}

        {/* Flood Simulation Layer */}
        {floodNodes && floodNodes.length > 0 && graphGeojson && (
          <FloodLayer floodNodes={floodNodes} graphGeojson={graphGeojson} />
        )}

        {/* Relief Camps Layer */}
        {reliefCamps && reliefCamps.length > 0 && (
          <ReliefCampLayer reliefCamps={reliefCamps} />
        )}

        {activeLayer === "centrality" && centrality && (
          <CentralityLayer centrality={centrality} />
        )}

        {(activeLayer === "centrality" || activeLayer === "topology") && centrality && (
          <ArticulationLayer centrality={centrality} graphGeojson={graphGeojson} />
        )}

        {activeLayer === "hospitals" && hospitals && (
          <HospitalLayer hospitals={hospitals} />
        )}

        {activeLayer === "equity" && equity && (
          <EquityLayer equity={equity} />
        )}

        {(activeLayer === "topology" || activeLayer === "simulate") && centrality && (
          <TopologyLayer centrality={centrality} />
        )}
      </MapContainer>

      {/* Floating Theme Switcher */}
      <div style={{ position: "absolute", top: "12px", right: "12px", zIndex: 1000 }} className="bg-[#111827]/90 border border-white/10 rounded-md p-1 flex gap-1 shadow-lg backdrop-blur-sm">
        {(["dark", "light", "satellite"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTheme(t)}
            className={`px-2 py-1 rounded text-[10px] font-semibold uppercase tracking-wider transition-all duration-200 ${
              theme === t
                ? "bg-[#00E5B4] text-[#0B0F1A] shadow-sm"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Centrality Layer ─────────────────────────────────────────────────────────

function CentralityLayer({ centrality }: { centrality: CriticalityResponse }) {
  const allScores = centrality.betweenness;

  return (
    <>
      {Object.entries(allScores).map(([nodeId, score]) => {
        const gk = centrality.gatekeepers.find((g) => g.node_id === nodeId);
        if (!gk) return null;
        const color = centralityColor(score);
        const radius = 4 + score * 10;
        return (
          <CircleMarker
            key={nodeId}
            center={[gk.y, gk.x]}
            radius={radius}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.85,
              weight: score > 0.7 ? 2 : 1,
            }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-semibold">Node {nodeId}</div>
                <div>Betweenness: {(score * 100).toFixed(2)}%</div>
                <div>Closeness: {((centrality.closeness[nodeId] || 0) * 100).toFixed(2)}%</div>
                <div className="text-gray-400 text-xs">
                  {gk.y.toFixed(5)}, {gk.x.toFixed(5)}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

// ── Articulation Layer ────────────────────────────────────────────────────────

function ArticulationLayer({ centrality, graphGeojson }: { centrality: CriticalityResponse, graphGeojson: GeoJSON.FeatureCollection | null }) {
  if (!graphGeojson) return null;

  const warningIcon = L.divIcon({
    html: `<div style="width:12px;height:12px;background:#FF4444;border-radius:50%;border:2px solid #fff;box-shadow:0 2px 6px rgba(255, 68, 68, 0.6);"></div>`,
    className: "",
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });

  const nodes = centrality.articulation_points.map(id => {
    // Only show critical articulation points (betweenness centrality >= 0.01)
    const score = centrality.betweenness[id] || 0;
    if (score < 0.01) return null;

    const f = graphGeojson.features.find(f => f.properties?.id === id);
    if (!f || f.geometry.type !== "Point") return null;
    return { id, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
  }).filter(Boolean) as { id: string, lat: number, lon: number }[];

  return (
    <>
      {nodes.map(n => (
        <Marker key={`ap-${n.id}`} position={[n.lat, n.lon]} icon={warningIcon}>
          <Popup>
            <div className="text-sm">
              <div className="font-semibold text-[#FF4444]">Critical Articulation Point</div>
              <div>Node: {n.id}</div>
              <div className="text-xs text-gray-400">Removing this node partitions the network.</div>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}

// ── Hospital Layer ────────────────────────────────────────────────────────────

function HospitalLayer({ hospitals }: { hospitals: HospitalAccessibility }) {
  const hospitalIcon = L.divIcon({
    html: `<div style="width:24px;height:24px;background:#00E5B4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:bold;color:#0B0F1A;border:2px solid #fff;">H</div>`,
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });

  return (
    <>
      {hospitals.hospitals.map((h) => (
        <Marker key={h.osm_id} position={[h.lat, h.lon]} icon={hospitalIcon}>
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">{h.name}</div>
              <div className="text-gray-400 capitalize">{h.amenity}</div>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}

// ── Equity Layer ──────────────────────────────────────────────────────────────

import { Circle } from "react-leaflet";

function EquityLayer({ equity }: { equity: EquityResponse }) {
  return (
    <>
      {equity.deserts.map((d, i) => (
        <Circle
          key={`desert-${i}`}
          center={[d.lat, d.lon]}
          radius={d.radius}
          pathOptions={{ color: "transparent", fillColor: "#FF4444", fillOpacity: 0.2 }}
        >
          <Popup>
            <div className="text-sm font-semibold text-[#FF4444]">Healthcare Desert</div>
            <div className="text-xs text-gray-600 mt-1">Nearest facility is {(d.nearest_facility_distance_m / 1000).toFixed(1)}km away.</div>
          </Popup>
        </Circle>
      ))}
      {equity.vulnerable_clusters.map((c, i) => (
        <Circle
          key={`cluster-${i}`}
          center={[c.lat, c.lon]}
          radius={800}
          pathOptions={{ color: "#FFB400", dashArray: "4 4", fillColor: "transparent", weight: 2 }}
        >
          <Popup>
            <div className="text-sm font-semibold text-[#FFB400]">Vulnerable Population</div>
            <div className="text-xs text-gray-600 mt-1">Type: {c.type}</div>
            <div className="text-xs text-gray-600">Population: {c.population}</div>
            <div className="text-xs mt-1 font-semibold">Risk Level: {c.risk_level}</div>
          </Popup>
        </Circle>
      ))}
    </>
  );
}

// ── Topology Layer ────────────────────────────────────────────────────────────

function TopologyLayer({ centrality }: { centrality: CriticalityResponse }) {
  return (
    <>
      {centrality.gatekeepers.map((node) => (
        <CircleMarker
          key={node.node_id}
          center={[node.y, node.x]}
          radius={5}
          pathOptions={{ color: "#00E5B4", fillColor: "#00E5B4", fillOpacity: 0.6, weight: 1 }}
        >
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">Node {node.node_id}</div>
              <div>Centrality: {(node.score * 100).toFixed(2)}%</div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

// ── Selection & Routing Layers ──────────────────────────────────────────────

function SelectedNodesLayer({ selectedNodes, graphGeojson }: { selectedNodes: string[], graphGeojson: GeoJSON.FeatureCollection }) {
  const nodes = selectedNodes.map(id => {
    const f = graphGeojson.features.find(f => f.properties?.id === id);
    if (!f || f.geometry.type !== "Point") return null;
    return { id, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
  }).filter(Boolean) as { id: string, lat: number, lon: number }[];

  return (
    <>
      {nodes.map(n => (
        <CircleMarker
          key={n.id}
          center={[n.lat, n.lon]}
          radius={6}
          pathOptions={{ color: "#FF4444", fillColor: "#FF4444", fillOpacity: 0.8, weight: 2 }}
        >
          <Popup>Selected Node: {n.id}</Popup>
        </CircleMarker>
      ))}
    </>
  );
}

function NodeMarker({ nodeId, label, color, graphGeojson }: { nodeId: string, label: string, color: string, graphGeojson: GeoJSON.FeatureCollection }) {
  const f = graphGeojson.features.find(f => f.properties?.id === nodeId);
  if (!f || f.geometry.type !== "Point") return null;
  const [lon, lat] = f.geometry.coordinates;

  const icon = L.divIcon({
    html: `<div style="width:28px;height:28px;background:${color};border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:bold;color:#0B0F1A;border:3px solid #fff;box-shadow:0 4px 6px rgba(0,0,0,0.3);">${label}</div>`,
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

  return (
    <Marker position={[lat, lon]} icon={icon}>
      <Popup>{label === "S" ? "Source" : "Target"} Node: {nodeId}</Popup>
    </Marker>
  );
}

import { Polyline } from "react-leaflet";

function RouteLayer({ routeResult }: { routeResult: RouteResponse }) {
  return (
    <>
      {routeResult.baseline?.path_geojson && (
        <GeoJSON
          key={`baseline-${routeResult.baseline.distance_m}`}
          data={routeResult.baseline.path_geojson}
          style={{ color: "#00E5B4", weight: 5, opacity: 0.8 }}
        />
      )}
      {routeResult.rerouted?.path_geojson && (
        <GeoJSON
          key={`rerouted-${routeResult.rerouted.distance_m}`}
          data={routeResult.rerouted.path_geojson}
          style={{ color: "#FFB400", weight: 5, opacity: 0.8, dashArray: "10, 10" }}
        />
      )}
    </>
  );
}

function FloodLayer({ floodNodes, graphGeojson }: { floodNodes: string[], graphGeojson: GeoJSON.FeatureCollection }) {
  const nodes = floodNodes.map(id => {
    const f = graphGeojson.features.find(f => f.properties?.id === id);
    if (!f || f.geometry.type !== "Point") return null;
    return { id, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
  }).filter(Boolean) as { id: string, lat: number, lon: number }[];

  return (
    <>
      {nodes.map(n => (
        <CircleMarker
          key={`flood-${n.id}`}
          center={[n.lat, n.lon]}
          radius={5}
          pathOptions={{ color: "transparent", fillColor: "#0099FF", fillOpacity: 0.8 }}
        >
          <Popup>Flooded Node: {n.id}</Popup>
        </CircleMarker>
      ))}
    </>
  );
}

function ReliefCampLayer({ reliefCamps }: { reliefCamps: Array<{ id: string; lat: number; lng: number }> }) {
  const campIcon = L.divIcon({
    html: `<div style="width:24px;height:24px;background:#00E5B4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;color:#0B0F1A;border:2px solid #fff;">⛺</div>`,
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });

  return (
    <>
      {reliefCamps.map((c, i) => (
        <Marker key={`camp-${c.id}`} position={[c.lat, c.lng]} icon={campIcon}>
          <Popup>
            <div className="text-sm font-semibold">Relief Camp {i + 1}</div>
            <div className="text-xs text-gray-400">Optimal location for node {c.id}</div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}
