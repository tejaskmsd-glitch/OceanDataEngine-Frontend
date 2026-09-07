"use client";

import { useEffect, useRef } from "react";

export function UnderwaterAtmosphere() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.defaultMuted = true;
      video.muted = true;
      const playPromise = video.play();
      if (playPromise !== undefined) {
        playPromise.catch(() => {
          // Autoplay policy fallback
        });
      }
    }
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none select-none -z-10">
      {/* 1. Approved Underwater Hero Video */}
      <video
        ref={videoRef}
        autoPlay
        loop
        muted
        playsInline
        controls={false}
        preload="auto"
        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
      >
        <source src="/videos/underwater-hero.mp4" type="video/mp4" />
      </video>

      {/* 2. Very subtle localized gradient behind open-water text area only - never over-darkening video */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-black/10 via-30% to-transparent pointer-events-none" />

      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 40% at 50% 28%, rgba(2, 8, 18, 0.30) 0%, rgba(2, 8, 18, 0.06) 60%, transparent 100%)",
        }}
      />
    </div>
  );
}
