"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Layers,
  Filter,
  RefreshCw,
  Compass,
  Sliders,
  ChevronRight,
  ChevronLeft,
} from "lucide-react";
import type { AlertModel, PFZModel, SafeRouteModel, ZoneModel } from "@/types/api";
import { api } from "@/lib/api";
import { MapContainerDynamic } from "@/components/map/MapContainerDynamic";
import { LocationInspector, type InspectorTab } from "@/components/explore/LocationInspector";

function ExploreContent() {
  const searchParams = useSearchParams();

  // Selected coordinate state (defaults to Indian West Coast: 15.2, 73.8)
  const [lat, setLat] = useState<number>(() => {
    const pLat = searchParams.get("lat");
    return pLat ? parseFloat(pLat) : 15.2;
  });

  const [lon, setLon] = useState<number>(() => {
    const pLon = searchParams.get("lon");
    return pLon ? parseFloat(pLon) : 73.8;
  });

  const [radiusKm, setRadiusKm] = useState<number>(() => {
    const pRadius = searchParams.get("radius");
    return pRadius ? parseFloat(pRadius) : 250;
  });

  const [zoom, setZoom] = useState<number>(() => {
    const pZoom = searchParams.get("zoom");
    return pZoom ? parseInt(pZoom, 10) : 5;
  });

  const [activeTab, setActiveTab] = useState<InspectorTab>(() => {
    const pTab = searchParams.get("tab") as InspectorTab;
    return pTab || "conditions";
  });

  // Layer toggle switches
  const [activeLayers, setActiveLayers] = useState({
    alerts: true,
    pfz: true,
    zones: true,
    route: true,
  });

  // Global layer data
  const [alerts, setAlerts] = useState<AlertModel[]>([]);
  const [pfzList, setPfzList] = useState<PFZModel[]>([]);
  const [zones, setZones] = useState<ZoneModel[]>([]);
  const [route, setRoute] = useState<SafeRouteModel | null>(null);

  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorExpanded, setInspectorExpanded] = useState(false);

  // Load global alerts & PFZ on initial mount
  useEffect(() => {
    let mounted = true;
    api
      .alerts({ limit: 100 })
      .then((res) => {
        if (mounted) setAlerts(res.data);
      })
      .catch(() => {});

    api
      .pfz({ lat, lon, radius_km: radiusKm })
      .then((res) => {
        if (mounted) setPfzList(res.data);
      })
      .catch(() => {});

    api
      .geofenceNearby(lat, lon, radiusKm)
      .then((res) => {
        if (mounted) setZones(res.data);
      })
      .catch(() => {});

    return () => {
      mounted = false;
    };
  }, [lat, lon, radiusKm]);

  const handleMapClick = (clickLat: number, clickLon: number) => {
    setLat(clickLat);
    setLon(clickLon);
    setInspectorOpen(true);
  };

  return (
    <div className="flex-1 flex flex-col h-screen pt-14 overflow-hidden bg-[#08090a]">
      {/* Top Map Control Bar - Clean flat dark bar */}
      <div className="h-12 bg-[#08090a] border-b border-[#202124] px-4 flex items-center justify-between z-20 shrink-0 text-xs font-sans">
        {/* Left: Current Coordinates & Radius */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 px-3 py-1 rounded bg-[#111214] border border-[#202124] text-[#8e8e93]">
            <Compass className="w-3.5 h-3.5 text-white/70" />
            <span className="hidden sm:inline text-[#8e8e93]">Target:</span>
            <span className="text-white font-mono">
              {lat.toFixed(3)}°N, {lon.toFixed(3)}°E
            </span>
          </div>

          <div className="hidden md:flex items-center space-x-2 text-[#8e8e93]">
            <span>Radius:</span>
            <select
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
              className="bg-[#111214] border border-[#202124] rounded px-2.5 py-1 text-white focus:outline-none focus:border-white/40 text-xs font-sans cursor-pointer"
            >
              <option value={100} className="bg-[#111214]">100 km</option>
              <option value={250} className="bg-[#111214]">250 km</option>
              <option value={500} className="bg-[#111214]">500 km</option>
              <option value={1000} className="bg-[#111214]">1000 km</option>
            </select>
          </div>
        </div>

        {/* Right: Layer Toggles & Regional Quick Jumps */}
        <div className="flex items-center space-x-2.5">
          {/* Quick Regions */}
          <div className="hidden lg:flex items-center space-x-1.5 text-[#8e8e93]">
            <button
              type="button"
              onClick={() => {
                setLat(18.0);
                setLon(66.5);
              }}
              className="px-2.5 py-1 rounded bg-[#111214] border border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a] transition-colors text-xs font-sans"
            >
              Arabian Sea
            </button>
            <span className="text-[#38393d]">·</span>
            <button
              type="button"
              onClick={() => {
                setLat(15.0);
                setLon(88.0);
              }}
              className="px-2.5 py-1 rounded bg-[#111214] border border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a] transition-colors text-xs font-sans"
            >
              Bay of Bengal
            </button>
            <span className="text-[#38393d]">·</span>
            <button
              type="button"
              onClick={() => {
                setLat(15.2);
                setLon(73.8);
              }}
              className="px-2.5 py-1 rounded bg-[#111214] border border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a] transition-colors text-xs font-sans"
            >
              West Coast
            </button>
          </div>

          {/* Layer Checkboxes */}
          <div className="flex items-center space-x-2 text-xs">
            <button
              type="button"
              onClick={() =>
                setActiveLayers((prev) => ({ ...prev, alerts: !prev.alerts }))
              }
              className={`px-3 py-1 rounded border transition-colors font-sans ${
                activeLayers.alerts
                  ? "bg-[#241717] border-[#3d2424] text-[#e0a8a8]"
                  : "bg-[#111214] border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a]"
              }`}
            >
              Warnings ({alerts.length})
            </button>

            <button
              type="button"
              onClick={() =>
                setActiveLayers((prev) => ({ ...prev, pfz: !prev.pfz }))
              }
              className={`px-3 py-1 rounded border transition-colors font-sans ${
                activeLayers.pfz
                  ? "bg-[#181a1c] border-[#2c2e32] text-white"
                  : "bg-[#111214] border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a]"
              }`}
            >
              PFZ ({pfzList.length})
            </button>
          </div>

          {/* Inspector Toggle Button */}
          <button
            type="button"
            onClick={() => setInspectorOpen((prev) => !prev)}
            className="p-1.5 rounded bg-[#111214] border border-[#202124] text-[#8e8e93] hover:text-white hover:bg-[#16171a] transition-colors"
            title={inspectorOpen ? "Hide Inspector" : "Show Inspector"}
          >
            {inspectorOpen ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main Workspace: 65-75% Map + 25-35% Location Inspector */}
      <div className="flex-1 h-[calc(100vh-6.5rem)] flex min-h-0 relative overflow-hidden">
        {/* The Map Canvas (The Hero Product) */}
        <div className="flex-1 relative h-full min-h-0">
          <div className="absolute inset-0">
            <MapContainerDynamic
              center={[lat, lon]}
              zoom={zoom}
              selectedLocation={{ lat, lon }}
              onSelectLocation={handleMapClick}
              radiusKm={radiusKm}
              alerts={alerts}
              pfzList={pfzList}
              zones={zones}
              route={route}
              activeLayers={activeLayers}
            />
          </div>
        </div>

        {/* The Contextual Inspector Drawer */}
        {inspectorOpen && (
          <div
            className={`transition-all duration-300 z-30 h-full ${
              inspectorExpanded ? "w-full md:w-[600px]" : "w-full sm:w-[380px] md:w-[420px]"
            }`}
          >
            <LocationInspector
              location={{ lat, lon }}
              radiusKm={radiusKm}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              onRouteCalculated={setRoute}
              isExpanded={inspectorExpanded}
              onToggleExpand={() => setInspectorExpanded((prev) => !prev)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default function ExplorePage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center bg-[#08090a] text-[#9ca3af] font-sans text-xs">
          Loading geospatial exploration environment...
        </div>
      }
    >
      <ExploreContent />
    </Suspense>
  );
}
