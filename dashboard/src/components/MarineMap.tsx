import { useMemo, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, GeoJSON, LayersControl, useMap } from 'react-leaflet';
import L, { type PathOptions } from 'leaflet';
import type { Feature, GeoJsonObject } from 'geojson';
import 'leaflet/dist/leaflet.css';
import type { Alert, Pfz, GeoJsonFeatureCollection } from '../types/api';

/**
 * Operational map (Leaflet + OpenStreetMap tiles) rendering PFZ polygons and
 * active warning geometries as toggleable GeoJSON layers with severity-based
 * coloring, informative popups, and auto-zoom to fit.
 */

const PFZ_STYLE: PathOptions = {
  color: '#0b8a52',
  weight: 2,
  fillColor: '#26c281',
  fillOpacity: 0.35,
};

const SEVERITY_COLORS: Record<string, { color: string; fill: string }> = {
  extreme: { color: '#7f1d1d', fill: '#dc2626' },
  severe: { color: '#991b1b', fill: '#ef4444' },
  moderate: { color: '#b45309', fill: '#f59e0b' },
  minor: { color: '#1e40af', fill: '#60a5fa' },
  unknown: { color: '#6b7280', fill: '#9ca3af' },
};

function warningStyle(severity?: string): PathOptions {
  const s = (severity ?? 'unknown').toLowerCase();
  const c = SEVERITY_COLORS[s] ?? SEVERITY_COLORS.unknown;
  return {
    color: c.color,
    weight: 2,
    fillColor: c.fill,
    fillOpacity: 0.3,
    dashArray: s === 'extreme' ? '4 2' : undefined,
  };
}

const POINT_RADIUS = 7;

function circleMarker(latlng: L.LatLng, style: PathOptions) {
  return L.circleMarker(latlng, { radius: POINT_RADIUS, ...style });
}

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toFeatureCollection<T extends { geometry?: unknown }>(
  items: T[],
  buildProps: (item: T) => Record<string, unknown>,
): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: items
      .filter((i) => i.geometry)
      .map((i) => ({
        type: 'Feature' as const,
        geometry: i.geometry as GeoJsonFeatureCollection['features'][number]['geometry'],
        properties: buildProps(i),
      })),
  };
}

function formatPopupAlert(props: Record<string, unknown>): string {
  const title = props.title as string ?? 'Warning';
  const severity = props.severity as string ?? '';
  const area = props.area as string ?? '';
  const expires = props.expires_at as string ?? '';
  const source = props.source as string ?? '';

  return `
    <div style="max-width:280px; font-size:13px;">
      <div style="font-weight:700; font-size:14px; margin-bottom:4px;">
        ⚠️ ${escapeHtml(title)}
      </div>
      ${severity ? `<div><strong>Severity:</strong> <span style="text-transform:capitalize">${escapeHtml(severity)}</span></div>` : ''}
      ${area ? `<div><strong>Area:</strong> ${escapeHtml(area)}</div>` : ''}
      ${expires ? `<div><strong>Expires:</strong> ${escapeHtml(expires)}</div>` : ''}
      ${source ? `<div style="color:#888; margin-top:4px;">Source: ${escapeHtml(source)}</div>` : ''}
    </div>`;
}

function formatPopupPfz(props: Record<string, unknown>): string {
  const title = props.title as string ?? 'PFZ';
  const advisory = props.advisory as string ?? '';
  const validUntil = props.valid_until as string ?? '';
  const source = props.source as string ?? '';
  const sst = props.sst_context as string ?? '';
  const chl = props.chlorophyll_context as string ?? '';

  return `
    <div style="max-width:280px; font-size:13px;">
      <div style="font-weight:700; font-size:14px; margin-bottom:4px;">
        🐟 ${escapeHtml(title)}
      </div>
      ${advisory ? `<div>${escapeHtml(advisory)}</div>` : ''}
      ${sst ? `<div><strong>SST:</strong> ${escapeHtml(sst)}°C</div>` : ''}
      ${chl ? `<div><strong>CHL:</strong> ${escapeHtml(chl)} mg/m³</div>` : ''}
      ${validUntil ? `<div><strong>Valid until:</strong> ${escapeHtml(validUntil)}</div>` : ''}
      ${source ? `<div style="color:#888; margin-top:4px;">Source: ${escapeHtml(source)}</div>` : ''}
    </div>`;
}

function onEachFeature(feature: Feature, layer: L.Layer) {
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const kind = props.kind as string;
  const html = kind === 'pfz' ? formatPopupPfz(props) : formatPopupAlert(props);
  layer.bindPopup(html);
}

/** Auto-zoom to fit all features when data changes. */
function FitBounds({ geoJsonRef }: { geoJsonRef: React.RefObject<L.GeoJSON | null> }) {
  const map = useMap();
  useEffect(() => {
    if (geoJsonRef.current) {
      const bounds = geoJsonRef.current.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 });
      }
    }
  }, [map, geoJsonRef]);
  return null;
}

export interface MarineMapProps {
  pfz?: Pfz[];
  alerts?: Alert[];
  center?: [number, number];
  zoom?: number;
}

export function MarineMap({
  pfz = [],
  alerts = [],
  center = [15.2, 73.8],
  zoom = 5,
}: MarineMapProps) {
  const alertsRef = useRef<L.GeoJSON | null>(null);

  const pfzFc = useMemo(
    () =>
      toFeatureCollection(pfz, (p) => ({
        kind: 'pfz',
        title: p.region ?? p.pfz_id,
        advisory: p.advisory_text ?? '',
        valid_until: p.valid_until ?? '',
        source: p.source ?? '',
        sst_context: p.sst_context ?? '',
        chlorophyll_context: p.chlorophyll_context ?? '',
      })),
    [pfz],
  );

  const alertsFc = useMemo(
    () =>
      toFeatureCollection(
        alerts.filter((a) => a.geometry),
        (a) => ({
          kind: 'alert',
          title: a.headline ?? a.event_type ?? a.warning_id,
          severity: a.severity ?? 'Unknown',
          area: a.area_description ?? '',
          expires_at: a.expires_at ?? '',
          source: a.source ?? '',
        }),
      ),
    [alerts],
  );

  const hasFeatures = alertsFc.features.length > 0 || pfzFc.features.length > 0;

  return (
    <div className="map-frame">
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom
        style={{ height: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <LayersControl position="topright">
          <LayersControl.Overlay
            checked
            name={`PFZ (${pfzFc.features.length})`}
          >
            {pfzFc.features.length > 0 ? (
              <GeoJSON
                key={`pfz-${pfzFc.features.length}`}
                data={pfzFc as unknown as GeoJsonObject}
                style={() => PFZ_STYLE}
                pointToLayer={(_f, ll) => circleMarker(ll, PFZ_STYLE)}
                onEachFeature={onEachFeature}
              />
            ) : (
              <GeoJSON
                data={
                  { type: 'FeatureCollection', features: [] } as unknown as GeoJsonObject
                }
              />
            )}
          </LayersControl.Overlay>
          <LayersControl.Overlay
            checked
            name={`Warnings (${alertsFc.features.length})`}
          >
            {alertsFc.features.length > 0 ? (
              <GeoJSON
                ref={alertsRef}
                key={`alerts-${alertsFc.features.length}`}
                data={alertsFc as unknown as GeoJsonObject}
                style={(feature) => {
                  const sev = (feature?.properties?.severity ?? 'unknown') as string;
                  return warningStyle(sev);
                }}
                pointToLayer={(_f, ll) => circleMarker(ll, warningStyle('unknown'))}
                onEachFeature={onEachFeature}
              />
            ) : (
              <GeoJSON
                data={
                  { type: 'FeatureCollection', features: [] } as unknown as GeoJsonObject
                }
              />
            )}
          </LayersControl.Overlay>
        </LayersControl>
        {hasFeatures && <FitBounds geoJsonRef={alertsRef} />}
      </MapContainer>
      <div className="map-legend">
        <span>
          <span className="legend-swatch" style={{ background: '#26c281' }} /> PFZ
        </span>
        <span>
          <span className="legend-swatch" style={{ background: '#ef4444' }} /> Severe
        </span>
        <span>
          <span className="legend-swatch" style={{ background: '#f59e0b' }} /> Moderate
        </span>
        <span>
          <span className="legend-swatch" style={{ background: '#60a5fa' }} /> Minor
        </span>
      </div>
    </div>
  );
}
