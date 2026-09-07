"use client";

import { AlertTriangle, MapPin, Calendar } from "lucide-react";
import type { AlertModel } from "@/types/api";

interface AlertsSectionProps {
  alerts: AlertModel[];
  radiusKm?: number;
}

function getSeverityStyle(severity: string) {
  const s = severity.toLowerCase();
  if (s === "severe" || s === "extreme") {
    return { text: "text-[#f87171]", bg: "bg-[#dc2626]/10", border: "border-[#dc2626]/30", label: "SEVERE" };
  }
  if (s === "moderate") {
    return { text: "text-[#facc15]", bg: "bg-[#ca8a04]/10", border: "border-[#ca8a04]/30", label: "MODERATE" };
  }
  return { text: "text-[#93c5fd]", bg: "bg-[#2563eb]/10", border: "border-[#2563eb]/30", label: "ADVISORY" };
}

export function AlertsSection({ alerts, radiusKm = 150 }: AlertsSectionProps) {
  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header (Requirement 1) */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">06</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Warnings Near You
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Authoritative meteorological & ocean hazard bulletins · IMD & INCOIS
        </span>
      </div>

      {alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const style = getSeverityStyle(alert.severity);
            const validFromStr = alert.valid_from
              ? new Date(alert.valid_from).toISOString().replace("T", " ").replace("Z", " UTC").slice(0, 16)
              : null;
            const validUntilStr = alert.valid_until
              ? new Date(alert.valid_until).toISOString().replace("T", " ").replace("Z", " UTC").slice(0, 16)
              : null;

            return (
              <div
                key={alert.alert_uid}
                className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] space-y-3 text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider font-semibold border ${style.text} ${style.bg} ${style.border}`}
                    >
                      {style.label}
                    </span>
                    <h3 className="text-sm text-white font-medium capitalize">
                      {alert.event_type.replace(/_/g, " ")}
                    </h3>
                  </div>

                  <div className="flex items-center space-x-2 text-[10.5px] font-mono text-[#71767e]">
                    <span>Urgency: {alert.urgency || "Expected"}</span>
                    <span>·</span>
                    <span>Certainty: {alert.certainty || "Likely"}</span>
                  </div>
                </div>

                {alert.headline && (
                  <p className="text-sm text-white font-normal leading-snug">
                    {alert.headline}
                  </p>
                )}

                {alert.description && (
                  <p className="text-xs text-[#BDCDC9] font-light leading-relaxed">
                    {alert.description}
                  </p>
                )}

                {alert.area_description && (
                  <div className="flex items-center space-x-1.5 text-xs text-[#BDCDC9]">
                    <MapPin className="w-3.5 h-3.5 text-[#7FCBC5] shrink-0" />
                    <span>Affected Area: {alert.area_description}</span>
                  </div>
                )}

                {/* Validity & Source footer */}
                <div className="pt-2 border-t border-[#161a20] flex flex-wrap items-center justify-between gap-2 text-[10.5px] font-mono text-[#71767e]">
                  <div className="flex items-center space-x-1.5">
                    <Calendar className="w-3 h-3 text-[#7FCBC5]/70" />
                    <span>
                      Valid: {validFromStr || "Immediate"}{validUntilStr ? ` — ${validUntilStr}` : ""}
                    </span>
                  </div>

                  <div>
                    Source: <strong className="text-[#BDCDC9] font-normal">{alert.provider || "IMD / INCOIS"}</strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty state: Notice requirement strictly states: Do not say "Everything is safe." */
        <div className="py-4 px-1 text-sm text-[#8e8e93] font-light flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#16181d]">
          <p>
            No active warnings were found for this area.
          </p>
          <span className="text-xs font-mono text-[#BDCDC9] px-2 py-0.5 rounded bg-[#111418] border border-[#1b222a] shrink-0 self-start sm:self-auto">
            Authoritative monitoring · Active
          </span>
        </div>
      )}
    </section>
  );
}