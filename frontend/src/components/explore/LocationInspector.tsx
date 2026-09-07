"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  Wind,
  Fish,
  ShieldAlert,
  Navigation,
  Waves,
  Maximize2,
  Minimize2,
  Info,
  Calendar,
  Compass,
  FileText,
} from "lucide-react";
import type {
  Envelope,
  FishingSuitabilityModel,
  ForecastModel,
  MarineRiskModel,
  ObservationModel,
  PFZModel,
  SafeRouteModel,
} from "@/types/api";
import { api } from "@/lib/api";
import { LoadingView, ErrorView, EmptyDataView, SourceUnavailableView } from "../ui/StateViews";
import { ProvenanceDrawer } from "../provenance/ProvenanceDrawer";

export type InspectorTab = "conditions" | "weather" | "risk" | "fishing" | "routes" | "tides";

interface LocationInspectorProps {
  location: { lat: number; lon: number };
  radiusKm: number;
  activeTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onRouteCalculated?: (route: SafeRouteModel | null) => void;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

export function LocationInspector({
  location,
  radiusKm,
  activeTab,
  onTabChange,
  onRouteCalculated,
  isExpanded = false,
  onToggleExpand,
}: LocationInspectorProps) {
  // State for Conditions tab
  const [oceanObs, setOceanObs] = useState<ObservationModel[]>([]);
  const [oceanFc, setOceanFc] = useState<ForecastModel[]>([]);
  const [oceanEnvelope, setOceanEnvelope] = useState<Envelope<any> | null>(null);
  const [loadingOcean, setLoadingOcean] = useState(false);
  const [errorOcean, setErrorOcean] = useState<string | null>(null);

  // State for Weather tab
  const [weatherObs, setWeatherObs] = useState<ObservationModel[]>([]);
  const [weatherFc, setWeatherFc] = useState<ForecastModel[]>([]);
  const [weatherEnvelope, setWeatherEnvelope] = useState<Envelope<any> | null>(null);
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [errorWeather, setErrorWeather] = useState<string | null>(null);

  // State for Risk tab
  const [riskAssessment, setRiskAssessment] = useState<MarineRiskModel | null>(null);
  const [riskEnvelope, setRiskEnvelope] = useState<Envelope<any> | null>(null);
  const [vesselType, setVesselType] = useState<string>("default");
  const [loadingRisk, setLoadingRisk] = useState(false);
  const [errorRisk, setErrorRisk] = useState<string | null>(null);

  // State for Fishing tab
  const [fishingSuitability, setFishingSuitability] = useState<FishingSuitabilityModel | null>(null);
  const [fishingEnvelope, setFishingEnvelope] = useState<Envelope<any> | null>(null);
  const [pfzList, setPfzList] = useState<PFZModel[]>([]);
  const [loadingFishing, setLoadingFishing] = useState(false);
  const [errorFishing, setErrorFishing] = useState<string | null>(null);

  // State for Tides tab
  const [tidesList, setTidesList] = useState<ObservationModel[]>([]);
  const [tidesEnvelope, setTidesEnvelope] = useState<Envelope<any> | null>(null);
  const [loadingTides, setLoadingTides] = useState(false);
  const [errorTides, setErrorTides] = useState<string | null>(null);

  // State for Routes tab
  const [destLat, setDestLat] = useState("15.49");
  const [destLon, setDestLon] = useState("73.82");
  const [routeResult, setRouteResult] = useState<SafeRouteModel | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [errorRoute, setErrorRoute] = useState<string | null>(null);

  // Fetch logic per tab
  useEffect(() => {
    let active = true;

    if (activeTab === "conditions") {
      setLoadingOcean(true);
      setErrorOcean(null);
      Promise.allSettled([
        api.oceanConditions({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
        api.oceanForecast({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
      ]).then(([obsRes, fcRes]) => {
        if (!active) return;
        setLoadingOcean(false);
        if (obsRes.status === "fulfilled") {
          setOceanObs(obsRes.value.data);
          setOceanEnvelope(obsRes.value.envelope);
        } else {
          setErrorOcean(obsRes.reason?.message || "Failed to load ocean observations");
        }
        if (fcRes.status === "fulfilled") {
          setOceanFc(fcRes.value.data);
        }
      });
    } else if (activeTab === "weather") {
      setLoadingWeather(true);
      setErrorWeather(null);
      Promise.allSettled([
        api.weatherConditions({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
        api.weatherForecast({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
      ]).then(([obsRes, fcRes]) => {
        if (!active) return;
        setLoadingWeather(false);
        if (obsRes.status === "fulfilled") {
          setWeatherObs(obsRes.value.data);
          setWeatherEnvelope(obsRes.value.envelope);
        } else {
          setErrorWeather(obsRes.reason?.message || "Failed to load weather observations");
        }
        if (fcRes.status === "fulfilled") {
          setWeatherFc(fcRes.value.data);
        }
      });
    } else if (activeTab === "risk") {
      setLoadingRisk(true);
      setErrorRisk(null);
      api
        .marineRisk({
          lat: location.lat,
          lon: location.lon,
          radius_km: radiusKm,
          vessel_type: vesselType,
        })
        .then((res) => {
          if (!active) return;
          setLoadingRisk(false);
          setRiskAssessment(res.data);
          setRiskEnvelope(res.envelope);
        })
        .catch((err) => {
          if (!active) return;
          setLoadingRisk(false);
          setErrorRisk(err.message || "Failed to compute marine risk");
        });
    } else if (activeTab === "fishing") {
      setLoadingFishing(true);
      setErrorFishing(null);
      Promise.allSettled([
        api.fishingSuitability({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
        api.pfz({ lat: location.lat, lon: location.lon, radius_km: radiusKm }),
      ]).then(([suitRes, pfzRes]) => {
        if (!active) return;
        setLoadingFishing(false);
        if (suitRes.status === "fulfilled") {
          setFishingSuitability(suitRes.value.data);
          setFishingEnvelope(suitRes.value.envelope);
        } else {
          setErrorFishing(suitRes.reason?.message || "Failed to compute suitability");
        }
        if (pfzRes.status === "fulfilled") {
          setPfzList(pfzRes.value.data);
        }
      });
    } else if (activeTab === "tides") {
      setLoadingTides(true);
      setErrorTides(null);
      api
        .tides({ lat: location.lat, lon: location.lon, radius_km: radiusKm })
        .then((res) => {
          if (!active) return;
          setLoadingTides(false);
          setTidesList(res.data);
          setTidesEnvelope(res.envelope);
        })
        .catch((err) => {
          if (!active) return;
          setLoadingTides(false);
          setErrorTides(err.message || "Failed to query TEWS tide observations");
        });
    }

    return () => {
      active = false;
    };
  }, [location.lat, location.lon, radiusKm, activeTab, vesselType]);

  const handleComputeRoute = async (e: React.FormEvent) => {
    e.preventDefault();
    const dLat = parseFloat(destLat);
    const dLon = parseFloat(destLon);
    if (isNaN(dLat) || isNaN(dLon)) return;

    setLoadingRoute(true);
    setErrorRoute(null);
    try {
      const res = await api.safeRoutes({
        start: { lat: location.lat, lon: location.lon },
        end: { lat: dLat, lon: dLon },
        vessel_type: vesselType,
      });
      setRouteResult(res.data);
      if (onRouteCalculated) {
        onRouteCalculated(res.data);
      }
    } catch (err: any) {
      setErrorRoute(err.message || "Route calculation failed");
    } finally {
      setLoadingRoute(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#08090a] border-l border-[#202124] font-sans">
      {/* Inspector Header */}
      <div className="p-4 border-b border-[#202124] flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-xs font-sans text-[#8e8e93]">
            <Compass className="w-3.5 h-3.5 text-white/70" />
            <span>Target Location</span>
          </div>
          <div className="text-sm text-white font-normal flex items-center flex-wrap gap-x-2">
            <span className="font-mono">{location.lat.toFixed(3)}°N, {location.lon.toFixed(3)}°E</span>
            <span className="text-xs text-[#8e8e93] font-sans">
              ({radiusKm} km radius)
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-1.5">
          <Link
            href={`/report?lat=${location.lat}&lon=${location.lon}&radius=${radiusKm}&tab=${activeTab}`}
            className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded bg-[#111214] hover:bg-[#181a1f] border border-[#202124] hover:border-[#7FCBC5]/50 text-[11px] text-[#BDCDC9] hover:text-white transition-all font-sans"
            title="Generate comprehensive Visual Data Report"
          >
            <FileText className="w-3 h-3 text-[#7FCBC5]" />
            <span className="hidden sm:inline">Visual Report</span>
          </Link>

          {onToggleExpand && (
            <button
              type="button"
              onClick={onToggleExpand}
              className="p-1.5 rounded hover:bg-[#16171a] text-[#8e8e93] hover:text-white transition-colors border border-transparent hover:border-[#202124]"
              title={isExpanded ? "Collapse Panel" : "Expand Panel"}
            >
              {isExpanded ? (
                <Minimize2 className="w-4 h-4" />
              ) : (
                <Maximize2 className="w-4 h-4" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Tabs navigation */}
      <div className="flex items-center border-b border-[#202124] px-2 overflow-x-auto text-xs font-sans space-x-0.5">
        <button
          type="button"
          onClick={() => onTabChange("conditions")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "conditions"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <Activity className={`w-3.5 h-3.5 ${activeTab === "conditions" ? "text-white" : "text-[#71767e]"}`} />
          <span>Ocean</span>
        </button>
        <button
          type="button"
          onClick={() => onTabChange("weather")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "weather"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <Wind className={`w-3.5 h-3.5 ${activeTab === "weather" ? "text-white" : "text-[#71767e]"}`} />
          <span>Weather</span>
        </button>
        <button
          type="button"
          onClick={() => onTabChange("risk")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "risk"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <ShieldAlert className={`w-3.5 h-3.5 ${activeTab === "risk" ? "text-white" : "text-[#71767e]"}`} />
          <span>Risk</span>
        </button>
        <button
          type="button"
          onClick={() => onTabChange("fishing")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "fishing"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <Fish className={`w-3.5 h-3.5 ${activeTab === "fishing" ? "text-white" : "text-[#71767e]"}`} />
          <span>Fisheries</span>
        </button>
        <button
          type="button"
          onClick={() => onTabChange("routes")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "routes"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <Navigation className={`w-3.5 h-3.5 ${activeTab === "routes" ? "text-white" : "text-[#71767e]"}`} />
          <span>Routing</span>
        </button>
        <button
          type="button"
          onClick={() => onTabChange("tides")}
          className={`px-3 py-2.5 border-b-2 transition-colors flex items-center space-x-1.5 whitespace-nowrap font-medium ${
            activeTab === "tides"
              ? "border-white text-white bg-[#111214]"
              : "border-transparent text-[#8e8e93] hover:text-white hover:bg-[#111214]/50"
          }`}
        >
          <Waves className={`w-3.5 h-3.5 ${activeTab === "tides" ? "text-white" : "text-[#71767e]"}`} />
          <span>Tides</span>
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 1. Ocean Conditions Tab */}
        {activeTab === "conditions" && (
          <div className="space-y-4">
            {loadingOcean ? (
              <LoadingView label="Sampling oceanographic telemetry..." variant="graphite" />
            ) : errorOcean ? (
              <ErrorView message="Failed to load ocean data" detail={errorOcean} variant="graphite" />
            ) : (
              <>
                {/* Observations list */}
                <div className="space-y-2">
                  <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider flex items-center justify-between font-medium">
                    <span>In-Situ Observations ({oceanObs.length})</span>
                    <span className="text-[10px] text-[#8e8e93] flex items-center space-x-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
                      <span>Live Sensors</span>
                    </span>
                  </div>

                  {oceanObs.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {oceanObs.map((obs) => (
                        <div
                          key={obs.observation_uid}
                          className="bg-[#111214] rounded p-3 border border-[#202124] space-y-1 text-xs"
                        >
                          <div className="text-[10px] text-[#8e8e93] uppercase font-sans tracking-wide">
                            {obs.parameter.replace(/_/g, " ")}
                          </div>
                          <div className="text-base font-normal text-white font-mono">
                            {obs.value != null ? obs.value.toFixed(2) : "—"}
                            <span className="text-xs text-[#8e8e93] ml-1 font-mono">{obs.unit || ""}</span>
                          </div>
                          <div className="text-[10px] text-[#8e8e93] flex items-center justify-between pt-1 font-mono">
                            <span>{obs.provider}</span>
                            {obs.distance_km != null && <span>{obs.distance_km} km</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyDataView
                      title="No in-situ ocean observations in radius"
                      description="No moored buoys or observation platforms reporting inside this radius window."
                      variant="graphite"
                    />
                  )}
                </div>

                {/* Forecasts list */}
                {oceanFc.length > 0 && (
                  <div className="space-y-2 pt-3 border-t border-[#202124]">
                    <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                      Numerical Model Forecasts ({oceanFc.length})
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {oceanFc.map((fc) => (
                        <div
                          key={fc.forecast_uid}
                          className="bg-[#111214] rounded p-3 border border-[#202124] space-y-1 text-xs"
                        >
                          <div className="text-[10px] text-[#8e8e93] uppercase font-sans tracking-wide">
                            {fc.parameter.replace(/_/g, " ")} (Forecast)
                          </div>
                          <div className="text-base font-normal text-white font-mono">
                            {fc.value != null ? fc.value.toFixed(2) : "—"}
                            <span className="text-xs text-[#8e8e93] ml-1 font-mono">{fc.unit || ""}</span>
                          </div>
                          <div className="text-[10px] text-[#8e8e93] flex items-center justify-between font-mono pt-1">
                            <span>{fc.model_name || fc.provider}</span>
                            {fc.forecast_time && (
                              <span>{new Date(fc.forecast_time).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Provenance Footer */}
                <ProvenanceDrawer
                  meta={oceanEnvelope?.meta}
                  sources={oceanEnvelope?.sources}
                  warnings={oceanEnvelope?.warnings}
                  quality={oceanEnvelope?.quality}
                  variant="graphite"
                />
              </>
            )}
          </div>
        )}

        {/* 2. Weather Tab */}
        {activeTab === "weather" && (
          <div className="space-y-4">
            {loadingWeather ? (
              <LoadingView label="Querying marine atmospheric models..." variant="graphite" />
            ) : errorWeather ? (
              <ErrorView message="Failed to load weather data" detail={errorWeather} variant="graphite" />
            ) : (
              <>
                <div className="space-y-2">
                  <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                    Surface Weather Observations ({weatherObs.length})
                  </div>

                  {weatherObs.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {weatherObs.map((obs) => (
                        <div
                          key={obs.observation_uid}
                          className="bg-[#111214] rounded p-3 border border-[#202124] space-y-1 text-xs"
                        >
                          <div className="text-[10px] text-[#8e8e93] uppercase font-sans tracking-wide">
                            {obs.parameter.replace(/_/g, " ")}
                          </div>
                          <div className="text-base font-normal text-white font-mono">
                            {obs.value != null ? obs.value.toFixed(2) : "—"}
                            <span className="text-xs text-[#8e8e93] ml-1 font-mono">{obs.unit || ""}</span>
                          </div>
                          <div className="text-[10px] text-[#8e8e93] flex items-center justify-between pt-1 font-mono">
                            <span>{obs.provider}</span>
                            {obs.distance_km != null && <span>{obs.distance_km} km</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyDataView
                      title="No weather station records in radius"
                      description="No coastal or marine weather stations active inside this query radius."
                      variant="graphite"
                    />
                  )}
                </div>

                <ProvenanceDrawer
                  meta={weatherEnvelope?.meta}
                  sources={weatherEnvelope?.sources}
                  warnings={weatherEnvelope?.warnings}
                  quality={weatherEnvelope?.quality}
                  variant="graphite"
                />
              </>
            )}
          </div>
        )}

        {/* 3. Marine Risk Tab */}
        {activeTab === "risk" && (
          <div className="space-y-4">
            {/* Vessel Type Selector */}
            <div className="flex items-center justify-between p-2.5 rounded bg-[#111214] border border-[#202124] text-xs font-sans">
              <span className="text-[#8e8e93] font-normal">Vessel Profile:</span>
              <select
                value={vesselType}
                onChange={(e) => setVesselType(e.target.value)}
                className="bg-[#08090a] border border-[#202124] rounded px-2.5 py-1 text-white font-sans text-xs focus:outline-none focus:border-white/40 cursor-pointer"
              >
                <option value="default">Default / General</option>
                <option value="artisanal">Artisanal Craft (Light)</option>
                <option value="trawler">Commercial Trawler</option>
                <option value="cargo">Cargo / Heavy Vessel</option>
              </select>
            </div>

            {loadingRisk ? (
              <LoadingView label="Calculating composite marine risk matrix..." variant="graphite" />
            ) : errorRisk ? (
              <ErrorView message="Risk assessment failed" detail={errorRisk} variant="graphite" />
            ) : riskAssessment ? (
              <div className="space-y-4">
                {/* Composite Risk Score Badge */}
                <div className="bg-[#111214] rounded p-4 border border-[#202124] text-center space-y-2">
                  <div className="text-[10px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                    Marine Risk Index
                  </div>
                  <div className="text-3xl font-light text-white font-mono flex items-center justify-center space-x-2">
                    <span>{riskAssessment.risk_score.toFixed(1)}</span>
                    <span className="text-sm text-[#8e8e93]">/ 100</span>
                  </div>
                  <div className="inline-block px-3 py-1 rounded text-xs font-sans font-medium uppercase tracking-wide">
                    <span
                      className={
                        riskAssessment.risk_level === "LOW"
                          ? "text-[#a0d4b8] bg-[#141c18] border border-[#203828] px-2.5 py-0.5 rounded"
                          : riskAssessment.risk_level === "MODERATE"
                          ? "text-[#d4b06a] bg-[#222017] border border-[#383424] px-2.5 py-0.5 rounded"
                          : "text-[#e0a8a8] bg-[#241717] border border-[#3d2424] px-2.5 py-0.5 rounded"
                      }
                    >
                      {riskAssessment.risk_level} RISK
                    </span>
                  </div>
                </div>

                {/* Risk Factors Breakdown */}
                {riskAssessment.factors.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                      Factor Contribution Breakdown
                    </div>
                    <div className="space-y-2">
                      {riskAssessment.factors.map((f, i) => (
                        <div
                          key={i}
                          className="bg-[#0d0e10] rounded p-2.5 border border-[#202124] text-xs space-y-1.5"
                        >
                          <div className="flex items-center justify-between font-sans">
                            <span className="capitalize text-[#d1d5db]">
                              {f.name.replace(/_/g, " ")}
                            </span>
                            <span className="text-[#8e8e93] font-mono">
                              {f.value != null ? f.value.toFixed(2) : "N/A"}
                            </span>
                          </div>
                          {/* Contribution bar */}
                          <div className="w-full bg-[#202124] h-1.5 rounded-full overflow-hidden">
                            <div
                              className="bg-white/80 h-full rounded-full transition-all"
                              style={{
                                width: `${Math.min(100, Math.max(0, f.contribution * 10))}%`,
                              }}
                            />
                          </div>
                          <div className="flex items-center justify-between text-[10px] text-[#8e8e93] font-mono">
                            <span>Thresh: {f.threshold_low} - {f.threshold_high}</span>
                            <span>Weight: {f.weight}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <ProvenanceDrawer
                  meta={riskEnvelope?.meta}
                  sources={riskEnvelope?.sources}
                  warnings={riskAssessment.warnings}
                  variant="graphite"
                />
              </div>
            ) : null}
          </div>
        )}

        {/* 4. Fishing Suitability Tab */}
        {activeTab === "fishing" && (
          <div className="space-y-4">
            {loadingFishing ? (
              <LoadingView label="Evaluating pelagic productivity and PFZ proximity..." variant="graphite" />
            ) : errorFishing ? (
              <ErrorView message="Suitability evaluation failed" detail={errorFishing} variant="graphite" />
            ) : fishingSuitability ? (
              <div className="space-y-4">
                {/* Score Card */}
                <div className="bg-[#111214] rounded p-4 border border-[#202124] text-center space-y-2">
                  <div className="text-[10px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                    Fishing Suitability Index
                  </div>
                  <div className="text-3xl font-light text-white font-mono">
                    {(fishingSuitability.score * 100).toFixed(0)}%
                  </div>
                  <div className="inline-block px-3 py-1 rounded text-xs font-sans font-medium uppercase tracking-wide">
                    <span
                      className={
                        fishingSuitability.classification.toUpperCase() === "HIGH"
                          ? "text-[#a0d4b8] bg-[#141c18] border border-[#203828] px-2.5 py-0.5 rounded"
                          : fishingSuitability.classification.toUpperCase() === "MODERATE"
                          ? "text-[#d4b06a] bg-[#222017] border border-[#383424] px-2.5 py-0.5 rounded"
                          : "text-[#e0a8a8] bg-[#241717] border border-[#3d2424] px-2.5 py-0.5 rounded"
                      }
                    >
                      {fishingSuitability.classification} SUITABILITY
                    </span>
                  </div>
                </div>

                {/* Positive and Negative Drivers */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-sans">
                  <div className="bg-[#0d0e10] rounded p-3 border border-[#202124] space-y-1.5">
                    <div className="text-[#a0d4b8] font-medium text-[11px] uppercase tracking-wide">
                      Positive Drivers
                    </div>
                    {fishingSuitability.positive_drivers.length > 0 ? (
                      <ul className="space-y-1 text-[#9ca3af] text-[11px]">
                        {fishingSuitability.positive_drivers.map((d, i) => (
                          <li key={i} className="flex items-center space-x-1.5">
                            <span className="text-[#86c89e] font-bold">+</span>
                            <span>{d}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-[11px] text-[#71767e] italic">None detected</span>
                    )}
                  </div>

                  <div className="bg-[#0d0e10] rounded p-3 border border-[#202124] space-y-1.5">
                    <div className="text-[#d4b06a] font-medium text-[11px] uppercase tracking-wide">
                      Negative Factors
                    </div>
                    {fishingSuitability.negative_drivers.length > 0 ? (
                      <ul className="space-y-1 text-[#9ca3af] text-[11px]">
                        {fishingSuitability.negative_drivers.map((d, i) => (
                          <li key={i} className="flex items-center space-x-1.5">
                            <span className="text-[#d4b06a] font-bold">-</span>
                            <span>{d}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-[11px] text-[#8e8e93] italic">None detected</span>
                    )}
                  </div>
                </div>

                {/* Nearest PFZ info */}
                {pfzList.length > 0 && (
                  <div className="space-y-1.5 text-xs font-sans">
                    <span className="text-[10px] text-[#8e8e93] uppercase tracking-wider font-medium">
                      Nearby INCOIS PFZ Advisories ({pfzList.length})
                    </span>
                    <div className="space-y-1.5">
                      {pfzList.slice(0, 3).map((p) => (
                        <div
                          key={p.pfz_uid}
                          className="bg-[#0d0e10] rounded p-2.5 border border-[#202124] text-[11px] space-y-1"
                        >
                          <div className="font-medium text-white">{p.region || "PFZ Zone"}</div>
                          <div className="text-[#9ca3af]">{p.advisory_text}</div>
                          <div className="text-[10px] text-[#8e8e93] font-mono mt-1">
                            Distance: {p.distance_km} km · Provider: {p.provider}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <ProvenanceDrawer
                  meta={fishingEnvelope?.meta}
                  sources={fishingEnvelope?.sources}
                  warnings={fishingEnvelope?.warnings}
                  variant="graphite"
                />
              </div>
            ) : null}
          </div>
        )}

        {/* 5. Safe Routing Tab */}
        {activeTab === "routes" && (
          <div className="space-y-4">
            <form onSubmit={handleComputeRoute} className="bg-[#111214] rounded p-3.5 border border-[#202124] space-y-3 font-sans">
              <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                Geodesic Route Risk Planner
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <label className="text-[10px] text-[#8e8e93] block mb-1 font-sans">
                    Start Lat, Lon
                  </label>
                  <input
                    type="text"
                    readOnly
                    value={`${location.lat.toFixed(2)}, ${location.lon.toFixed(2)}`}
                    className="w-full bg-[#0d0e10] border border-[#202124] rounded px-2.5 py-1.5 text-[#8e8e93] text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-[#8e8e93] block mb-1 font-sans">
                    Dest Lat
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={destLat}
                    onChange={(e) => setDestLat(e.target.value)}
                    className="w-full bg-[#0d0e10] border border-[#202124] rounded px-2.5 py-1.5 text-white text-xs font-mono focus:outline-none focus:border-white/40"
                  />
                </div>
                <div className="col-span-2">
                  <label className="text-[10px] text-[#8e8e93] block mb-1 font-sans">
                    Dest Lon
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={destLon}
                    onChange={(e) => setDestLon(e.target.value)}
                    className="w-full bg-[#0d0e10] border border-[#202124] rounded px-2.5 py-1.5 text-white text-xs font-mono focus:outline-none focus:border-white/40"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loadingRoute}
                className="w-full py-2.5 rounded bg-[#1e2023] hover:bg-[#282a2e] border border-[#2c2e33] text-white text-xs font-medium transition-colors flex items-center justify-center space-x-1.5 disabled:opacity-50 cursor-pointer shadow-none"
              >
                <Navigation className="w-3.5 h-3.5 text-white" />
                <span>{loadingRoute ? "Computing Geodesic Segments..." : "Calculate Safe Route"}</span>
              </button>
            </form>

            {errorRoute && <ErrorView message="Route computation error" detail={errorRoute} variant="graphite" />}

            {routeResult && (
              <div className="bg-[#111214] rounded p-3.5 border border-[#202124] space-y-2 text-xs font-sans">
                <div className="flex items-center justify-between text-white font-medium">
                  <span>Status: {routeResult.status.toUpperCase()}</span>
                  <span className="text-white font-mono">
                    Risk Score: {routeResult.route_risk_score.toFixed(1)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[#8e8e93] text-[11px] font-mono">
                  <span>Distance: {routeResult.total_distance_km.toFixed(1)} km</span>
                  {routeResult.estimated_duration_hours && (
                    <span>Est: {routeResult.estimated_duration_hours.toFixed(1)} hrs</span>
                  )}
                </div>
                <div className="text-[10px] text-[#8e8e93] font-mono">
                  Segments analyzed: {routeResult.segments.length} legs
                </div>

                {routeResult.avoided_zones.length > 0 && (
                  <div className="p-2 rounded bg-[#1c1822] border border-[#362744] text-[#d4c0e8] text-[10px]">
                    Avoided Restricted Zones: {routeResult.avoided_zones.join(", ")}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 6. Tides Tab */}
        {activeTab === "tides" && (
          <div className="space-y-4">
            {loadingTides ? (
              <LoadingView label="Fetching TEWS tide gauge telemetry..." variant="graphite" />
            ) : errorTides ? (
              <ErrorView message="Failed to load tide observations" detail={errorTides} variant="graphite" />
            ) : tidesList.length > 0 ? (
              <div className="space-y-2">
                <div className="text-[11px] font-sans uppercase text-[#8e8e93] tracking-wider font-medium">
                  TEWS Water Level Observations ({tidesList.length})
                </div>
                <div className="space-y-2">
                  {tidesList.map((tide) => (
                    <div
                      key={tide.observation_uid}
                      className="bg-[#111214] rounded p-3 border border-[#202124] text-xs font-sans space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-white">
                          {tide.station_id || "TEWS Station"}
                        </span>
                        <span className="text-white font-mono font-medium">
                          {tide.value != null ? tide.value.toFixed(2) : "—"} {tide.unit || "m"}
                        </span>
                      </div>
                      <div className="text-[10px] text-[#8e8e93] flex items-center justify-between pt-1 font-mono">
                        <span>Provider: {tide.provider}</span>
                        {tide.distance_km != null && <span>Dist: {tide.distance_km} km</span>}
                      </div>
                    </div>
                  ))}
                </div>

                <ProvenanceDrawer
                  meta={tidesEnvelope?.meta}
                  sources={tidesEnvelope?.sources}
                  warnings={tidesEnvelope?.warnings}
                  variant="graphite"
                />
              </div>
            ) : (
              <EmptyDataView
                title="No active TEWS tide gauge within radius"
                description="No tide gauge reporting in this coastal perimeter. Expand your query radius to include regional ports."
                variant="graphite"
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
