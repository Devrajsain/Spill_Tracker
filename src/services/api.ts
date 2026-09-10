/**
 * SlickTrace API Client
 * 
 * Centralized service layer for all backend API interactions.
 * All endpoints are proxied through Vite's dev server to avoid CORS issues.
 */

const API_BASE = '/api/v1';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface CaseResponse {
  id: string;
  name: string;
  status: string;
  location_name: string;
  center_latitude: number;
  center_longitude: number;
  summary_json: any;
  created_at: string;
}

export interface SpillResponse {
  id: string;
  case_id: string;
  confidence_score: number;
  confidence_label: string;
  area_km2: number;
  length_km: number;
  width_km: number;
  est_volume_bbl: number;
  detection_timestamp: string;
  satellite_source: string;
  polygon_geojson: any;
  origin_latitude: number;
  origin_longitude: number;
  origin_timestamp: string;
  drift_trajectory_json: any[];
}

export interface VesselResponse {
  id: string;
  case_id: string;
  mmsi: string;
  name: string;
  type: string;
  flag: string;
  overall_score: number;
  proximity_score: number;
  trajectory_score: number;
  behavioral_score: number;
  warning_flags: string[];
  current_latitude: number;
  current_longitude: number;
  heading_deg: number;
  speed_kts: string;
}

export interface Feature2ResultResponse {
  id: string;
  case_id: string;
  status: string;
  processing_mode: string;
  origin_latitude: number | null;
  origin_longitude: number | null;
  origin_timestamp: string | null;
  origin_confidence_score: number | null;
  origin_uncertainty_radius_km: number | null;
  release_window_start: string | null;
  release_window_end: string | null;
  forecast_json: any;
  geojson_feature_collection: any;
  pipeline_response_json: any;
  error_message: string | null;
  created_at: string;
}

export interface DashboardCaseData {
  case: CaseResponse;
  spill: SpillResponse | null;
  vessels: VesselResponse[];
  feature2: Feature2ResultResponse | null;
}

// ─── API Functions ──────────────────────────────────────────────────────────

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${errorBody || res.statusText}`);
  }
  return res.json();
}

/** Create a new forensic case with file uploads. */
export async function createCase(
  name: string,
  locationName: string,
  centerLatitude?: number | null,
  centerLongitude?: number | null,
  imageFile?: File | null,
  csvFile?: File | null,
): Promise<CaseResponse> {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('location_name', locationName);
  if (centerLatitude !== undefined && centerLatitude !== null && !isNaN(centerLatitude)) {
    formData.append('center_latitude', String(centerLatitude));
  }
  if (centerLongitude !== undefined && centerLongitude !== null && !isNaN(centerLongitude)) {
    formData.append('center_longitude', String(centerLongitude));
  }

  if (imageFile) {
    formData.append('image_file', imageFile);
  }
  if (csvFile) {
    formData.append('csv_file', csvFile);
  }

  const res = await fetch(`${API_BASE}/cases/`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`Failed to create case: ${res.status} ${errorBody}`);
  }

  return res.json();
}

/** Continues Feature 2 execution with user-entered coordinates. */
export async function continueCaseFeature2(
  caseId: string,
  latitude: number,
  longitude: number,
): Promise<CaseResponse> {
  const formData = new FormData();
  formData.append('latitude', String(latitude));
  formData.append('longitude', String(longitude));

  const res = await fetch(`${API_BASE}/cases/${caseId}/continue-feature2`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`Feature 2 execution failed: ${res.status} ${errorBody}`);
  }

  return res.json();
}

/** List all forensic cases. */
export async function listCases(): Promise<CaseResponse[]> {
  return fetchJSON<CaseResponse[]>(`${API_BASE}/cases/`);
}

/** Delete a case by ID. */
export async function deleteCase(caseId: string): Promise<{ message: string; id: string }> {
  const res = await fetch(`${API_BASE}/cases/${caseId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`Failed to delete case: ${res.status} ${errorBody}`);
  }
  return res.json();
}

/** Get a single case by ID. */
export async function getCase(caseId: string): Promise<CaseResponse> {
  return fetchJSON<CaseResponse>(`${API_BASE}/cases/${caseId}`);
}

/** Get spill detection data for a case. */
export async function getCaseSpill(caseId: string): Promise<SpillResponse> {
  return fetchJSON<SpillResponse>(`${API_BASE}/cases/${caseId}/spill`);
}

/** Get vessel attribution records for a case. */
export async function getCaseVessels(caseId: string): Promise<VesselResponse[]> {
  return fetchJSON<VesselResponse[]>(`${API_BASE}/cases/${caseId}/vessels`);
}

/** Get Feature 2 results for a case. */
export async function getFeature2Results(caseId: string): Promise<Feature2ResultResponse> {
  return fetchJSON<Feature2ResultResponse>(`${API_BASE}/feature2-results/${caseId}`);
}

/** Get Feature 2 GeoJSON for map rendering. */
export async function getFeature2GeoJSON(caseId: string): Promise<any> {
  return fetchJSON<any>(`${API_BASE}/feature2-results/${caseId}/geojson`);
}

/** Get Feature 2 forecast horizons. */
export async function getFeature2Forecast(caseId: string): Promise<any> {
  return fetchJSON<any>(`${API_BASE}/feature2-results/${caseId}/forecast`);
}

/** 
 * Load all dashboard data for a case in parallel.
 * Gracefully handles missing sub-resources.
 */
export async function loadDashboardData(caseId: string): Promise<DashboardCaseData> {
  const [caseData, spill, vessels, feature2] = await Promise.all([
    getCase(caseId),
    getCaseSpill(caseId).catch(() => null),
    getCaseVessels(caseId).catch(() => []),
    getFeature2Results(caseId).catch(() => null),
  ]);

  return {
    case: caseData,
    spill,
    vessels,
    feature2,
  };
}
