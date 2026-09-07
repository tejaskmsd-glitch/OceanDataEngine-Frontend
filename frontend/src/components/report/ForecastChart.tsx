"use client";

import { useState } from "react";
import type { ForecastModel, ObservationModel } from "@/types/api";

interface ForecastChartProps {
  forecasts: ForecastModel[];
  currentObs?: ObservationModel[];
  radiusKm?: number;
}

export function ForecastChart({ forecasts, currentObs = [], radiusKm = 150 }: ForecastChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Filter for wave forecasts
  const wavePoints = forecasts
    .filter(
      (f) =>
        f.value !== null &&
        (f.parameter.toLowerCase().includes("wave_height") || f.parameter.toLowerCase().includes("wave"))
    )
    .sort((a, b) => (a.forecast_hour || 0) - (b.forecast_hour || 0));

  // Current wave observation
  const currentWaveObs = currentObs.find(
    (o) =>
      o.value !== null &&
      (o.parameter.toLowerCase().includes("wave_height") || o.parameter.toLowerCase().includes("wave"))
  );

  // If no wave forecasts (Section 7 - Designed source-gap state)
  if (wavePoints.length === 0) {
    return (
      <section className="space-y-4 font-sans">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
          <div className="flex items-center space-x-2.5">
            <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">03</span>
            <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
              How The Sea May Change
            </h2>
          </div>
          <span className="text-[11.5px] text-[#71767e] font-light">
            Significant wave height · Numerical forecast
          </span>
        </div>

        {currentWaveObs && typeof currentWaveObs.value === "number" && (
          <div className="p-4 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-[#BDCDC9]">
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#7FCBC5] font-medium block">
                CURRENT IN-SITU OBSERVATION
              </span>
              <div className="flex items-baseline space-x-2">
                <span className="text-3xl font-light font-mono text-white">
                  {currentWaveObs.value.toFixed(1)}
                </span>
                <span className="text-sm font-mono text-[#7FCBC5]">
                  {currentWaveObs.unit || "m"}
                </span>
                <span className="text-xs text-[#8e8e93] font-light ml-1">
                  Significant wave height (Hs)
                </span>
              </div>
            </div>
            <div className="text-right sm:text-right text-[11px] font-mono text-[#71767e] space-y-0.5">
              <div>Station: {currentWaveObs.station_id || "Buoy BD08"}</div>
              <div>Measured live by moored ocean buoy</div>
            </div>
          </div>
        )}

        {/* Designed Empty/Source-Gap Box (Section 7) */}
        <div className="p-5 sm:p-6 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-white font-medium">
              Forecast Unavailable
            </span>
            <span className="text-[10.5px] font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#161c24] border border-[#232d3a]">
              MODEL SCHEDULE · IDLE
            </span>
          </div>
          <p className="text-sm text-[#8e8e93] font-light leading-relaxed">
            No numerical wave forecast schedule is currently available for this {radiusKm} km area in the active model cycle.
          </p>
        </div>
      </section>
    );
  }

  // Build unified trajectory points: NOW (if observed) + Forecast steps (+6h, +12h)
  interface TrajectoryPoint {
    label: string;
    sublabel: string;
    val: number;
    isObs: boolean;
    validFrom?: string | null;
  }

  const trajectory: TrajectoryPoint[] = [];
  if (currentWaveObs && typeof currentWaveObs.value === "number") {
    trajectory.push({
      label: "NOW",
      sublabel: "Observed",
      val: currentWaveObs.value,
      isObs: true,
      validFrom: currentWaveObs.observed_at,
    });
  }

  wavePoints.forEach((p) => {
    trajectory.push({
      label: `+${p.forecast_hour}h`,
      sublabel: "Forecast",
      val: p.value as number,
      isObs: false,
      validFrom: p.valid_from,
    });
  });

  // Calculate trend (Section 3: STEADY / RISING / FALLING)
  let trend = "STEADY";
  let trendColor = "text-[#7FCBC5] bg-[#15616d]/20 border-[#15616d]/40";
  if (trajectory.length >= 2) {
    const diff = trajectory[trajectory.length - 1].val - trajectory[0].val;
    if (diff > 0.2) {
      trend = "RISING";
      trendColor = trajectory[trajectory.length - 1].val >= 2.0
        ? "text-[#fbbf24] bg-[#fbbf24]/15 border-[#fbbf24]/40"
        : "text-[#7FCBC5] bg-[#15616d]/20 border-[#15616d]/40";
    } else if (diff < -0.2) {
      trend = "FALLING";
      trendColor = "text-[#7FCBC5] bg-[#15616d]/20 border-[#15616d]/40";
    }
  }

  // SVG dimensions
  const width = 800;
  const height = 260;
  const padLeft = 55;
  const padRight = 55;
  const padTop = 35;
  const padBottom = 50;

  const chartWidth = width - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;

  const rawValues = trajectory.map((p) => p.val);
  const minVal = 0;
  const maxVal = Math.max(3.5, Math.ceil(Math.max(...rawValues, 2.2) + 0.5));

  // Calculate coordinates for trajectory points
  const points = trajectory.map((p, idx) => {
    const x =
      trajectory.length === 1
        ? padLeft + chartWidth / 2
        : padLeft + (idx / (trajectory.length - 1)) * chartWidth;
    const y = padTop + chartHeight - ((p.val - minVal) / (maxVal - minVal)) * chartHeight;
    return { x, y, point: p };
  });

  const pathD = points.reduce((acc, curr, idx) => {
    return idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`;
  }, "");

  const areaD =
    points.length > 1
      ? `${pathD} L ${points[points.length - 1].x} ${padTop + chartHeight} L ${points[0].x} ${padTop + chartHeight} Z`
      : "";

  // 2.0m Small Craft Caution threshold line
  const yCaution = padTop + chartHeight - ((2.0 - minVal) / (maxVal - minVal)) * chartHeight;

  const modelInfo = wavePoints[0].model_name || "IMD-GFS";

  // Plain language explanation
  let plainExplanation = "Wave height remains close to the current observed level across the available forecast points.";
  if (points.length >= 2) {
    const firstVal = points[0].point.val;
    const lastVal = points[points.length - 1].point.val;
    const diff = lastVal - firstVal;
    if (diff > 0.2) {
      plainExplanation = `Wave height is projected to rise from ${firstVal.toFixed(1)} m to ${lastVal.toFixed(1)} m${
        lastVal >= 2.0 ? ", approaching or crossing the 2.0 m small craft caution threshold" : ""
      }.`;
    } else if (diff < -0.2) {
      plainExplanation = `Wave height is projected to subside from ${firstVal.toFixed(1)} m to ${lastVal.toFixed(1)} m over the forecast period.`;
    } else {
      plainExplanation = `Wave height remains steady near ${firstVal.toFixed(1)} m across the available forecast period.`;
    }
  }

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">03</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            How The Sea May Change
          </h2>
        </div>
        <div className="flex items-center space-x-2.5">
          <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded font-semibold border ${trendColor}`}>
            TREND · {trend}
          </span>
          <span className="text-[11.5px] text-[#71767e] font-light hidden sm:inline">
            {modelInfo} numerical model
          </span>
        </div>
      </div>

      {/* Observation vs Forecast distinction cards (Section 4) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-4 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-1.5">
          <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-[#7FCBC5] font-medium">
            <span>CURRENT / OBSERVED</span>
            <span className="text-[#71767e]">In-Situ Telemetry</span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
              {currentWaveObs && typeof currentWaveObs.value === "number" ? currentWaveObs.value.toFixed(1) : "—"}
            </span>
            <span className="text-sm font-mono text-[#7FCBC5]">
              {currentWaveObs?.unit || "m"}
            </span>
            <span className="text-xs text-[#BDCDC9] font-light ml-1">
              {currentWaveObs ? "Live Sensor Measurement" : "No buoy observation nearby"}
            </span>
          </div>
          <div className="text-[10.5px] font-mono text-[#71767e]">
            {currentWaveObs?.station_id ? `Station: ${currentWaveObs.station_id}` : "Offshore grid point"}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-1.5">
          <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-[#BDCDC9] font-medium">
            <span>FORECAST / MODEL</span>
            <span className="text-[#71767e]">Numerical Projection</span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
              {(wavePoints[0].value as number).toFixed(1)}
            </span>
            <span className="text-sm font-mono text-[#BDCDC9]">
              m
            </span>
            <span className="text-xs font-mono text-[#7FCBC5] ml-1">
              at +{wavePoints[0].forecast_hour}h
            </span>
            {wavePoints.length > 1 && (
              <span className="text-xs font-mono text-[#BDCDC9]">
                → {(wavePoints[wavePoints.length - 1].value as number).toFixed(1)} m (+{wavePoints[wavePoints.length - 1].forecast_hour}h)
              </span>
            )}
          </div>
          <div className="text-[10.5px] font-mono text-[#71767e]">
            Model: {modelInfo} · Discrete lead-hour simulation
          </div>
        </div>
      </div>

      {/* Scientific Forecast Canvas (Reference 1 & 2) */}
      <div className="p-4 sm:p-6 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#8e8e93]">
          <div className="flex items-center space-x-4 font-mono text-[11px]">
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-0.5 bg-[#7FCBC5]" />
              <span className="text-white">Wave Height (Hs)</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-0.5 bg-[#fbbf24] border-t border-dashed" />
              <span className="text-[#fbbf24]">2.0m Caution Threshold</span>
            </span>
          </div>
          <span className="font-mono text-[11px] text-[#71767e]">
            {modelInfo} Discrete Simulation
          </span>
        </div>

        <div className="w-full overflow-x-auto">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto max-h-[340px] select-none"
          >
            <defs>
              <linearGradient id="waveFillGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#7FCBC5" stopOpacity="0.16" />
                <stop offset="100%" stopColor="#7FCBC5" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Gridlines */}
            {[0, 1.0, 1.5, 2.0, 2.5, 3.0].filter((v) => v <= maxVal).map((val) => {
              const y = padTop + chartHeight - ((val - minVal) / (maxVal - minVal)) * chartHeight;
              return (
                <g key={val}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={padLeft + chartWidth}
                    y2={y}
                    stroke="#1a2029"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={padLeft - 10}
                    y={y + 3.5}
                    fill="#666c75"
                    fontSize="10"
                    fontFamily="monospace"
                    textAnchor="end"
                  >
                    {val.toFixed(1)}m
                  </text>
                </g>
              );
            })}

            {/* 2.0m Caution Line with text */}
            {yCaution >= padTop && yCaution <= padTop + chartHeight && (
              <g>
                <line
                  x1={padLeft}
                  y1={yCaution}
                  x2={padLeft + chartWidth}
                  y2={yCaution}
                  stroke="#d97706"
                  strokeWidth="1.2"
                  strokeDasharray="5 5"
                  strokeOpacity="0.8"
                />
                <text
                  x={padLeft + chartWidth - 8}
                  y={yCaution - 6}
                  fill="#fbbf24"
                  fontSize="10"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  caution threshold (2.0 m)
                </text>
              </g>
            )}

            {/* Area under curve */}
            {areaD && <path d={areaD} fill="url(#waveFillGrad)" />}

            {/* Connected trajectory path */}
            <path
              d={pathD}
              fill="none"
              stroke="#7FCBC5"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Trajectory Points */}
            {points.map((p, idx) => {
              const isHovered = hoveredIdx === idx;
              return (
                <g
                  key={idx}
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                  className="cursor-pointer"
                >
                  {/* Point circle */}
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={isHovered ? 7.5 : 5.5}
                    fill="#0a0d11"
                    stroke="#7FCBC5"
                    strokeWidth="2.5"
                    className="transition-all duration-150"
                  />
                  <circle cx={p.x} cy={p.y} r={2.5} fill="#F4F7F5" />

                  {/* Value pill */}
                  <rect
                    x={p.x - 22}
                    y={p.y - 28}
                    width={44}
                    height={19}
                    rx={3}
                    fill="#11161d"
                    stroke="#26323f"
                    strokeWidth="1"
                  />
                  <text
                    x={p.x}
                    y={p.y - 15}
                    fill="#FFFFFF"
                    fontSize="11"
                    fontFamily="monospace"
                    fontWeight="500"
                    textAnchor="middle"
                  >
                    {p.point.val.toFixed(1)}m
                  </text>

                  {/* X Axis Primary Label (NOW, +6h) */}
                  <text
                    x={p.x}
                    y={padTop + chartHeight + 20}
                    fill={p.point.isObs ? "#7FCBC5" : "#BDCDC9"}
                    fontSize="11.5"
                    fontFamily="monospace"
                    fontWeight="500"
                    textAnchor="middle"
                  >
                    {p.point.label}
                  </text>

                  {/* X Axis Sublabel (Observed, Forecast) */}
                  <text
                    x={p.x}
                    y={padTop + chartHeight + 34}
                    fill="#666c75"
                    fontSize="9.5"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    {p.point.sublabel}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Human explanation: "What you're seeing" */}
        <div className="pt-3 border-t border-[#181d24] space-y-2">
          <div className="text-[11px] font-mono uppercase tracking-wider text-[#7FCBC5] font-medium">
            What you're seeing
          </div>
          <p className="text-sm text-[#BDCDC9] font-light leading-relaxed">
            {plainExplanation}
          </p>
        </div>

        {/* Technical Metadata Strip */}
        <div className="pt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] font-mono text-[#71767e] border-t border-[#151920]">
          <span>Model · {modelInfo}</span>
          <span>·</span>
          <span>Lead Steps · {wavePoints.map((w) => `+${w.forecast_hour}h`).join(" / ")}</span>
          <span>·</span>
          <span>Parameter · Significant Wave Height (Hs)</span>
          <span>·</span>
          <span>Caution Threshold · 2.0 m</span>
        </div>
      </div>
    </section>
  );
}