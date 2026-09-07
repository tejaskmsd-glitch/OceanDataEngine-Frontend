/**
 * Authoritative TypeScript interfaces matching the FastAPI backend schemas exactly.
 * No invented fields, no fake data types.
 */

export interface FreshnessModel {
  reference_at?: string | null;
  age_seconds?: number | null;
  age_minutes?: number | null;
  is_stale: boolean;
  freshness_score: number;
  expected_update_interval_s?: number | null;
  stale_threshold_s?: number | null;
}

export interface SourceRef {
  provider: string;
  dataset: string;
  source_url?: string | null;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  retrieved_at?: string | null;
  processing_version?: string | null;
}

export interface QualityModel {
  quality_status?: string | null;
  quality_score?: number | null;
}

export interface Meta {
  generated_at: string;
  request_id: string;
  valid_from?: string | null;
  valid_until?: string | null;
  freshness?: FreshnessModel | null;
  confidence?: number | null;
}

export interface Envelope<T> {
  data: T;
  meta: Meta;
  sources: SourceRef[];
  quality?: QualityModel | null;
  warnings: string[];
}

export interface HealthData {
  status: string;
  version: string;
  environment: string;
  live_sources_enabled: boolean;
  time: string;
}

export interface DatasetModel {
  key: string;
  dataset_id?: string | null;
  provider: string;
  product: string;
  parameters: string[];
  status: string;
  fmt?: string | null;
  format?: string | null;
  spatial_coverage?: string | null;
  spatial_resolution?: string | null;
  temporal_resolution?: string | null;
  expected_update_interval_s?: number | null;
  last_success_at?: string | null;
  last_success?: string | null;
  last_processed_at?: string | null;
  last_updated?: string | null;
  last_checked_at?: string | null;
  last_result_count?: number | null;
  last_result_state?: string | null;
  status_detail?: string | null;
  consecutive_failures: number;
}

export interface DataHealthModel {
  dataset: string;
  dataset_id?: string | null;
  provider: string;
  status: string;
  consecutive_failures: number;
  last_success_at?: string | null;
  last_success?: string | null;
  last_checked_at?: string | null;
  last_result_count?: number | null;
  last_result_state?: string | null;
  status_detail?: string | null;
  freshness: FreshnessModel;
}

export interface JobModel {
  job_id: string;
  source?: string | null;
  dataset?: string | null;
  job_type?: string | null;
  status?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  worker?: string | null;
  error?: string | null;
  retry_count?: number | null;
}

export interface AlertModel {
  alert_uid: string;
  warning_id?: string | null;
  event_type: string;
  severity: string;
  certainty: string;
  urgency: string;
  headline?: string | null;
  description?: string | null;
  area_description?: string | null;
  geometry?: any | null;
  distance_km?: number | null;
  issued_at?: string | null;
  valid_from?: string | null;
  effective_from?: string | null;
  valid_until?: string | null;
  expires_at?: string | null;
  quality_status: string;
  provider: string;
  source_dataset: string;
  source?: string | null;
  source_url?: string | null;
}

export interface EvidenceModel {
  request_id: string;
  endpoint: string;
  query_params: Record<string, any>;
  sources: Array<Record<string, any>>;
  record_refs: Array<any>;
  confidence?: number | null;
  freshness: Record<string, any>;
  quality: Record<string, any>;
  warnings: string[];
  capability_status?: string | null;
  data_versions: Record<string, any>;
  data_lineage: Array<Record<string, any>>;
  generated_at: string;
}

export interface ObservationModel {
  observation_uid: string;
  parameter: string;
  value?: number | null;
  unit?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  station_id?: string | null;
  station_type?: string | null;
  distance_km?: number | null;
  observed_at?: string | null;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  retrieved_at?: string | null;
  quality_status: string;
  quality_score?: number | null;
  provider: string;
  source_dataset: string;
  source_url?: string | null;
}

export interface ForecastModel {
  forecast_uid: string;
  parameter: string;
  value?: number | null;
  unit?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  model_name?: string | null;
  model_cycle?: string | null;
  forecast_hour?: number | null;
  resolution?: string | null;
  distance_km?: number | null;
  forecast_time?: string | null;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  retrieved_at?: string | null;
  quality_status: string;
  quality_score?: number | null;
  provider: string;
  source_dataset: string;
  source_url?: string | null;
}

export interface PFZModel {
  pfz_uid: string;
  pfz_id?: string | null;
  region?: string | null;
  advisory_text?: string | null;
  advisory_type?: string | null;
  geometry?: any | null;
  distance_km: number;
  inside: boolean;
  valid?: boolean | null;
  issued_at?: string | null;
  issue_time?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  confidence?: number | null;
  quality_status: string;
  provider: string;
  source?: string | null;
  source_dataset: string;
  source_url?: string | null;
}

export interface AdvisoryModel {
  advisory_uid: string;
  advisory_type: string;
  species_or_ecosystem?: string | null;
  region?: string | null;
  recommendation?: string | null;
  geometry?: any | null;
  distance_km?: number | null;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  retrieved_at?: string | null;
  quality_status: string;
  provider: string;
  source_dataset: string;
  source_url?: string | null;
}

export interface ZoneModel {
  zone_uid: string;
  zone_type: string;
  name: string;
  status?: string | null;
  restriction?: string | null;
  authority?: string | null;
  geometry?: any | null;
  distance_km?: number | null;
  inside?: boolean | null;
  effective_from?: string | null;
  effective_until?: string | null;
  source?: string | null;
  source_url?: string | null;
}

export interface RiskFactorModel {
  name: string;
  value?: number | null;
  threshold_low: number;
  threshold_high: number;
  weight: number;
  contribution: number;
}

export interface MarineRiskModel {
  risk_score: number;
  risk_level: string;
  factors: RiskFactorModel[];
  warnings: string[];
  valid_from?: string | null;
  valid_until?: string | null;
  sources: Array<Record<string, any>>;
}

export interface FishingSuitabilityModel {
  score: number;
  classification: string;
  positive_drivers: string[];
  negative_drivers: string[];
  confidence?: number | null;
  sources: Array<Record<string, any>>;
}

export interface RouteSegmentModel {
  start: [number, number];
  end: [number, number];
  distance_km: number;
  travel_time_hours?: number | null;
  risk_score: number;
  penalties: Record<string, any>;
}

export interface SafeRouteModel {
  geometry: any;
  total_distance_km: number;
  estimated_duration_hours?: number | null;
  route_risk_score: number;
  segments: RouteSegmentModel[];
  avoided_zones: string[];
  major_risk_drivers: string[];
  sources: Array<Record<string, any>>;
  status: string;
  warnings: string[];
}

export interface GeoPoint {
  lat: number;
  lon: number;
}

export interface SafeRouteRequest {
  start: GeoPoint;
  end: GeoPoint;
  departure_time?: string | null;
  vessel_type?: string | null;
}

export interface StacLink {
  rel: string;
  type?: string;
  href: string;
  title?: string;
}

export interface StacCollection {
  id: string;
  title?: string;
  description: string;
  license?: string;
  extent?: {
    spatial?: { bbox: number[][] };
    temporal?: { interval: (string | null)[][] };
  };
  links?: StacLink[];
}

export interface StacItem {
  id: string;
  type: string;
  geometry: any;
  bbox?: number[];
  properties: Record<string, any>;
  assets: Record<string, any>;
  links?: StacLink[];
  collection?: string;
}

export interface StacItemCollection {
  type: "FeatureCollection";
  features: StacItem[];
  links?: StacLink[];
}
