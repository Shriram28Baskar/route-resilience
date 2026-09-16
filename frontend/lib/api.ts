/**
 * Route Resilience — typed API client for the FastAPI backend.
 * All functions throw on non-2xx responses with descriptive errors.
 */

const BASE = "/api";
// Long-running requests bypass the Next.js proxy (which has a ~30s timeout)
// and call the backend directly from the browser.
const DIRECT_BASE = typeof window !== "undefined" 
  ? (window.location.hostname === "localhost" 
      ? `${window.location.protocol}//127.0.0.1:8000` 
      : `${window.location.protocol}//${window.location.hostname}:8000`)
  : "http://127.0.0.1:8000";

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
  const res = await fetch(`${DIRECT_BASE}/simulate/ablate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_ids: nodeIds, auto_top_n: autoTopN }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
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

export interface ApplyPrescriptionResponse {
  success: boolean;
  bridge: {
    from_node: string;
    to_node: string;
    length_m: number;
    time_s: number;
  };
  routing_verification: {
    path_existed_before: boolean;
    travel_time_before_s: number | "INF";
    path_exists_after: boolean;
    travel_time_after_s: number | null;
    detour_reduction_pct: number;
  };
  active_graph_nodes: number;
  active_graph_edges: number;
  message: string;
}

export async function applyTacticalPrescription(params: {
  from_node: string;
  to_node: string;
  length_m?: number;
  time_s?: number;
  origin_node?: string;
  target_hospital_node?: string;
}): Promise<ApplyPrescriptionResponse> {
  return request<ApplyPrescriptionResponse>(`/simulate/ablate/prescribe/apply`, {
    method: "POST",
    body: JSON.stringify(params),
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
  const res = await fetch(`${DIRECT_BASE}/simulate/cascade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_ids: nodeIds, max_iterations: maxIterations, threshold }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
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

export async function simulateFlood(waterLevel: number, isAnimation: boolean = false): Promise<{ 
  ablated_nodes: string[]; 
  elevation_bounds: { min: number; max: number }; 
  water_level: number;
  impact_metrics: FloodImpactMetrics;
  road_length_flooded_km?: number;
}> {
  return request(`/simulate/flood`, {
    method: "POST",
    body: JSON.stringify({ water_level: waterLevel, is_animation: isAnimation }),
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
  /** M11: renamed from affected_daily_trips. DERIVED, not measured — a city-wide
   *  commuter constant scaled by a relative betweenness ratio. Not a trip count. */
  derived_trip_scale: number;
  max_relative_betweenness: number;
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

// ── Accessibility Impact Engine ─────────────────────────────────────────────

export interface AccessibilityImpactResponse {
  hospital_count: number;
  hospital_node_ids: string[];
  hospitals: Array<{ name: string; lat: number; lon: number; osm_id: string; amenity?: string }>;
  ablated_node_ids: string[];
  baseline: {
    accessible_node_count: number;
    inaccessible_node_count: number;
    avg_time_s: number | null;
    node_coverage: Record<string, number>;
  };
  post_disaster: {
    accessible_node_count: number;
    inaccessible_node_count: number;
    avg_time_s: number | null;
    node_coverage: Record<string, number>;
  };
  impact: {
    nodes_lost_access: string[];
    nodes_lost_access_count: number;
    nodes_degraded: string[];
    nodes_degraded_count: number;
    avg_travel_time_increase_s: number;
    median_travel_time_increase_s: number;
    disconnected_hospital_count: number;
    resilience_index_before: number | null;
    resilience_index_after: number | null;
    resilience_index: number | null;
    network_disconnected: boolean;
    partition_count: number;
  };
  best_alternative_route: RouteResult | null;
}

export async function getAccessibilityImpact(
  ablatedNodeIds: string[],
  south = 12.92,
  west = 77.57,
  north = 12.99,
  east = 77.64,
): Promise<AccessibilityImpactResponse> {
  return request<AccessibilityImpactResponse>("/accessibility/impact", {
    method: "POST",
    body: JSON.stringify({ ablated_node_ids: ablatedNodeIds, south, west, north, east }),
  });
}

// ── Copilot API ────────────────────────────────────────────────────────────

export async function chatWithCopilot(
  message: string,
  history: { role: "user" | "assistant"; content: string }[] = []
): Promise<CopilotResponse> {
  return request<CopilotResponse>(`/copilot/chat`, {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

export async function generateBriefNarrative(
  floodData: any, impactData: any, wardData: any
): Promise<{ narrative: string }> {
  return request<{ narrative: string }>(`/copilot/brief-narrative`, {
    method: "POST",
    body: JSON.stringify({ flood_data: floodData, impact_data: impactData, ward_data: wardData }),
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

// ── Step 7: Rainfall Backtest ──────────────────────────────────────────────

export interface BacktestEvent {
  date: string;
  rainfall_mm: number;
  classification: string;
  water_level_model: { water_level_m: number; methodology: string };
  flood_result: { flooded_nodes: number; flood_fraction_pct: number };
  ward_validation: {
    known_prone_wards_matched: string[];
    ward_overlap_score_pct: number;  // renamed from validation_score_pct — this is an overlap check, not recall/precision
  };

}

export interface BacktestResponse {
  backtest_config: { events_backtested: number; district: string };
  validation_summary: {
    total_events_backtested: number;
    monotonicity_check: string;
    avg_ward_overlap_score_pct: number;        // renamed from avg_ward_validation_score_pct (H1 fix)
    avg_false_positive_wards: number;          // added by H1 fix
    model_limitations: string[];
  };
  events: BacktestEvent[];
}

export async function runRainfallBacktest(
  min_rainfall_mm = 0,
  max_events = 50
): Promise<BacktestResponse> {
  const res = await fetch(`${DIRECT_BASE}/simulate/rainfall-backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_rainfall_mm, max_events }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── Step 8: Ward Report ────────────────────────────────────────────────────

export interface WardReport {
  ward_name: string;
  assembly_constituency: string;
  zone: string;
  census_population_2011: number;
  graph_nodes_flooded: number;
  flood_fraction_pct: number;
  severity: "critical" | "high" | "moderate" | "low";
}

export interface WardReportResponse {
  summary: {
    total_wards_in_graph: number;
    wards_affected: number;
    wards_critical: number;
    total_census_pop_in_affected_wards: number;
    population_note: string;
  };
  critical_wards: string[];
  ward_reports: WardReport[];
}

export async function fetchWardReport(ablated_node_ids: string[]): Promise<WardReportResponse> {
  const res = await fetch(`${DIRECT_BASE}/accessibility/ward-report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ablated_node_ids }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── Steps 4+5+6: Flood Accessibility Impact ────────────────────────────────

export interface FacilityImpact {
  label: string;
  facility_count: number;
  facilities_flooded: number;
  facilities_intact: number;
  baseline: { accessible_nodes: number; avg_travel_time_min: number | null };
  post_flood: { accessible_nodes: number; avg_travel_time_min: number | null };
  impact: {
    nodes_lost_15min_access: number;
    avg_travel_time_increase_min: number;
    facilities_disconnected: number;
  };
  best_alternative_route: {
    distance_m: number;
    travel_time_min: number;
    path_geojson: GeoJSON.Feature | null;
  } | null;
}

export interface FloodAccessibilityResponse {
  flood_summary: { flooded_nodes: number; road_length_flooded_km: number };
  population: { affected: number; source: string };
  ward_breakdown: { top_affected_wards: { ward: string; flooded_nodes: number }[]; total_wards_affected: number };
  facility_impact: {
    hospitals: FacilityImpact;
    fire_stations: FacilityImpact;
    police: FacilityImpact;
  };
}

export async function fetchFloodAccessibilityImpact(
  ablated_node_ids: string[]
): Promise<FloodAccessibilityResponse> {
  const res = await fetch(`${DIRECT_BASE}/accessibility/flood-impact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ablated_node_ids }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── Step 9: Live Weather ───────────────────────────────────────────────────

export interface WeatherData {
  city: string;
  current_rainfall_1h_mm: number;
  temperature_c: number;
  humidity_pct: number;
  description: string;
  risk: { level: string; description: string };
  source: string;
}

export async function fetchCurrentWeather(): Promise<WeatherData> {
  return request<WeatherData>(`/alerts/weather`);
}

export async function fetchWeatherForecast(hours = 24) {
  return request(`/alerts/forecast?hours=${hours}`);
}

// ── Step 10: Alert WebSocket ───────────────────────────────────────────────

export interface FloodAlert {
  type: "flood_alert";
  severity: "critical" | "high" | "moderate" | "low";
  title: string;
  message: string;
  details: Record<string, string | number>;
}

/**
 * Connect to the backend alert WebSocket.
 * onAlert is called every time a flood alert is broadcast.
 * Returns a cleanup function to close the connection.
 */
export function connectAlertWebSocket(
  onAlert: (alert: FloodAlert) => void,
  onConnect?: () => void,
  onDisconnect?: () => void,
): () => void {
  const WS_BASE = BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${WS_BASE}/alerts/ws`);

  ws.onopen = () => {
    console.log("[Route Resilience] Alert WebSocket connected");
    onConnect?.();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event === "flood_alert" && data.payload) {
        onAlert(data.payload as FloodAlert);
      }
    } catch {
      // ignore malformed messages
    }
  };

  ws.onclose = () => {
    console.log("[Route Resilience] Alert WebSocket disconnected");
    onDisconnect?.();
  };

  ws.onerror = (e) => console.error("[Route Resilience] Alert WS error:", e);

  return () => ws.close();
}

// ── Historical Disaster Scenarios ─────────────────────────────────────────────

export interface HistoricalScenarioSummary {
  id: string;
  name: string;
  peak_date: string;
  description: string;
  data_type: string;
}

export interface HistoricalScenarioResponse {
  scenario_metadata: {
    id: string;
    name: string;
    peak_date: string;
    data_type: string;
    description: string;
  };
  observed_historical_facts: {
    _label: string;
    rainfall_mm: number;
    rainfall_source: string;
    rainfall_precision: string;
    rainfall_source_note: string;
    known_affected_areas_qualitative: string[];
    known_affected_areas_source: string;
    known_affected_areas_note: string;
    infrastructure_impact_note: string;
  };
  model_inputs: {
    _label: string;
    dem_source: string;
    graph_source: string;
    flood_model: string;
    graph_nodes: number;
    graph_edges: number;
    dem_elevation_range: { min_m: number; max_m: number; mean_m: number; unknown_nodes: number };
    rainfall_runoff_model_output: {
      _note: string;
      rainfall_mm: number;
      water_level_m: number;
      flooded_nodes_at_this_level: number;
      limitation: string;
    };
    scenario_water_level_m: number;
    scenario_water_level_basis: string;
    scenario_water_level_note: string;
  };
  simulated_results: {
    _label: string;
    water_level_m: number;
    flood_model: string;
    flooded_nodes: number;
    total_nodes: number;
    flood_fraction_pct: number;
    road_length_flooded_km: number;
    surviving_network: {
      surviving_nodes: number;
      surviving_components: number;
      largest_connected_component_nodes: number;
    };
    population_in_flood_zone: {
      value: number;
      source: string;
      methodology: string;
      note: string;
    };
    facility_impact: {
      hospitals_in_flood_zone: number | null;
      hospitals_total_in_aoi: number | null;
      emergency_stations_in_flood_zone: number | null;
      emergency_total_in_aoi: number | null;
      source: string;
      note: string;
    };
    ward_impact: {
      wards_with_flooded_nodes: number;
      top_affected_wards: [string, number][];
      ward_boundary_source: string;
    };
  };
  directional_comparison: {
    _label: string;
    model_predicted_wards_count: number;
    documented_affected_areas_count: number;
    exact_name_overlap: string[];
    partial_name_overlap: string[];
    areas_outside_aoi: string[];
    aoi_coverage_note: string;
    comparison_note: string;
  };
  model_limitations: string[];
}

export async function fetchHistoricalScenarios(): Promise<{ scenarios: HistoricalScenarioSummary[] }> {
  return request<{ scenarios: HistoricalScenarioSummary[] }>("/simulate/historical/");
}

export async function fetchHistoricalScenario(
  scenarioId: string,
  overrideWaterLevelM?: number
): Promise<HistoricalScenarioResponse> {
  const url = overrideWaterLevelM != null
    ? `${DIRECT_BASE}/simulate/historical/${scenarioId}?override_water_level_m=${overrideWaterLevelM}`
    : `${DIRECT_BASE}/simulate/historical/${scenarioId}`;
  const res = await fetch(url, { headers: { "Content-Type": "application/json" } });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

// ── Temporal Flood Projection ─────────────────────────────────────────────────

export interface TemporalNetworkImpact {
  water_level_m: number;
  flooded_nodes: number;
  total_nodes: number;
  flood_fraction_pct: number;
  road_length_flooded_km: number;
  population_in_flood_zone: { value: number; source: string; note: string };
  wards_affected: number;
  surviving_components: number;
  hospitals_flooded: number;
  total_hospitals: number;
  resilience_index: number;
  water_level_clamped_to_dem_max: boolean;
  clamp_note?: string;
}

export interface TemporalHorizon {
  horizon_label: string;
  data_type: "OBSERVED" | "EXTRAPOLATED" | "MODELED";
  status: "STABLE" | "DEGRADING" | "CRITICAL";
  additional_water_depth_mm: number;
  projected_water_level_m: number;
  methodology_note: string;
  network_consequences_note: string;
  network_impact: TemporalNetworkImpact;
}

export interface TemporalProjectionResponse {
  methodology: {
    model: string;
    data_limitation: string;
    observed_source: string;
    rainfall_rate_note: string;
    labels_guide: Record<string, string>;
  };
  observed_conditions: {
    _section: string;
    rainfall_rate_mm_h: number;
    rainfall_source: string;
    rainfall_note: string;
    temperature_c: number | null;
    humidity_pct: number | null;
    description: string | null;
    risk: { level: string; description: string } | null;
    weather_api_ok: boolean;
    weather_api_error: string | null;
  };
  base_state: {
    base_water_level_m: number;
    base_note: string;
    dem_range: { min_m: number; max_m: number; mean_m: number };
    override_rainfall_used: boolean;
    override_base_used: boolean;
  };
  temporal_horizons: TemporalHorizon[];
  next_3h_owm_forecast: {
    rain_3h_mm: number;
    data_type: string;
    source: string;
    note: string;
  } | null;
  computation_ms: number;
}

export async function fetchTemporalProjection(
  baseWaterLevelM?: number,
  overrideRainfallMmH?: number,
): Promise<TemporalProjectionResponse> {
  const params = new URLSearchParams();
  if (baseWaterLevelM !== undefined) params.set("base_water_level_m", String(baseWaterLevelM));
  if (overrideRainfallMmH !== undefined) params.set("override_rainfall_mm_h", String(overrideRainfallMmH));
  const qs = params.toString();
  const url = `${BASE}/simulate/temporal-projection${qs ? `?${qs}` : ""}`;
  return request<TemporalProjectionResponse>(url);
}
export async function triggerWeatherAlert(thresholdMm: number = 15.6) {
  return request(`/alerts/weather-trigger`, {
    method: "POST",
    body: JSON.stringify({ threshold_mm: thresholdMm, send_email: true, send_ws: true }),
  });
}

export async function dispatchManualAlert(payload: any) {
  return request(`/alerts/dispatch`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── AMDIROS Autonomous Loop API ───────────────────────────────────────────────

export interface NodeETA {
  node_id: string;
  lat: number | null;
  lon: number | null;
  elevation_m: number;
  eta_minutes: number;
  risk_label: "imminent" | "critical" | "warning" | "watch";
  data_type: "EXTRAPOLATED";
  projection_basis: "linear_effective_runoff_persistence";
}

export interface HospStatus {
  name: string;
  lat: number;
  lon: number;
  reachable: boolean;
  travel_time_s: number | null;
}

export interface EvacAdvisory {
  ward_name: string;
  action: "EVACUATE_NOW" | "EVACUATE_ADVISED" | "MONITOR";
  population_estimate: number;
  population_source: string;
  flooded_node_count: number;
  nearest_camp_id: string;
  recommended_corridor: string;
  travel_time_estimate_s: number;
  hospital_reachable: boolean;
}

export interface CitizenReport {
  report_id: string;
  lat: number;
  lon: number;
  message: string;
  severity: string;
  snapped_node_id: number | null;
  flooding_indicator: boolean;
  received_at: string;
  twin_agreement: "AGREES" | "DISAGREES" | "UNVERIFIABLE";
  twin_note: string;
}

export interface ActionPlan {
  sequence_no: number;
  created_at: string;
  relief_camps: { id: string; lat: number; lng: number; [k: string]: unknown }[];
  evacuation_advisories: EvacAdvisory[];
  tactical_prescriptions: unknown[];
  affected_ward_count: number;
  hospitals_isolated: number;
}

export interface DecisionEvent {
  severity: "HIGH" | "MEDIUM" | "LOW";
  trigger_reason: string;
  changed_components: string[];
}

export interface DisasterStateUpdate {
  type: "DISASTER_STATE_UPDATE";
  sequence_no: number;
  observed_at: string;
  loop_duration_s: number;
  partial: boolean;
  rainfall_rate_mm_h: number;
  water_level_m: number;
  flooded_node_count: number;
  flooded_node_ids?: string[];
  resilience_index: number | null;
  partition_count: number;
  affected_wards: string[];
  population_at_risk: number;
  hospital_status: HospStatus[];
  citizen_reports: CitizenReport[];
  predicted_flood_exposure: NodeETA[];
  action_plan: ActionPlan | null;
  narrative: string;
  narrative_source: "llm" | "template";
  material_change: boolean;
  decision_event: DecisionEvent | null;
}

export interface LoopHeartbeat {
  type: "LOOP_HEARTBEAT";
  sequence_no: number;
  observed_at: string;
  rainfall_rate_mm_h: number;
  material_change: false;
  retained_from_seq: number;
}

export type WsDisasterMessage = DisasterStateUpdate | LoopHeartbeat;

/** Trigger one immediate autonomous observation cycle with optional rainfall injection. */
export async function triggerLoop(rainfallRateMmH?: number): Promise<{ triggered: boolean; current_seq: number | null }> {
  return request("/simulate/trigger-loop", {
    method: "POST",
    body: JSON.stringify({ rainfall_rate_mm_h: rainfallRateMmH ?? null }),
  });
}

/** Get the latest DisasterState (use on page load before WS connects). */
export async function getCurrentDisasterState(): Promise<DisasterStateUpdate | { status: string }> {
  return request("/simulate/current-state");
}

/** Get last N states from the ring buffer (max 12). */
export async function getStateHistory(n = 12): Promise<{ count: number; states: DisasterStateUpdate[] }> {
  return request(`/simulate/state-history?n=${n}`);
}

/** Get current ward-level evacuation advisories. */
export async function getEvacuationAdvisory(): Promise<{ sequence_no: number; advisories: EvacAdvisory[] }> {
  return request("/simulate/evacuation-advisory");
}

/** Get current Projected Flood Exposure ETA list. */
export async function getPredictedFloodExposure(): Promise<{ predictions: NodeETA[]; data_type: string }> {
  return request("/simulate/predict-flood-exposure");
}

export interface CitizenReportRequest {
  lat: number;
  lon: number;
  message: string;
  severity: "critical" | "high" | "moderate" | "low";
}

export interface CitizenReportResponse {
  status: string;
  report_id: string;
  snapped_node_id: number;
  snap_distance_m: number;
  flooding_indicator: boolean;
  twin_agreement: "AGREES" | "DISAGREES" | "UNVERIFIABLE";
  twin_note: string;
}

/** Submit a citizen distress report. */
export async function submitCitizenReport(report: CitizenReportRequest): Promise<CitizenReportResponse> {
  return request("/citizens/report", {
    method: "POST",
    body: JSON.stringify(report),
  });
}

/** Get recent citizen reports. */
export async function getCitizenReports(n = 50): Promise<{ count: number; reports: CitizenReport[] }> {
  return request(`/citizens/reports?n=${n}`);
}

/** Clear all citizen reports (demo reset). */
export async function clearCitizenReports(): Promise<{ status: string }> {
  return request("/citizens/reports", { method: "DELETE" });
}

/** Pre-scripted demo reports for fallback demonstration. */
export const DEMO_CITIZEN_REPORTS: CitizenReportRequest[] = [
  {
    lat: 12.9352, lon: 77.6245,
    message: "Road completely flooded near Koramangala 1st block. Cars stuck, water above tyre level.",
    severity: "high",
  },
  {
    lat: 12.9150, lon: 77.6240,
    message: "Water entering homes on HSR Layout 27th Main. Families need evacuation help.",
    severity: "critical",
  },
  {
    lat: 12.9576, lon: 77.6374,
    message: "Underpass near Marathahalli completely blocked with water. Buses have been diverted.",
    severity: "high",
  },
];

/** Post all three pre-scripted demo reports sequentially. */
export async function runDemoCitizenReports(): Promise<CitizenReportResponse[]> {
  const results: CitizenReportResponse[] = [];
  for (const report of DEMO_CITIZEN_REPORTS) {
    try {
      const res = await submitCitizenReport(report);
      results.push(res);
    } catch (e) {
      console.error("Demo report failed:", e);
    }
  }
  return results;
}
