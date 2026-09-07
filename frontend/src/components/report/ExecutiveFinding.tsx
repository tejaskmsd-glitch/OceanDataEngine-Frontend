"use client";

import { AlertTriangle, Info, CheckCircle2, ShieldCheck, Waves } from "lucide-react";
import type {
  AlertModel,
  ForecastModel,
  MarineRiskModel,
  ObservationModel,
  PFZModel,
} from "@/types/api";

interface ExecutiveFindingProps {
  observations: ObservationModel[];
  forecasts: ForecastModel[];
  risk: MarineRiskModel | null;
  alerts: AlertModel[];
  pfzList?: PFZModel[];
  warnings?: string[];
  radiusKm?: number;
}

function getRiskColor(level: string) {
  const l = level.toUpperCase();
  if (l === "CRITICAL") return { text: "text-[#f87171]", bg: "bg-[#dc2626]/10", border: "border-[#dc2626]/30" };
  if (l === "HIGH") return { text: "text-[#fb923c]", bg: "bg-[#ea580c]/10", border: "border-[#ea580c]/30" };
  if (l === "MODERATE") return { text: "text-[#facc15]", bg: "bg-[#ca8a04]/10", border: "border-[#ca8a04]/30" };
  return { text: "text-[#7FCBC5]", bg: "bg-[#15616d]/20", border: "border-[#15616d]/40" };
}

export function ExecutiveFinding({
  observations,
  forecasts,
  risk,
  alerts,
  pfzList = [],
  warnings = [],
  radiusKm = 150,
}: ExecutiveFindingProps) {
  // Extract key in-situ observations
  const sstObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("sea_surface_temperature") || o.parameter.toLowerCase().includes("sst")
  );
  const waveObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("wave_height") || o.parameter.toLowerCase().includes("wave")
  );
  const windObs = observations.find((o) =>
    o.parameter.toLowerCase().includes("wind_speed")
  );

  // Extract wave forecasts
  const waveFc = forecasts
    .filter((f) => f.parameter.toLowerCase().includes("wave_height") || f.parameter.toLowerCase().includes("wave"))
    .sort((a, b) => (a.forecast_hour || 0) - (b.forecast_hour || 0));

  const riskLevel = risk?.risk_level?.toUpperCase() || "UNKNOWN";
  const riskScore = risk ? risk.risk_score : null;
  const colors = getRiskColor(riskLevel);

  // Determine human summary headline (Requirement 2)
  let headline = "Sea conditions look calm right now.";
  if (riskLevel === "CRITICAL" || riskLevel === "HIGH") {
    headline = "Rough or hazardous sea conditions detected right now.";
  } else if (riskLevel === "MODERATE") {
    headline = "Moderate sea conditions observed right now.";
  } else if (alerts.length > 0) {
    headline = `Active coastal warnings in effect (${alerts.length} advisory notice${alerts.length === 1 ? "" : "s"}).`;
  } else if (waveObs && typeof waveObs.value === "number") {
    if (waveObs.value <= 1.25) {
      headline = "Sea conditions look calm right now.";
    } else if (waveObs.value <= 2.2) {
      headline = "Sea conditions look moderate right now.";
    } else {
      headline = "Rough sea conditions detected right now.";
    }
  } else if (observations.length === 0) {
    headline = "Sea conditions appear calm in available data, but local observations are limited.";
  }

  // Determine if coverage is limited
  const hasLimitedCoverage = observations.length === 0 || warnings.length > 0;

  // Build "Why?" factual explanations
  const facts: string[] = [];

  if (waveObs && typeof waveObs.value === "number") {
    facts.push(
      `In-situ buoy (${waveObs.station_id || "Station"}) reports significant wave height of ${waveObs.value.toFixed(1)} ${waveObs.unit || "m"}${
        sstObs && typeof sstObs.value === "number" ? ` and water temperature of ${sstObs.value.toFixed(1)} ${sstObs.unit || "°C"}` : ""
      }.`
    );
  } else if (observations.length > 0) {
    facts.push(`${observations.length} discrete in-situ sensor parameter(s) recorded within queried radius.`);
  }

  if (waveFc.length >= 2) {
    const first = waveFc[0];
    const last = waveFc[waveFc.length - 1];
    if (typeof first.value === "number" && typeof last.value === "number") {
      const diff = last.value - first.value;
      const trend = diff > 0.2 ? "projected to build from" : diff < -0.2 ? "projected to ease from" : "holding steady around";
      facts.push(
        `Numerical model (${first.model_name || "IMD-GFS"}) shows significant wave height ${trend} ${first.value.toFixed(1)} m (+${first.forecast_hour}h) to ${last.value.toFixed(1)} m (+${last.forecast_hour}h).`
      );
    }
  }

  if (risk && risk.factors.length > 0) {
    const factorList = risk.factors.map((f) => `${f.name.replace(/_/g, " ")} (${f.contribution.toFixed(1)} pts)`).join(", ");
    facts.push(`Operational risk model factors evaluated: ${factorList}.`);
  }

  if (alerts.length > 0) {
    facts.push(
      `${alerts.length} authoritative coastal bulletin(s) active in region, including: “${alerts[0].headline || alerts[0].event_type.replace(/_/g, " ")}”.`
    );
  }

  if (facts.length === 0) {
    facts.push(`No active moored buoys or hazard bulletins matched within the ${radiusKm} km search radius in the current data snapshot.`);
  }

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">01</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            What's Happening?
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Executive environmental summary · Real-time synthesis
        </span>
      </div>

      {/* Main Human Headline & Score Block */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8 space-y-3">
          <p className="text-xl sm:text-2xl lg:text-3xl font-light text-[#F4F7F5] leading-snug">
            {headline}
          </p>

          {/* Qualification banner when coverage is limited (Requirement 2) */}
          {hasLimitedCoverage && (
            <div className="p-3 rounded-lg bg-[#14120e] border border-[#2e2617] flex items-start space-x-2.5 text-xs text-[#d4af37]">
              <AlertTriangle className="w-4 h-4 text-[#facc15] shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <span className="font-medium text-[#facc15]">Limited data coverage:</span>
                <p className="text-[#c7bf9e] font-light leading-relaxed">
                  This assessment is based only on information currently available for this {radiusKm} km area.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Score & Risk badge */}
        {riskScore !== null && (
          <div className="lg:col-span-4 p-4 rounded-xl bg-[#0c0e12] border border-[#1b1f26] space-y-2">
            <div className="text-[10.5px] font-mono uppercase tracking-wider text-[#8e8e93]">
              Current Risk
            </div>
            <div className="flex items-baseline space-x-2">
              <span className="text-3xl sm:text-4xl font-light font-mono text-white tracking-tight">
                {riskScore.toFixed(1)}
              </span>
              <span className="text-xs font-mono text-[#71767e]">/ 100</span>
              <span className={`ml-auto px-2 py-0.5 rounded text-[11px] font-mono uppercase font-semibold border ${colors.text} ${colors.bg} ${colors.border}`}>
                {riskLevel} RISK
              </span>
            </div>
            <div className="text-[10px] font-mono text-[#71767e] pt-1 border-t border-[#16181d]">
              Evaluated Server-Side · §14 Weighted Vulnerability
            </div>
          </div>
        )}
      </div>

      {/* "Why?" Factual Breakdown */}
      <div className="space-y-2.5 pt-2">
        <div className="text-xs font-mono uppercase tracking-wider text-[#8e8e93] font-medium">
          Why?
        </div>
        <div className="space-y-2">
          {facts.map((fact, idx) => (
            <div
              key={idx}
              className="flex items-start space-x-3 text-sm text-[#BDCDC9] font-light leading-relaxed"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#7FCBC5] shrink-0 mt-2" />
              <span>{fact}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}