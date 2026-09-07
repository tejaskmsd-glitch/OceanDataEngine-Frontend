"use client";

import type { MarineRiskModel, RiskFactorModel } from "@/types/api";

interface RiskAnalysisProps {
  risk: MarineRiskModel | null;
  radiusKm?: number;
}

function getLevelBadge(level: string) {
  const l = level.toUpperCase();
  if (l === "CRITICAL") return { text: "text-[#f87171]", bg: "bg-[#dc2626]/15", border: "border-[#dc2626]/40", badge: "CRITICAL RISK" };
  if (l === "HIGH") return { text: "text-[#fb923c]", bg: "bg-[#ea580c]/15", border: "border-[#ea580c]/40", badge: "HIGH RISK" };
  if (l === "MODERATE") return { text: "text-[#facc15]", bg: "bg-[#ca8a04]/15", border: "border-[#ca8a04]/40", badge: "MODERATE RISK" };
  return { text: "text-[#7FCBC5]", bg: "bg-[#15616d]/20", border: "border-[#15616d]/40", badge: "LOW RISK" };
}

function getFactorDisplayName(name: string): { label: string; unit: string } {
  const n = name.toLowerCase();
  if (n.includes("wave")) return { label: "Wave Height", unit: "m" };
  if (n.includes("wind")) return { label: "Wind Speed", unit: "m/s" };
  if (n.includes("rain") || n.includes("precip")) return { label: "Precipitation", unit: "mm" };
  if (n.includes("pressure") || n.includes("mslp")) return { label: "Air Pressure", unit: "hPa" };
  if (n.includes("temp") || n.includes("sst")) return { label: "Water Temperature", unit: "°C" };
  return { label: name.replace(/_/g, " "), unit: "" };
}

export function RiskAnalysis({ risk, radiusKm = 150 }: RiskAnalysisProps) {
  if (!risk) {
    return (
      <section className="space-y-4 font-sans">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
          <div className="flex items-center space-x-2.5">
            <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">05</span>
            <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
              Current Risk
            </h2>
          </div>
          <span className="text-[11.5px] text-[#71767e] font-light">
            Authoritative operational safety index
          </span>
        </div>

        <div className="py-4 px-1 text-sm text-[#8e8e93] font-light flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#16181d]">
          <p>
            No environmental factors were matched to compute an operational risk score for this {radiusKm} km area.
          </p>
          <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#111418] border border-[#1b222a] shrink-0 self-start sm:self-auto">
            Risk engine · Idle
          </span>
        </div>
      </section>
    );
  }

  const level = risk.risk_level.toUpperCase();
  const badgeStyle = getLevelBadge(level);
  const isZeroOrLow = risk.risk_score === 0 || level === "LOW";

  // Dynamic plain-language verdict (Requirement 8A)
  let verdict = "Conditions are well within safe limits for all maritime operations.";
  if (level === "MODERATE") {
    verdict = "Elevated sea conditions present moderate caution for small craft and coastal vessels.";
  } else if (level === "HIGH") {
    verdict = "Rough sea state presents significant hazard; small craft operations are discouraged.";
  } else if (level === "CRITICAL") {
    verdict = "Severe marine conditions detected; all vessel operations should seek immediate shelter.";
  }

  // Factor summaries for dynamic "WHY?" explanation (Requirement 8C)
  const factorsWithValues = risk.factors.filter((f) => f.value !== null && f.value !== undefined);
  const activeParamNames = factorsWithValues.map((f) => getFactorDisplayName(f.name).label.toLowerCase());
  const elevatedFactors = risk.factors.filter((f) => (f.contribution || 0) > 0);

  let whyExplanation = "";
  if (isZeroOrLow) {
    const factorListText = factorsWithValues
      .map((f) => {
        const { label, unit } = getFactorDisplayName(f.name);
        return `${label.toLowerCase()} at ${f.value?.toFixed(1)} ${unit}`;
      })
      .join(", ");
    whyExplanation = factorListText
      ? `All measured parameters (${factorListText}) are below caution thresholds. No penalty points were incurred.`
      : "Measured parameters remain below caution thresholds. No penalty points were incurred.";
  } else {
    whyExplanation = elevatedFactors
      .map((f) => {
        const { label, unit } = getFactorDisplayName(f.name);
        return `${label} (${f.value?.toFixed(1)} ${unit}) exceeded the safe threshold of ${f.threshold_low} ${unit}, contributing +${f.contribution.toFixed(1)} penalty points`;
      })
      .join("; ") + ".";
  }

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">05</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Current Risk
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Authoritative operational safety index · Server-side evaluation
        </span>
      </div>

      {/* Main Score & Factor Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* DOMINANT SCORE DISPLAY (Requirement 8A) */}
        <div className="lg:col-span-4 p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-4">
          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-[#8e8e93]">
              Marine Risk Index
            </div>
            <div className="flex items-baseline space-x-2 pt-0.5">
              <span className="text-4xl sm:text-5xl font-light font-mono text-white tracking-tight">
                {risk.risk_score.toFixed(1)}
              </span>
              <span className="text-sm font-mono text-[#71767e]">/ 100</span>
            </div>
          </div>

          <div>
            <span
              className={`inline-block px-3 py-1 rounded text-xs font-mono uppercase tracking-wider font-semibold border ${badgeStyle.text} ${badgeStyle.bg} ${badgeStyle.border}`}
            >
              {badgeStyle.badge}
            </span>
          </div>

          {/* Plain Language Verdict */}
          <p className="text-xs sm:text-sm text-white font-light leading-relaxed">
            {verdict}
          </p>

          {/* "WHY?" Explanation (Requirement 8C) */}
          <div className="pt-3 border-t border-[#161a20] space-y-1.5">
            <span className="text-[10.5px] font-mono uppercase tracking-wider text-[#7FCBC5] block font-medium">
              Why this score?
            </span>
            <p className="text-xs text-[#BDCDC9] font-light leading-relaxed">
              {whyExplanation}
            </p>
          </div>

          {/* Explicit Limitation Note (Requirement 8D) */}
          <div className="pt-3 border-t border-[#161a20] space-y-1">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#71767e] block">
              Data Coverage Scope
            </span>
            <p className="text-[11px] text-[#71767e] font-light leading-relaxed">
              Risk evaluation is calculated only from active sensors within this {radiusKm} km radius ({activeParamNames.length > 0 ? activeParamNames.join(", ") : "available feeds"}). If other data feeds are offline, true conditions may differ.
            </p>
          </div>

          {risk.valid_from && (
            <div className="pt-2 border-t border-[#161a20] text-[10px] font-mono text-[#71767e]">
              Evaluated: {new Date(risk.valid_from).toISOString().replace("T", " ").replace("Z", " UTC").slice(0, 16)}
            </div>
          )}
        </div>

        {/* HORIZONTAL COMPARISON GAUGES (Requirement 8B) */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8e8e93] font-mono border-b border-[#1b1f26] pb-2">
            <span className="uppercase tracking-wider">Assessed Factors vs Safe Thresholds</span>
            <span className="text-[11px] text-[#71767e]">Backend Safe Limits (§14)</span>
          </div>

          {risk.factors.length > 0 ? (
            <div className="space-y-4">
              {risk.factors.map((factor: RiskFactorModel, idx: number) => {
                const { label, unit } = getFactorDisplayName(factor.name);
                const actual = factor.value;
                const penalty = factor.contribution || 0;
                const caution = factor.threshold_low;
                const hazard = factor.threshold_high;

                // Max scale for the horizontal gauge
                const scaleMax = Math.max(hazard * 1.25, (actual ?? 0) * 1.15);
                const safeWidthPct = (caution / scaleMax) * 100;
                const cautionWidthPct = ((hazard - caution) / scaleMax) * 100;
                const hazardWidthPct = 100 - safeWidthPct - cautionWidthPct;

                // Marker position
                const markerPct = actual !== null && actual !== undefined
                  ? Math.min(97, Math.max(3, (actual / scaleMax) * 100))
                  : null;

                const isCaution = actual !== null && actual !== undefined && actual >= caution && actual < hazard;
                const isHazard = actual !== null && actual !== undefined && actual >= hazard;
                const isSafe = actual !== null && actual !== undefined && actual < caution;

                return (
                  <div
                    key={idx}
                    className="p-4 rounded-xl bg-[#0a0d11] border border-[#181d24] space-y-3"
                  >
                    {/* Factor Header & Value */}
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <div className="flex items-center space-x-2">
                          <span className="text-white font-medium text-sm">
                            {label}
                          </span>
                          <span className="text-[11px] font-mono text-[#71767e]">
                            Safe range: 0 – {caution} {unit}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center space-x-2.5 font-mono">
                        <span className="text-base text-white font-medium">
                          {actual !== null && actual !== undefined ? `${actual.toFixed(1)} ${unit}` : "—"}
                        </span>
                        <span className="text-[#71767e]">·</span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-mono ${
                            penalty > 0
                              ? "bg-[#ea580c]/15 text-[#fb923c] border border-[#ea580c]/30"
                              : "bg-[#15616d]/20 text-[#7FCBC5] border border-[#15616d]/30"
                          }`}
                        >
                          {penalty > 0 ? `+${penalty.toFixed(1)} pts penalty` : "0 pts (Safe)"}
                        </span>
                      </div>
                    </div>

                    {/* HORIZONTAL THREE-ZONE COMPARISON GAUGE */}
                    <div className="space-y-1.5 pt-1">
                      <div className="w-full h-3 rounded-full bg-[#12161c] relative flex overflow-hidden border border-[#1e242d]">
                        {/* Safe Zone (Green/Teal) */}
                        <div
                          className="h-full bg-[#7FCBC5]/25 border-r border-[#7FCBC5]/50 transition-all duration-300"
                          style={{ width: `${safeWidthPct}%` }}
                        />
                        {/* Caution Zone (Amber) */}
                        <div
                          className="h-full bg-[#fbbf24]/20 border-r border-[#fbbf24]/50 transition-all duration-300"
                          style={{ width: `${cautionWidthPct}%` }}
                        />
                        {/* Hazard Zone (Red) */}
                        <div
                          className="h-full bg-[#f87171]/20 transition-all duration-300"
                          style={{ width: `${hazardWidthPct}%` }}
                        />
                      </div>

                      {/* Pin/Marker overlay */}
                      {markerPct !== null && (
                        <div className="relative w-full h-3">
                          <div
                            className="absolute -top-4 flex flex-col items-center -translate-x-1/2 transition-all duration-300 pointer-events-none"
                            style={{ left: `${markerPct}%` }}
                          >
                            <span
                              className={`text-[9.5px] font-mono px-1 rounded font-semibold ${
                                isHazard
                                  ? "bg-[#f87171] text-black"
                                  : isCaution
                                  ? "bg-[#fbbf24] text-black"
                                  : "bg-[#7FCBC5] text-black"
                              }`}
                            >
                              {actual?.toFixed(1)}
                            </span>
                            <div
                              className={`w-0.5 h-2 ${
                                isHazard ? "bg-[#f87171]" : isCaution ? "bg-[#fbbf24]" : "bg-[#7FCBC5]"
                              }`}
                            />
                          </div>
                        </div>
                      )}

                      {/* Threshold Scale Reference Labels */}
                      <div className="flex items-center justify-between text-[10px] font-mono text-[#71767e] pt-0.5">
                        <span className="text-[#7FCBC5]">0 {unit} (Safe)</span>
                        <span className="text-[#BDCDC9]">Safe limit: {caution} {unit}</span>
                        <span className="text-[#f87171]">Hazard: {hazard} {unit}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-6 px-4 rounded-xl bg-[#0a0d11] border border-[#1b222a] text-xs text-[#71767e] italic font-light">
              No individual environmental penalty factors triggered; parameters remain in safe bands.
            </div>
          )}

          {/* Model Footnote */}
          <div className="text-[10.5px] font-mono text-[#71767e] pt-1">
            Algorithm · Multi-factor Marine Vulnerability Risk (§14) · Evaluated Server-Side
          </div>
        </div>
      </div>
    </section>
  );
}