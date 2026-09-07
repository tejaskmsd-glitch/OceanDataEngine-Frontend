"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api, type ApiResult } from "@/lib/api";
import type {
  AlertModel,
  FishingSuitabilityModel,
  ForecastModel,
  MarineRiskModel,
  ObservationModel,
  PFZModel,
  SourceRef,
} from "@/types/api";

import { MissingLocationView, ReportLoadingSkeleton } from "@/components/report/ReportState";
import { ReportHeader } from "@/components/report/ReportHeader";
import { ExecutiveFinding } from "@/components/report/ExecutiveFinding";
import { KeyObservations } from "@/components/report/KeyObservations";
import { ForecastChart } from "@/components/report/ForecastChart";
import { WeatherForecastChart } from "@/components/report/WeatherForecastChart";
import { RiskAnalysis } from "@/components/report/RiskAnalysis";
import { FishingAnalysis } from "@/components/report/FishingAnalysis";
import { TideAnalysis } from "@/components/report/TideAnalysis";
import { AlertsSection } from "@/components/report/AlertsSection";
import { DataCoverage } from "@/components/report/DataCoverage";
import { SpatialContext } from "@/components/report/SpatialContext";
import { ReportProvenance } from "@/components/report/ReportProvenance";

type ReportDomain = "OCEAN" | "WEATHER" | "FISHING" | "TIDES" | "ALL";

function determineDomain(tab?: string | null, query?: string | null): ReportDomain {
  const t = (tab || "").toLowerCase();
  const q = (query || "").toLowerCase();

  if (t === "fishing" || q.includes("fish") || q.includes("pfz") || q.includes("tuna") || q.includes("hilsa")) {
    return "FISHING";
  }
  if (t === "weather" || q.includes("weather") || q.includes("wind") || q.includes("pressure") || q.includes("rain")) {
    return "WEATHER";
  }
  if (t === "tides" || q.includes("tide") || q.includes("water level") || q.includes("sea level")) {
    return "TIDES";
  }
  if (t === "conditions" || q.includes("ocean") || q.includes("sst") || q.includes("wave") || q.includes("swell")) {
    return "OCEAN";
  }
  return "ALL";
}

function ReportContent() {
  const searchParams = useSearchParams();

  // Parse location
  const rawLat = searchParams.get("lat");
  const rawLon = searchParams.get("lon");
  const rawRadius = searchParams.get("radius");
  const rawTime = searchParams.get("time");
  const queryText = searchParams.get("query") || searchParams.get("search");
  const activeTab = searchParams.get("tab");

  const hasCoords = rawLat !== null && rawLon !== null && !isNaN(parseFloat(rawLat)) && !isNaN(parseFloat(rawLon));
  const lat = hasCoords ? parseFloat(rawLat!) : NaN;
  const lon = hasCoords ? parseFloat(rawLon!) : NaN;
  const radiusKm = rawRadius && !isNaN(parseFloat(rawRadius)) ? parseFloat(rawRadius) : 150;
  const time = rawTime || undefined;

  // Domain selection
  const domain = determineDomain(activeTab, queryText);

  // States for aggregated data
  const [loading, setLoading] = useState(hasCoords);
  const [observations, setObservations] = useState<ObservationModel[]>([]);
  const [forecasts, setForecasts] = useState<ForecastModel[]>([]);
  const [risk, setRisk] = useState<MarineRiskModel | null>(null);
  const [suitability, setSuitability] = useState<FishingSuitabilityModel | null>(null);
  const [pfzList, setPfzList] = useState<PFZModel[]>([]);
  const [tides, setTides] = useState<ObservationModel[]>([]);
  const [alerts, setAlerts] = useState<AlertModel[]>([]);
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [primaryRequestId, setPrimaryRequestId] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!hasCoords) return;

    let active = true;
    setLoading(true);

    // Build promises intelligently based on domain
    const promises: Promise<any>[] = [];
    const keys: string[] = [];

    // Always fetch alerts within radius or coastal scope
    promises.push(api.alerts({ lat, lon, radius_km: radiusKm * 1.5 }));
    keys.push("alerts");

    // Always fetch marine risk for location
    promises.push(api.marineRisk({ lat, lon, radius_km: radiusKm, time }));
    keys.push("risk");

    // Primary ocean surface telemetry (Wave height, SST) & forecasts
    promises.push(api.oceanConditions({ lat, lon, radius_km: radiusKm, time }));
    keys.push("ocean_obs");
    promises.push(api.oceanForecast({ lat, lon, radius_km: radiusKm, time }));
    keys.push("ocean_fc");

    // Primary atmospheric telemetry (Wind speed, pressure) & forecasts
    promises.push(api.weatherConditions({ lat, lon, radius_km: radiusKm, time }));
    keys.push("weather_obs");
    promises.push(api.weatherForecast({ lat, lon, radius_km: radiusKm, time }));
    keys.push("weather_fc");

    // Coastal tide gauge stations (allow up to 250km for coastal stations)
    promises.push(api.tides({ lat, lon, radius_km: Math.max(radiusKm, 250), time }));
    keys.push("tides");

    // When fishing tab or fishing keywords are queried
    if (domain === "FISHING" || domain === "ALL") {
      promises.push(api.pfz({ lat, lon, radius_km: radiusKm, include_expired: true }));
      keys.push("pfz");
      promises.push(api.fishingSuitability({ lat, lon, radius_km: radiusKm }));
      keys.push("suitability");
    }

    Promise.allSettled(promises).then((results) => {
      if (!active) return;
      setLoading(false);

      const allObs: ObservationModel[] = [];
      const allFc: ForecastModel[] = [];
      const allSources: SourceRef[] = [];
      const allWarnings: string[] = [];
      let rootReqId: string | undefined = undefined;

      results.forEach((res, idx) => {
        const key = keys[idx];
        if (res.status === "fulfilled") {
          const val = res.value as ApiResult<any>;
          if (val.requestId && !rootReqId) {
            rootReqId = val.requestId;
          }
          if (val.warnings) {
            allWarnings.push(...val.warnings);
          }
          if (val.envelope?.sources) {
            allSources.push(...val.envelope.sources);
          }

          if (key === "alerts") {
            setAlerts(val.data || []);
          } else if (key === "risk") {
            setRisk(val.data || null);
          } else if (key === "ocean_obs" || key === "weather_obs") {
            if (Array.isArray(val.data)) allObs.push(...val.data);
          } else if (key === "ocean_fc" || key === "weather_fc") {
            if (Array.isArray(val.data)) allFc.push(...val.data);
          } else if (key === "pfz") {
            setPfzList(val.data || []);
          } else if (key === "suitability") {
            setSuitability(val.data || null);
          } else if (key === "tides") {
            setTides(val.data || []);
          }
        }
      });

      // Deduplicate observations by parameter + station_id
      const uniqueObs = allObs.filter(
        (obs, index, self) =>
          index === self.findIndex((o) => o.parameter === obs.parameter && o.station_id === obs.station_id)
      );

      setObservations(uniqueObs);
      setForecasts(allFc);
      setSources(allSources);
      setWarnings(Array.from(new Set(allWarnings)));
      setPrimaryRequestId(rootReqId);
    });

    return () => {
      active = false;
    };
  }, [lat, lon, radiusKm, time, domain, hasCoords]);

  // Gracefully handle missing coordinates without inventing fake locations
  if (!hasCoords) {
    return (
      <main className="min-h-screen bg-[#08090c] pt-14 text-white flex flex-col justify-center relative overflow-hidden">
        <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_75%_55%_at_50%_-15%,rgba(16,36,44,0.35),rgba(8,9,12,0))] z-0" />
        <div className="relative z-10">
          <MissingLocationView />
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[#08090c] pt-14 text-white relative overflow-hidden">
        <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_75%_55%_at_50%_-15%,rgba(16,36,44,0.35),rgba(8,9,12,0))] z-0" />
        <div className="relative z-10">
          <ReportLoadingSkeleton />
        </div>
      </main>
    );
  }

  const showFishing = domain === "FISHING" || suitability !== null || pfzList.length > 0;
  const showTides = domain === "TIDES" || tides.length > 0;

  return (
    <main className="min-h-screen bg-[#08090c] pt-14 pb-24 text-[#F4F7F5] selection:bg-[#7FCBC5]/20 selection:text-white relative overflow-hidden">
      {/* Sophisticated deep-ocean ambient background depth (Part 3) */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_75%_55%_at_50%_-15%,rgba(16,36,44,0.35),rgba(8,9,12,0))] z-0" />
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_60%_40%_at_50%_105%,rgba(11,26,34,0.25),rgba(8,9,12,0))] z-0" />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-14 sm:space-y-16 font-sans relative z-10">
        {/* Report Opening Header */}
        <ReportHeader
          location={{ lat, lon }}
          radiusKm={radiusKm}
          queryText={queryText}
          referenceTime={time}
          sourceCount={sources.length}
          activeTab={activeTab || "conditions"}
        />

        {/* 01. What's Happening? (Human Entry Point & Coverage Qualification) */}
        <ExecutiveFinding
          observations={observations}
          forecasts={forecasts}
          risk={risk}
          alerts={alerts}
          pfzList={pfzList}
          warnings={warnings}
          radiusKm={radiusKm}
        />

        {/* 02. At A Glance (Horizontal Metric Strip: Wave, Temp, Wind, Pressure, Tide) */}
        <KeyObservations
          observations={observations}
          tides={tides}
          radiusKm={radiusKm}
        />

        {/* 03. How The Sea May Change (Hero Data Visualization: Wave Height) */}
        <ForecastChart
          forecasts={forecasts}
          currentObs={observations}
          radiusKm={radiusKm}
        />

        {/* 04. Weather Around This Area (Atmospheric Dynamics: Wind & Pressure) */}
        <WeatherForecastChart
          forecasts={forecasts}
          currentObs={observations}
          radiusKm={radiusKm}
        />

        {/* 05. Current Risk (Authoritative Operational Safety Index & Factor Penalties) */}
        <RiskAnalysis
          risk={risk}
          radiusKm={radiusKm}
        />

        {/* Domain Insight: Fishing Conditions & PFZ Advisory (When relevant or domain-requested) */}
        {showFishing && (
          <FishingAnalysis
            suitability={suitability}
            pfzList={pfzList}
            location={{ lat, lon }}
            radiusKm={radiusKm}
          />
        )}

        {/* Domain Insight: Coastal Tide Gauges (When relevant or domain-requested) */}
        {showTides && (
          <TideAnalysis
            tides={tides}
            radiusKm={radiusKm}
          />
        )}

        {/* 06. Warnings Near You (Authoritative Bulletins or Direct Notice) */}
        <AlertsSection
          alerts={alerts}
          radiusKm={radiusKm}
        />

        {/* 07. How Much Do We Know? (Data Coverage & Availability Breakdown) */}
        <DataCoverage
          observations={observations}
          forecasts={forecasts}
          tideCount={tides.length}
          alertCount={alerts.length}
          sources={sources}
          warnings={warnings}
          radiusKm={radiusKm}
        />

        {/* 08. Where This Information Comes From (Providers & Provenance Drawer Trigger) */}
        <ReportProvenance
          primaryRequestId={primaryRequestId}
          sources={sources}
          warnings={warnings}
        />

        {/* 09. Explore This Area (Spatial Map Transition) */}
        <SpatialContext
          location={{ lat, lon }}
          radiusKm={radiusKm}
          activeTab={activeTab || "conditions"}
        />
      </div>
    </main>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<ReportLoadingSkeleton />}>
      <ReportContent />
    </Suspense>
  );
}