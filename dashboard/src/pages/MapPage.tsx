import { useMemo, useState } from 'react';
import { api } from '../lib/apiClient';
import { useAsyncData } from '../hooks/useAsyncData';
import { MarineMap } from '../components/MarineMap';
import { ErrorState, LoadingState } from '../components/States';

/**
 * Map explorer: overlays active warning geometries (loaded globally on init)
 * and PFZ polygons (loaded when user queries a specific area).
 */
export function MapPage() {
  const [lat, setLat] = useState('15.2');
  const [lon, setLon] = useState('73.8');
  const [radius, setRadius] = useState('300');
  const [pfzQuery, setPfzQuery] = useState<{
    lat: number;
    lon: number;
    radius_km: number;
  } | null>(null);

  // Alerts load globally (no lat/lon required) — always show all active alerts
  const alerts = useAsyncData(
    (signal) => api.alerts({}, { signal }),
    [],
    { pollMs: 30_000 },
  );

  // PFZ only loads when user explicitly queries an area (lat/lon required by API)
  const pfz = useAsyncData(
    (signal) => {
      if (!pfzQuery) return Promise.resolve([]);
      return api.pfz(pfzQuery, { signal });
    },
    [pfzQuery ? JSON.stringify(pfzQuery) : 'none'],
    { pollMs: 60_000 },
  );

  const center = useMemo<[number, number]>(() => {
    if (pfzQuery) return [pfzQuery.lat, pfzQuery.lon];
    const la = Number(lat);
    const lo = Number(lon);
    if (!Number.isNaN(la) && !Number.isNaN(lo)) return [la, lo];
    return [15.2, 73.8]; // Default: Indian west coast
  }, [lat, lon, pfzQuery]);

  const applyQuery = () => {
    const la = Number(lat);
    const lo = Number(lon);
    const r = Number(radius);
    if (Number.isNaN(la) || Number.isNaN(lo)) return;
    setPfzQuery({
      lat: la,
      lon: lo,
      radius_km: Number.isNaN(r) ? 300 : r,
    });
  };

  const clearQuery = () => {
    setPfzQuery(null);
  };

  const loading = alerts.loading && !alerts.loaded;
  const error =
    alerts.error && !alerts.loaded
      ? alerts.error
      : pfz.error && !pfz.loaded
        ? pfz.error
        : null;

  const alertsWithGeom = (alerts.data ?? []).filter((a) => a.geometry);
  const pfzWithGeom = (pfz.data ?? []).filter((p) => p.geometry);

  return (
    <div>
      <div className="topbar">
        <div className="page-title">Map explorer</div>
      </div>

      <div className="control-row">
        <label className="field">
          Latitude
          <input
            type="number"
            step="0.1"
            value={lat}
            onChange={(e) => setLat(e.target.value)}
          />
        </label>
        <label className="field">
          Longitude
          <input
            type="number"
            step="0.1"
            value={lon}
            onChange={(e) => setLon(e.target.value)}
          />
        </label>
        <label className="field">
          Radius (km)
          <input
            type="number"
            step="10"
            value={radius}
            onChange={(e) => setRadius(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn btn--primary"
          style={{ alignSelf: 'flex-end' }}
          onClick={applyQuery}
        >
          Query PFZ
        </button>
        {pfzQuery && (
          <button
            type="button"
            className="btn"
            style={{ alignSelf: 'flex-end' }}
            onClick={clearQuery}
          >
            Clear PFZ
          </button>
        )}
      </div>

      {error ? (
        <ErrorState
          error={error}
          onRetry={() => {
            alerts.refetch();
            pfz.refetch();
          }}
        />
      ) : loading ? (
        <LoadingState rows={6} label="Loading map layers…" />
      ) : (
        <>
          <MarineMap
            pfz={pfz.data ?? []}
            alerts={alerts.data ?? []}
            center={center}
          />
          <p className="muted" style={{ marginTop: '0.6rem' }}>
            {alertsWithGeom.length} warning geometr
            {alertsWithGeom.length === 1 ? 'y' : 'ies'}
            {pfzQuery && (
              <>
                {' · '}
                {pfzWithGeom.length} PFZ zone{pfzWithGeom.length !== 1 ? 's' : ''}
                {' within '}
                {pfzQuery.radius_km} km of ({pfzQuery.lat.toFixed(1)},{' '}
                {pfzQuery.lon.toFixed(1)})
              </>
            )}
            {!pfzQuery && ' · Enter coordinates and click "Query PFZ" to load fishing zones'}
          </p>
        </>
      )}
    </div>
  );
}
