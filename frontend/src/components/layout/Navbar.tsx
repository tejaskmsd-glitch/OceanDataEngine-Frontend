"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Compass,
  Layers,
  Bell,
  Info,
  Volume2,
  VolumeX,
  Radio,
  Menu,
  X,
} from "lucide-react";
import { api } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/explore", label: "Explore", icon: Compass },
  { href: "/datasets", label: "Datasets", icon: Layers },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/about", label: "About", icon: Info },
];

export function Navbar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    api
      .health()
      .then((h) => {
        if (mounted) setBackendHealthy(h.status === "ok");
      })
      .catch(() => {
        if (mounted) setBackendHealthy(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const isHome = pathname === "/";

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-colors duration-200 ${
        isHome
          ? "bg-[#08090a]/70 backdrop-blur-md border-b border-white/[0.08]"
          : "bg-[#08090a] border-b border-[#202124]"
      }`}
    >
      <div className="w-full px-5 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Brand identity */}
        <Link href="/" className="flex items-center space-x-3 group">
          <div className="w-4 h-4 rounded-full border border-white/30 flex items-center justify-center transition-colors group-hover:border-white/60">
            <span className="w-1.5 h-1.5 rounded-full bg-white" />
          </div>
          <div className="flex flex-col">
            <span className="font-medium tracking-tight text-white text-[15px] transition-colors">
              OceanDataEngine
            </span>
            <span className="text-[10px] text-[#8e8e93] tracking-wide font-sans font-normal">
              Marine Intelligence Layer
            </span>
          </div>
        </Link>

        {/* Desktop navigation */}
        <nav className="hidden md:flex items-center space-x-7">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative py-1 text-[13px] transition-colors font-sans ${
                  isActive
                    ? "text-white font-medium"
                    : "text-[#9ca3af] hover:text-white font-normal"
                }`}
              >
                <span>{item.label}</span>
                {isActive && (
                  <span className="absolute bottom-[-5px] left-0 right-0 h-[1.5px] bg-white rounded-full" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right side controls */}
        <div className="hidden sm:flex items-center space-x-2.5">
          {/* Audio Chime Toggle */}
          <button
            type="button"
            onClick={() => setSoundEnabled((prev) => !prev)}
            title={soundEnabled ? "Alert Chimes Active" : "Alert Chimes Muted"}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-sans transition-colors border ${
              soundEnabled
                ? "bg-[#18191c] border-[#2c2d31] text-white"
                : "bg-[#111214] border-[#202124] text-[#9ca3af] hover:text-white hover:bg-[#16171a]"
            }`}
          >
            {soundEnabled ? (
              <Volume2 className="w-3.5 h-3.5 text-white" />
            ) : (
              <VolumeX className="w-3.5 h-3.5 text-[#8e8e93]" />
            )}
            <span>Audio {soundEnabled ? "ON" : "OFF"}</span>
          </button>

          {/* Backend link indicator */}
          <div
            className="flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-sans bg-[#111214] border border-[#202124] text-[#9ca3af]"
            title={
              backendHealthy === true
                ? "Backend API Connected (Port 8000)"
                : backendHealthy === false
                ? "Backend API Unreachable"
                : "Connecting to API..."
            }
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                backendHealthy === true
                  ? "bg-[#22c55e]"
                  : backendHealthy === false
                  ? "bg-[#ef4444]"
                  : "bg-[#eab308]"
              }`}
            />
            <span className="text-[11px] text-[#9ca3af]">
              {backendHealthy === true
                ? "Live API"
                : backendHealthy === false
                ? "Offline"
                : "Syncing"}
            </span>
          </div>
        </div>

        {/* Mobile menu button */}
        <div className="md:hidden flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-1.5 rounded text-[#9ca3af] hover:text-white hover:bg-[#16171a] transition-colors"
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile navigation dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden px-5 pt-2 pb-4 bg-[#08090a] border-b border-[#202124]">
          <nav className="space-y-1 font-sans">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`block px-3 py-2 rounded text-sm font-normal transition-colors ${
                    isActive
                      ? "text-white bg-[#16171a] font-medium"
                      : "text-[#9ca3af] hover:text-white hover:bg-[#111214]"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-3 pt-3 border-t border-[#202124] flex items-center justify-between text-xs font-sans text-[#9ca3af]">
            <button
              type="button"
              onClick={() => setSoundEnabled(!soundEnabled)}
              className="flex items-center space-x-2 text-[#9ca3af] hover:text-white"
            >
              {soundEnabled ? (
                <Volume2 className="w-4 h-4 text-white" />
              ) : (
                <VolumeX className="w-4 h-4 text-[#8e8e93]" />
              )}
              <span>Audio: {soundEnabled ? "ON" : "OFF"}</span>
            </button>
            <span className="flex items-center space-x-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  backendHealthy ? "bg-[#22c55e]" : "bg-[#ef4444]"
                }`}
              />
              <span>API: {backendHealthy ? "Connected" : "Offline"}</span>
            </span>
          </div>
        </div>
      )}
    </header>
  );
}
