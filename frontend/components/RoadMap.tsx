"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, WMSTileLayer, CircleMarker, Popup, Marker, useMapEvents, GeoJSON } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { centralityColor, findNearestNodeId } from "@/lib/utils";
import type { CriticalityResponse, HospitalAccessibility, RouteResponse, EquityResponse, EmergencyServicesResponse } from "@/lib/api";

// Vibrant categorical color palette for catchment zones
const CATCHMENT_COLORS = [
  "#00E5B4",  // Teal (Camp 1)
  "#FFB400",  // Amber (Camp 2)
  "#FF2D6B",  // Rose (Camp 3)
  "#A855F7",  // Purple (Camp 4)
  "#3B82F6",  // Blue (Camp 5)
  "#F97316",  // Orange (Camp 6)
  "#10B981",  // Emerald (Camp 7)
  "#EC4899",  // Pink (Camp 8)
  "#14B8A6",  // Cyan-teal (Camp 9)
  "#F59E0B",  // Yellow (Camp 10)
];

interface RoadMapProps {
  centrality: CriticalityResponse | null;
  hospitals: HospitalAccessibility | null;
  emergencyServices?: EmergencyServicesResponse | null;
  equity: EquityResponse | null;
  activeLayer: "centrality" | "hospitals" | "topology" | "route" | "simulate" | "equity" | "emergency";
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
}: RoadMapProps) {
  const [theme, setTheme] = useState<"dark" | "light" | "satellite" | "bhuvan">("dark");

  const tileUrls = {
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    light: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    satellite: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    bhuvan: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
  };

  const attributions = {
    dark: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    light: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    satellite: 'Tiles &copy; Esri &mdash; World Imagery',
    bhuvan: 'Esri World Topo Map | ISRO NNRMS Terrain Analysis &copy; <a href="https://bhuvan.nrsc.gov.in">NRSC/ISRO</a>'
  };

  // ISRO mode: classify roads by highway type → colour-coded criticality tier
  const getBhuvanRoadStyle = (feature: any) => {
    const hw = feature?.properties?.highway || "";
    if (["motorway", "motorway_link", "trunk", "trunk_link"].includes(hw))
      return { color: "#FF2D2D", weight: 3.5, opacity: 1 };       // CRITICAL – red
    if (["primary", "primary_link"].includes(hw))
      return { color: "#FF8C00", weight: 2.5, opacity: 1 };        // HIGH – orange
    if (["secondary", "secondary_link"].includes(hw))
      return { color: "#FFE600", weight: 2, opacity: 1 };          // MEDIUM – yellow
    if (["tertiary", "tertiary_link"].includes(hw))
      return { color: "#00E5B4", weight: 1.5, opacity: 0.9 };      // LOW – teal
    return { color: "#00FF7F", weight: 1, opacity: 0.5 };          // LOCAL – green
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
                  return { color, weight: 2.5, opacity: 0.85 };
                }
              }
              return {
                color: theme === "dark"
                  ? "rgba(0, 213, 255, 0.35)"
                  : theme === "light"
                  ? "rgba(0,0,0,0.15)"
                  : "rgba(255,255,255,0.35)",
                weight: theme === "dark" ? 2 : 1.5,
                opacity: 0.9,
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

        {/* Route visualization - RENDERS LAST (ON TOP) */}
        {routeResult && <RouteLayer routeResult={routeResult} activeRoute={activeRoute} />}

        {/* Source/Target markers */}
        {srcNodeId && graphGeojson && <NodeMarker nodeId={srcNodeId} label="S" color="#00E5B4" graphGeojson={graphGeojson} />}
        {tgtNodeId && graphGeojson && <NodeMarker nodeId={tgtNodeId} label="T" color="#FFB400" graphGeojson={graphGeojson} />}
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
            { color: '#FF2D2D', label: 'Motorway / Expressway', tier: 'CRITICAL' },
            { color: '#FF8C00', label: 'Primary Artery', tier: 'HIGH' },
            { color: '#FFE600', label: 'Secondary Road', tier: 'MEDIUM' },
            { color: '#00E5B4', label: 'Tertiary Road', tier: 'LOW' },
            { color: '#00FF7F', label: 'Local / Residential', tier: 'MINIMAL' },
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

// ── Emergency Layer ───────────────────────────────────────────────────────────

function EmergencyLayer({ emergencyServices, graphGeojson }: { emergencyServices: EmergencyServicesResponse, graphGeojson: GeoJSON.FeatureCollection | null }) {
  const getIcon = (amenity: string) => {
    let emoji = "🚨";
    if (amenity === "fire_station") emoji = "🚒";
    if (amenity === "police") emoji = "🚓";
    return L.divIcon({
      html: `<div style="font-size: 24px; filter: drop-shadow(0 0 4px rgba(0,0,0,0.8)); text-align: center;">${emoji}</div>`,
      className: "",
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
  };

  return (
    <>
      {/* Emergency Stations */}
      {emergencyServices.facilities.map((fac, idx) => (
        <Marker
          key={idx}
          position={[fac.lat, fac.lon]}
          icon={getIcon(fac.amenity)}
        >
          <Popup className="custom-popup">
            <div className="p-2">
              <strong className="font-semibold block text-gray-800">{fac.name || "Emergency Station"}</strong>
              <span className="text-gray-500 text-xs uppercase">{fac.amenity.replace("_", " ")}</span>
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
          fillColor: "#00E5B4",
          fillOpacity: 0.6,
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
          style={{ color: "#00E5B4", weight: 4, opacity: 0.4 }}
        />
      )}
      {activeGeojson && (
        <>
          {/* Thick black outline for high contrast */}
          <GeoJSON
            key={`active-route-bg-${activeRoute}`}
            data={activeGeojson}
            style={{ color: "#000000", weight: 10, opacity: 0.8 }}
          />
          {/* Bright white dashed inner line */}
          <GeoJSON
            key={`active-route-fg-${activeRoute}`}
            data={activeGeojson}
            style={{ color: "#FFFFFF", weight: 5, opacity: 1.0, dashArray: "10, 10" }}
          />
        </>
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
    const color = type === 'ablated' ? '#FF4444' : '#FFB400';
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
