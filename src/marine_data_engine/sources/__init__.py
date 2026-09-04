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
    ParsedObservation,
    ParsedPFZ,
    RawPayload,
    SourceAdapter,
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
    parse_high_wave_alerts,
)
from .incois_pfz import (
    INCOISPfzFixtureAdapter,
    INCOISPfzLiveAdapter,
    parse_pfz_featurecollection,
)
from .incois_tide import (
    INCOISTideFixtureAdapter,
    INCOISTideLiveAdapter,
    parse_tide_observations,
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

__all__ = [
    # base
    "FetchResult",
    "AuthenticationRequiredError",
    "LiveSourceDisabledError",
    "ParsedAlert",
    "ParsedForecast",
    "ParsedObservation",
    "ParsedPFZ",
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
    # INCOIS high wave alerts
    "INCOISHighWaveFixtureAdapter",
    "INCOISHighWaveLiveAdapter",
    "parse_high_wave_alerts",
    # Hazards (cyclone / tsunami / storm surge)
    "CycloneFixtureAdapter",
    "CycloneLiveAdapter",
    "TsunamiFixtureAdapter",
    "TsunamiLiveAdapter",
    "parse_cyclone_bulletin",
    "parse_tsunami_bulletin",
    "parse_storm_surge_advisory",
]
