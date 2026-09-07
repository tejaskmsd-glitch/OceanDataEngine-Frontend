"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Anchor, ShieldCheck } from "lucide-react";

export function Footer() {
  const pathname = usePathname();
  if (pathname === "/explore") return null;
  return (
    <footer className="border-t border-[#202124] bg-[#08090a] text-[#8e8e93] py-10 px-4 sm:px-6 lg:px-8 font-sans">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex flex-col items-center md:items-start space-y-1">
          <div className="flex items-center space-x-2 text-white font-medium text-sm">
            <Anchor className="w-4 h-4 text-white/70" />
            <span>OceanDataEngine</span>
            <span className="text-[#3a3c42]">·</span>
            <span className="text-xs text-[#8e8e93]">Marine Intelligence</span>
          </div>
          <p className="text-xs text-[#8e8e93] max-w-md text-center md:text-left leading-relaxed">
            Authoritative oceanographic observations, numerical forecasts, and hazard alerts sourced from IMD, INCOIS, MOSDAC, and Marine Regions.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-6 text-xs font-sans">
          <Link href="/explore" className="text-[#8e8e93] hover:text-white transition-colors">
            Map Explorer
          </Link>
          <Link href="/datasets" className="text-[#8e8e93] hover:text-white transition-colors">
            Dataset Catalog
          </Link>
          <Link href="/alerts" className="text-[#8e8e93] hover:text-white transition-colors">
            Hazard Stream
          </Link>
          <Link href="/about" className="text-[#8e8e93] hover:text-white transition-colors">
            About & Methodology
          </Link>
        </div>

        <div className="flex items-center space-x-2 text-xs font-sans text-[#8e8e93]">
          <ShieldCheck className="w-3.5 h-3.5 text-white/70" />
          <span>Verified Contracts</span>
        </div>
      </div>
    </footer>
  );
}
