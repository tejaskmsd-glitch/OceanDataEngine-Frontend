"use client";

import { useState } from "react";
import { CheckCircle2, AlertCircle, Info, Database, Radio, ChevronDown, ChevronUp } from "lucide-react";
import type { ObservationModel, ForecastModel, SourceRef } from "@/types/api";

interface DataCoverageProps {
  observations: ObservationModel[];
  forecasts: ForecastModel[];
  tideCount: number;
  alertCount: number;
  sources: SourceRef[];
  warnings: string[];
  radiusKm?: number;
}

interface CoverageItem {
  domain: string;
  userStatus: string;
  statusType: "available" | "limited" | "not_available" | "checked";
  countLabel: string;
  humanExplanation: string;
  technicalState: string;
}

function getStatusStyle(type: CoverageItem["statusType"]) {
  if (type === "available") return "bg-[#22c55e]/15 text-[#4ade80] border-[#22c55e]/30";
  if (type === "limited") return "bg-[#ca8a04]/15 text-[#facc15] border-[#ca8a04]/30";
  if (type === "checked") return "bg-[#15616d]/25 text-[#7FCBC5] border-[#15616d]/40";
  return "bg-[#1f242d] text-[#8e8e93] border-[#2a313d]";
}

export function DataCoverage({
  observations,
  forecasts,
  tideCount,
  alertCount,
  sources,
  warnings = [],
  radiusKm = 150,
}: DataCoverageProps) {
  const [showTechnical, setShowTechnical] = useState(false);

  // Derive unique forecast lead hours
  const leadHours = Array.from(
    new Set(
      forecasts
        .map((f) => f.forecast_hour)
        .filter((h): h is number => h !== null && h !== undefined)
    )
  ).sort((a, b) => a - b);

  const hasAuthBlocked = warnings.some((w) => w.toLowerCase().includes("auth_blocked") || w.toLowerCase().includes("auth"));

  const items: CoverageItem[] = [];

  // 1. Ocean Conditions
  if (observations.length > 0) {
    const stations = Array.from(new Set(observations.map((o) => o.station_id).filter(Boolean)));
    items.push({
      domain: "Ocean conditions",
      userStatus: "Available",
      statusType: "available",
      countLabel: `${observations.length} parameter(s) across ${stations.length} station(s)`,
      humanExplanation: `Active moored buoys (${stations.join(", ")}) provided verified surface measurements within ${radiusKm} km.`,
      technicalState: "available",
    });
  } else {
    items.push({
      domain: "Ocean conditions",
      userStatus: "Not available in this area",
      statusType: "not_available",
      countLabel: "0 records in range",
      humanExplanation: `Ocean observations were queried within the selected ${radiusKm} km area, but no in-situ buoys are currently deployed in this sector.`,
      technicalState: "healthy_empty / source_gap",
    });
  }

  // 2. Forecast
  if (leadHours.length >= 2) {
    items.push({
      domain: "Forecast",
      userStatus: "Available",
      statusType: "available",
      countLabel: `${leadHours.length} lead steps (${leadHours.map((h) => `+${h}h`).join(", ")})`,
      humanExplanation: "Discrete wave and atmospheric model projections were successfully retrieved and verified.",
      technicalState: "available",
    });
  } else if (leadHours.length === 1) {
    items.push({
      domain: "Forecast",
      userStatus: "Limited",
      statusType: "limited",
      countLabel: `1 lead step (+${leadHours[0]}h)`,
      humanExplanation: "Single lead-hour projection available in the current model cycle.",
      technicalState: "available / single_lead",
    });
  } else {
    items.push({
      domain: "Forecast",
      userStatus: "Not available in this area",
      statusType: "not_available",
      countLabel: "0 forecast points",
      humanExplanation: `Numerical model forecasts are not scheduled or ingested for this coordinate window in the current cycle.`,
      technicalState: "healthy_empty",
    });
  }

  // 3. Tides
  if (tideCount > 0) {
    items.push({
      domain: "Tides",
      userStatus: "Available",
      statusType: "available",
      countLabel: `${tideCount} gauge station(s)`,
      humanExplanation: "Real-time water level readings reported from operational INCOIS TEWS coastal gauge stations.",
      technicalState: "available",
    });
  } else {
    items.push({
      domain: "Tides",
      userStatus: "Not available in this area",
      statusType: "not_available",
      countLabel: "0 stations in radius",
      humanExplanation: `No coastal tide gauges are located within the selected ${radiusKm} km radius. Continuous curves are not synthesized.`,
      technicalState: "healthy_empty",
    });
  }

  // 4. Warnings
  items.push({
    domain: "Warnings",
    userStatus: alertCount > 0 ? "Active warnings" : "Checked",
    statusType: alertCount > 0 ? "limited" : "checked",
    countLabel: alertCount > 0 ? `${alertCount} active bulletin(s)` : "Feed active",
    humanExplanation: alertCount > 0
      ? "Authoritative meteorological and ocean hazard warnings were retrieved and rendered."
      : "Active hazard feeds were queried; no warning bulletins currently affect this sector.",
    technicalState: "available",
  });

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header (Requirement 1) */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">07</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            How Much Do We Know?
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Data completeness, sensor density & coverage transparency
        </span>
      </div>

      {/* Coverage Grid */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-4">
        <div className="flex items-center justify-between text-xs text-[#8e8e93] font-mono">
          <span className="uppercase tracking-wider">Information Availability</span>
          <span className="text-[#7FCBC5]">{items.filter((i) => i.statusType === "available" || i.statusType === "checked").length} / {items.length} Feeds Monitored</span>
        </div>

        <div className="space-y-3">
          {items.map((item, idx) => (
            <div
              key={idx}
              className="p-3.5 rounded-lg bg-[#0c0f13] border border-[#181d24] space-y-2 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center space-x-2.5">
                  <span className="text-white font-medium text-sm">
                    {item.domain}
                  </span>
                  <span className="text-[#4b5563]">―</span>
                  <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${getStatusStyle(item.statusType)}`}>
                    {item.userStatus}
                  </span>
                </div>

                <span className="font-mono text-[11px] text-[#8e8e93]">
                  {item.countLabel}
                </span>
              </div>

              <p className="text-[#BDCDC9] font-light text-xs leading-relaxed">
                {item.humanExplanation}
              </p>

              {/* Technical state exposed only when toggled (Requirement 8) */}
              {showTechnical && (
                <div className="pt-2 border-t border-[#14171d] flex items-center justify-between text-[10.5px] font-mono text-[#71767e]">
                  <span>Raw Ingestion State:</span>
                  <span className="px-1.5 py-0.5 rounded bg-[#12151a] text-[#BDCDC9] uppercase">
                    {item.technicalState}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Technical Details Toggle */}
        <div className="pt-2 border-t border-[#151920] flex items-center justify-between">
          <button
            type="button"
            onClick={() => setShowTechnical(!showTechnical)}
            className="inline-flex items-center space-x-1.5 text-[11px] font-mono text-[#71767e] hover:text-[#BDCDC9] transition-colors"
          >
            <span>{showTechnical ? "Hide technical details" : "Show technical details"}</span>
            {showTechnical ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          <span className="text-[10px] font-mono text-[#4b5563]">
            Telemetry audit
          </span>
        </div>
      </div>
    </section>
  );
}
