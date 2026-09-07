"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ArrowRight } from "lucide-react";

interface QueryPreset {
  label: string;
  query: string;
  href: string;
}

const PRESET_QUERIES: QueryPreset[] = [
  {
    label: "Sea Surface Temperature",
    query: "Show sea surface temperature around the Arabian Sea",
    href: "/explore?lat=17.5&lon=67.0&radius=500&param=sst",
  },
  {
    label: "Conditions near Mumbai",
    query: "What are the ocean conditions near Mumbai?",
    href: "/explore?lat=18.9&lon=72.8&radius=150&tab=conditions",
  },
  {
    label: "Fishing Suitability",
    query: "Is this area suitable for fishing?",
    href: "/explore?lat=15.2&lon=73.8&radius=200&tab=fishing",
  },
  {
    label: "Active Marine Alerts",
    query: "Show marine alerts along the Indian coastline",
    href: "/alerts",
  },
  {
    label: "TEWS Tide Observations",
    query: "What are the tides here?",
    href: "/explore?lat=18.95&lon=72.83&radius=150&tab=tides",
  },
];

export function OceanQueryGateway() {
  const router = useRouter();
  const [queryText, setQueryText] = useState("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = queryText.trim().toLowerCase();
    if (!trimmed) {
      router.push("/explore");
      return;
    }

    // Check for explicit lat,lon patterns e.g. "15.2, 73.8"
    const coordMatch = trimmed.match(/(-?\d+(\.\d+)?)\s*,\s*(-?\d+(\.\d+)?)/);
    if (coordMatch) {
      const lat = parseFloat(coordMatch[1]);
      const lon = parseFloat(coordMatch[3]);
      router.push(`/explore?lat=${lat}&lon=${lon}&radius=200`);
      return;
    }

    // Known marine geographic targets
    if (trimmed.includes("mumbai")) {
      router.push("/explore?lat=18.95&lon=72.83&radius=150&tab=conditions");
    } else if (trimmed.includes("arabian")) {
      router.push("/explore?lat=17.0&lon=66.5&radius=600&param=sst");
    } else if (trimmed.includes("bengal")) {
      router.push("/explore?lat=15.5&lon=87.5&radius=600&param=sst");
    } else if (trimmed.includes("kochi") || trimmed.includes("cochin") || trimmed.includes("kerala")) {
      router.push("/explore?lat=9.93&lon=76.26&radius=150&tab=fishing");
    } else if (trimmed.includes("chennai")) {
      router.push("/explore?lat=13.08&lon=80.27&radius=150&tab=conditions");
    } else if (trimmed.includes("goa")) {
      router.push("/explore?lat=15.49&lon=73.82&radius=150&tab=fishing");
    } else if (trimmed.includes("fish") || trimmed.includes("pfz")) {
      router.push("/explore?lat=15.2&lon=73.8&radius=250&tab=fishing");
    } else if (trimmed.includes("alert") || trimmed.includes("cyclone") || trimmed.includes("wave")) {
      router.push("/alerts");
    } else if (trimmed.includes("tide")) {
      router.push("/explore?lat=18.95&lon=72.83&radius=150&tab=tides");
    } else {
      router.push(`/explore?search=${encodeURIComponent(trimmed)}`);
    }
  };

  return (
    <div className="w-full max-w-md sm:max-w-[500px] mx-auto flex flex-col items-center">
      {/* 1. Refined, more transparent & subtle floating search lens */}
      <form onSubmit={handleSearch} className="relative group w-full">
        <div className="relative flex items-center w-full rounded-full bg-black/25 hover:bg-black/35 focus-within:bg-black/45 border border-white/15 group-hover:border-white/25 group-focus-within:border-[#7FCBC5]/60 transition-all shadow-lg backdrop-blur-md">
          <div className="pl-3.5 pr-2 text-[#7FCBC5]/80 shrink-0">
            <Search className="w-3.5 h-3.5" />
          </div>
          <input
            type="text"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            placeholder="Search ocean data, coordinates..."
            className="w-full min-w-0 py-2.5 pr-20 text-xs sm:text-sm bg-transparent text-[#F4F7F5] placeholder:text-[#BDCDC9]/55 focus:outline-none font-[300]"
          />
          <button
            type="submit"
            className="absolute right-1.5 px-3 py-1 rounded-full bg-white/[0.08] hover:bg-[#7FCBC5]/20 border border-white/15 hover:border-[#7FCBC5]/40 text-[#F4F7F5]/90 hover:text-white text-xs font-[350] tracking-wide flex items-center space-x-1 transition-all shadow-xs shrink-0"
          >
            <span>Explore</span>
            <ArrowRight className="w-3 h-3 text-[#7FCBC5]/80" />
          </button>
        </div>
      </form>

      {/* 2. Quick Queries: Small spacing below search bar, quieter, more compact, subtle */}
      <div className="mt-2.5 flex flex-wrap items-center justify-center gap-x-2 gap-y-0.5 text-[10px] sm:text-[10.5px] font-[300] text-[#A4B8B6]/75 drop-shadow-[0_1px_3px_rgba(0,0,0,0.7)] max-w-full">
        <span className="text-[#7FCBC5]/65 font-mono text-[9px] tracking-wider uppercase">
          Prompts:
        </span>
        {PRESET_QUERIES.map((preset, idx) => (
          <span key={preset.label} className="inline-flex items-center space-x-1.5">
            <button
              type="button"
              onClick={() => router.push(preset.href)}
              className="hover:text-[#7FCBC5] hover:underline underline-offset-2 transition-colors text-left"
            >
              {preset.label}
            </button>
            {idx < PRESET_QUERIES.length - 1 && (
              <span className="text-white/20 select-none">·</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
