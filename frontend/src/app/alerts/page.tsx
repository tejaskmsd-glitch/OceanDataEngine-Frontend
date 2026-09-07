"use client";

import { useEffect, useState } from "react";
import {
  Bell,
  Radio,
  Volume2,
  VolumeX,
  Search,
  Filter,
  AlertTriangle,
  Clock,
  MapPin,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import type { AlertModel, Envelope } from "@/types/api";
import { api } from "@/lib/api";
import { useAlertStream } from "@/lib/useAlertStream";
import { LoadingView, ErrorView, EmptyDataView } from "@/components/ui/StateViews";
import { ProvenanceDrawer } from "@/components/provenance/ProvenanceDrawer";

const SEVERITY_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  extreme: { bg: "bg-[#261515]", text: "text-[#fca5a5]", border: "border-[#441f1f]" },
  severe: { bg: "bg-[#241c14]", text: "text-[#fdba74]", border: "border-[#402d1a]" },
  moderate: { bg: "bg-[#222014]", text: "text-[#fde047]", border: "border-[#3d381c]" },
  minor: { bg: "bg-[#161a20]", text: "text-[#93c5fd]", border: "border-[#222c3b]" },
  unknown: { bg: "bg-[#111214]", text: "text-[#9ca3af]", border: "border-[#202124]" },
};

export default function AlertsPage() {
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [alerts, setAlerts] = useState<AlertModel[]>([]);
  const [envelope, setEnvelope] = useState<Envelope<any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [severityFilter, setSeverityFilter] = useState("all");
  const [searchFilter, setSearchFilter] = useState("");

  // Connect to live WebSocket stream
  const { alerts: wsAlerts, status: wsStatus, lastEventAt } = useAlertStream({
    soundEnabled,
  });

  // Fetch baseline active alerts via REST
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    api
      .alerts({ limit: 100 })
      .then((res) => {
        if (!mounted) return;
        setLoading(false);
        setAlerts(res.data);
        setEnvelope(res.envelope);
      })
      .catch((err) => {
        if (!mounted) return;
        setLoading(false);
        setError(err.message || "Failed to query active marine alerts");
      });

    return () => {
      mounted = false;
    };
  }, []);

  // Merge REST baseline with any incoming WebSocket events (deduplicating by alert_uid)
  const combinedAlerts = (() => {
    const map = new Map<string, AlertModel>();
    for (const a of wsAlerts) {
      if (a.alert_uid) map.set(a.alert_uid, a);
    }
    for (const a of alerts) {
      if (a.alert_uid && !map.has(a.alert_uid)) map.set(a.alert_uid, a);
    }
    return Array.from(map.values());
  })();

  const filteredAlerts = combinedAlerts.filter((a) => {
    const matchesSeverity =
      severityFilter === "all" || a.severity.toLowerCase() === severityFilter.toLowerCase();
    const searchTarget = `${a.headline || ""} ${a.description || ""} ${
      a.area_description || ""
    } ${a.event_type || ""}`.toLowerCase();
    const matchesSearch = !searchFilter || searchTarget.includes(searchFilter.toLowerCase());
    return matchesSeverity && matchesSearch;
  });

  return (
    <div className="flex-1 min-h-screen pt-20 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full space-y-8 font-sans">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-light text-white tracking-tight">
            Marine Hazard & Coastal Warning Feed
          </h1>
          <p className="text-xs sm:text-sm text-[#9ca3af] max-w-2xl leading-relaxed">
            Real-time hazard notifications broadcast by the India Meteorological Department
            (IMD) and INCOIS for cyclones, high waves, gale winds, and swell surges.
          </p>
        </div>

        {/* Live Stream Telemetry Pill */}
        <div className="flex items-center space-x-3 p-2.5 rounded-md bg-[#111214] border border-[#202124] shrink-0 text-xs">
          <div className="flex items-center space-x-2">
            <Radio
              className={`w-3.5 h-3.5 ${
                wsStatus === "connected"
                  ? "text-[#22c55e]"
                  : wsStatus === "connecting"
                  ? "text-[#eab308] animate-spin"
                  : "text-[#ef4444]"
              }`}
            />
            <span className="text-[#9ca3af] capitalize">
              WS: <span className="text-white">{wsStatus}</span>
            </span>
          </div>

          <div className="h-4 w-px bg-[#202124]" />

          <button
            type="button"
            onClick={() => setSoundEnabled((prev) => !prev)}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded transition-colors text-xs ${
              soundEnabled
                ? "bg-[#1e2023] text-white border border-[#2c2e33]"
                : "bg-[#0d0e10] text-[#9ca3af] hover:text-white border border-[#202124]"
            }`}
            title="Toggle audible chime for incoming severe hazard warnings"
          >
            {soundEnabled ? (
              <Volume2 className="w-3.5 h-3.5" />
            ) : (
              <VolumeX className="w-3.5 h-3.5" />
            )}
            <span>Audio {soundEnabled ? "ON" : "OFF"}</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-md bg-[#111214] border border-[#202124]">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-[#8e8e93] mr-1 text-[11px] uppercase tracking-wide">Severity:</span>
          {["all", "extreme", "severe", "moderate", "minor"].map((sev) => (
            <button
              key={sev}
              type="button"
              onClick={() => setSeverityFilter(sev)}
              className={`px-2.5 py-1 rounded capitalize transition-colors text-xs ${
                severityFilter === sev
                  ? "bg-[#202124] text-white font-medium border border-[#2c2d31]"
                  : "bg-[#0d0e10] text-[#9ca3af] hover:text-white border border-[#202124]"
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        <div className="relative sm:w-64">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#8e8e93]" />
          <input
            type="text"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Search headline, area..."
            className="w-full bg-[#0d0e10] border border-[#202124] rounded pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-[#6b7280] focus:outline-none focus:border-white/40 transition-colors"
          />
        </div>
      </div>

      {/* Alerts Feed */}
      {loading ? (
        <LoadingView label="Connecting to CAP warning registry..." variant="graphite" />
      ) : error ? (
        <ErrorView message="Failed to load hazard alerts" detail={error} variant="graphite" />
      ) : filteredAlerts.length > 0 ? (
        <div className="space-y-3">
          {filteredAlerts.map((alert) => {
            const badge =
              SEVERITY_BADGES[alert.severity?.toLowerCase()] || SEVERITY_BADGES.unknown;

            return (
              <div
                key={alert.alert_uid}
                className="bg-[#111214] rounded-md p-4 border border-[#202124] space-y-3 hover:border-[#33353a] transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center space-x-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider border ${badge.bg} ${badge.text} ${badge.border}`}
                    >
                      {alert.severity}
                    </span>
                    <span className="text-xs font-medium text-white uppercase">
                      {alert.provider}
                    </span>
                    <span className="text-xs text-[#8e8e93]">·</span>
                    <span className="text-xs text-[#9ca3af] capitalize">
                      {alert.event_type.replace(/_/g, " ")}
                    </span>
                  </div>

                  {alert.issued_at && (
                    <div className="text-[11px] font-mono text-[#8e8e93] flex items-center space-x-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      <span>Issued: {new Date(alert.issued_at).toLocaleString()}</span>
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="text-base font-medium text-white leading-snug">
                    {alert.headline || alert.event_type}
                  </h3>
                  {alert.description && (
                    <p className="text-xs text-[#9ca3af] mt-1.5 leading-relaxed font-sans">
                      {alert.description}
                    </p>
                  )}
                </div>

                {alert.area_description && (
                  <div className="flex items-start space-x-2 text-xs text-[#9ca3af] bg-[#0d0e10] p-2.5 rounded border border-[#202124]">
                    <MapPin className="w-3.5 h-3.5 text-[#8e8e93] shrink-0 mt-0.5" />
                    <span>Area: {alert.area_description}</span>
                  </div>
                )}

                <div className="pt-2 border-t border-[#1a1b1e] flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#8e8e93]">
                  <div className="flex items-center space-x-3">
                    <span>Certainty: <span className="text-[#9ca3af]">{alert.certainty}</span></span>
                    <span>·</span>
                    <span>Urgency: <span className="text-[#9ca3af]">{alert.urgency}</span></span>
                  </div>

                  {alert.valid_until && (
                    <span className="font-mono">Valid Until: {new Date(alert.valid_until).toLocaleString()}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyDataView
          title="No active hazard alerts matching filter"
          description="The marine atmosphere in this sector is currently clear with no active CAP bulletins published by IMD or INCOIS."
          variant="graphite"
        />
      )}

      {/* Provenance Audit for Alerts Query */}
      {envelope && (
        <div className="pt-4">
          <ProvenanceDrawer
            meta={envelope.meta}
            sources={envelope.sources}
            warnings={envelope.warnings}
            quality={envelope.quality}
            variant="graphite"
          />
        </div>
      )}
    </div>
  );
}
