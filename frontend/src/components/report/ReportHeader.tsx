"use client";

import Link from "next/link";
import { Compass, Printer, Radio, Calendar, FileText } from "lucide-react";

interface ReportHeaderProps {
  location: { lat: number; lon: number };
  radiusKm: number;
  queryText?: string | null;
  referenceTime?: string | null;
  sourceCount: number;
  activeTab?: string;
}

function getMarineBasin(lat: number, lon: number): string {
  if (lat >= 8 && lat <= 26 && lon >= 65 && lon <= 77.5) {
    return "Arabian Sea";
  }
  if (lat >= 8 && lat <= 24 && lon > 77.5 && lon <= 95) {
    return "Bay of Bengal";
  }
  if (lat >= 6 && lat < 14 && lon >= 71 && lon <= 75) {
    return "Lakshadweep Sea";
  }
  if (lat >= 6 && lat <= 14 && lon >= 92 && lon <= 94) {
    return "Andaman Sea";
  }
  if (lat < 8) {
    return "Equatorial Indian Ocean";
  }
  return "Northern Indian Ocean";
}

export function ReportHeader({
  location,
  radiusKm,
  queryText,
  referenceTime,
  sourceCount,
  activeTab = "conditions",
}: ReportHeaderProps) {
  const basin = getMarineBasin(location.lat, location.lon);

  const formattedDate = referenceTime
    ? new Date(referenceTime).toUTCString().replace("GMT", "UTC")
    : new Date().toUTCString().replace("GMT", "UTC");

  const docId = `ODE-REP-${Math.abs(location.lat * 100).toFixed(0)}-${Math.abs(location.lon * 100).toFixed(0)}`;

  return (
    <header className="space-y-6 font-sans">
      {/* Top micro-tag & actions bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-2 text-[10.5px] font-mono uppercase tracking-[0.18em] text-[#7FCBC5]">
          <span>Marine Intelligence Report</span>
        </div>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-[#0e1216] border border-[#1f252d] text-[11px] font-mono text-[#BDCDC9]">
            <Radio className="w-2.5 h-2.5 text-[#22c55e] animate-pulse" />
            <span>
              {sourceCount > 0
                ? `${sourceCount} Grounded Dataset${sourceCount === 1 ? "" : "s"}`
                : "Authoritative Feeds Monitored"}
            </span>
          </div>

          <button
            type="button"
            onClick={() => window.print()}
            className="hidden sm:inline-flex items-center space-x-1.5 px-3 py-1 rounded-md bg-[#101317] hover:bg-[#181c22] border border-[#1f2329] text-[11px] text-[#8e8e93] hover:text-white transition-colors"
            title="Print or export as PDF"
          >
            <Printer className="w-3 h-3" />
            <span>Print Report</span>
          </button>

          <Link
            href={`/explore?lat=${location.lat}&lon=${location.lon}&radius=${radiusKm}&tab=${activeTab}`}
            className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-md bg-[#12161b] hover:bg-[#181f26] border border-[#222b35] hover:border-[#7FCBC5]/40 text-xs text-white transition-all group"
          >
            <Compass className="w-3.5 h-3.5 text-[#7FCBC5] group-hover:rotate-45 transition-transform duration-300" />
            <span>Open in Map Explorer</span>
          </Link>
        </div>
      </div>

      {/* Editorial Title & Location Area */}
      <div className="space-y-2">
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-light tracking-tight text-[#F4F7F5]">
          {basin}
        </h1>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm sm:text-base text-[#BDCDC9] font-light">
          <span className="font-mono text-white font-normal">
            {location.lat.toFixed(3)}°N · {location.lon.toFixed(3)}°E
          </span>
          <span className="text-[#3a3e47]">·</span>
          <span className="text-[#8e8e93]">
            {radiusKm} km area around this location
          </span>
        </div>
      </div>

      {/* Thin editorial divider */}
      <div className="border-t border-[#1b1f26]" />

      {/* Subline & Timestamp Strip */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-[#8e8e93]">
        <div className="flex items-center space-x-2 text-[#BDCDC9] font-normal">
          <span>Current observations</span>
          <span className="text-[#383a40]">·</span>
          <span>Forecast</span>
          <span className="text-[#383a40]">·</span>
          <span>Risk</span>
          <span className="text-[#383a40]">·</span>
          <span>Warnings</span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[#71767e]">
          <span className="flex items-center space-x-1.5">
            <Calendar className="w-3 h-3 text-[#7FCBC5]/70" />
            <span>Generated {formattedDate}</span>
          </span>
          <span className="text-[#383a40]">·</span>
          <span>Document {docId}</span>
        </div>
      </div>

      {/* Query Context Strip if user entered a search prompt */}
      {queryText && (
        <div className="p-3 rounded-lg bg-[#0c0f13] border border-[#1b2027] flex items-center space-x-3 text-xs">
          <span className="text-[10px] font-mono uppercase text-[#7FCBC5] tracking-wider shrink-0 font-medium">
            Report Focus
          </span>
          <span className="text-[#BDCDC9] font-light italic truncate">
            “{queryText}”
          </span>
        </div>
      )}
    </header>
  );
}