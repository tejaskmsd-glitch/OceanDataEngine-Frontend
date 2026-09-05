"""Source adapters: fetch raw upstream data and parse to canonical records.

Adapters isolate all source-specific behavior (discovery, auth, formats, rate
limits, provenance) and emit canonical dataclasses. Live connectors are
disabled by default; fixture connectors provide deterministic offline data.
"""

from __future__ import annotations

from .base import (
    AuthenticationRequiredError,
    FetchResult,
    LiveSourceDisabledError,
    ParsedAlert,
    ParsedForecast,
    ParsedMarineZone,
    ParsedObservation,
    ParsedPFZ,
    ParsedStation,
    RawPayload,
    SourceAdapter,
    SourceAdapterError,
    SourceContractError,
    SourceContractUnavailableError,
    SourceLicenseRequiredError,
    SourceUnavailableError,
)
from .hazards import (
    CycloneFixtureAdapter,
    CycloneLiveAdapter,
    TsunamiFixtureAdapter,
    TsunamiLiveAdapter,
    parse_cyclone_bulletin,
    parse_storm_surge_advisory,
    parse_tsunami_bulletin,
)
from .imd_buoy import (
    BuoyStructureError,
    IMDBuoyFixtureAdapter,
    IMDBuoyLiveAdapter,
    INCOISBuoyLiveAdapter,
    parse_buoy_html,
    parse_oon_backend_status,
    parse_oon_chart,
    parse_oon_station_catalog,
)
from .imd_cap import (
    IMDCapFixtureAdapter,
    IMDCapLiveAdapter,
    parse_cap_document,
)
from .imd_nwp import (
    IMDNwpAdapter,
    IMDNwpFixtureAdapter,
    parse_nwp_forecast,
)
from .incois_erddap import (
    DEFAULT_BASE_URL as ERDDAP_DEFAULT_BASE_URL,
)
from .incois_erddap import (
    ErddapDataset,
    INCOISErddapCatalogAdapter,
    INCOISErddapFixtureAdapter,
    INCOISErddapLiveAdapter,
)
from .incois_erddap import (
    parse_catalog as parse_erddap_catalog,
)
from .incois_hwa import (
    INCOISHighWaveFixtureAdapter,
    INCOISHighWaveLiveAdapter,
    parse_alert_validity,
    parse_high_wave_alerts,
    parse_live_high_wave_alerts,
)
from .incois_pfz import (
    INCOISPfzFixtureAdapter,
    INCOISPfzLiveAdapter,
    parse_live_pfz,
    parse_pfz_featurecollection,
)
from .incois_tide import (
    INCOISTideFixtureAdapter,
    INCOISTideLiveAdapter,
    parse_tews_observation_series,
    parse_tews_station_xml,
    parse_tide_observations,
)
from .marine_regions import (
    MarineRegionsEEZLiveAdapter,
    build_india_eez_url,
    parse_india_eez,
)
from .mosdac_download import (
    MOSDACDownloadAdapter,
    MOSDACDownloadFixtureAdapter,
)
from .mosdac_search import (
    MosdacDataset,
    MOSDACRateLimitError,
    MOSDACSearchAdapter,
    MOSDACSearchFixtureAdapter,
)
from .mosdac_search import (
    parse_search_response as parse_mosdac_search,
)
from .nga_ports import (
    NGAPortFixtureAdapter,
    NGAPortLiveAdapter,
    PortRecord,
    parse_wpi_json,
)

__all__ = [
    # base
    "FetchResult",
    "AuthenticationRequiredError",
    "LiveSourceDisabledError",
    "SourceAdapterError",
    "SourceContractError",
    "SourceContractUnavailableError",
    "SourceLicenseRequiredError",
    "SourceUnavailableError",
    "ParsedAlert",
    "ParsedForecast",
    "ParsedMarineZone",
    "ParsedObservation",
    "ParsedPFZ",
    "ParsedStation",
    "RawPayload",
    "SourceAdapter",
    # IMD CAP
    "IMDCapFixtureAdapter",
    "IMDCapLiveAdapter",
    "parse_cap_document",
    # INCOIS PFZ
    "INCOISPfzFixtureAdapter",
    "INCOISPfzLiveAdapter",
    "parse_pfz_featurecollection",
    "parse_live_pfz",
    # INCOIS ERDDAP
    "ErddapDataset",
    "ERDDAP_DEFAULT_BASE_URL",
    "INCOISErddapCatalogAdapter",
    "INCOISErddapFixtureAdapter",
    "INCOISErddapLiveAdapter",
    "parse_erddap_catalog",
    # MOSDAC search
    "MosdacDataset",
    "MOSDACRateLimitError",
    "MOSDACSearchAdapter",
    "MOSDACSearchFixtureAdapter",
    "parse_mosdac_search",
    # MOSDAC download
    "MOSDACDownloadAdapter",
    "MOSDACDownloadFixtureAdapter",
    # IMD NWP
    "IMDNwpAdapter",
    "IMDNwpFixtureAdapter",
    "parse_nwp_forecast",
    # INCOIS tide
    "INCOISTideFixtureAdapter",
    "INCOISTideLiveAdapter",
    "parse_tide_observations",
    "parse_tews_station_xml",
    "parse_tews_observation_series",
    # INCOIS high wave alerts
    "INCOISHighWaveFixtureAdapter",
    "INCOISHighWaveLiveAdapter",
    "parse_high_wave_alerts",
    "parse_live_high_wave_alerts",
    "parse_alert_validity",
    # Hazards (cyclone / tsunami / storm surge)
    "CycloneFixtureAdapter",
    "CycloneLiveAdapter",
    "TsunamiFixtureAdapter",
    "TsunamiLiveAdapter",
    "parse_cyclone_bulletin",
    "parse_tsunami_bulletin",
    "parse_storm_surge_advisory",
    # OON Buoy (legacy IMD fixture names retained for compatibility)
    "IMDBuoyFixtureAdapter",
    "IMDBuoyLiveAdapter",
    "INCOISBuoyLiveAdapter",
    "parse_buoy_html",
    "parse_oon_station_catalog",
    "parse_oon_backend_status",
    "parse_oon_chart",
    "BuoyStructureError",
    # Marine Regions EEZ
    "MarineRegionsEEZLiveAdapter",
    "build_india_eez_url",
    "parse_india_eez",
    # NGA Ports
    "NGAPortFixtureAdapter",
    "NGAPortLiveAdapter",
    "parse_wpi_json",
    "PortRecord",
]
