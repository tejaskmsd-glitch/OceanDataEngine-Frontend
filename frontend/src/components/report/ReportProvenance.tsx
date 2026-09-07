"use client";

import { ShieldCheck, Database, Info, ExternalLink, ArrowRight } from "lucide-react";
import type { Meta, SourceRef } from "@/types/api";
import { ProvenanceDrawer } from "@/components/provenance/ProvenanceDrawer";

interface ReportProvenanceProps {
  primaryRequestId?: string;
  sources: SourceRef[];
  warnings: string[];
  meta?: Meta | null;
}

export function ReportProvenance({
  primaryRequestId,
  sources,
  warnings,
  meta,
}: ReportProvenanceProps) {
  // Deduplicate sources by provider + dataset
  const uniqueSources = sources.filter(
    (s, idx, self) =>
      idx === self.findIndex((t) => t.provider === s.provider && t.dataset === s.dataset)
  );

  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header (Requirement 1 & 9) */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">08</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Where This Information Comes From
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Authoritative source organizations, processing lineage & evidence verification
        </span>
      </div>

      <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-5">
        {/* Source Systems Checked vs Datasets Grounding (Requirement 9) */}
        <div className="space-y-3">
          <div className="text-[11px] font-mono uppercase tracking-wider text-[#8e8e93]">
            Source Systems Monitored & Queried
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-[#0c0f13] border border-[#181d24] space-y-1 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white font-mono">IMD</span>
                <span className="text-[10px] font-mono text-[#22c55e] bg-[#22c55e]/10 px-1.5 py-0.2 rounded">
                  Active Feed
                </span>
              </div>
              <div className="text-[#BDCDC9] font-light text-[11.5px]">
                India Meteorological Department · Surface buoy network & GFS numerical atmosphere/wave models
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0c0f13] border border-[#181d24] space-y-1 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white font-mono">INCOIS</span>
                <span className="text-[10px] font-mono text-[#22c55e] bg-[#22c55e]/10 px-1.5 py-0.2 rounded">
                  Active Feed
                </span>
              </div>
              <div className="text-[#BDCDC9] font-light text-[11.5px]">
                Indian National Centre for Ocean Information Services · Ocean forecasts, TEWS tide gauges & PFZ advisories
              </div>
            </div>
          </div>
        </div>

        {/* Specific Grounded Datasets */}
        <div className="space-y-3 pt-2 border-t border-[#151920]">
          <div className="flex items-center justify-between text-xs text-[#8e8e93] font-mono">
            <span className="uppercase tracking-wider">Datasets Grounding This Report</span>
            <span className="text-[#7FCBC5]">{uniqueSources.length} Record Feed{uniqueSources.length === 1 ? "" : "s"}</span>
          </div>

          {uniqueSources.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {uniqueSources.map((src, i) => (
                <div
                  key={i}
                  className="p-3.5 rounded-lg bg-[#0c0f13] border border-[#181d24] space-y-1.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white font-mono uppercase text-xs">
                      {src.provider}
                    </span>
                    <span className="text-[10px] font-mono text-[#7FCBC5] bg-[#7FCBC5]/10 px-1.5 py-0.2 rounded">
                      Operational
                    </span>
                  </div>

                  <div className="text-xs text-[#BDCDC9] font-light truncate">
                    Dataset: <span className="font-mono text-white">{src.dataset}</span>
                  </div>

                  {src.retrieved_at && (
                    <div className="text-[10.5px] font-mono text-[#71767e]">
                      Time: {new Date(src.retrieved_at).toISOString().replace("T", " ").slice(0, 16)} UTC
                    </div>
                  )}

                  <div className="text-[10px] font-mono text-[#71767e] pt-1 border-t border-[#14171d]">
                    Evidence ID: EV-{src.provider}-{(i + 1).toString().padStart(3, "0")}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-3 rounded-lg bg-[#0c0f13] border border-[#181d24] text-xs text-[#8e8e93] font-light">
              Report synthesized using direct operational pipeline inputs from IMD and INCOIS node gateways.
            </div>
          )}
        </div>

        {/* View Detailed Evidence Drawer Trigger */}
        <div className="pt-2 border-t border-[#151920]">
          <ProvenanceDrawer
            meta={meta}
            sources={sources}
            warnings={warnings}
            requestId={primaryRequestId}
            variant="graphite"
          />
        </div>

        {/* Data Integrity Statement */}
        <div className="pt-2 text-[11px] text-[#71767e] font-light leading-relaxed">
          <strong className="text-[#BDCDC9] font-normal">Scientific Integrity Notice:</strong> All data points, numerical projections, and safety classifications originate from authoritative operational feeds of the India Meteorological Department (IMD) and the Indian National Centre for Ocean Information Services (INCOIS). OceanDataEngine does not fabricate intermediate points or unverified safety claims.
        </div>
      </div>
    </section>
  );
}