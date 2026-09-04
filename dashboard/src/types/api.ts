/**
 * TypeScript models for the Marine Data Layer API.
 *
 * These mirror the canonical response envelope and entity fields documented in
 * the platform requirements (see marine_data_layer_requirements.md and
 * prompt.md). Because the API is still evolving, all consumer-facing types are
 * intentionally permissive: fields the backend may omit are optional, and
 * accessors are defensive. The dashboard never assumes a field is present.
 */

/** Common canonical response envelope used across capability APIs. */
export interface ResponseEnvelope<T> {
  data: T;
  meta?: EnvelopeMeta;
  sources?: SourceRef[];
  quality?: QualityInfo;
  warnings?: string[];
}

export interface EnvelopeMeta {
  generated_at?: string;
  valid_from?: string | null;
  valid_until?: string | null;
  freshness?: FreshnessInfo | string | null;
  confidence?: number | null;
  /** Present on evidence/provenance responses. */
  request_id?: string;
}

export interface FreshnessInfo {
  age_minutes?: number | null;
  is_stale?: boolean | null;
  freshness_score?: number | null;
  retrieved_at?: string | null;
  observed_at?: string | null;
}

export interface QualityInfo {
  quality_status?: string | null;
  quality_score?: number | null;
  missing_flag?: boolean | null;
  outlier_flag?: boolean | null;
  interpolated_flag?: boolean | null;
}

export interface SourceRef {
  source?: string;
  provider?: string;
  dataset?: string;
  dataset_id?: string;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  retrieved_at?: string | null;
  source_url?: string | null;
  processing_version?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Datasets & health                                                          */
/* -------------------------------------------------------------------------- */

export type DatasetStatus =
  | 'HEALTHY'
  | 'STALE'
  | 'DEGRADED'
  | 'FAILED'
  | 'DISABLED'
  | string;

export interface Dataset {
  dataset_id: string;
  provider?: string;
  product?: string;
  parameters?: string[];
  coverage?: string;
  spatial_resolution?: string;
  temporal_resolution?: string;
  format?: string;
  update_frequency?: string;
  access_method?: string;
  status?: DatasetStatus;
  last_success?: string | null;
  last_failure?: string | null;
  last_updated?: string | null;
  age_minutes?: number | null;
  is_stale?: boolean | null;
  freshness_score?: number | null;
  consecutive_failures?: number | null;
}

export interface DataHealth {
  datasets?: Dataset[];
  sources?: SourceHealth[];
  summary?: HealthSummary;
}

export interface SourceHealth {
  source: string;
  status?: DatasetStatus;
  last_fetch?: string | null;
  last_success?: string | null;
  failure_count?: number | null;
  latency_ms?: number | null;
}

export interface HealthSummary {
  healthy?: number;
  stale?: number;
  degraded?: number;
  failed?: number;
  disabled?: number;
}

/* -------------------------------------------------------------------------- */
/* Processing jobs                                                            */
/* -------------------------------------------------------------------------- */

export type JobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'retrying'
  | 'cancelled'
  | string;

export interface ProcessingJob {
  job_id: string;
  source?: string;
  dataset?: string;
  job_type?: string;
  status?: JobStatus;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  worker?: string;
  error?: string | null;
  retry_count?: number | null;
}

/* -------------------------------------------------------------------------- */
/* Alerts / warnings                                                          */
/* -------------------------------------------------------------------------- */

export type AlertSeverity =
  | 'Minor'
  | 'Moderate'
  | 'Severe'
  | 'Extreme'
  | 'Unknown'
  | string;

export interface Alert {
  warning_id: string;
  event_type?: string;
  severity?: AlertSeverity;
  certainty?: string;
  urgency?: string;
  headline?: string;
  description?: string;
  area_description?: string;
  issued_at?: string | null;
  effective_from?: string | null;
  expires_at?: string | null;
  source?: string;
  source_url?: string | null;
  geometry?: GeoJsonGeometry | null;
}

/* -------------------------------------------------------------------------- */
/* PFZ / fishing zones                                                        */
/* -------------------------------------------------------------------------- */

export interface Pfz {
  pfz_id: string;
  region?: string;
  advisory_text?: string;
  advisory_type?: string;
  issue_time?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  confidence?: number | null;
  sst_context?: number | null;
  chlorophyll_context?: number | null;
  source?: string;
  source_url?: string | null;
  geometry?: GeoJsonGeometry | null;
}

/* -------------------------------------------------------------------------- */
/* Evidence / lineage                                                         */
/* -------------------------------------------------------------------------- */

export interface Evidence {
  request_id: string;
  capability?: string;
  generated_at?: string | null;
  inputs?: Record<string, unknown>;
  input_datasets?: string[];
  sources?: SourceRef[];
  processing_steps?: EvidenceStep[];
  quality?: QualityInfo;
  meta?: EnvelopeMeta;
  result?: unknown;
}

export interface EvidenceStep {
  step: string;
  status?: string;
  detail?: string;
  processing_version?: string;
  at?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Minimal GeoJSON types (map layers)                                         */
/* -------------------------------------------------------------------------- */

export type GeoJsonPosition = [number, number] | [number, number, number];

export interface GeoJsonGeometry {
  type:
    | 'Point'
    | 'MultiPoint'
    | 'LineString'
    | 'MultiLineString'
    | 'Polygon'
    | 'MultiPolygon'
    | 'GeometryCollection';
  coordinates?: unknown;
  geometries?: GeoJsonGeometry[];
}

export interface GeoJsonFeature<P = Record<string, unknown>> {
  type: 'Feature';
  geometry: GeoJsonGeometry | null;
  properties: P;
  id?: string | number;
}

export interface GeoJsonFeatureCollection<P = Record<string, unknown>> {
  type: 'FeatureCollection';
  features: GeoJsonFeature<P>[];
}

/* -------------------------------------------------------------------------- */
/* Stream events (WS /v1/stream/alerts)                                       */
/* -------------------------------------------------------------------------- */

export interface StreamEvent {
  type: string;
  at?: string;
  payload?: unknown;
}
