"use client";

import type { ForecastModel, ObservationModel } from "@/types/api";

interface WeatherForecastChartProps {
  forecasts: ForecastModel[];
  currentObs?: ObservationModel[];
  radiusKm?: number;
}

function getWindBeaufort(speed?: number | null): string {
  if (speed === null || speed === undefined) return "Wind";
  if (speed < 0.5) return "Calm";
  if (speed < 1.5) return "Light air";
  if (speed < 3.3) return "Light breeze";
  if (speed < 5.5) return "Gentle breeze";
  if (speed < 8.0) return "Moderate breeze";
  if (speed < 10.8) return "Fresh breeze";
  if (speed < 13.9) return "Strong breeze";
  if (speed < 17.2) return "High wind";
  if (speed < 20.7) return "Gale";
  if (speed < 24.5) return "Strong gale";
  return "Storm force";
}

function getCardinalDirection(degrees?: number | null): string {
  if (degrees === null || degrees === undefined) return "";
  const directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const index = Math.round((degrees % 360) / 22.5) % 16;
  return directions[index];
}

export function WeatherForecastChart({ forecasts, currentObs = [], radiusKm = 150 }: WeatherForecastChartProps) {
  // Extract in-situ observations
  const currentWind = currentObs.find((o) => o.parameter.toLowerCase().includes("wind_speed"));
  const currentWindDir = currentObs.find((o) => o.parameter.toLowerCase().includes("wind_direction"));
  const currentPressure = currentObs.find((o) =>
    o.parameter.toLowerCase().includes("pressure") || o.parameter.toLowerCase().includes("mslp")
  );

  // Group forecasts by forecast_hour
  const hoursMap = new Map<number, { wind?: number; windDir?: number; mslp?: number; rain?: number; time?: string }>();

  forecasts.forEach((f) => {
    if (f.forecast_hour === null || f.forecast_hour === undefined || f.value === null) return;
    const hour = f.forecast_hour;
    const entry = hoursMap.get(hour) || { time: f.valid_from || undefined };
    const pLower = f.parameter.toLowerCase();

    if (pLower.includes("wind_speed")) entry.wind = f.value;
    else if (pLower.includes("wind_direction") || pLower.includes("wind_dir")) entry.windDir = f.value;
    else if (pLower.includes("mslp") || pLower.includes("pressure")) entry.mslp = f.value;
    else if (pLower.includes("rain") || pLower.includes("precip")) entry.rain = f.value;

    hoursMap.set(hour, entry);
  });

  const sortedHours = Array.from(hoursMap.keys()).sort((a, b) => a - b);
  const hasForecasts = sortedHours.length > 0;
  const hasBuoyObs = currentWind || currentPressure;

  if (!hasForecasts && !hasBuoyObs) {
    return (
      <section className="space-y-4 font-sans">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
          <div className="flex items-center space-x-2.5">
            <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">04</span>
            <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
              Weather Around This Area
            </h2>
          </div>
          <span className="text-[11.5px] text-[#71767e] font-light">
            Atmospheric conditions & trajectory
          </span>
        </div>

        <div className="py-4 px-1 text-sm text-[#8e8e93] font-light flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#16181d]">
          <p>
            Atmospheric forecasts and weather observations are not available for this {radiusKm} km search window in the current ingestion cycle.
          </p>
          <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#111418] border border-[#1b222a] shrink-0 self-start sm:self-auto">
            Atmosphere · Idle
          </span>
        </div>
      </section>
    );
  }

  // Determine displayed values
  // For wind:
  const firstFcWind = hasForecasts ? hoursMap.get(sortedHours[0])?.wind : undefined;
  const firstFcWindDir = hasForecasts ? hoursMap.get(sortedHours[0])?.windDir : undefined;
  const activeWindVal = currentWind?.value ?? firstFcWind;
  const activeWindDirVal = currentWindDir?.value ?? firstFcWindDir;
  const windDirCardinal = getCardinalDirection(activeWindDirVal);
  const windBeaufort = getWindBeaufort(activeWindVal);

  // For pressure:
  const firstFcMslp = hasForecasts ? hoursMap.get(sortedHours[0])?.mslp : undefined;
  const lastFcMslp = hasForecasts ? hoursMap.get(sortedHours[sortedHours.length - 1])?.mslp : undefined;
  const activeMslpVal = currentPressure?.value ?? firstFcMslp;
  const pressureDelta = (firstFcMslp !== undefined && lastFcMslp !== undefined && sortedHours.length > 1)
    ? lastFcMslp - firstFcMslp
    : null;

  let pressureTrendLabel = "Steady barometric pressure";
  let pressureMeaning = "Stable maritime atmospheric conditions likely.";
  if (pressureDelta !== null) {
    if (pressureDelta < -1.5) {
      pressureTrendLabel = `Falling (${pressureDelta.toFixed(1)} hPa)`;
      pressureMeaning = "Falling pressure may indicate approaching weather disturbance or wind pickup.";
    } else if (pressureDelta > 1.5) {
      pressureTrendLabel = `Rising (+${pressureDelta.toFixed(1)} hPa)`;
      pressureMeaning = "Rising pressure indicates settling weather and clearing skies.";
    }
  } else if (activeMslpVal !== undefined && activeMslpVal !== null) {
    if (activeMslpVal < 1005) {
      pressureTrendLabel = "Moderate low pressure";
      pressureMeaning = "Convective cloudiness or breezy conditions typical of maritime troughs.";
    } else if (activeMslpVal > 1015) {
      pressureTrendLabel = "High pressure";
      pressureMeaning = "Fair weather and stable sea-level atmosphere.";
    }
  }

  // For rainfall:
  const rainEntries = sortedHours
    .map((h) => ({ hour: h, rain: hoursMap.get(h)?.rain }))
    .filter((e): e is { hour: number; rain: number } => e.rain !== undefined && e.rain !== null);
  const hasRainData = rainEntries.length > 0;
  const maxRain = hasRainData ? Math.max(...rainEntries.map((e) => e.rain)) : 0;
  const firstRainEntry = rainEntries[0];

  // Dynamic "SO WHAT?" summary calculation
  let soWhatText = "";
  if (hasForecasts) {
    const leadHoursText = `+${sortedHours[0]}h${sortedHours.length > 1 ? ` to +${sortedHours[sortedHours.length - 1]}h` : ""}`;
    
    if (hasRainData && maxRain > 0) {
      soWhatText = `Model projects ${activeWindVal ? `${activeWindVal.toFixed(1)} m/s wind` : "active wind"} with ${activeMslpVal ? `${activeMslpVal.toFixed(0)} hPa pressure` : "surface pressure"} and ${maxRain.toFixed(1)} mm rainfall at ${leadHoursText}, indicating active maritime weather that requires monitoring.`;
    } else if (pressureDelta !== null && pressureDelta < -1.0) {
      soWhatText = `Wind remains near ${activeWindVal ? activeWindVal.toFixed(1) : "—"} m/s with falling pressure (${firstFcMslp?.toFixed(0)} → ${lastFcMslp?.toFixed(0)} hPa), suggesting deteriorating conditions over the forecast horizon.`;
    } else {
      soWhatText = `Atmospheric conditions project steady ${activeWindVal ? `${activeWindVal.toFixed(1)} m/s (${windBeaufort.toLowerCase()})` : "winds"} and stable barometric pressure through ${leadHoursText} lead time.`;
    }
  } else {
    soWhatText = `Buoy telemetry reports ${activeWindVal ? `${activeWindVal.toFixed(1)} m/s (${windBeaufort.toLowerCase()})` : "nominal wind"} and ${activeMslpVal ? `${activeMslpVal.toFixed(1)} hPa MSLP` : "stable pressure"}. No numerical forecast model grid was mapped within this radius.`;
  }

  // SVG Chart Dimensions for Wind Panel
  const windSvgWidth = 340;
  const windSvgHeight = 100;
  const padL = 36;
  const padR = 20;
  const padT = 16;
  const padB = 24;
  const cWidth = windSvgWidth - padL - padR;
  const cHeight = windSvgHeight - padT - padB;

  const windValues = sortedHours.map((h) => hoursMap.get(h)?.wind).filter((v): v is number => v !== undefined);
  const maxWindScale = windValues.length > 0 ? Math.max(16, Math.ceil(Math.max(...windValues) + 2)) : 20;

  const windPoints = sortedHours.map((h, i) => {
    const x = sortedHours.length === 1 ? padL + cWidth / 2 : padL + (i / (sortedHours.length - 1)) * cWidth;
    const val = hoursMap.get(h)?.wind ?? 0;
    const y = padT + cHeight - (val / maxWindScale) * cHeight;
    return { hour: h, val, x, y };
  });

  const windLinePath = windPoints.reduce((acc, curr, idx) => (idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`), "");

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">04</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Weather Around This Area
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Surface wind velocity, barometric pressure & precipitation
        </span>
      </div>

      {/* THREE SEPARATE VISUAL PANELS (Requirement 6) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* PANEL A: WIND */}
        <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#BDCDC9] font-medium">
                Wind
              </span>
              <span className="text-[10px] font-mono text-[#7FCBC5] px-1.5 py-0.5 rounded bg-[#15616d]/20 border border-[#15616d]/30">
                {windBeaufort}
              </span>
            </div>

            <div className="flex items-baseline space-x-2">
              <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
                {activeWindVal !== undefined && activeWindVal !== null ? activeWindVal.toFixed(1) : "—"}
              </span>
              <span className="text-xs font-mono text-[#BDCDC9]">m/s</span>
            </div>

            <div className="text-xs text-[#BDCDC9] font-light">
              {windDirCardinal ? (
                <span>Blowing from {windDirCardinal} ({activeWindDirVal?.toFixed(0)}°)</span>
              ) : (
                <span>Surface wind speed</span>
              )}
            </div>
          </div>

          {/* Wind Trend Mini-Chart or In-situ Badge */}
          {hasForecasts && windValues.length > 0 ? (
            <div className="pt-2 border-t border-[#14181e] space-y-1">
              <div className="text-[10px] font-mono text-[#71767e] flex items-center justify-between">
                <span>FORECAST TRAJECTORY</span>
                <span>Max: {maxWindScale} m/s</span>
              </div>
              <svg viewBox={`0 0 ${windSvgWidth} ${windSvgHeight}`} className="w-full h-auto select-none">
                {/* Horizontal Baseline */}
                <line x1={padL} y1={padT + cHeight} x2={padL + cWidth} y2={padT + cHeight} stroke="#181e26" strokeWidth="1" />
                {/* Mid Gridline */}
                <line x1={padL} y1={padT + cHeight / 2} x2={padL + cWidth} y2={padT + cHeight / 2} stroke="#181e26" strokeWidth="1" strokeDasharray="3 3" />
                
                {/* Wind Path */}
                {windLinePath && (
                  <path d={windLinePath} fill="none" stroke="#7FCBC5" strokeWidth="2" strokeLinecap="round" />
                )}

                {/* Wind Points */}
                {windPoints.map((p, idx) => (
                  <g key={idx}>
                    <circle cx={p.x} cy={p.y} r={3.5} fill="#0a0d11" stroke="#7FCBC5" strokeWidth="1.5" />
                    <text x={p.x} y={p.y - 7} fill="#7FCBC5" fontSize="10" fontFamily="monospace" textAnchor="middle">
                      {p.val.toFixed(1)}
                    </text>
                    <text x={p.x} y={padT + cHeight + 15} fill="#71767e" fontSize="9.5" fontFamily="monospace" textAnchor="middle">
                      +{p.hour}h
                    </text>
                  </g>
                ))}
              </svg>
            </div>
          ) : (
            <div className="pt-2 border-t border-[#14181e] text-[11px] text-[#71767e] font-light">
              Observed at station {currentWind?.station_id || "Buoy telemetry"}
            </div>
          )}
        </div>

        {/* PANEL B: AIR PRESSURE */}
        <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#BDCDC9] font-medium">
                Air Pressure
              </span>
              <span className="text-[10px] font-mono text-[#BDCDC9] px-1.5 py-0.5 rounded bg-[#181d24] border border-[#222933]">
                MSLP
              </span>
            </div>

            <div className="flex items-baseline space-x-2">
              <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
                {activeMslpVal !== undefined && activeMslpVal !== null ? activeMslpVal.toFixed(1) : "—"}
              </span>
              <span className="text-xs font-mono text-[#BDCDC9]">hPa</span>
            </div>

            <div className="text-xs text-[#BDCDC9] font-medium">
              {pressureTrendLabel}
            </div>
          </div>

          {/* Barometric Meaning */}
          <div className="pt-2 border-t border-[#14181e] space-y-1.5">
            <p className="text-[11.5px] text-[#8e8e93] font-light leading-relaxed">
              {pressureMeaning}
            </p>
            {hasForecasts && firstFcMslp !== undefined && (
              <div className="text-[10px] font-mono text-[#71767e]">
                Model lead: +{sortedHours[0]}h ({firstFcMslp.toFixed(0)} hPa)
              </div>
            )}
          </div>
        </div>

        {/* PANEL C: RAINFALL / PRECIPITATION */}
        <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-[#BDCDC9] font-medium">
                Precipitation
              </span>
              <span className="text-[10px] font-mono text-[#38bdf8] px-1.5 py-0.5 rounded bg-[#0284c7]/20 border border-[#0284c7]/30">
                Rainfall
              </span>
            </div>

            {hasRainData && maxRain > 0 ? (
              <>
                <div className="flex items-baseline space-x-2">
                  <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
                    {maxRain.toFixed(1)}
                  </span>
                  <span className="text-xs font-mono text-[#BDCDC9]">mm</span>
                </div>
                <div className="text-xs text-[#38bdf8] font-medium">
                  {maxRain < 2.5 ? "Light rain expected" : maxRain < 7.5 ? "Moderate rain showers" : "Heavy rain expected"}
                </div>
              </>
            ) : (
              <>
                <div className="flex items-baseline space-x-2">
                  <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
                    0.0
                  </span>
                  <span className="text-xs font-mono text-[#BDCDC9]">mm</span>
                </div>
                <div className="text-xs text-[#71767e] font-light">
                  {hasForecasts ? "No significant rainfall expected" : "No rain sensor on current buoy"}
                </div>
              </>
            )}
          </div>

          {/* Rainfall Visual Bar or Clean Status */}
          <div className="pt-2 border-t border-[#14181e] space-y-1.5">
            {hasRainData && firstRainEntry ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[10.5px] font-mono text-[#BDCDC9]">
                  <span>Lead hour +{firstRainEntry.hour}h</span>
                  <span className="text-[#38bdf8]">{firstRainEntry.rain.toFixed(1)} mm</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-[#181d24] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#38bdf8]"
                    style={{ width: `${Math.min(100, Math.max(8, (firstRainEntry.rain / 20) * 100))}%` }}
                  />
                </div>
              </div>
            ) : (
              <p className="text-[11.5px] text-[#71767e] font-light leading-relaxed">
                {hasForecasts
                  ? "Precipitation projection is zero for the active lead steps."
                  : "Buoy platform measures oceanographic & atmospheric state."}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* SO WHAT? BOTTOM NOTE (Requirement 6) */}
      <div className="p-4 rounded-lg bg-[#090b0e] border border-[#161a20] space-y-2">
        <div className="flex items-center space-x-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-[#7FCBC5] font-semibold">
            WHAT IS IT?
          </span>
          <span className="text-xs text-[#8e8e93]">
            → {hasForecasts ? `Numerical weather prediction from ${forecasts[0]?.model_name || "IMD-GFS"} atmospheric model.` : "In-situ atmospheric telemetry from regional moored observation buoy."}
          </span>
        </div>
        <div className="flex items-start space-x-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-[#BDCDC9] font-semibold shrink-0 pt-0.5">
            SO WHAT?
          </span>
          <p className="text-xs sm:text-sm text-[#F4F7F5] font-light leading-relaxed">
            → {soWhatText}
          </p>
        </div>
      </div>
    </section>
  );
}