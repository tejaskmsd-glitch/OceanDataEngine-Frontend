"use client";

import Link from "next/link";
import { Compass, Layers, MapPin } from "lucide-react";

interface SpatialContextProps {
  location: { lat: number; lon: number };
  radiusKm: number;
  activeTab?: string;
}

export function SpatialContext({
  location,
  radiusKm,
  activeTab = "conditions",
}: SpatialContextProps) {
  return (
    <section className="space-y-6 font-sans">
      {/* Editorial Section Header (Requirement 1) */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-[#1b1f26] pb-3">
        <div className="flex items-center space-x-2.5">
          <span className="text-[11px] font-mono text-[#7FCBC5] tracking-wider">09</span>
          <h2 className="text-sm font-mono uppercase tracking-[0.14em] text-[#BDCDC9] font-medium">
            Explore This Area
          </h2>
        </div>
        <span className="text-[11.5px] text-[#71767e] font-light">
          Interactive spatial mapping & bathymetric visualization
        </span>
      </div>

      <div className="p-4 sm:p-5 rounded-xl bg-[#0a0d11] border border-[#1b222a] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-white font-medium">
            <MapPin className="w-3.5 h-3.5 text-[#7FCBC5]" />
            <span>Target Anchor: {location.lat.toFixed(3)}°N · {location.lon.toFixed(3)}°E ({radiusKm} km radius)</span>
          </div>
          <p className="text-[#BDCDC9] font-light text-xs max-w-lg leading-relaxed">
            Transition directly to the interactive Map Explorer to inspect spatial buoy telemetry markers, PFZ polygons, hazard polygons, and safe route calculations.
          </p>
        </div>

        <div className="flex items-center space-x-2.5 shrink-0">
          <Link
            href={`/explore?lat=${location.lat}&lon=${location.lon}&radius=${radiusKm}&tab=${activeTab}`}
            className="inline-flex items-center space-x-2 px-4 py-2 rounded-md bg-[#12161b] hover:bg-[#181f26] border border-[#222b35] hover:border-[#7FCBC5]/40 text-xs font-medium text-white transition-all group shadow-sm"
          >
            <Compass className="w-3.5 h-3.5 text-[#7FCBC5] group-hover:rotate-45 transition-transform duration-300" />
            <span>Open in Map Explorer</span>
          </Link>

          <Link
            href="/datasets"
            className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-md bg-[#101317] hover:bg-[#181c22] border border-[#1f2329] text-xs text-[#8e8e93] hover:text-white transition-colors"
          >
            <Layers className="w-3.5 h-3.5 text-[#71767e]" />
            <span>Datasets</span>
          </Link>
        </div>
      </div>
    </section>
  );
}