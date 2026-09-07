import Link from "next/link";
import { Compass } from "lucide-react";
import { UnderwaterAtmosphere } from "@/components/home/UnderwaterAtmosphere";
import { OceanQueryGateway } from "@/components/home/OceanQueryGateway";
import { TypingHeading } from "@/components/home/TypingHeading";

export default function HomePage() {
  return (
    <main className="relative min-h-screen h-screen w-full flex flex-col justify-between items-center px-4 sm:px-6 lg:px-8 text-center pt-16 sm:pt-20 md:pt-24 pb-8 sm:pb-10 md:pb-12 overflow-hidden select-none max-w-full">
      {/* 1. Approved Underwater Video Background (autoplay, loop, muted, playsInline) */}
      <UnderwaterAtmosphere />

      {/* 2. Upper/Middle Content: Headline + Description + Search + Prompts */}
      <div className="relative z-10 w-full max-w-3xl mx-auto flex flex-col items-center">
        {/* Headline */}
        <h1 className="text-3xl sm:text-5xl md:text-[62px] lg:text-[66px] font-[300] tracking-[0.02em] leading-[1.12] text-[#F4F7F5] drop-shadow-[0_2px_14px_rgba(0,0,0,0.5)]">
          <TypingHeading />
        </h1>

        {/* 1. Headline → description: 24–32px breathing room */}
        <p className="mt-6 sm:mt-7 md:mt-8 max-w-lg sm:max-w-[530px] text-xs sm:text-sm md:text-[15.5px] font-[300] leading-[1.65] text-[#BDCDC9] drop-shadow-[0_1px_6px_rgba(0,0,0,0.5)] px-2">
          Discover real-time ocean observations, forecasts, coastal hazard warnings, and spatial analysis across the Indian Ocean, synthesized from verified IMD, INCOIS, and MOSDAC data.
        </p>

        {/* 2. Description → search bar: moderate gap, moved slightly upward */}
        {/* 3. Quick queries: directly below search bar */}
        <div className="mt-4 sm:mt-5 w-full max-w-full">
          <OceanQueryGateway />
        </div>
      </div>

      {/* 4. Lower CTA: Open Map Explorer moved significantly lower toward bottom of hero */}
      <div className="relative z-10 w-full flex justify-center pb-2 sm:pb-3">
        <Link
          href="/explore"
          className="inline-flex items-center space-x-2 px-6 py-2.5 rounded-full bg-[#7FCBC5]/15 hover:bg-[#7FCBC5]/25 border border-[#7FCBC5]/40 hover:border-[#7FCBC5]/75 text-[#F4F7F5] hover:text-white transition-all text-xs font-normal tracking-[0.14em] uppercase shadow-md backdrop-blur-md group"
        >
          <Compass className="w-3.5 h-3.5 text-[#7FCBC5] group-hover:rotate-45 transition-transform duration-300" />
          <span>Open Map Explorer</span>
        </Link>
      </div>
    </main>
  );
}
