"use client";

import { useEffect, useState } from "react";
import {
  Layers,
  Database,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  Globe,
  ExternalLink,
  ChevronRight,
  Filter,
} from "lucide-react";
import type { DataHealthModel, DatasetModel, StacCollection } from "@/types/api";
import { api } from "@/lib/api";
import { LoadingView, ErrorView, EmptyDataView } from "@/components/ui/StateViews";

export default function DatasetsPage() {
  const [activeTab, setActiveTab] = useState<"catalog" | "stac">("catalog");
  const [datasets, setDatasets] = useState<DatasetModel[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, DataHealthModel>>({});
  const [stacCollections, setStacCollections] = useState<StacCollection[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<DatasetModel | null>(null);
  const [selectedStac, setSelectedStac] = useState<StacCollection | null>(null);

  const [searchFilter, setSearchFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("all");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    Promise.allSettled([
      api.datasets(),
      api.dataHealth(),
      api.stacCollections(),
    ]).then(([dsRes, healthRes, stacRes]) => {
      if (!mounted) return;
      setLoading(false);

      if (dsRes.status === "fulfilled") {
        setDatasets(dsRes.value.data);
      } else {
        setError(dsRes.reason?.message || "Failed to load datasets");
      }

      if (healthRes.status === "fulfilled") {
        const map: Record<string, DataHealthModel> = {};
        for (const item of healthRes.value.data) {
          map[item.dataset] = item;
        }
        setHealthMap(map);
      }

      if (stacRes.status === "fulfilled") {
        setStacCollections(stacRes.value.collections || []);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);

  const filteredDatasets = datasets.filter((ds) => {
    const matchesSearch =
      ds.product.toLowerCase().includes(searchFilter.toLowerCase()) ||
      ds.key.toLowerCase().includes(searchFilter.toLowerCase()) ||
      ds.parameters.some((p) => p.toLowerCase().includes(searchFilter.toLowerCase()));
    const matchesProvider =
      providerFilter === "all" || ds.provider.toLowerCase() === providerFilter.toLowerCase();
    return matchesSearch && matchesProvider;
  });

  const filteredStac = stacCollections.filter((stac) => {
    return (
      stac.id.toLowerCase().includes(searchFilter.toLowerCase()) ||
      stac.description.toLowerCase().includes(searchFilter.toLowerCase())
    );
  });

  const uniqueProviders = Array.from(new Set(datasets.map((d) => d.provider.toLowerCase())));

  return (
    <div className="flex-1 min-h-screen pt-20 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full space-y-8 font-sans">
      {/* Header Section */}
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-light text-white tracking-tight">
          Oceanographic Datasets & STAC Collections
        </h1>
        <p className="text-xs sm:text-sm text-[#9ca3af] max-w-3xl leading-relaxed">
          Authoritative marine observations, numerical weather prediction grids, and
          spatiotemporal asset collections registered and validated in the Marine Data Layer.
        </p>
      </div>

      {/* Controls Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-md bg-[#111214] border border-[#202124]">
        {/* Tab switcher */}
        <div className="flex items-center space-x-1 p-0.5 rounded bg-[#0d0e10] border border-[#202124] text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("catalog")}
            className={`px-3 py-1.5 rounded transition-colors text-xs ${
              activeTab === "catalog"
                ? "bg-[#202124] text-white font-medium shadow-xs"
                : "text-[#9ca3af] hover:text-white"
            }`}
          >
            Registered Datasets ({datasets.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("stac")}
            className={`px-3 py-1.5 rounded transition-colors text-xs ${
              activeTab === "stac"
                ? "bg-[#202124] text-white font-medium shadow-xs"
                : "text-[#9ca3af] hover:text-white"
            }`}
          >
            STAC Collections ({stacCollections.length})
          </button>
        </div>

        {/* Search & Provider Filter */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#8e8e93]" />
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter parameters, titles..."
              className="w-full bg-[#0d0e10] border border-[#202124] rounded pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-[#6b7280] focus:outline-none focus:border-white/40 transition-colors"
            />
          </div>

          {activeTab === "catalog" && (
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="bg-[#0d0e10] border border-[#202124] rounded px-3 py-1.5 text-xs text-white focus:outline-none focus:border-white/40 transition-colors"
            >
              <option value="all">All Providers</option>
              {uniqueProviders.map((p) => (
                <option key={p} value={p}>
                  {p.toUpperCase()}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <LoadingView label="Consulting authoritative dataset catalog..." variant="graphite" />
      ) : error ? (
        <ErrorView message="Failed to load dataset catalogue" detail={error} variant="graphite" />
      ) : activeTab === "catalog" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {filteredDatasets.map((ds) => {
            const health = healthMap[ds.key];
            const isHealthy = ds.status === "healthy" || health?.status === "healthy";
            const isDegraded = ds.status === "degraded" || health?.status === "degraded";

            return (
              <div
                key={ds.key}
                onClick={() => setSelectedDataset(ds)}
                className="bg-[#111214] border border-[#202124] hover:border-[#33353a] rounded-md p-4 flex flex-col justify-between space-y-3.5 cursor-pointer transition-colors group"
              >
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-[#0d0e10] border border-[#202124] text-[#9ca3af]">
                      {ds.provider}
                    </span>
                    <span
                      className={`text-[10px] flex items-center space-x-1.5 ${
                        isHealthy
                          ? "text-[#9ca3af]"
                          : isDegraded
                          ? "text-[#d4b06a]"
                          : "text-[#8e8e93]"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          isHealthy
                            ? "bg-[#22c55e]"
                            : isDegraded
                            ? "bg-[#eab308]"
                            : "bg-[#8e8e93]"
                        }`}
                      />
                      <span className="capitalize">{ds.status}</span>
                    </span>
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-white transition-colors line-clamp-2">
                      {ds.product}
                    </h3>
                    <p className="text-[11px] font-mono text-[#8e8e93] mt-0.5">{ds.key}</p>
                  </div>

                  {ds.spatial_coverage && (
                    <div className="text-xs text-[#9ca3af] flex items-start space-x-1.5">
                      <Globe className="w-3.5 h-3.5 text-[#8e8e93] shrink-0 mt-0.5" />
                      <span className="line-clamp-1">{ds.spatial_coverage}</span>
                    </div>
                  )}

                  {ds.parameters.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {ds.parameters.map((param, i) => (
                        <span
                          key={i}
                          className="px-1.5 py-0.5 rounded bg-[#0d0e10] border border-[#202124] text-[10px] text-[#8e8e93]"
                        >
                          {param}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="pt-2.5 border-t border-[#1a1b1e] flex items-center justify-between text-[11px] text-[#8e8e93]">
                  <span>{ds.fmt || "Format: Standard"}</span>
                  <span className="flex items-center space-x-1 text-[#9ca3af] group-hover:text-white group-hover:underline transition-colors">
                    <span>Inspect</span>
                    <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* STAC Collections View */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {filteredStac.map((stac) => (
            <div
              key={stac.id}
              onClick={() => setSelectedStac(stac)}
              className="bg-[#111214] border border-[#202124] hover:border-[#33353a] rounded-md p-4 flex flex-col justify-between space-y-3.5 cursor-pointer transition-colors group"
            >
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-[#0d0e10] border border-[#202124] text-[#9ca3af]">
                    STAC Collection
                  </span>
                  <span className="text-[10px] font-mono text-[#8e8e93]">v1.0.0</span>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-white transition-colors">
                    {stac.title || stac.id}
                  </h3>
                  <p className="text-xs text-[#9ca3af] mt-1 leading-relaxed line-clamp-3">
                    {stac.description}
                  </p>
                </div>

                {stac.extent?.spatial?.bbox && (
                  <div className="text-[11px] font-mono text-[#8e8e93]">
                    BBox: [{stac.extent.spatial.bbox[0]?.join(", ")}]
                  </div>
                )}
              </div>

              <div className="pt-2.5 border-t border-[#1a1b1e] flex items-center justify-between text-[11px] text-[#8e8e93]">
                <span>License: {stac.license || "Proprietary"}</span>
                <span className="flex items-center space-x-1 text-[#9ca3af] group-hover:text-white group-hover:underline transition-colors">
                  <span>View Details</span>
                  <ChevronRight className="w-3 h-3" />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dataset Detail Modal */}
      {selectedDataset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs">
          <div className="bg-[#111214] rounded-lg max-w-xl w-full p-5 space-y-4 border border-[#202124] shadow-2xl">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded text-xs font-medium uppercase bg-[#0d0e10] border border-[#202124] text-[#9ca3af]">
                {selectedDataset.provider}
              </span>
              <button
                type="button"
                onClick={() => setSelectedDataset(null)}
                className="text-[#9ca3af] hover:text-white text-xs p-1 transition-colors"
              >
                Close ✕
              </button>
            </div>

            <div className="space-y-1">
              <h2 className="text-base font-medium text-white">{selectedDataset.product}</h2>
              <p className="text-xs font-mono text-[#8e8e93]">{selectedDataset.key}</p>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between py-1.5 border-b border-[#1a1b1e]">
                <span className="text-[#9ca3af]">Spatial Coverage:</span>
                <span className="text-white">{selectedDataset.spatial_coverage || "Regional"}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1a1b1e]">
                <span className="text-[#9ca3af]">Temporal Cadence:</span>
                <span className="text-white">{selectedDataset.temporal_resolution || "Variable"}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1a1b1e]">
                <span className="text-[#9ca3af]">Payload Format:</span>
                <span className="text-white">{selectedDataset.fmt || "Canonical GeoJSON"}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1a1b1e]">
                <span className="text-[#9ca3af]">Consecutive Failures:</span>
                <span className="text-white font-mono">{selectedDataset.consecutive_failures}</span>
              </div>
              {selectedDataset.status_detail && (
                <div className="py-2 text-[11px] text-[#d4b06a] leading-relaxed bg-[#0d0e10] p-2.5 rounded border border-[#202124]">
                  Status Note: {selectedDataset.status_detail}
                </div>
              )}
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedDataset(null)}
                className="px-4 py-1.5 rounded bg-[#1a1b1d] hover:bg-[#222428] border border-[#28292c] text-xs text-white transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STAC Detail Modal */}
      {selectedStac && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs">
          <div className="bg-[#111214] rounded-lg max-w-xl w-full p-5 space-y-4 border border-[#202124] shadow-2xl">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded text-xs font-medium uppercase bg-[#0d0e10] border border-[#202124] text-[#9ca3af]">
                STAC Collection
              </span>
              <button
                type="button"
                onClick={() => setSelectedStac(null)}
                className="text-[#9ca3af] hover:text-white text-xs p-1 transition-colors"
              >
                Close ✕
              </button>
            </div>

            <div className="space-y-1">
              <h2 className="text-base font-medium text-white">{selectedStac.title || selectedStac.id}</h2>
              <p className="text-xs font-mono text-[#8e8e93]">{selectedStac.id}</p>
            </div>

            <p className="text-xs text-[#9ca3af] leading-relaxed font-sans">
              {selectedStac.description}
            </p>

            {selectedStac.links && selectedStac.links.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-[#1a1b1e]">
                <span className="text-[10px] uppercase text-[#8e8e93] tracking-wider">
                  STAC API Hypermedia Links
                </span>
                <div className="space-y-1">
                  {selectedStac.links.slice(0, 4).map((link, i) => (
                    <div key={i} className="flex items-center justify-between text-xs font-mono">
                      <span className="text-[#9ca3af]">{link.rel}:</span>
                      <span className="text-white truncate max-w-xs">{link.href}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedStac(null)}
                className="px-4 py-1.5 rounded bg-[#1a1b1d] hover:bg-[#222428] border border-[#28292c] text-xs text-white transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
