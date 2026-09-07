"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Circle,
  Marker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AlertModel, PFZModel, SafeRouteModel, ZoneModel } from "@/types/api";

// Severity color palette - muted & natural, not neon
const SEVERITY_COLORS: Record<string, { color: string; fill: string }> = {
  extreme: { color: "#dc2626", fill: "#ef4444" },
  severe: { color: "#ea580c", fill: "#f97316" },
  moderate: { color: "#d97706", fill: "#f59e0b" },
  minor: { color: "#2563eb", fill: "#3b82f6" },
  unknown: { color: "#475569", fill: "#64748b" },
};

const PFZ_STYLE: L.PathOptions = {
  color: "#10b981",
  weight: 2,
  dashArray: "4, 3",
  fillColor: "#059669",
  fillOpacity: 0.18,
};

const ZONE_STYLE: L.PathOptions = {
  color: "#a855f7",
  weight: 1.5,
  dashArray: "4, 4",
  fillColor: "#7c3aed",
  fillOpacity: 0.12,
};

const ROUTE_STYLE: L.PathOptions = {
  color: "#38bdf8",
  weight: 3,
  dashArray: "6, 4",
  opacity: 0.9,
};

interface OceanMapProps {
  center: [number, number];
  zoom?: number;
  selectedLocation: { lat: number; lon: number } | null;
  onSelectLocation: (lat: number, lon: number) => void;
  radiusKm?: number;
  alerts?: AlertModel[];
  pfzList?: PFZModel[];
  zones?: ZoneModel[];
  route?: SafeRouteModel | null;
  activeLayers: {
    alerts: boolean;
    pfz: boolean;
    zones: boolean;
    route: boolean;
  };
}

// Helper hook to capture map clicks
function MapClickHandler({
  onSelectLocation,
}: {
  onSelectLocation: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(e: L.LeafletMouseEvent) {
      onSelectLocation(Number(e.latlng.lat.toFixed(4)), Number(e.latlng.lng.toFixed(4)));
    },
  });
  return null;
}

// Helper to center the map when requested
function CenterController({ center }: { center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, map.getZoom(), { animate: true });
  }, [center, map]);
  return null;
}

function MapResizeHandler() {
  const map = useMap();
  useEffect(() => {
    const handleResize = () => map.invalidateSize();
    handleResize();
    const timer1 = setTimeout(handleResize, 100);
    const timer2 = setTimeout(handleResize, 400);
    window.addEventListener("resize", handleResize);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      window.removeEventListener("resize", handleResize);
    };
  }, [map]);
  return null;
}

// Ensure geographic reference labels sit cleanly between basemap and overlays
function MapPanesSetup() {
  const map = useMap();
  useEffect(() => {
    if (!map.getPane("ocean-labels")) {
      const pane = map.createPane("ocean-labels");
      pane.style.zIndex = "350";
      pane.style.pointerEvents = "none";
    }
  }, [map]);
  return null;
}

export default function OceanMap({
  center,
  zoom = 5,
  selectedLocation,
  onSelectLocation,
  radiusKm = 250,
  alerts = [],
  pfzList = [],
  zones = [],
  route = null,
  activeLayers,
}: OceanMapProps) {
  // Precision oceanographic probe marker icon
  const probeIcon = useMemo(() => {
    return L.divIcon({
      className: "custom-probe-marker",
      html: `
        <div style="position: relative; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;">
          <div style="position: absolute; width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid rgba(45, 212, 191, 0.45); background: rgba(45, 212, 191, 0.1); animation: sonarPing 3s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: absolute; width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid rgba(45, 212, 191, 0.75); background: rgba(3, 7, 16, 0.65);"></div>
          <div style="position: absolute; width: 26px; height: 1px; background: rgba(45, 212, 191, 0.55);"></div>
          <div style="position: absolute; width: 1px; height: 26px; background: rgba(45, 212, 191, 0.55);"></div>
          <div style="position: relative; width: 5px; height: 5px; border-radius: 50%; background: #2dd4bf; box-shadow: 0 0 6px rgba(45, 212, 191, 0.9);"></div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
  }, []);

  // Convert alerts to GeoJSON FeatureCollection
  const alertsGeoJson = useMemo(() => {
    const validAlerts = alerts.filter((a) => a.geometry);
    return {
      type: "FeatureCollection" as const,
      features: validAlerts.map((a) => ({
        type: "Feature" as const,
        geometry: a.geometry,
        properties: {
          uid: a.alert_uid,
          headline: a.headline || a.event_type,
          severity: a.severity?.toLowerCase() || "unknown",
          area: a.area_description || "",
          source: a.provider,
          expires_at: a.expires_at || a.valid_until,
        },
      })),
    };
  }, [alerts]);

  // Convert PFZ to GeoJSON FeatureCollection
  const pfzGeoJson = useMemo(() => {
    const validPfz = pfzList.filter((p) => p.geometry);
    return {
      type: "FeatureCollection" as const,
      features: validPfz.map((p) => ({
        type: "Feature" as const,
        geometry: p.geometry,
        properties: {
          uid: p.pfz_uid,
          region: p.region || "PFZ Zone",
          advisory: p.advisory_text || "Potential Fishing Zone detected",
          distance: p.distance_km,
          provider: p.provider,
          valid_until: p.valid_until,
        },
      })),
    };
  }, [pfzList]);

  // Convert zones to GeoJSON FeatureCollection
  const zonesGeoJson = useMemo(() => {
    const validZones = zones.filter((z) => z.geometry);
    return {
      type: "FeatureCollection" as const,
      features: validZones.map((z) => ({
        type: "Feature" as const,
        geometry: z.geometry,
        properties: {
          name: z.name,
          type: z.zone_type,
          restriction: z.restriction,
        },
      })),
    };
  }, [zones]);

  return (
    <div className="relative w-full h-full min-h-[450px]">
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom={true}
        className="w-full h-full z-10"
        style={{ width: "100%", height: "100%", minHeight: "450px" }}
        attributionControl={true}
      >
        <MapClickHandler onSelectLocation={onSelectLocation} />
        <CenterController center={center} />
        <MapResizeHandler />
        <MapPanesSetup />

        {/* 1. Base Geography: Land & Ocean Canvas (Esri World Dark Gray Base) */}
        <TileLayer
          className="ocean-tile-layer"
          attribution='Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />

        {/* 2. Geographic Labels: Countries, Cities, Seas, Coastlines (Esri World Dark Gray Reference) */}
        <TileLayer
          className="ocean-reference-layer"
          pane="ocean-labels"
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />

        {/* 1. Alerts Layer */}
        {activeLayers.alerts && alertsGeoJson.features.length > 0 && (
          <GeoJSON
            key={`alerts-${alertsGeoJson.features.length}`}
            data={alertsGeoJson as any}
            style={(feature: any) => {
              const sev = feature?.properties?.severity || "unknown";
              const palette = SEVERITY_COLORS[sev] || SEVERITY_COLORS.unknown;
              return {
                color: palette.color,
                weight: 2,
                fillColor: palette.fill,
                fillOpacity: 0.24,
              };
            }}
            onEachFeature={(feature: any, layer: L.Layer) => {
              const p = feature.properties;
              layer.bindPopup(`
                <div style="font-size: 12px; line-height: 1.4;">
                  <strong style="color: #f1f5f9;">⚠️ ${p.headline}</strong>
                  <div style="margin-top: 4px; color: #94a3b8;">Severity: <span style="text-transform: capitalize; color: #f59e0b;">${p.severity}</span></div>
                  ${p.area ? `<div style="color: #cbd5e1;">Area: ${p.area}</div>` : ""}
                  <div style="margin-top: 4px; font-size: 10px; color: #64748b;">Source: ${p.source}</div>
                </div>
              `);
            }}
          />
        )}

        {/* 2. PFZ Features Layer */}
        {activeLayers.pfz && pfzGeoJson.features.length > 0 && (
          <GeoJSON
            key={`pfz-${pfzGeoJson.features.length}`}
            data={pfzGeoJson as any}
            style={() => PFZ_STYLE}
            onEachFeature={(feature: any, layer: L.Layer) => {
              const p = feature.properties;
              layer.bindPopup(`
                <div style="font-size: 12px; line-height: 1.4;">
                  <strong style="color: #10b981;">🐟 ${p.region}</strong>
                  <p style="margin-top: 4px; color: #cbd5e1;">${p.advisory}</p>
                  <div style="margin-top: 4px; font-size: 10px; color: #64748b;">Source: ${p.provider} · Dist: ${p.distance} km</div>
                </div>
              `);
            }}
          />
        )}

        {/* 3. Marine Zones Layer */}
        {activeLayers.zones && zonesGeoJson.features.length > 0 && (
          <GeoJSON
            key={`zones-${zonesGeoJson.features.length}`}
            data={zonesGeoJson as any}
            style={() => ZONE_STYLE}
            onEachFeature={(feature: any, layer: L.Layer) => {
              const p = feature.properties;
              layer.bindPopup(`
                <div style="font-size: 12px; line-height: 1.4;">
                  <strong style="color: #a855f7;">⚓ ${p.name}</strong>
                  <div style="color: #94a3b8;">Type: ${p.type}</div>
                  ${p.restriction ? `<div style="color: #cbd5e1;">Restriction: ${p.restriction}</div>` : ""}
                </div>
              `);
            }}
          />
        )}

        {/* 4. Safe Route Path */}
        {activeLayers.route && route && route.geometry && (
          <GeoJSON
            key={`route-${route.route_risk_score}-${route.segments.length}`}
            data={route.geometry as any}
            style={() => ROUTE_STYLE}
          />
        )}

        {/* 5. Exploration Radius Perimeter */}
        {selectedLocation && radiusKm > 0 && (
          <Circle
            center={[selectedLocation.lat, selectedLocation.lon]}
            radius={radiusKm * 1000}
            pathOptions={{
              color: "#0d9488",
              weight: 1.2,
              dashArray: "4, 6",
              fillColor: "#0f766e",
              fillOpacity: 0.03,
            }}
          />
        )}

        {/* 6. Active Oceanographic Probe Marker */}
        {selectedLocation && (
          <Marker
            position={[selectedLocation.lat, selectedLocation.lon]}
            icon={probeIcon}
          >
            <Popup>
              <div className="text-xs font-mono space-y-1.5 p-1 min-w-[170px]">
                <div className="flex items-center space-x-1.5 text-teal-300 font-semibold border-b border-white/10 pb-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-300 animate-pulse" />
                  <span>Active Ocean Probe</span>
                </div>
                <div className="text-slate-300 text-[11px]">
                  {selectedLocation.lat.toFixed(4)}°N, {selectedLocation.lon.toFixed(4)}°E
                </div>
                <div className="text-[10px] text-slate-400">
                  Radius: {radiusKm} km observation window
                </div>
                <div className="text-[9px] text-slate-500 pt-0.5">
                  Click anywhere on the map to relocate probe
                </div>
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="absolute bottom-5 left-4 z-20 bg-slate-950/80 border border-white/10 rounded-full px-3.5 py-1.5 text-[11px] font-mono flex flex-wrap items-center gap-3 backdrop-blur-md shadow-lg">
        <div className="flex items-center space-x-1.5 text-slate-400">
          <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
          <span className="text-slate-300">Probe: {radiusKm}km</span>
        </div>
        <span className="text-white/20">|</span>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400/90" />
          <span className="text-slate-300">PFZ ({pfzList.length})</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-rose-400/90" />
          <span className="text-slate-300">Alerts ({alerts.length})</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-purple-400/90" />
          <span className="text-slate-300">Zones ({zones.length})</span>
        </div>
      </div>
    </div>
  );
}
