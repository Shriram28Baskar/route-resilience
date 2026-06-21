import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Map a centrality score [0, 1] to a hex color on a green → yellow → red scale.
 */
export function centralityColor(score: number): string {
  // Low centrality → green, medium → yellow, high → red
  const r = Math.round(score * 255 + (1 - score) * 34);
  const g = Math.round((1 - score) * 197 + score * 68);
  const b = 34;
  return `rgb(${r},${g},${b})`;
}

/**
 * Format seconds into a human-readable duration string.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "N/A";
  const isNeg = seconds < 0;
  const s = Math.round(Math.abs(seconds));
  const sign = isNeg ? "-" : "";
  if (s < 60) return `${sign}${s}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const rs = s % 60;
    return rs > 0 ? `${sign}${m}m ${rs}s` : `${sign}${m}m`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return m > 0 ? `${sign}${h}h ${m}m` : `${sign}${h}h`;
}

/**
 * Format metres into km with appropriate precision.
 */
export function formatDistance(metres: number | null | undefined): string {
  if (metres === null || metres === undefined) return "N/A";
  const isNeg = metres < 0;
  const m = Math.abs(metres);
  const sign = isNeg ? "-" : "";
  if (m < 1000) return `${sign}${Math.round(m)}m`;
  return `${sign}${(m / 1000).toFixed(2)}km`;
}

/**
 * Convert a base64 PNG string to an Image src URL.
 */
export function b64ToDataUrl(b64: string, mimeType = "image/png"): string {
  return `data:${mimeType};base64,${b64}`;
}

/**
 * Truncate a node ID for display.
 */
export function shortNodeId(nodeId: string, len = 6): string {
  return nodeId.length > len ? `…${nodeId.slice(-len)}` : nodeId;
}

/**
 * Compute a colour for the Resilience Index badge.
 * R close to 1 = good (green), R far from 1 = bad (red).
 */
export function resilienceColor(ri: number | null): string {
  if (ri === null) return "#6B7280";
  if (ri >= 0.9) return "#22C55E";
  if (ri >= 0.7) return "#FFB400";
  return "#FF4444";
}

/**
 * Find the nearest node ID to a given lat/lon coordinate from the graph GeoJSON.
 */
export function findNearestNodeId(lat: number, lon: number, geojson: GeoJSON.FeatureCollection | null): string | null {
  if (!geojson) return null;
  let nearestId = null;
  let minD2 = Infinity;
  for (const f of geojson.features) {
    if (f.geometry.type === "Point" && f.properties?.type === "node") {
      const [nLon, nLat] = f.geometry.coordinates;
      // Simple squared Euclidean distance is sufficient for finding the closest node locally
      const d2 = (nLat - lat) ** 2 + (nLon - lon) ** 2;
      if (d2 < minD2) {
        minD2 = d2;
        nearestId = f.properties.id;
      }
    }
  }
  return nearestId;
}

