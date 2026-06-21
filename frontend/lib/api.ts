/**
 * Route Resilience — typed API client for the FastAPI backend.
 * All functions throw on non-2xx responses with descriptive errors.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

export interface GraphMetrics {
  num_nodes: number;
  num_edges: number;
  num_components: number;
  largest_component_size: number;
  largest_component_fraction: number;
  avg_node_degree: number;
  density: number;
  avg_shortest_path_length: number | null;
  diameter: number | null;
}

export interface CentralityNode {
  node_id: string;
  score: number;
  x: number;
  y: number;
  [key: string]: unknown;
}

export interface CentralityResponse {
  gatekeepers: CentralityNode[];
  all_centrality: Record<string, number>;
  top_n: number;
}

export interface CriticalityResponse {
  betweenness: Record<string, number>;
  closeness: Record<string, number>;
  gatekeepers: CentralityNode[];
  articulation_points: string[];
  critical_edges: { u: string; v: string; score: number }[];
}

export interface PopulationImpact {
  total_affected: number;
  isolated_count: number;
  percent_affected: number;
}

export interface AblationResponse {
  ablated_nodes: string[];
  graph_geojson: GeoJSON.FeatureCollection;
  baseline_metrics: GraphMetrics;
  perturbed_metrics: GraphMetrics;
  resilience_index: number | null;
  baseline_avg_path_length: number | null;
  perturbed_avg_path_length: number | null;
  disconnected: boolean;
  population_impact: PopulationImpact;
}

export interface CascadeStep {
  iteration: number;
  ablated: string[];
  newly_stressed: { node_id: string; centrality: number; x: number; y: number }[];
  component_count: number;
  lcc_size: number;
  note?: string;
}

export interface RouteResult {
  path_nodes: string[];
  path_geojson: GeoJSON.Feature | null;
  distance_m: number | null;
  travel_time_s: number | null;
  reachable: boolean;
  reason?: string;
}

export interface RouteResponse {
  baseline: RouteResult;
  rerouted: RouteResult | null;
  delta_distance_m: number | null;
  delta_time_s: number | null;
}

export interface Hospital {
  name: string;
  lat: number;
  lon: number;
  osm_id: string;
  amenity: string;
}

export interface HospitalAccessibility {
  hospitals: Array<{ name: string; lat: number; lon: number; osm_id: string; amenity?: string }>;
  hospital_node_ids: string[];
  baseline: Record<string, number>;
  perturbed: Record<string, number> | null;
  unreachable_delta: string[] | null;
}

export interface EquityResponse {
  equity_score: number;
  desert_count: number;
  total_facilities: number;
  deserts: Array<{ lat: number; lon: number; radius: number; nearest_facility_distance_m: number }>;
  vulnerable_clusters: Array<{ lat: number; lon: number; population: number; risk_level: string; type: string }>;
}

export interface CopilotResponse {
  reply: string;
  context_snapshot: Record<string, unknown>;
}

export interface TimelineStep {
  day: number;
  phase: string;
  active_ablated_count: number;
  global_resilience_score: number;
  isolated_population: number;
  lcc_fraction: number;
  affected_nodes: string[];
  metrics: GraphMetrics;
}

export interface Recommendation {
  type: "bypass" | "reinforcement";
  title: string;
  description: string;
  target_node?: string;
  target_nodes?: string[];
  rgs: number;
  cost_estimate: string;
  action: string;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
}

export interface EmergencyServicesResponse {
  facilities: Array<{
    name: string;
    lat: number;
    lon: number;
    osm_id: string;
    amenity: string;
  }>;
  facility_node_ids: string[];
}


export interface SimulateInvestmentResponse {
  baseline_ri: number;
  projected_ri: number;
  rgs: number;
  recommendation: Recommendation;
}

export interface FragilityPoint {
  fraction_ablated: number;
  lcc_fraction: number;
  efficiency: number;
}

export interface FragilityResponse {
  curve: FragilityPoint[];
  percolation_threshold: number;
  robustness_integral: number;
}

export interface ScenarioDef {
  name: string;
  description: string;
  ablated_node_ids: string[];
}

export interface ScenarioResult {
  name: string;
  description: string;
  ablated_count: number;
  ri: number;
  lcc_fraction: number;
  avg_path_length: number;
  efficiency: number;
}

export interface MultiScenarioResponse {
  scenarios: ScenarioResult[];
}

export interface ResilienceScoreResponse {
  global_resilience_score: number;
  metrics: GraphMetrics;
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ── Graph API ──────────────────────────────────────────────────────────────

export async function getGraphMetrics(useHealed = true): Promise<GraphMetrics> {
  return request<GraphMetrics>(`/graph/metrics?use_healed=${useHealed}`);
}

export async function getCentrality(topN = 20, k = 200): Promise<CentralityResponse> {
  return request<CentralityResponse>(`/graph/centrality?top_n=${topN}&k=${k}`);
}

export async function getCriticality(topN = 20, k = 200): Promise<CriticalityResponse> {
  return request<CriticalityResponse>(`/graph/criticality?top_n=${topN}&k=${k}`);
}

export async function getGraphGeoJSON(): Promise<GeoJSON.FeatureCollection> {
  return request<GeoJSON.FeatureCollection>(`/graph/geojson`);
}

export async function buildGraph(maskB64: string): Promise<{ graph_geojson: GeoJSON.FeatureCollection; metrics: GraphMetrics }> {
  return request(`/graph/build`, {
    method: "POST",
    body: JSON.stringify({ mask_b64: maskB64 }),
  });
}

export async function healGraph(): Promise<{
  graph_geojson: GeoJSON.FeatureCollection;
  before: GraphMetrics;
  after: GraphMetrics;
  connectivity_ratio: number;
}> {
  return request(`/graph/heal`, { method: "POST" });
}

// ── Segmentation API ───────────────────────────────────────────────────────

export async function segmentTile(file: File): Promise<{ mask_b64: string; confidence_b64: string; road_pixel_ratio: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/segment/`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Segment API ${res.status}`);
  return res.json();
}

export async function explainTile(file: File): Promise<{ overlay_b64: string; method: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/segment/explain`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Explain API ${res.status}`);
  return res.json();
}

// ── Simulation API ─────────────────────────────────────────────────────────

export async function ablateNodes(nodeIds: string[], autoTopN = 0): Promise<AblationResponse> {
  return request<AblationResponse>(`/simulate/ablate`, {
    method: "POST",
    body: JSON.stringify({ node_ids: nodeIds, auto_top_n: autoTopN }),
  });
}

export interface AblateStrategyResult {
  strategy: string;
  color: string;
  nodes_removed: number;
  resilience_index: number | null;
  avg_path_length: number | null;
  disconnected: boolean;
  components: number;
  winner_label?: string;
}

export interface AblateCompareResponse {
  strategies: AblateStrategyResult[];
  baseline_avg_path: number | null;
  top_n: number;
}

export async function compareAblation(topN: number): Promise<AblateCompareResponse> {
  return request<AblateCompareResponse>(`/simulate/ablate/compare`, {
    method: "POST",
    body: JSON.stringify({ top_n: topN }),
  });
}

export interface PrescribeSuggestion {
  rank: number;
  type: string;
  from_node: string;
  to_node: string;
  from_coords: [number, number];
  to_coords: [number, number];
  estimated_resilience_gain: number;
  attacked_ri: number;
  validated_ri: number;
  baseline_ri: number;
  new_resilience_index: number;
  rationale: string;
  isolated_nodes: number;
  priority: string;
  cost_estimate: string;
}

export interface PrescribeResponse {
  baseline_ri: number;
  attacked_ri: number;
  ablated_count: number;
  suggestions: PrescribeSuggestion[];
}

export async function prescribeAblation(ablatedNodeIds: string[], autoTopN = 0): Promise<PrescribeResponse> {
  return request<PrescribeResponse>(`/simulate/ablate/prescribe`, {
    method: "POST",
    body: JSON.stringify({ ablated_node_ids: ablatedNodeIds, auto_top_n: autoTopN, max_recommendations: 3 }),
  });
}

export interface VulnerabilityCriticalNode {
  rank: number;
  node_id: string;
  x: number;
  y: number;
  betweenness_score: number;
  is_articulation_point: boolean;
  estimated_impact_nodes: number;
  risk_label: string;
}

export interface VulnerabilityResponse {
  critical_nodes: VulnerabilityCriticalNode[];
  articulation_point_count: number;
  total_nodes: number;
  total_edges: number;
  baseline_metrics: any;
  fragility_summary: {
    single_points_of_failure: number;
    risk_level: string;
    top_threat: string;
  };
}

export async function getVulnerability(topN = 20): Promise<VulnerabilityResponse> {
  return request<VulnerabilityResponse>(`/simulate/ablate/vulnerability`, {
    method: "POST",
    body: JSON.stringify({ top_n: topN }),
  });
}

export async function runCascade(nodeIds: string[], maxIterations = 3, threshold = 0.7): Promise<{ cascade_steps: CascadeStep[] }> {
  return request(`/simulate/cascade`, {
    method: "POST",
    body: JSON.stringify({ node_ids: nodeIds, max_iterations: maxIterations, threshold }),
  });
}

export async function computeRoute(
  sourceNode: string,
  targetNode: string,
  ablatedNodeIds: string[] = [],
  weightType: string = "time_s",
): Promise<RouteResponse> {
  return request<RouteResponse>(`/simulate/route`, {
    method: "POST",
    body: JSON.stringify({ source_node: sourceNode, target_node: targetNode, ablated_node_ids: ablatedNodeIds, weight_type: weightType }),
  });
}

export async function runTimeline(seedNodeIds: string[], repairRate = 2, maxDays = 10): Promise<{ timeline_steps: TimelineStep[] }> {
  return request<{ timeline_steps: TimelineStep[] }>(`/simulate/timeline`, {
    method: "POST",
    body: JSON.stringify({ seed_node_ids: seedNodeIds, repair_rate: repairRate, max_days: maxDays }),
  });
}

export async function getGlobalResilience(): Promise<ResilienceScoreResponse> {
  return request<ResilienceScoreResponse>(`/simulate/resilience-score`);
}

export async function getRecommendations(): Promise<RecommendationsResponse> {
  return request<RecommendationsResponse>(`/simulate/recommendations`);
}

export async function simulateInvestment(idx: number): Promise<SimulateInvestmentResponse> {
  return request<SimulateInvestmentResponse>(`/simulate/simulate-investment`, {
    method: "POST",
    body: JSON.stringify({ recommendation_idx: idx }),
  });
}



export async function getEmergencyServices(): Promise<EmergencyServicesResponse> {
  return request<EmergencyServicesResponse>('/accessibility/emergency-services');
}

export async function getFragilityCurve(): Promise<FragilityResponse> {
  return request<FragilityResponse>(`/simulate/fragility`);
}

export async function runScenarios(scenarios: ScenarioDef[]): Promise<MultiScenarioResponse> {
  return request<MultiScenarioResponse>(`/simulate/scenarios`, {
    method: "POST",
    body: JSON.stringify({ scenarios }),
  });
}

export interface FloodImpactMetrics {
  population_affected: number;
  cost_estimate_usd: number;
  hospitals_affected: number;
  emergency_stations_affected: number;
}

export async function simulateFlood(waterLevel: number): Promise<{ 
  ablated_nodes: string[]; 
  elevation_bounds: { min: number; max: number }; 
  water_level: number;
  impact_metrics: FloodImpactMetrics;
}> {
  return request(`/simulate/flood`, {
    method: "POST",
    body: JSON.stringify({ water_level: waterLevel }),
  });
}

export async function getReliefCamps(
  ablatedNodeIds: string[] = [],
  numCamps: number = 3
): Promise<{
  camps: Array<{ id: string; lat: number; lng: number; node_count: number; population_estimate: number }>;
  catchment_mapping: Record<string, number>;
}> {
  return request(`/simulate/relief-camps`, {
    method: "POST",
    body: JSON.stringify({ ablated_node_ids: ablatedNodeIds, num_camps: numCamps }),
  });
}

export interface CrisisPriorityNode {
  node_id: string;
  lat: number;
  lon: number;
  centrality: number;
  vulnerability: number;
  crisis_priority: number;
}

export interface ZoneImpact {
  zone_name: string;
  lat: number;
  lon: number;
  population: number;
  vulnerability: number;
  critical_nodes_nearby: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
}

export interface EquityMetricsResponse {
  equity_score: number;
  crisis_priority_nodes: CrisisPriorityNode[];
  zone_impact_matrix: ZoneImpact[];
  total_zones_analyzed: number;
  high_risk_zones: number;
}

export interface TrafficImpactResponse {
  ablated_count: number;
  affected_daily_trips: number;
  avg_baseline_trip_m: number;
  avg_perturbed_trip_m: number;
  avg_detour_km: number;
  extra_minutes_per_commuter: number;
  total_commuter_minutes_lost: number;
  total_commuter_hours_lost: number;
  person_days_lost: number;
  unreachable_trip_pairs_pct: number;
  wage_loss_inr: number;
  fuel_loss_inr: number;
  logistics_loss_inr: number;
  total_economic_loss_inr: number;
  annual_loss_projection_inr: number;
}

export interface ZoneForecast {
  zone: string;
  avg_health_y0: number;
  avg_health_y10: number;
  risk_level: "CRITICAL" | "HIGH" | "MODERATE" | "LOW";
}

export interface DegradationForecastResponse {
  forecast_years: number[];
  network_health_trajectory: number[];
  confidence_band_low: number[];
  confidence_band_high: number[];
  annual_failure_probability: number[];
  budget_scenario: string;
  zone_forecasts: ZoneForecast[];
  total_reinvestment_needed_inr: number;
  critical_segments_count: number;
  monte_carlo_runs: number;
}

export async function getEquityMetrics(ablatedNodeIds: string[] = []): Promise<EquityMetricsResponse> {
  return request<EquityMetricsResponse>(`/simulate/equity-metrics`, {
    method: "POST",
    body: JSON.stringify({ ablated_node_ids: ablatedNodeIds }),
  });
}

export async function getTrafficImpact(ablatedNodeIds: string[] = []): Promise<TrafficImpactResponse> {
  return request<TrafficImpactResponse>(`/simulate/traffic-impact`, {
    method: "POST",
    body: JSON.stringify({ ablated_node_ids: ablatedNodeIds }),
  });
}

export async function getDegradationForecast(
  years = 10,
  monteCarlRuns = 50,
  budgetScenario: "optimistic" | "baseline" | "austerity" = "baseline"
): Promise<DegradationForecastResponse> {
  return request<DegradationForecastResponse>(`/simulate/degradation-forecast`, {
    method: "POST",
    body: JSON.stringify({ years, monte_carlo_runs: monteCarlRuns, budget_scenario: budgetScenario }),
  });
}


// ── Accessibility API ──────────────────────────────────────────────────────

export async function getHospitalAccessibility(
  south = 12.92,
  west = 77.57,
  north = 12.99,
  east = 77.64,
  ablatedNodeIds?: string[]
): Promise<HospitalAccessibility> {
  const url = `/accessibility/hospitals?south=${south}&west=${west}&north=${north}&east=${east}`;
  const finalUrl = ablatedNodeIds && ablatedNodeIds.length > 0
    ? `${url}&ablated_node_ids=${ablatedNodeIds.join(",")}`
    : url;
  return request<HospitalAccessibility>(finalUrl);
}

export async function getEquityAnalysis(
  south = 12.92,
  west = 77.57,
  north = 12.99,
  east = 77.64
): Promise<EquityResponse> {
  const url = `/accessibility/equity?south=${south}&west=${west}&north=${north}&east=${east}`;
  return request<EquityResponse>(url);
}

// ── Copilot API ────────────────────────────────────────────────────────────

export async function chatWithCopilot(
  message: string,
  history: { role: string; content: string }[] = [],
): Promise<CopilotResponse> {
  return request<CopilotResponse>(`/copilot/chat`, {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

// ── Reports API ────────────────────────────────────────────────────────────

export async function generateReport(city_name: string, sections: string[], timeline_seed_nodes: string[] = []): Promise<Blob> {
  const res = await fetch(`${BASE}/reports/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city_name, sections, timeline_seed_nodes }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.blob();
}
