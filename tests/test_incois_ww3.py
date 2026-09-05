"""Tests for the unit resolver and the INCOIS WaveWatch III NCSS adapter.

Fixture strings below are copied from live responses captured from
``incois.gov.in/thredds`` so the parser is exercised against the real shapes,
including the empty ``unit=""`` headers and the land-masked ``NaN`` rows.
"""

from __future__ import annotations

import math

import pytest

from marine_data_engine.domain.unit_labels import (
    UnitContractError,
    UnknownUnitError,
    canonical_unit,
    extract_unit_from_long_name,
    require_unit,
)
from marine_data_engine.sources.base import (
    LiveSourceDisabledError,
    SourceContractError,
    SourceUnavailableError,
)
from marine_data_engine.sources.incois_ww3 import (
    WW3_VARIABLES,
    IncoisWW3LiveAdapter,
    haversine_km,
    init_datetime,
    parse_catalog_latest_coast_file,
    parse_dataset_units,
    parse_ncss_point_csv,
    records_from_samples,
    resolve_wind,
)

# --------------------------------------------------------------------------
# Fixtures mirroring live payload shapes
# --------------------------------------------------------------------------

CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<catalog><dataset name="OSF_ww3">
<dataset name="io_ww3_20250930.nc" urlPath="osf/ww3/io_ww3_20250930.nc"/>
<dataset name="nio_ww3_20260211.nc" urlPath="osf/ww3/nio_ww3_20260211.nc"/>
<dataset name="rsmc_coast_ww3_20260902.nc" urlPath="osf/ww3/rsmc_coast_ww3_20260902.nc"/>
<dataset name="rsmc_coast_ww3_20260904.nc" urlPath="osf/ww3/rsmc_coast_ww3_20260904.nc"/>
<dataset name="rsmc_coast_ww3_20260903.nc" urlPath="osf/ww3/rsmc_coast_ww3_20260903.nc"/>
<dataset name="pacific_ww3_20260904.nc" urlPath="osf/ww3/pacific_ww3_20260904.nc"/>
</dataset></catalog>"""


def _grid(name: str, long_name: str) -> str:
    return (
        f'<grid name="{name}" type="float">'
        f'<attribute name="long_name" value="{long_name}" />'
        f'<attribute name="units" value="" />'
        f"</grid>"
    )


# Exactly the long_name strings the live dataset.xml publishes.
LIVE_LONG_NAMES = {
    "HS": "Wave height (m)",
    "T01": "Mean Per Tm (s)",
    "T02": "Mean Per Tz (s)",
    "PHS00": "Part. Hs (m)",
    "PHS01": "Part. Hs (m)",
    "MWD": "Mean Wave Direction (Deg)",
    "UWND": "Wind U (m/s)",
    "VWND": "Wind V (m/s)",
    "PWP": "Peak Wave Period",  # no unit stated -- deliberately unusable
    "FP": "Peak Freq. (Hz)",
    "DIR": "Mean Dir. (rad)",
}

DATASET_XML = (
    '<?xml version="1.0"?><gridDataset><gridSet>'
    + "".join(_grid(k, v) for k, v in LIVE_LONG_NAMES.items())
    + "</gridSet></gridDataset>"
)

# Live CSV: note unit="" on every variable, and the land-masked NaN rows.
CSV_LAND = (
    'time,station,latitude[unit="degrees_north"],longitude[unit="degrees_east"],'
    'HS[unit=""],T01[unit=""],T02[unit=""],PHS00[unit=""],PHS01[unit=""],'
    'MWD[unit=""],UWND[unit=""],VWND[unit=""]\n'
    "2026-09-06T00:00:00Z,GridPointRequestedAt[15.491N_73.828E],15.500,73.800,"
    "NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN\n"
)

CSV_WET = (
    'time,station,latitude[unit="degrees_north"],longitude[unit="degrees_east"],'
    'HS[unit=""],T01[unit=""],T02[unit=""],PHS00[unit=""],PHS01[unit=""],'
    'MWD[unit=""],UWND[unit=""],VWND[unit=""]\n'
    "2026-09-06T00:00:00Z,GridPointRequestedAt[15.491N_73.628E],15.500,73.600,"
    "1.4332463,7.10,5.90,1.31,0.62,265.0,-4.20,1.90\n"
    "2026-09-06T03:00:00Z,GridPointRequestedAt[15.491N_73.628E],15.500,73.600,"
    "1.5100178,7.30,6.00,1.40,0.55,268.0,-4.60,2.10\n"
)


# --------------------------------------------------------------------------
# Unit resolver
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("m", "m"),
        ("Meters", "m"),  # the live OON buoy label that used to be quarantined
        ("METRE", "m"),
        ("metres", "m"),
        ("m/s", "m/s"),
        ("m s-1", "m/s"),
        ("Deg", "deg"),
        ("degrees", "deg"),
        ("s", "s"),
        ("Seconds", "s"),
        ("Hz", "hz"),
        ("rad", "rad"),
        ("mbar", "hpa"),
    ],
)
def test_canonical_unit_resolves_known_synonyms(label, expected):
    assert canonical_unit(label) == expected


def test_meters_label_now_resolves_so_oon_buoy_is_no_longer_degraded():
    """The OON buoy hm0 label 'Meters' is unambiguous and must be accepted."""
    assert require_unit("Meters", "m", context="oon.hm0") == "m"


@pytest.mark.parametrize("label", ["fathoms", "furlongs", "wibble", "??"])
def test_unknown_unit_is_refused_not_guessed(label):
    with pytest.raises(UnknownUnitError):
        canonical_unit(label)


def test_none_unit_is_refused_rather_than_treated_as_dimensionless():
    with pytest.raises(UnknownUnitError):
        canonical_unit(None)


@pytest.mark.parametrize("label", ["feet", "ft", "knots", "kt", "cm", "nm"])
def test_scale_different_labels_are_absent_from_synonyms(label):
    """Units needing arithmetic must never be silently relabelled to canonical."""
    with pytest.raises(UnknownUnitError):
        canonical_unit(label)


def test_require_unit_rejects_recognised_but_wrong_unit():
    with pytest.raises(UnitContractError, match="unit contract violation"):
        require_unit("s", "m", context="HS")


@pytest.mark.parametrize(
    ("long_name", "expected"),
    [
        ("Wave height (m)", "m"),
        ("Mean Per Tm (s)", "s"),
        ("Wind U (m/s)", "m/s"),
        ("Mean Wave Direction (Deg)", "deg"),
        ("Peak Freq. (Hz)", "hz"),
        ("Mean Dir. (rad)", "rad"),
    ],
)
def test_extract_unit_from_live_long_names(long_name, expected):
    assert extract_unit_from_long_name(long_name) == expected


def test_long_name_without_unit_group_is_refused():
    """'Peak Wave Period' states no unit, so no unit may be inferred."""
    with pytest.raises(UnknownUnitError, match="no trailing"):
        extract_unit_from_long_name("Peak Wave Period")


def test_empty_long_name_is_refused():
    with pytest.raises(UnknownUnitError):
        extract_unit_from_long_name("")


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------


def test_catalog_picks_newest_coastal_file_ignoring_other_products():
    name, init = parse_catalog_latest_coast_file(CATALOG)
    assert name == "rsmc_coast_ww3_20260904.nc"
    assert init == "20260904"


def test_catalog_without_coastal_product_raises_contract_error():
    xml = '<catalog><dataset urlPath="osf/ww3/pacific_ww3_20260904.nc"/></catalog>'
    with pytest.raises(SourceContractError, match="no rsmc_coast_ww3"):
        parse_catalog_latest_coast_file(xml)


# --------------------------------------------------------------------------
# Dataset description / unit verification
# --------------------------------------------------------------------------


def test_dataset_units_resolved_from_long_name_despite_empty_units_attr():
    units = parse_dataset_units(DATASET_XML)
    assert units["HS"] == "m"
    assert units["T01"] == "s"
    assert units["UWND"] == "m/s"
    assert units["MWD"] == "deg"
    assert set(units) == set(WW3_VARIABLES)


def test_pwp_is_excluded_because_it_states_no_unit():
    assert "PWP" not in WW3_VARIABLES
    assert "PWP" not in parse_dataset_units(DATASET_XML)


def test_missing_required_variable_raises_contract_error():
    xml = DATASET_XML.replace(_grid("HS", "Wave height (m)"), "")
    with pytest.raises(SourceContractError, match="missing required variable"):
        parse_dataset_units(xml)


def test_variable_with_wrong_unit_raises_contract_error():
    xml = DATASET_XML.replace("Wave height (m)", "Wave height (s)")
    with pytest.raises(SourceContractError, match="unit contract violation"):
        parse_dataset_units(xml)


def test_variable_losing_its_unit_group_raises_contract_error():
    xml = DATASET_XML.replace("Wave height (m)", "Wave height")
    with pytest.raises(SourceContractError, match="no verifiable unit"):
        parse_dataset_units(xml)


def test_dataset_description_without_grids_raises():
    with pytest.raises(SourceContractError, match="no <grid> variables"):
        parse_dataset_units("<gridDataset></gridDataset>")


# --------------------------------------------------------------------------
# NCSS CSV parsing / land mask
# --------------------------------------------------------------------------


def test_land_masked_row_yields_no_values_and_is_not_wet():
    samples = parse_ncss_point_csv(CSV_LAND)
    assert len(samples) == 1
    assert samples[0].values == {}
    assert samples[0].is_wet is False


def test_land_mask_never_becomes_zero():
    """A NaN must be absence of evidence, not a calm sea."""
    sample = parse_ncss_point_csv(CSV_LAND)[0]
    assert "HS" not in sample.values
    assert 0.0 not in sample.values.values()


def test_wet_rows_parse_values_and_times():
    samples = parse_ncss_point_csv(CSV_WET)
    assert len(samples) == 2
    first = samples[0]
    assert first.is_wet
    assert first.values["HS"] == pytest.approx(1.4332463)
    assert first.values["T01"] == pytest.approx(7.10)
    assert first.latitude == pytest.approx(15.5)
    assert first.longitude == pytest.approx(73.6)
    assert first.valid_from.isoformat() == "2026-09-06T00:00:00+00:00"


def test_html_error_body_is_refused_not_parsed():
    with pytest.raises(SourceContractError, match="markup instead of CSV"):
        parse_ncss_point_csv("<!DOCTYPE HTML><html><body>400</body></html>")


def test_empty_response_is_refused():
    with pytest.raises(SourceContractError, match="empty response"):
        parse_ncss_point_csv("   ")


def test_missing_required_column_raises():
    with pytest.raises(SourceContractError, match="missing a required column"):
        parse_ncss_point_csv('foo,bar\n1,2\n')


def test_unparseable_time_raises():
    bad = CSV_WET.replace("2026-09-06T00:00:00Z", "not-a-time")
    with pytest.raises(SourceContractError, match="unparseable time"):
        parse_ncss_point_csv(bad)


# --------------------------------------------------------------------------
# Wind derivation
# --------------------------------------------------------------------------


def test_wind_speed_is_vector_magnitude():
    speed, _ = resolve_wind(3.0, 4.0)
    assert speed == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("u", "v", "bearing"),
    [
        (-1.0, 0.0, 90.0),   # blowing toward -x => from the east
        (0.0, -1.0, 0.0),    # blowing toward -y => from the north
        (1.0, 0.0, 270.0),   # blowing toward +x => from the west
        (0.0, 1.0, 180.0),   # blowing toward +y => from the south
    ],
)
def test_wind_direction_uses_meteorological_from_convention(u, v, bearing):
    _, got = resolve_wind(u, v)
    assert got == pytest.approx(bearing, abs=1e-9)


# --------------------------------------------------------------------------
# Record construction
# --------------------------------------------------------------------------


def _records():
    return records_from_samples(
        parse_ncss_point_csv(CSV_WET),
        request_lat=15.4909,
        request_lon=73.8278,
        source_url="https://incois.gov.in/thredds/ncss/grid/osf/ww3/x.nc",
        init_date="20260904",
        requested_point_land_masked=True,
    )


def test_records_carry_numeric_wave_height_in_metres():
    hs = [r for r in _records() if r.parameter == "significant_wave_height"]
    assert len(hs) == 2
    assert hs[0].unit == "m"
    assert hs[0].value == pytest.approx(1.4332463)


def test_records_disclose_grid_displacement_and_land_mask():
    rec = _records()[0]
    meta = rec.source_metadata
    assert meta["requested_point_land_masked"] is True
    assert meta["grid_latitude"] == pytest.approx(15.5)
    assert meta["grid_longitude"] == pytest.approx(73.6)
    assert meta["grid_distance_km"] > 20.0
    assert meta["requested_latitude"] == pytest.approx(15.4909)


def test_model_values_are_never_labelled_measurements():
    for rec in _records():
        assert rec.source_metadata["is_measurement"] is False
        assert rec.source_metadata["provenance"] == "numerical_wave_model"


def test_swell_height_takes_the_larger_partition_conservatively():
    swell = [r for r in _records() if r.parameter == "swell_height"]
    assert swell[0].value == pytest.approx(1.31)  # max(1.31, 0.62)
    assert swell[0].unit == "m"


def test_derived_wind_speed_emitted_with_documented_derivation():
    ws = [r for r in _records() if r.parameter == "wind_speed"]
    assert ws[0].unit == "m/s"
    assert ws[0].value == pytest.approx(math.hypot(-4.20, 1.90))
    assert "hypot" in ws[0].source_metadata["derivation"]


CSV_TWO_NODES = (
    'time,station,latitude[unit="degrees_north"],longitude[unit="degrees_east"],'
    'HS[unit=""]\n'
    "2026-09-06T00:00:00Z,a,15.400,73.800,0.470786\n"  # near, sheltered
    "2026-09-06T00:00:00Z,b,15.500,73.600,1.4332463\n"  # farther, rougher
)


def _two_node_records():
    return records_from_samples(
        parse_ncss_point_csv(CSV_TWO_NODES),
        request_lat=15.4909,
        request_lon=73.8278,
        source_url="u",
        init_date="20260904",
        requested_point_land_masked=True,
        search_radius_km=30.0,
    )


def test_both_nearest_and_roughest_nodes_are_reported():
    """Collapsing to one node would hide either locality or exposure."""
    hs = [
        r
        for r in _two_node_records()
        if r.parameter == "significant_wave_height"
    ]
    by_sel = {r.source_metadata["node_selection"]: r for r in hs}
    assert set(by_sel) == {"nearest_wet_node", "max_within_radius"}
    assert by_sel["nearest_wet_node"].value == pytest.approx(0.470786)
    assert by_sel["max_within_radius"].value == pytest.approx(1.4332463)


def test_nearest_selection_is_actually_the_closest_node():
    hs = [
        r
        for r in _two_node_records()
        if r.parameter == "significant_wave_height"
    ]
    near = next(
        r for r in hs if r.source_metadata["node_selection"] == "nearest_wet_node"
    )
    rough = next(
        r for r in hs if r.source_metadata["node_selection"] == "max_within_radius"
    )
    assert (
        near.source_metadata["grid_distance_km"]
        < rough.source_metadata["grid_distance_km"]
    )


def test_search_radius_is_recorded_for_auditability():
    rec = _two_node_records()[0]
    assert rec.source_metadata["search_radius_km"] == pytest.approx(30.0)


def test_single_node_collapses_to_one_tagged_selection():
    """When nearest and roughest coincide, no duplicate rows are emitted."""
    hs = [
        r for r in _records() if r.parameter == "significant_wave_height"
    ]
    assert len(hs) == 2  # two time steps, one node each
    for r in hs:
        assert (
            r.source_metadata["node_selection"]
            == "nearest_wet_node+max_within_radius"
        )


def test_land_only_samples_produce_no_records_rather_than_zeroes():
    recs = records_from_samples(
        parse_ncss_point_csv(CSV_LAND),
        request_lat=15.4909,
        request_lon=73.8278,
        source_url="u",
        init_date="20260904",
        requested_point_land_masked=True,
    )
    assert recs == []


def test_haversine_matches_known_separation():
    # 0.1 deg of latitude is ~11.1 km.
    assert haversine_km(15.4, 73.8, 15.5, 73.8) == pytest.approx(11.1, abs=0.2)


# --------------------------------------------------------------------------
# Result-state honesty
# --------------------------------------------------------------------------


class _StubAdapter(IncoisWW3LiveAdapter):
    """Adapter with I/O stubbed so result-state semantics can be asserted."""

    def __init__(self, *, bodies, **kw):
        super().__init__(live_enabled=True, cache=None, **kw)
        self._bodies = bodies

    def discover(self):
        return "rsmc_coast_ww3_20260904.nc", "20260904", dict(
            (k, v[1]) for k, v in WW3_VARIABLES.items()
        )

    def _http_get(self, url):
        body = self._bodies.pop(0) if self._bodies else None
        if isinstance(body, Exception):
            raise body
        if body is None:
            raise SourceUnavailableError(f"stub exhausted for {url}")
        return body


def test_total_upstream_failure_is_degraded_not_empty():
    """A failed poll must never look like a healthy source with no data."""
    adapter = _StubAdapter(
        bodies=[SourceUnavailableError("HTTP 400")] * 400,
        points=[(15.4909, 73.8278)],
        search_radius_km=10.0,
    )
    result = adapter.fetch()
    assert result.result_state == "degraded"
    assert result.forecasts == []
    assert result.diagnostics
    assert "HTTP 400" in result.status_detail


def test_land_masked_but_reachable_source_is_empty_not_degraded():
    """Genuinely no wet node, with no errors, is an honest empty poll."""
    adapter = _StubAdapter(
        bodies=[CSV_LAND] * 400,
        points=[(15.4909, 73.8278)],
        search_radius_km=10.0,
    )
    result = adapter.fetch()
    assert result.result_state == "empty"
    assert result.forecasts == []


def test_partial_probe_failure_is_degraded_even_though_data_returned():
    near_wet = CSV_WET.replace("15.500,73.600", "15.500,73.800")
    adapter = _StubAdapter(
        bodies=[near_wet, SourceUnavailableError("HTTP 500")] + [CSV_LAND] * 400,
        points=[(15.4909, 73.8278)],
        search_radius_km=12.0,
    )
    result = adapter.fetch()
    assert result.result_state == "degraded"
    assert result.forecasts
    assert "probe(s) failed" in result.status_detail


def test_disabled_live_sources_raises_rather_than_returning_empty():
    adapter = IncoisWW3LiveAdapter(live_enabled=False, cache=None)
    with pytest.raises(LiveSourceDisabledError):
        adapter.fetch()


def test_default_time_window_uses_explicit_bounds_not_present():
    """``time=present`` is rejected by this THREDDS build with HTTP 400."""
    adapter = IncoisWW3LiveAdapter(live_enabled=True, cache=None, horizon_hours=6)
    url = adapter._point_url("f.nc", ["HS"], 15.0, 73.0, None)
    assert "time=present" not in url
    assert "time_start=" in url and "time_end=" in url


def test_forecast_time_is_production_instant_not_valid_time():
    """A forecast's valid_from is in the future; its forecast_time is not.

    Conflating the two makes QC's "no future timestamps" check hard-reject every
    genuine forecast step beyond now, which silently discarded the entire
    forward horizon on the first live run.
    """
    csv_future = (
        'time,station,latitude[unit="degrees_north"],longitude[unit="degrees_east"],'
        'HS[unit=""]\n'
        "2026-09-08T00:00:00Z,a,15.500,73.600,1.4\n"
    )
    rec = records_from_samples(
        parse_ncss_point_csv(csv_future),
        request_lat=15.4909,
        request_lon=73.8278,
        source_url="u",
        init_date="20260904",
        requested_point_land_masked=True,
    )[0]
    assert rec.valid_from > rec.forecast_time
    assert rec.forecast_time == init_datetime("20260904")
    assert rec.forecast_hour == 96
    assert rec.model_cycle == "20260904T00"
    assert rec.source_metadata["model_produced_at"].startswith("2026-09-04")
