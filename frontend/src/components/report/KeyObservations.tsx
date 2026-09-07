"use client";

import type { ObservationModel } from "@/types/api";

interface KeyObservationsProps {
  observations: ObservationModel[];
  tides?: ObservationModel[];
  radiusKm?: number;
}

interface MetricItem {
  key: string;
  icon: string;
  humanTitle: string;
  value: string;
  unit: string;
  plainDescriptor: string;
  scientificName: string;
  stationId?: string | null;
  distanceKm?: number | null;
  provider?: string;
}

function getWaveDescriptor(val: number): string {
  if (val < 0.5) return "Calm";
  if (val < 1.25) return "Smooth";
  if (val < 2.5) return "Moderate";
  if (val < 4.0) return "Rough";
  return "High seas";
}

function getSstDescriptor(val: number): string {
  if (val >= 28) return "Warm";
  if (val >= 24) return "Mild";
  return "Cool";
}

function getWindDescriptor(val: number): string {
  if (val < 3.3) return "Light";
  if (val < 8.0) return "Gentle";
  if (val < 13.9) return "Fresh";
  return "Strong";
}

function getPressureDescriptor(val: number): string {
  if (val >= 1013) return "Standard";
  if (val >= 1005) return "Moderate";
  return "Low";
}

export function KeyObservations({ observations, tides = [], radiusKm = 150 }: KeyObservationsProps) {
  // Extract specific observations
  const waveObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("wave_height") || o.parameter.toLowerCase().includes("wave")
  );
  const sstObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("sea_surface_temperature") || o.parameter.toLowerCase().includes("sst")
  );
  const windObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("wind_speed")
  );
  const pressureObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("pressure") || o.parameter.toLowerCase().includes("mslp")
  );

  // Tide observation from observations or tides list
  const tideObs =
    observations.find(
      (o) => o.parameter.toLowerCase().includes("water_level") || o.parameter.toLowerCase().includes("tide")
    ) ||
    tides.find(
      (t) => t.parameter.toLowerCase().includes("water_level") || t.parameter.toLowerCase().includes("tide")
    );

  const items: MetricItem[] = [];

  // 1. Wave Height
  if (waveObs && typeof waveObs.value === "number") {
    items.push({
      key: "wave",
      icon: "🌊",
      humanTitle: "WAVE",
      value: waveObs.value.toFixed(1),
      unit: waveObs.unit || "m",
      plainDescriptor: `${getWaveDescriptor(waveObs.value)} waves`,
      scientificName: "Significant wave height (Hs)",
      stationId: waveObs.station_id,
      distanceKm: waveObs.distance_km,
      provider: waveObs.provider || "IMD",
    });
  }

  // 2. Sea Surface Temperature
  if (sstObs && typeof sstObs.value === "number") {
    const rawUnit = sstObs.unit || "°C";
    const cleanUnit = rawUnit.toLowerCase().includes("deg") ? "°C" : rawUnit;
    items.push({
      key: "sst",
      icon: "🌡",
      humanTitle: "WATER",
      value: sstObs.value.toFixed(1),
      unit: cleanUnit,
      plainDescriptor: `${getSstDescriptor(sstObs.value)} tropical water`,
      scientificName: "Sea surface temperature",
      stationId: sstObs.station_id,
      distanceKm: sstObs.distance_km,
      provider: sstObs.provider || "IMD",
    });
  }

  // 3. Wind Speed
  if (windObs && typeof windObs.value === "number") {
    items.push({
      key: "wind",
      icon: "💨",
      humanTitle: "WIND",
      value: windObs.value.toFixed(1),
      unit: windObs.unit || "m/s",
      plainDescriptor: `${getWindDescriptor(windObs.value)} breeze`,
      scientificName: "Surface wind velocity",
      stationId: windObs.station_id,
      distanceKm: windObs.distance_km,
      provider: windObs.provider || "IMD",
    });
  }

  // 4. Sea-Level Pressure
  if (pressureObs && typeof pressureObs.value === "number") {
    items.push({
      key: "pressure",
      icon: "🔘",
      humanTitle: "PRESSURE",
      value: Math.round(pressureObs.value).toString(),
      unit: pressureObs.unit || "hPa",
      plainDescriptor: `${getPressureDescriptor(pressureObs.value)} low pressure`,
      scientificName: "Mean sea-level pressure",
      stationId: pressureObs.station_id,
      distanceKm: pressureObs.distance_km,
      provider: pressureObs.provider || "IMD",
    });
  }

  // 5. Tide Level (when available)
  if (tideObs && typeof tideObs.value === "number") {
    items.push({
      key: "tide",
      icon: "⚓",
      humanTitle: "TIDE",
      value: tideObs.value.toFixed(2),
      unit: tideObs.unit || "m",
      plainDescriptor: "Normal water level",
      scientificName: "Coastal gauge datum level",
      stationId: tideObs.station_id,
      distanceKm: tideObs.distance_km,
      provider: tideObs.provider || "INCOIS",
    });
  }

  // If no in-situ observations were returned
  if (items.length === 0) {
    return (
      <section className="space-y-4 font-sans">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
          <div className="flex items-center space-x-2.5">
            <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">02</span>
            <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
              At A Glance
            </h2>
          </div>
          <span className="text-[11.5px] text-[#71767e] font-light">
            In-situ telemetry · Verified sensor stations
          </span>
        </div>

        <div className="py-4 px-1 text-sm text-[#8e8e93] font-light flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#16181d]">
          <p>
            No in-situ moored buoys or coastal gauges were recorded within the selected {radiusKm} km area.
          </p>
          <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#111418] border border-[#1b222a] shrink-0 self-start sm:self-auto">
            Source coverage · Limited
          </span>
        </div>
      </section>
    );
  }

  const colClass =
    items.length === 1
      ? "grid-cols-1"
      : items.length === 2
      ? "grid-cols-2"
      : items.length === 3
      ? "grid-cols-1 sm:grid-cols-3"
      : items.length === 4
      ? "grid-cols-2 lg:grid-cols-4"
      : "grid-cols-2 md:grid-cols-3 lg:grid-cols-5";

  // Build a concise 1-sentence "SO WHAT?" summary for current conditions
  const summaryParts: string[] = [];
  const waveItem = items.find((i) => i.key === "wave");
  const sstItem = items.find((i) => i.key === "sst");
  const windItem = items.find((i) => i.key === "wind");

  if (waveItem) summaryParts.push(`${waveItem.plainDescriptor.toLowerCase()} (${waveItem.value} ${waveItem.unit})`);
  if (sstItem) summaryParts.push(`${sstItem.plainDescriptor.toLowerCase()} (${sstItem.value} ${sstItem.unit})`);
  if (windItem) summaryParts.push(`${windItem.plainDescriptor.toLowerCase()} (${windItem.value} ${windItem.unit})`);

  const currentConditionsSentence =
    summaryParts.length > 0
      ? `Conditions currently feature ${summaryParts.join(", ")}.`
      : "Measured surface parameters remain within standard operational bounds.";

  return (
    <section className="space-y-4 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">02</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            At A Glance
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Real-time in-situ environmental snapshot
        </span>
      </div>

      {/* Responsive Visual Metric Grid (Reference 1) */}
      <div className={`grid ${colClass} gap-3 sm:gap-4`}>
        {items.map((item) => (
          <div
            key={item.key}
            className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col justify-between space-y-3 relative group hover:border-[#2a3442] transition-colors"
          >
            {/* Header: Icon + Parameter Tag */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono tracking-[0.14em] uppercase text-[#7FCBC5] font-medium flex items-center space-x-1.5">
                <span>{item.icon}</span>
                <span>{item.humanTitle}</span>
              </span>
              <span className="w-1.5 h-1.5 rounded-full bg-[#7FCBC5]/60" />
            </div>

            {/* Visually Dominant Numerical Figure */}
            <div className="space-y-1">
              <div className="flex items-baseline space-x-1.5">
                <span className="text-4xl sm:text-5xl lg:text-5xl font-light font-mono text-white tracking-tight leading-none">
                  {item.value}
                </span>
                <span className="text-base font-mono text-[#7FCBC5] font-light">
                  {item.unit}
                </span>
              </div>

              {/* Short Human-Readable Descriptor */}
              <div className="text-sm sm:text-base text-[#F4F7F5] font-normal pt-1">
                {item.plainDescriptor}
              </div>
            </div>

            {/* Station Attribution */}
            <div className="pt-2 border-t border-[#14181f] text-[10.5px] font-mono text-[#71767e]">
              {item.stationId ? (
                <div className="truncate text-[#8e8e93]">
                  Station {item.stationId} · {item.provider || "IMD"}
                  {item.distanceKm !== null && item.distanceKm !== undefined
                    ? ` · ${item.distanceKm === 0 ? "at site" : `${item.distanceKm.toFixed(0)} km`}`
                    : ""}
                </div>
              ) : (
                <div className="truncate text-[#71767e]">{item.scientificName}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Human-First "What it means" Interpretation */}
      <div className="px-3.5 py-2.5 rounded-lg bg-[#0c0f13] border border-[#181d24] flex items-center space-x-2.5 text-xs">
        <span className="text-[10px] font-mono uppercase tracking-wider text-[#7FCBC5] font-medium shrink-0">
          What it means
        </span>
        <span className="text-[#BDCDC9] font-light">
          {currentConditionsSentence}
        </span>
      </div>
    </section>
  );
}