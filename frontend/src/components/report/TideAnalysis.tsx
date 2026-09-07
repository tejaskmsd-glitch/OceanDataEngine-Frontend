"use client";

import { MapPin } from "lucide-react";
import type { ObservationModel } from "@/types/api";

interface TideAnalysisProps {
  tides: ObservationModel[];
  radiusKm?: number;
}

function cleanStationName(stationId?: string | null): string {
  if (!stationId) return "Coastal Gauge";
  const stripped = stationId.replace(/^TG_/i, "").replace(/_/g, " ");
  // Capitalize properly
  return stripped.charAt(0).toUpperCase() + stripped.slice(1).toLowerCase();
}

export function TideAnalysis({ tides, radiusKm = 150 }: TideAnalysisProps) {
  const tideObs = tides.filter(
    (t) =>
      t.parameter.toLowerCase().includes("water_level") ||
      t.parameter.toLowerCase().includes("tide")
  );

  if (tideObs.length === 0) {
    return (
      <section className="space-y-4 font-sans">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
          <div className="flex items-center space-x-2.5">
            <span className="text-[10.5px] font-mono uppercase tracking-[0.16em] text-[#7FCBC5] px-1.5 py-0.5 rounded bg-[#15616d]/20 border border-[#15616d]/40">
              COASTAL GAUGES
            </span>
            <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
              Tide Levels Near This Area
            </h2>
          </div>
          <span className="text-[11.5px] text-[#71767e] font-light">
            Coastal tide gauge network
          </span>
        </div>

        <div className="py-4 px-1 text-sm text-[#8e8e93] font-light flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#16181d]">
          <p>
            No coastal tide gauges were located within the search radius. Predictive harmonic curves are not synthesized.
          </p>
          <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#111418] border border-[#1b222a] shrink-0 self-start sm:self-auto">
            Source coverage · Limited
          </span>
        </div>
      </section>
    );
  }

  const values = tideObs.map((t) => t.value || 0);
  const maxLevel = Math.max(2.0, Math.max(...values) * 1.15);

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[10.5px] font-mono uppercase tracking-[0.16em] text-[#7FCBC5] px-1.5 py-0.5 rounded bg-[#15616d]/20 border border-[#15616d]/40">
            COASTAL GAUGES
          </span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Tide Levels Near This Area
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Instantaneous water levels above datum · INCOIS TEWS coastal network
        </span>
      </div>

      {tideObs.length === 1 ? (
        /* Single Station Strong Visual Card (Section 8) */
        <div className="p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <MapPin className="w-4 h-4 text-[#7FCBC5]" />
              <span className="text-white font-medium text-sm">
                {cleanStationName(tideObs[0].station_id)} Coastal Gauge
              </span>
              <span className="text-xs font-mono text-[#71767e]">
                ({tideObs[0].station_id})
              </span>
            </div>
            {tideObs[0].distance_km !== undefined && tideObs[0].distance_km !== null && (
              <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#11161d] border border-[#1e2733]">
                {tideObs[0].distance_km === 0 ? "at site" : `${tideObs[0].distance_km.toFixed(0)} km away`}
              </span>
            )}
          </div>

          <div className="flex items-baseline space-x-2">
            <span className="text-4xl sm:text-5xl font-light font-mono text-white tracking-tight">
              {tideObs[0].value?.toFixed(2) ?? "—"}
            </span>
            <span className="text-sm font-mono text-[#7FCBC5]">
              {tideObs[0].unit || "m"}
            </span>
            <span className="text-xs text-[#BDCDC9] font-light ml-2">
              Water level above chart datum
            </span>
          </div>

          {/* Simple horizontal level gauge */}
          <div className="space-y-1 pt-1">
            <div className="w-full h-2 rounded-full bg-[#14181e] overflow-hidden">
              <div
                className="h-full bg-[#7FCBC5] rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(10, ((tideObs[0].value || 0) / maxLevel) * 100))}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono text-[#71767e]">
              <span>0 m</span>
              <span>Datum reference scale (max: {maxLevel.toFixed(1)} m)</span>
            </div>
          </div>

          <div className="pt-2 border-t border-[#14181f] flex flex-wrap items-center justify-between gap-2 text-[10.5px] font-mono text-[#71767e]">
            <span>Provider: {tideObs[0].provider || "INCOIS TEWS"}</span>
            <span>Observed: {tideObs[0].observed_at ? new Date(tideObs[0].observed_at).toISOString().replace("T", " ").replace("Z", " UTC").slice(0, 16) : "Recent snapshot"}</span>
          </div>
        </div>
      ) : (
        /* Multi-Station Comparative Bar Visualization (Section 8) */
        <div className="p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8e8e93] font-mono border-b border-[#181d24] pb-2">
            <span className="uppercase tracking-wider">Tide Level Comparison</span>
            <span className="text-[#7FCBC5]">{tideObs.length} Reporting Stations</span>
          </div>

          <div className="space-y-3.5">
            {tideObs.map((t, idx) => {
              const val = t.value || 0;
              const pct = Math.min(100, Math.max(6, (val / maxLevel) * 100));
              const stationName = cleanStationName(t.station_id);

              return (
                <div key={idx} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center space-x-2">
                      <span className="text-white font-mono font-medium">
                        {stationName}
                      </span>
                      {t.distance_km !== undefined && t.distance_km !== null && (
                        <span className="text-[10.5px] font-mono text-[#71767e]">
                          ({t.distance_km.toFixed(0)} km)
                        </span>
                      )}
                    </div>
                    <div className="flex items-center space-x-1 font-mono">
                      <span className="text-white font-medium text-sm">
                        {val.toFixed(2)}
                      </span>
                      <span className="text-xs text-[#7FCBC5]">
                        {t.unit || "m"}
                      </span>
                    </div>
                  </div>

                  {/* Proportional visual bar */}
                  <div className="w-full h-2.5 rounded-full bg-[#14181e] overflow-hidden border border-[#1b2129]">
                    <div
                      className="h-full bg-gradient-to-r from-[#15616d] to-[#7FCBC5] rounded-full transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-[#71767e] pt-1">
            <span>Scale: 0 m</span>
            <span>Max reference: {maxLevel.toFixed(1)} m</span>
          </div>

          <p className="text-[11px] text-[#71767e] font-light pt-2 border-t border-[#151920]">
            Telemetry from Indian Tsunami Early Warning System tide stations. Continuous harmonic sinusoidal predictions are not inferred.
          </p>
        </div>
      )}
    </section>
  );
}