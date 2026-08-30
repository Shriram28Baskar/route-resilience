"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, WMSTileLayer, CircleMarker, Popup, Marker, useMapEvents, GeoJSON } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { centralityColor, findNearestNodeId } from "@/lib/utils";
import type { CriticalityResponse, HospitalAccessibility, RouteResponse, EquityResponse, EmergencyServicesResponse, AccessibilityImpactResponse } from "@/lib/api";

// Premium deep-tech palette for catchment zones — cohesive, glowing, readable on dark maps
const CATCHMENT_COLORS = [
  "#06B6D4",  // Cyan (Camp 1)
  "#8B5CF6",  // Violet (Camp 2)
  "#F59E0B",  // Amber (Camp 3)
  "#10B981",  // Emerald (Camp 4)
  "#E11D48",  // Rose (Camp 5)
  "#3B82F6",  // Blue (Camp 6)
  "#F97316",  // Orange (Camp 7)
  "#A78BFA",  // Lavender (Camp 8)
  "#34D399",  // Mint (Camp 9)
  "#FBBF24",  // Gold (Camp 10)
];

interface RoadMapProps {
  centrality: CriticalityResponse | null;
  hospitals: HospitalAccessibility | null;
  emergencyServices?: EmergencyServicesResponse | null;
  equity: EquityResponse | null;
  activeLayer: "centrality" | "hospitals" | "topology" | "route" | "simulate" | "equity" | "emergency" | "impact";
  graphGeojson: GeoJSON.FeatureCollection | null;
  routeResult?: RouteResponse | null;
  srcNodeId?: string;
  tgtNodeId?: string;
  selectedNodes?: string[];
  onMapClick?: (nodeId: string) => void;
  floodNodes?: string[];
  reliefCamps?: Array<{ id: string; lat: number; lng: number; node_count?: number; population_estimate?: number }>;
  reliefCatchment?: Record<string, number>;
  cascadeSteps?: any[];
  activeRoute?: string;
  impactData?: AccessibilityImpactResponse | null;
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

export default function RoadMap({ 
  centrality, 
  hospitals, 
  equity, 
  activeLayer, 
  graphGeojson, 
  routeResult, 
  srcNodeId, 
  tgtNodeId, 
  selectedNodes, 
  onMapClick, 
  floodNodes, 
  reliefCamps, 
  reliefCatchment,
  cascadeSteps,
  activeRoute = "optimal",
  emergencyServices,
  impactData,
}: RoadMapProps) {
  const [theme, setTheme] = useState<"dark" | "light" | "satellite" | "bhuvan">("dark");

  const tileUrls = {
    dark: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    light: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    satellite: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    bhuvan: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
  };

  const attributions = {
    dark: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
    light: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
    satellite: 'Tiles &copy; Esri &mdash; World Imagery',
    bhuvan: 'Esri World Topo Map | ISRO NNRMS Terrain Analysis &copy; <a href="https://bhuvan.nrsc.gov.in">NRSC/ISRO</a>'
  };

  // ISRO mode: classify roads by highway type → colour-coded criticality tier
  const getBhuvanRoadStyle = (feature: any) => {
    const hw = feature?.properties?.highway || "";
    if (["motorway", "motorway_link", "trunk", "trunk_link"].includes(hw))
      return { color: "#E11D48", weight: 3, opacity: 0.9 };        // CRITICAL – deep rose
    if (["primary", "primary_link"].includes(hw))
      return { color: "#F97316", weight: 2.5, opacity: 0.85 };     // HIGH – burnt orange
    if (["secondary", "secondary_link"].includes(hw))
      return { color: "#F59E0B", weight: 2, opacity: 0.8 };        // MEDIUM – amber
    if (["tertiary", "tertiary_link"].includes(hw))
      return { color: "#06B6D4", weight: 1.5, opacity: 0.7 };      // LOW – cyan
    return { color: "#A855F7", weight: 1, opacity: 0.45 };         // LOCAL – purple
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
          url={
            theme === "satellite" || theme === "bhuvan" 
              ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              : theme === "dark"
                ? "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png"
                : "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png"
          }
          attribution={theme === "satellite" || theme === "bhuvan" ? attributions[theme] : '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; OpenStreetMap'}
          maxZoom={20}
          className=""
        />

        {/* Standard Modes: Dark / Light / Satellite — with optional catchment zone coloring */}
        {roadLines && theme !== "bhuvan" && (
          <GeoJSON
            key={String(roadLines.features.length) + theme + (reliefCatchment ? Object.keys(reliefCatchment).length : 0)}
            data={roadLines as any}
            style={(feature) => {
              if (reliefCatchment && feature?.properties) {
                // Try to find a catchment assignment for either endpoint of the road segment
                const srcId = feature.properties.source;
                const tgtId = feature.properties.target;
                const clusterIdx = reliefCatchment[srcId] ?? reliefCatchment[tgtId];
                if (clusterIdx !== undefined) {
                  const color = CATCHMENT_COLORS[clusterIdx % CATCHMENT_COLORS.length];
                  return { color, weight: 2, opacity: 0.75 };
                }
              }
              return {
                color: theme === "dark"
                  ? "rgba(168, 85, 247, 0.55)"   // purple glow on dark
                  : theme === "light"
                  ? "rgba(30, 41, 59, 0.25)"     // slate on light
                  : "rgba(148, 163, 184, 0.45)", // muted slate on satellite
                weight: theme === "dark" ? 1.5 : 1.2,
                opacity: 1,
              };
            }}
          />
        )}

        {/* ISRO Mode: Roads coloured by highway criticality tier */}
        {roadLines && theme === "bhuvan" && (
          <GeoJSON
            key={String(roadLines.features.length) + "bhuvan"}
            data={roadLines as any}
            style={(feature) => getBhuvanRoadStyle(feature)}
          />
        )}

        {/* Selected nodes for ablation/cascade */}
        {selectedNodes && selectedNodes.length > 0 && graphGeojson && (
          <SelectedNodesLayer selectedNodes={selectedNodes} graphGeojson={graphGeojson} />
        )}

        {/* Flood Simulation Layer */}
        {floodNodes && floodNodes.length > 0 && graphGeojson && (
          <FloodLayer floodNodes={floodNodes} graphGeojson={graphGeojson} />
        )}

        {/* Relief Camps Layer */}
        {reliefCamps && reliefCamps.length > 0 && (
          <ReliefCampLayer reliefCamps={reliefCamps} />
        )}

        {(activeLayer === "centrality" || activeLayer === "simulate") && centrality && (
          <CentralityLayer centrality={centrality} />
        )}

        {activeLayer === "centrality" && centrality && (
          <ArticulationLayer centrality={centrality} graphGeojson={graphGeojson} />
        )}

        {activeLayer === "hospitals" && hospitals && (
          <HospitalLayer hospitals={hospitals} />
        )}

        {activeLayer === "emergency" && emergencyServices && (
          <EmergencyLayer emergencyServices={emergencyServices} graphGeojson={graphGeojson} />
        )}

        {activeLayer === "equity" && equity && (
          <EquityLayer equity={equity} />
        )}

        {cascadeSteps && cascadeSteps.length > 0 && graphGeojson && (
          <CascadeLayer cascadeSteps={cascadeSteps} graphGeojson={graphGeojson} />
        )}

        {activeLayer === "topology" && graphGeojson && (
          <TopologyLayer graphGeojson={graphGeojson} />
        )}

        {/* Accessibility Impact Layer */}
        {activeLayer === "impact" && impactData && graphGeojson && (
          <ImpactLayer impactData={impactData} graphGeojson={graphGeojson} />
        )}

        {/* Route visualization - RENDERS LAST (ON TOP) */}
        {routeResult && <RouteLayer routeResult={routeResult} activeRoute={activeRoute} />}

        {/* Source/Target markers */}
        {srcNodeId && graphGeojson && <NodeMarker nodeId={srcNodeId} label="S" color="#00E5B4" graphGeojson={graphGeojson} />}
        {tgtNodeId && graphGeojson && <NodeMarker nodeId={tgtNodeId} label="T" color="#FFB400" graphGeojson={graphGeojson} />}
      </MapContainer>

      {/* Floating Theme Switcher */}
      <div style={{ position: "absolute", top: "12px", right: "12px", zIndex: 1000 }} className="bg-[#111827]/90 border border-white/10 rounded-md p-1 flex gap-1 shadow-lg backdrop-blur-sm">
        {(["dark", "light"] as const).map((t) => (
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
        <button
          onClick={() => setTheme("bhuvan")}
          className={`px-2 py-1 rounded text-[10px] font-semibold uppercase tracking-wider transition-all duration-200 ${
            theme === "bhuvan"
              ? "bg-[#FF9900] text-[#0B0F1A] shadow-sm"
              : "text-gray-400 hover:text-white hover:bg-white/5"
          }`}
        >
          ISRO
        </button>
      </div>

      {/* ISRO Mode: Road Criticality Legend */}
      {theme === 'bhuvan' && (
        <div style={{
          position: 'absolute', bottom: '24px', left: '12px', zIndex: 1000,
          background: 'rgba(11,15,26,0.92)', border: '1px solid rgba(255,153,0,0.5)',
          borderRadius: '8px', padding: '10px 12px', minWidth: '210px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.6)'
        }}>
          <div style={{ fontSize: '10px', color: '#FF9900', fontWeight: 800, letterSpacing: '0.08em', marginBottom: '8px' }}>
            🛰️ ISRO NNRMS — Criticality
          </div>
          
          <div style={{ fontSize: '9px', color: '#9CA3AF', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Road Infrastructure (Lines)</div>
          {[
            { color: '#E11D48', label: 'Motorway / Expressway', tier: 'CRITICAL' },
            { color: '#F97316', label: 'Primary Artery', tier: 'HIGH' },
            { color: '#F59E0B', label: 'Secondary Road', tier: 'MEDIUM' },
            { color: '#06B6D4', label: 'Tertiary Road', tier: 'LOW' },
            { color: '#6366F1', label: 'Local / Residential', tier: 'MINIMAL' },
          ].map(({ color, label, tier }) => (
            <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <div style={{ width: '24px', height: '3px', background: color, borderRadius: '2px', flexShrink: 0 }} />
              <span style={{ fontSize: '9px', color: '#D1D5DB' }}>{label}</span>
              <span style={{ fontSize: '8px', color: color, fontWeight: 700, marginLeft: 'auto' }}>{tier}</span>
            </div>
          ))}

          <div style={{ fontSize: '9px', color: '#9CA3AF', margin: '8px 0 4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Network Chokepoints (Spots)</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'rgba(255,0,0,0.7)', marginLeft: '6px' }} />
            <span style={{ fontSize: '9px', color: '#D1D5DB' }}>High Vulnerability Intersections</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'rgba(255,165,0,0.6)', marginLeft: '6px' }} />
            <span style={{ fontSize: '9px', color: '#D1D5DB' }}>Medium Vulnerability Nodes</span>
          </div>

          <div style={{ fontSize: '8px', color: '#6B7280', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '5px' }}>
            Lines: OSM Highway | Spots: Betweenness Centrality
          </div>
        </div>
      )}

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
    html: `<div style="width:12px;height:12px;background:#E11D48;border-radius:50%;border:2px solid rgba(255,255,255,0.8);box-shadow:0 0 10px rgba(225,29,72,0.8);"></div>`,
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
    html: `<div style="width:24px;height:24px;background:#06B6D4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:bold;color:#0B0F1A;border:2px solid rgba(255,255,255,0.9);box-shadow:0 0 12px rgba(6,182,212,0.7);">H</div>`,
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

// ── Emergency Layer ───────────────────────────────────────────────────────────

function EmergencyLayer({ emergencyServices, graphGeojson }: { emergencyServices: EmergencyServicesResponse, graphGeojson: GeoJSON.FeatureCollection | null }) {
  return (
    <>
      {emergencyServices.facilities.map((fac, idx) => {
        const isFireStation = fac.amenity === "fire_station";
        const color = isFireStation ? "#FF8C00" : "#0099FF";
        const glowColor = isFireStation ? "rgba(255,140,0,0.6)" : "rgba(0,153,255,0.6)";
        const label = isFireStation ? "🚒 FIRE" : "🚔 POLICE";
        return (
          <CircleMarker
            key={idx}
            center={[fac.lat, fac.lon]}
            radius={isFireStation ? 10 : 8}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.85,
              weight: 2,
            }}
          >
            <Popup>
              <div style={{ fontFamily: "monospace", fontSize: "12px", minWidth: "160px" }}>
                <div style={{ fontWeight: 700, color, marginBottom: "4px" }}>{label}</div>
                <div style={{ fontWeight: 600, color: "#111827" }}>{fac.name || "Emergency Station"}</div>
                <div style={{ color: "#6B7280", fontSize: "10px", textTransform: "uppercase", marginTop: "2px" }}>
                  {fac.amenity.replace("_", " ")}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
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

import { GeoJSON as LeafletGeoJSON } from "react-leaflet";

function TopologyLayer({ graphGeojson }: { graphGeojson: GeoJSON.FeatureCollection | null }) {
  if (!graphGeojson) return null;

  // Only render true intersections (degree >= 3) to keep the map clean and impressive
  const intersectionNodes = {
    type: "FeatureCollection",
    features: graphGeojson.features.filter((f) => 
      f.geometry.type === "Point" && (f.properties?.degree || 0) >= 3
    )
  };

  return (
    <LeafletGeoJSON
      key="topology-nodes-clickable"
      data={intersectionNodes as any}
      pointToLayer={(_, latlng) => {
        return L.circleMarker(latlng, {
          radius: 1.5,
          color: "transparent",
          fillColor: "#818CF8",
          fillOpacity: 0.55,
          weight: 15,
        });
      }}
      onEachFeature={(feature, layer) => {
        if (feature.properties) {
          layer.bindPopup(`
            <div style="font-family: monospace; font-size: 12px; color: #111827;">
              <div style="font-weight: bold; color: #00E5B4; background: #111827; padding: 2px 4px; border-radius: 4px; display: inline-block; margin-bottom: 4px;">Major Intersection</div>
              <div><b>Node ID:</b> ${feature.properties.id}</div>
              <div><b>Connections:</b> ${feature.properties.degree} roads</div>
            </div>
          `);
        }
      }}
    />
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
          pathOptions={{ color: "#E11D48", fillColor: "#E11D48", fillOpacity: 0.75, weight: 2, className: "" }}
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

function RouteLayer({ routeResult, activeRoute }: { routeResult: any, activeRoute: string }) {
  let activeGeojson = routeResult.rerouted?.path_geojson;
  const alts = routeResult.rerouted?.alternatives || [];
  
  if (activeRoute === "alt1" && alts.length > 0) {
    activeGeojson = alts[0].path_geojson;
  } else if (activeRoute === "alt2" && alts.length > 1) {
    activeGeojson = alts[1].path_geojson;
  }

  console.log("RouteLayer rendering: activeRoute=", activeRoute, "hasGeojson=", !!activeGeojson);

  return (
    <>
      {routeResult.baseline?.path_geojson && (
        <GeoJSON
          key={`baseline-${routeResult.baseline.distance_m}`}
          data={routeResult.baseline.path_geojson}
          style={{ color: "#F59E0B", weight: 3, opacity: 0.5 }}
        />
      )}
      {activeGeojson && (
        <>
          {/* Soft dark drop-shadow/outline for separation */}
          <GeoJSON
            key={`active-route-bg-${activeRoute}`}
            data={activeGeojson}
            style={{ color: "#000000", weight: 10, opacity: 0.7 }}
          />
          {/* Solid bright white core — clean and universally readable */}
          <GeoJSON
            key={`active-route-fg-${activeRoute}`}
            data={activeGeojson}
            style={{ color: "#FFFFFF", weight: 4, opacity: 1.0 }}
          />
        </>
      )}
    </>
  );
}

function FloodLayer({ floodNodes, graphGeojson }: { floodNodes: string[], graphGeojson: GeoJSON.FeatureCollection }) {
  // Performance Fix: Convert to O(N) lookup instead of O(N*M) which was causing massive browser lag
  const floodSet = new Set(floodNodes);
  const nodes: { id: string, lat: number, lon: number }[] = [];
  
  if (graphGeojson?.features) {
    for (const f of graphGeojson.features) {
      if (f.geometry.type === "Point" && f.properties?.id && floodSet.has(f.properties.id)) {
        nodes.push({ 
          id: f.properties.id, 
          lat: f.geometry.coordinates[1], 
          lon: f.geometry.coordinates[0] 
        });
      }
    }
  }

  return (
    <>
      {nodes.map(n => (
        <CircleMarker
          key={`flood-${n.id}`}
          center={[n.lat, n.lon]}
          radius={5}
          pathOptions={{ color: "rgba(56,189,248,0.6)", fillColor: "#0EA5E9", fillOpacity: 0.65, weight: 1 }}
        >
          <Popup>Flooded Node: {n.id}</Popup>
        </CircleMarker>
      ))}
    </>
  );
}

function ReliefCampLayer({ reliefCamps }: { reliefCamps: Array<{ id: string; lat: number; lng: number }> }) {
  const campIcon = L.divIcon({
    html: `<div style="width:24px;height:24px;background:#8B5CF6;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;color:#fff;border:2px solid rgba(255,255,255,0.85);box-shadow:0 0 12px rgba(139,92,246,0.7);">⛺</div>`,
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

// ── Cascade Animation Layer ───────────────────────────────────────────────────

function CascadeLayer({ cascadeSteps, graphGeojson }: { cascadeSteps: any[], graphGeojson: GeoJSON.FeatureCollection }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  useEffect(() => {
    if (!cascadeSteps || cascadeSteps.length === 0) return;
    const interval = setInterval(() => {
      setCurrentStepIndex(prev => (prev + 1) % cascadeSteps.length);
    }, 1500);
    return () => clearInterval(interval);
  }, [cascadeSteps]);

  if (!cascadeSteps || cascadeSteps.length === 0) return null;

  const currentStep = cascadeSteps[currentStepIndex];
  
  const ablatedNodes = (currentStep.ablated || []).map((id: string) => {
    const f = graphGeojson.features.find((f: any) => f.properties?.id === id);
    if (!f || f.geometry.type !== "Point") return null;
    return { id, type: 'ablated', lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
  }).filter(Boolean);

  const stressedNodes = (currentStep.newly_stressed || []).map((n: any) => {
    const f = graphGeojson.features.find((f: any) => f.properties?.id === n.node_id);
    if (!f || f.geometry.type !== "Point") return null;
    return { id: n.node_id, type: 'stressed', lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
  }).filter(Boolean);

  const allNodes = [...ablatedNodes, ...stressedNodes] as { id: string, type: 'ablated' | 'stressed', lat: number, lon: number }[];

  const createPulseIcon = (type: 'ablated' | 'stressed') => {
    const color = type === 'ablated' ? '#E11D48' : '#F59E0B';
    return L.divIcon({
      html: `
        <div style="position: relative; width: 24px; height: 24px;">
          <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 50%; background: ${color}; opacity: 0.6; animation: cascade-pulse 1.5s infinite;"></div>
          <div style="position: absolute; top: 25%; left: 25%; width: 50%; height: 50%; border-radius: 50%; background: ${color}; border: 1px solid white;"></div>
        </div>
        <style>
          @keyframes cascade-pulse {
            0% { transform: scale(0.5); opacity: 0.8; }
            100% { transform: scale(2); opacity: 0; }
          }
        </style>
      `,
      className: "",
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
  };

  return (
    <>
      <div style={{ position: 'absolute', top: '12px', left: '50%', transform: 'translateX(-50%)', zIndex: 1000 }} className="bg-[#111827]/90 border border-white/10 rounded-md px-3 py-1 text-xs text-white shadow-lg backdrop-blur-sm flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-[#FFB400] animate-pulse"></span>
        <span>Cascade Step: <span className="text-[#FFB400] font-bold">{currentStep.iteration + 1}</span> / {cascadeSteps.length}</span>
      </div>
      {allNodes.map(n => (
        <Marker key={`${currentStepIndex}-${n.id}`} position={[n.lat, n.lon]} icon={createPulseIcon(n.type as any)}>
          <Popup>
            <div className="text-sm text-[#111827]">
              <div className="font-semibold">{n.type === 'ablated' ? 'Ablated Node' : 'Stressed Node'}</div>
              <div>Node: {n.id}</div>
              <div className="text-xs text-gray-500">Cascade Step: {currentStep.iteration + 1}</div>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
}

// ── Impact Layer ──────────────────────────────────────────────────────────────

function ImpactLayer({
  impactData,
  graphGeojson,
}: {
  impactData: AccessibilityImpactResponse;
  graphGeojson: GeoJSON.FeatureCollection;
}) {
  const lostSet = new Set(impactData.impact.nodes_lost_access);
  const degradedSet = new Set(impactData.impact.nodes_degraded);
  const hospitalNodeSet = new Set(impactData.hospital_node_ids);
  const ablatedSet = new Set(impactData.ablated_node_ids);

  // Build node position lookup from GeoJSON
  const nodePositions: Record<string, [number, number]> = {};
  graphGeojson.features.forEach((f) => {
    if (f.geometry.type === "Point") {
      const id = f.properties?.id || f.properties?.node_id;
      if (id) {
        const [lng, lat] = (f.geometry as any).coordinates;
        nodePositions[String(id)] = [lat, lng];
      }
    }
  });

  // Build alternative route GeoJSON if available
  const altRoute = impactData.best_alternative_route;
  const altRouteFeature =
    altRoute?.path_geojson ?? null;

  return (
    <>
      {/* Lost access nodes — RED */}
      {impactData.impact.nodes_lost_access.slice(0, 2000).map((nid) => {
        const pos = nodePositions[nid];
        if (!pos) return null;
        return (
          <CircleMarker
            key={`lost-${nid}`}
            center={pos}
            radius={3}
            pathOptions={{ color: "#FF4444", fillColor: "#FF4444", fillOpacity: 0.75, weight: 0 }}
          >
            <Popup>
              <div className="text-xs">
                <div className="font-semibold text-[#FF4444]">Lost 15-min Hospital Access</div>
                <div>Node: {nid}</div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}

      {/* Degraded access nodes — ORANGE */}
      {impactData.impact.nodes_degraded.slice(0, 2000).map((nid) => {
        const pos = nodePositions[nid];
        if (!pos) return null;
        return (
          <CircleMarker
            key={`deg-${nid}`}
            center={pos}
            radius={2.5}
            pathOptions={{ color: "#FFB400", fillColor: "#FFB400", fillOpacity: 0.65, weight: 0 }}
          >
            <Popup>
              <div className="text-xs">
                <div className="font-semibold text-[#FFB400]">Degraded Accessibility (&gt;50% slower)</div>
                <div>Node: {nid}</div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}

      {/* Hospital markers — TEAL */}
      {impactData.hospitals.map((h, i) => (
        <CircleMarker
          key={`hosp-${i}`}
          center={[h.lat, h.lon]}
          radius={8}
          pathOptions={{ color: "#00E5B4", fillColor: "#00E5B4", fillOpacity: 0.9, weight: 2 }}
        >
          <Popup>
            <div className="text-xs">
              <div className="font-semibold text-[#00E5B4]">🏥 {h.name || "Hospital"}</div>
              <div className="text-gray-500 capitalize">{h.amenity}</div>
            </div>
          </Popup>
        </CircleMarker>
      ))}

      {/* Alternative route — BLUE line */}
      {altRouteFeature && (
        <GeoJSON
          key="alt-route"
          data={altRouteFeature as any}
          style={() => ({
            color: "#3B82F6",
            weight: 4,
            opacity: 0.9,
            dashArray: "8 4",
          })}
        />
      )}
    </>
  );
}
