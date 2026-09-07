"use client";

import { useState } from "react";
import { ShieldCheck, ChevronRight, ExternalLink, Clock, Database, AlertCircle, FileText } from "lucide-react";
import type { EvidenceModel, Meta, QualityModel, SourceRef } from "@/types/api";
import { api } from "@/lib/api";

interface ProvenanceProps {
  meta?: Meta | null;
  sources?: SourceRef[];
  warnings?: string[];
  quality?: QualityModel | null;
  requestId?: string;
  variant?: "default" | "graphite";
}

export function ProvenanceDrawer({
  meta,
  sources = [],
  warnings = [],
  quality,
  requestId,
  variant = "default",
}: ProvenanceProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [evidenceDetails, setEvidenceDetails] = useState<EvidenceModel | null>(null);
  const [isLoadingEvidence, setIsLoadingEvidence] = useState(false);

  const activeRequestId = requestId || meta?.request_id;

  const loadEvidence = async () => {
    if (!activeRequestId || evidenceDetails) return;
    setIsLoadingEvidence(true);
    try {
      const res = await api.evidence(activeRequestId);
      setEvidenceDetails(res.data);
    } catch {
      // Evidence endpoint may 404 if request was transient
    } finally {
      setIsLoadingEvidence(false);
    }
  };

  if (variant === "graphite") {
    return (
      <div className="bg-[#111214] rounded-lg p-3 text-xs space-y-2 border border-[#202124] font-sans">
        {/* Summary Bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-[#9ca3af]">
            <ShieldCheck className="w-4 h-4 text-[#8e8e93]" />
            <span className="font-medium text-white">Data Provenance</span>
            {activeRequestId && (
              <span className="text-[10px] font-mono text-[#8e8e93] truncate max-w-[130px]">
                ID: {activeRequestId}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              setIsOpen((prev) => !prev);
              if (!isOpen) loadEvidence();
            }}
            className="flex items-center space-x-1 text-[#9ca3af] hover:text-white text-[11px] font-sans transition-colors"
          >
            <span>{isOpen ? "Hide" : "Inspect"}</span>
            <ChevronRight className={`w-3 h-3 transition-transform ${isOpen ? "rotate-90" : ""}`} />
          </button>
        </div>

        {/* Warnings strip if any */}
        {warnings.length > 0 && (
          <div className="p-2 rounded-md bg-[#241717] border border-[#3d2424] text-[#fca5a5] space-y-1">
            {warnings.map((warn, i) => (
              <div key={i} className="flex items-start space-x-1.5 text-[11px] font-sans">
                <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-[#ef4444]" />
                <span>{warn}</span>
              </div>
            ))}
          </div>
        )}

        {/* Collapsible Details */}
        {isOpen && (
          <div className="pt-2 border-t border-[#202124] space-y-3">
            {/* Sources List */}
            {sources.length > 0 ? (
              <div className="space-y-1.5">
                <span className="text-[10px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                  Upstream Sources ({sources.length})
                </span>
                <div className="space-y-1">
                  {sources.map((src, i) => (
                    <div
                      key={i}
                      className="p-2 rounded-md bg-[#0d0e10] border border-[#202124] text-[11px] space-y-1 font-sans"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-white">{src.provider.toUpperCase()}</span>
                        <span className="text-[#9ca3af]">{src.dataset}</span>
                      </div>
                      {src.source_url && (
                        <a
                          href={src.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[#9ca3af] hover:text-white hover:underline flex items-center space-x-1 truncate text-[10px] transition-colors"
                        >
                          <span className="truncate">{src.source_url}</span>
                          <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                        </a>
                      )}
                      {src.retrieved_at && (
                        <div className="text-[10px] text-[#8e8e93] flex items-center space-x-1 font-mono">
                          <Clock className="w-2.5 h-2.5" />
                          <span>Retrieved: {new Date(src.retrieved_at).toLocaleString()}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-[#8e8e93] italic">
                No individual source records attached to this envelope.
              </p>
            )}

            {/* Evidence Record details if loaded */}
            {isLoadingEvidence && (
              <p className="text-[10px] font-sans text-[#8e8e93]">Loading backend evidence record...</p>
            )}

            {evidenceDetails && (
              <div className="p-2.5 rounded-md bg-[#0d0e10] border border-[#202124] space-y-1.5 text-[11px] font-sans">
                <div className="flex items-center justify-between text-[#8e8e93] text-[10px]">
                  <span>Evidence Endpoint:</span>
                  <span className="text-white font-mono">{evidenceDetails.endpoint}</span>
                </div>
                <div className="flex items-center justify-between text-[#8e8e93] text-[10px]">
                  <span>Generated At:</span>
                  <span className="text-white font-mono">
                    {new Date(evidenceDetails.generated_at).toLocaleString()}
                  </span>
                </div>
                {evidenceDetails.capability_status && (
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-[#8e8e93]">Capability:</span>
                    <span className="text-white">{evidenceDetails.capability_status}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="ocean-panel-subtle rounded-lg p-3 text-xs space-y-2 border border-ocean-border">
      {/* Summary Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-ocean-muted">
          <ShieldCheck className="w-4 h-4 text-ocean-teal-light" />
          <span className="font-medium text-ocean-text">Data Provenance</span>
          {activeRequestId && (
            <span className="text-[10px] font-mono text-ocean-dim truncate max-w-[130px]">
              ID: {activeRequestId}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => {
            setIsOpen((prev) => !prev);
            if (!isOpen) loadEvidence();
          }}
          className="flex items-center space-x-1 text-ocean-teal-light hover:underline font-mono text-[11px]"
        >
          <span>{isOpen ? "Hide" : "Inspect"}</span>
          <ChevronRight className={`w-3 h-3 transition-transform ${isOpen ? "rotate-90" : ""}`} />
        </button>
      </div>

      {/* Warnings strip if any */}
      {warnings.length > 0 && (
        <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 space-y-1">
          {warnings.map((warn, i) => (
            <div key={i} className="flex items-start space-x-1.5 text-[11px] font-mono">
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-400" />
              <span>{warn}</span>
            </div>
          ))}
        </div>
      )}

      {/* Collapsible Details */}
      {isOpen && (
        <div className="pt-2 border-t border-ocean-border/60 space-y-3">
          {/* Sources List */}
          {sources.length > 0 ? (
            <div className="space-y-1.5">
              <span className="text-[10px] font-mono uppercase text-ocean-dim tracking-wider">
                Upstream Sources ({sources.length})
              </span>
              <div className="space-y-1">
                {sources.map((src, i) => (
                  <div
                    key={i}
                    className="p-2 rounded bg-ocean-surface/60 border border-ocean-border/50 text-[11px] space-y-1 font-mono"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-ocean-text">{src.provider.toUpperCase()}</span>
                      <span className="text-ocean-muted">{src.dataset}</span>
                    </div>
                    {src.source_url && (
                      <a
                        href={src.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-ocean-teal-light hover:underline flex items-center space-x-1 truncate text-[10px]"
                      >
                        <span className="truncate">{src.source_url}</span>
                        <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                      </a>
                    )}
                    {src.retrieved_at && (
                      <div className="text-[10px] text-ocean-dim flex items-center space-x-1">
                        <Clock className="w-2.5 h-2.5" />
                        <span>Retrieved: {new Date(src.retrieved_at).toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-ocean-dim italic">
              No individual source records attached to this envelope.
            </p>
          )}

          {/* Evidence Record details if loaded */}
          {isLoadingEvidence && (
            <p className="text-[10px] font-mono text-ocean-dim">Loading backend evidence record...</p>
          )}

          {evidenceDetails && (
            <div className="p-2.5 rounded bg-ocean-surface/80 border border-ocean-border space-y-1.5 text-[11px] font-mono">
              <div className="flex items-center justify-between text-ocean-dim text-[10px]">
                <span>Evidence Endpoint:</span>
                <span className="text-ocean-text">{evidenceDetails.endpoint}</span>
              </div>
              <div className="flex items-center justify-between text-ocean-dim text-[10px]">
                <span>Generated At:</span>
                <span className="text-ocean-text">
                  {new Date(evidenceDetails.generated_at).toLocaleString()}
                </span>
              </div>
              {evidenceDetails.capability_status && (
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-ocean-dim">Capability:</span>
                  <span className="text-amber-400">{evidenceDetails.capability_status}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
