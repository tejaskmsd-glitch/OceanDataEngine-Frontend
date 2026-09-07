"use client";

import { Fish, CheckCircle2, AlertCircle, Compass } from "lucide-react";
import Link from "next/link";
import type { FishingSuitabilityModel, PFZModel } from "@/types/api";

interface FishingAnalysisProps {
  suitability: FishingSuitabilityModel | null;
  pfzList: PFZModel[];
  location: { lat: number; lon: number };
  radiusKm?: number;
}

export function FishingAnalysis({
  suitability,
  pfzList,
  location,
  radiusKm = 150,
}: FishingAnalysisProps) {
  if (!suitability && pfzList.length === 0) {
    return null;
  }

  const nearestPfz = pfzList.length > 0 ? pfzList[0] : null;

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[10.5px] font-mono uppercase tracking-[0.16em] text-[#7FCBC5] px-1.5 py-0.5 rounded bg-[#15616d]/20 border border-[#15616d]/40">
            DOMAIN FOCUS
          </span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Fishing Conditions & PFZ Advisory
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          INCOIS Potential Fishing Zones (PFZ) & habitat suitability assessment
        </span>
      </div>

      {/* Suitability Score & Drivers */}
      {suitability && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Score Block */}
          <div className="lg:col-span-4 p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-3">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-[#8e8e93]">
              Pelagic Habitat Suitability
            </div>

            <div className="flex items-baseline space-x-2 pt-1">
              <span className="text-4xl sm:text-5xl font-light font-mono text-[#7FCBC5] tracking-tight">
                {suitability.score.toFixed(0)}
              </span>
              <span className="text-sm font-mono text-[#71767e]">/ 100</span>
            </div>

            <div>
              <span className="inline-block px-3 py-1 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-[#15616d]/20 border border-[#15616d]/40 text-[#7FCBC5]">
                {suitability.classification}
              </span>
            </div>

            <div className="pt-2 border-t border-[#161a20] text-[10.5px] font-mono text-[#71767e] space-y-1">
              <div>Confidence: {(suitability.confidence ? suitability.confidence * 100 : 50).toFixed(0)}%</div>
              <div>Model: INCOIS Multi-Factor Fusion</div>
            </div>
          </div>

          {/* Drivers: What supports this? / What may limit it? */}
          <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Positive Drivers */}
            <div className="p-4 rounded-xl bg-[#0c0f13] border border-[#181d24] space-y-2.5">
              <div className="flex items-center space-x-2 text-[#22c55e] text-[11px] font-mono uppercase tracking-wider font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>What supports this?</span>
              </div>
              {suitability.positive_drivers.length > 0 ? (
                <ul className="space-y-1.5 pl-4 list-disc text-[#BDCDC9] font-light text-xs leading-relaxed">
                  {suitability.positive_drivers.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-[#71767e] italic text-xs font-light">
                  No specific positive environmental drivers recorded.
                </p>
              )}
            </div>

            {/* Negative / Limiting Factors */}
            <div className="p-4 rounded-xl bg-[#0c0f13] border border-[#181d24] space-y-2.5">
              <div className="flex items-center space-x-2 text-[#facc15] text-[11px] font-mono uppercase tracking-wider font-medium">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>What may limit it?</span>
              </div>
              {suitability.negative_drivers.length > 0 ? (
                <ul className="space-y-1.5 pl-4 list-disc text-[#BDCDC9] font-light text-xs leading-relaxed">
                  {suitability.negative_drivers.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-[#71767e] italic text-xs font-light">
                  No limiting environmental factors identified.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Potential Fishing Zones (PFZ) Details */}
      {nearestPfz && (
        <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-[#BDCDC9] font-medium">
              Potential Fishing Zones (PFZ) Advisory
            </span>
            <span className="text-[10px] font-mono text-[#7FCBC5] bg-[#7FCBC5]/10 px-2 py-0.5 rounded">
              INCOIS Ocean Color & Thermal Line
            </span>
          </div>

          <p className="text-sm text-[#BDCDC9] font-light leading-relaxed">
            Thermal gradient features and ocean color lines indicate productive pelagic conditions in the{" "}
            <strong className="text-white font-normal">
              {nearestPfz.region || "coastal"} sector
            </strong>.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-[#71767e] border-t border-[#161a20]">
            {nearestPfz.distance_km !== undefined && <span>Distance · {nearestPfz.distance_km.toFixed(1)} km</span>}
            {nearestPfz.inside !== undefined && (
              <span>Spatial Status · {nearestPfz.inside ? "Inside Zone" : "Adjacent Sector"}</span>
            )}
            {nearestPfz.advisory_type && <span>Type · {nearestPfz.advisory_type}</span>}
            {nearestPfz.valid_until && (
              <span>Valid Until · {new Date(nearestPfz.valid_until).toISOString().slice(0, 10)}</span>
            )}
            <span>Provider · {nearestPfz.provider}</span>
          </div>
        </div>
      )}
    </section>
  );
}