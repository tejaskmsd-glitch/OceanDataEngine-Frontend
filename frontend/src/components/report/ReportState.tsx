"use client";

import Link from "next/link";
import { Compass, ArrowRight, Layers } from "lucide-react";

interface MissingLocationProps {
  onSelectCoords?: (lat: number, lon: number, radius?: number) => void;
}

const PRESET_LOCATIONS = [
  { name: "Goa Coast (West Coast)", lat: 15.49, lon: 73.82, radius: 150 },
  { name: "Mumbai Offshore", lat: 18.95, lon: 72.83, radius: 150 },
  { name: "Bay of Bengal (Buoy BD08)", lat: 18.15, lon: 89.68, radius: 200 },
  { name: "Arabian Sea Central", lat: 14.02, lon: 69.24, radius: 200 },
  { name: "Kochi Coast (Kerala)", lat: 9.93, lon: 76.26, radius: 150 },
  { name: "Visakhapatnam (East Coast)", lat: 17.68, lon: 83.22, radius: 150 },
];

export function MissingLocationView({ onSelectCoords }: MissingLocationProps) {
  return (
    <div className="max-w-2xl mx-auto py-16 px-4 sm:px-6 text-center space-y-8 font-sans">
      <div className="w-12 h-12 rounded-full bg-[#111214] border border-[#202124] text-[#7FCBC5] mx-auto flex items-center justify-center shadow-md">
        <Compass className="w-6 h-6" />
      </div>

      <div className="space-y-2">
        <h2 className="text-xl sm:text-2xl font-light text-white tracking-wide">
          Geographic Target Required
        </h2>
        <p className="text-xs sm:text-sm text-[#8e8e93] max-w-lg mx-auto leading-relaxed">
          The Visual Data Report compiles in-situ telemetry, numerical model forecasts, and risk assessments for a specific spatial coordinate. Please provide target coordinates or select a verified maritime region.
        </p>
      </div>

      {/* Recommended verified target regions */}
      <div className="space-y-3 text-left">
        <div className="text-[11px] font-mono uppercase text-[#7FCBC5]/80 tracking-wider">
          Verified Indian Ocean Coordinates
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {PRESET_LOCATIONS.map((loc) => (
            <Link
              key={loc.name}
              href={`/report?lat=${loc.lat}&lon=${loc.lon}&radius=${loc.radius}`}
              className="p-3 rounded-lg bg-[#0d0f12] hover:bg-[#131519] border border-[#202124] hover:border-[#7FCBC5]/40 transition-all flex items-center justify-between group"
            >
              <div className="space-y-0.5">
                <div className="text-xs text-white font-medium group-hover:text-[#7FCBC5] transition-colors">
                  {loc.name}
                </div>
                <div className="text-[11px] font-mono text-[#71767e]">
                  {loc.lat.toFixed(2)}°N, {loc.lon.toFixed(2)}°E · {loc.radius} km
                </div>
              </div>
              <ArrowRight className="w-3.5 h-3.5 text-[#71767e] group-hover:text-[#7FCBC5] group-hover:translate-x-0.5 transition-all" />
            </Link>
          ))}
        </div>
      </div>

      {/* Alternative: Open in Explore */}
      <div className="pt-4 border-t border-[#202124]">
        <Link
          href="/explore"
          className="inline-flex items-center space-x-2 text-xs text-[#8e8e93] hover:text-white transition-colors"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Or select coordinates interactively via Map Explorer</span>
        </Link>
      </div>
    </div>
  );
}

export function ReportLoadingSkeleton() {
  return (
    <div className="max-w-5xl mx-auto py-10 px-4 sm:px-6 lg:px-8 space-y-8 animate-pulse font-sans">
      {/* Header skeleton */}
      <div className="space-y-3 border-b border-[#202124] pb-6">
        <div className="h-4 w-32 bg-[#16181d] rounded" />
        <div className="h-8 w-64 bg-[#16181d] rounded" />
        <div className="h-4 w-48 bg-[#16181d] rounded" />
      </div>

      {/* Finding skeleton */}
      <div className="h-28 bg-[#111317] rounded-xl border border-[#202124]" />

      {/* Metrics skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 bg-[#0d0f12] rounded-lg border border-[#202124]" />
        ))}
      </div>

      {/* Chart skeleton */}
      <div className="h-64 bg-[#0d0f12] rounded-xl border border-[#202124]" />
    </div>
  );
}