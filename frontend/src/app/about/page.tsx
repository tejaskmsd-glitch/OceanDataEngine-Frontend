import { ShieldCheck, Anchor, Compass, Database, Radio, Layers, Info } from "lucide-react";

export default function AboutPage() {
  return (
    <div className="flex-1 min-h-screen pt-20 pb-16 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto w-full space-y-10 font-sans">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-light text-white tracking-tight">
          About OceanDataEngine
        </h1>
        <p className="text-xs sm:text-sm text-[#9ca3af] leading-relaxed max-w-3xl">
          An authoritative, AI-agnostic marine intelligence data layer developed to unify,
          normalize, and verify oceanic observations, numerical forecasts, and coastal hazard
          bulletins across the Indian Ocean basin.
        </p>
      </div>

      {/* 1. Core Architecture Principles */}
      <section className="space-y-3.5">
        <h2 className="text-lg font-medium text-white tracking-tight">
          System Architecture & Data Guarantees
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <div className="bg-[#111214] rounded-md p-4 space-y-2 border border-[#202124]">
            <div className="flex items-center space-x-2 text-white font-medium text-xs sm:text-sm">
              <Database className="w-4 h-4 text-[#8e8e93]" />
              <span>Immutable Storage & Canonical Hypertables</span>
            </div>
            <p className="text-xs text-[#9ca3af] leading-relaxed">
              Raw scientific payloads from satellites, coastal radar, and buoy telemetry are
              stored immutably in S3 object storage with checksum SHA-256 verification.
              Time-series observations and forecasts are stored in TimescaleDB hypertables
              partitioned by observation time.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-4 space-y-2 border border-[#202124]">
            <div className="flex items-center space-x-2 text-white font-medium text-xs sm:text-sm">
              <ShieldCheck className="w-4 h-4 text-[#8e8e93]" />
              <span>Evidence Audit & Provenance Lineage</span>
            </div>
            <p className="text-xs text-[#9ca3af] leading-relaxed">
              Every query generates an immutable Evidence record addressable by its unique
              Request ID (<code className="bg-[#0d0e10] border border-[#202124] px-1.5 py-0.5 rounded font-mono text-[11px] text-white">GET /v1/evidence/{'{request_id}'}</code>). The evidence records the exact upstream
              source URLs, retrieval timestamps, processing pipeline versions, and confidence
              scores.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-4 space-y-2 border border-[#202124]">
            <div className="flex items-center space-x-2 text-white font-medium text-xs sm:text-sm">
              <Radio className="w-4 h-4 text-[#8e8e93]" />
              <span>Real-Time NATS JetStream Event Bridge</span>
            </div>
            <p className="text-xs text-[#9ca3af] leading-relaxed">
              Critical CAP bulletins (cyclone alerts, swell surges, gale warnings) are
              ingested asynchronously by dedicated workers and published over NATS JetStream
              durable queues, streaming to client browsers via WebSockets without blocking API queries.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-4 space-y-2 border border-[#202124]">
            <div className="flex items-center space-x-2 text-white font-medium text-xs sm:text-sm">
              <Compass className="w-4 h-4 text-[#8e8e93]" />
              <span>Deterministic Risk & Fishery Engines</span>
            </div>
            <p className="text-xs text-[#9ca3af] leading-relaxed">
              Marine risk scoring and pelagic fishery suitability models are pure, deterministic
              algorithms that combine physical observations (SST, chlorophyll-a, currents, wave
              heights) with vessel profile thresholds and official INCOIS PFZ coordinates.
            </p>
          </div>
        </div>
      </section>

      {/* 2. Authoritative Data Providers */}
      <section className="space-y-3.5">
        <h2 className="text-lg font-medium text-white tracking-tight">
          Upstream Data Providers & Verifications
        </h2>

        <div className="space-y-2.5 text-xs">
          <div className="bg-[#111214] rounded-md p-3.5 space-y-1.5 border border-[#202124]">
            <div className="flex items-center justify-between text-white font-medium">
              <span>INCOIS (Indian National Centre for Ocean Information Services)</span>
              <span className="text-[10px] text-[#9ca3af] font-sans">Verified Live Contracts</span>
            </div>
            <p className="text-[#9ca3af] text-xs leading-relaxed">
              Provides Potential Fishing Zone (PFZ) Point and LineString features, High Wave
              Alerts (HWA) and Swell Surge Alerts (SSA) with district polygons, TEWS
              coastal tide gauges, and WaveWatch III (WW3) 0.1° coastal wave models.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-3.5 space-y-1.5 border border-[#202124]">
            <div className="flex items-center justify-between text-white font-medium">
              <span>IMD (India Meteorological Department)</span>
              <span className="text-[10px] text-[#9ca3af] font-sans">Verified Live Contracts</span>
            </div>
            <p className="text-[#9ca3af] text-xs leading-relaxed">
              Provides Common Alerting Protocol (CAP 1.2) coastal hazard bulletins for
              cyclones, storms, heavy rainfall, and coastal weather bulletins.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-3.5 space-y-1.5 border border-[#202124]">
            <div className="flex items-center justify-between text-white font-medium">
              <span>MOSDAC (ISRO Space Applications Centre)</span>
              <span className="text-[10px] text-[#9ca3af] font-sans">OpenSearch Discovery Active</span>
            </div>
            <p className="text-[#9ca3af] text-xs leading-relaxed">
              Provides satellite oceanography discovery metadata for Indian Ocean spaceborne
              sensors. Authenticated downloads remain gated.
            </p>
          </div>

          <div className="bg-[#111214] rounded-md p-3.5 space-y-1.5 border border-[#202124]">
            <div className="flex items-center justify-between text-white font-medium">
              <span>Marine Regions (Flanders Marine Institute / VLIZ)</span>
              <span className="text-[10px] text-[#8e8e93] font-sans">World EEZ v12</span>
            </div>
            <p className="text-[#9ca3af] text-xs leading-relaxed">
              Provides sovereign Exclusive Economic Zone (EEZ) boundaries and maritime
              geofencing geometries.
            </p>
          </div>
        </div>
      </section>

      {/* 3. Scientific Integrity & Data Policy */}
      <section className="p-4 sm:p-5 rounded-md bg-[#0d0e10] border border-[#202124] space-y-2">
        <h3 className="text-xs font-medium text-white">Scientific Policy & Disclaimers</h3>
        <p className="text-xs text-[#9ca3af] leading-relaxed">
          OceanDataEngine strictly rejects synthetic or hallucinated oceanographic values. If an
          upstream satellite pass is obscured by cloud cover, or if an advisory provider has not yet
          been ingested by the Airflow scheduler, the platform represents that status honestly as
          `SOURCE_GAP`, `NOT_INGESTED`, or `DEGRADED`. Vessel routing and risk evaluations are
          decision-support tools and should be cross-referenced with official maritime notices to mariners.
        </p>
      </section>
    </div>
  );
}
