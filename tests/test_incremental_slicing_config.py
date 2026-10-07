import pytest

from nwb_benchmarks.benchmarks.params import (
    _parse_incremental_slicing_benchmarks_config,
)


@pytest.mark.parametrize("value", [None, "", "  ", "false", "0", "no", "OFF"])
def test_disabled_values(value):
    assert _parse_incremental_slicing_benchmarks_config(value) == (False, None)


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "all", " ALL "])
def test_values_enabling_all_modalities(value):
    assert _parse_incremental_slicing_benchmarks_config(value) == (True, None)


@pytest.mark.parametrize(
    ("value", "expected_modalities"),
    [
        ("icephys", {"icephys"}),
        ("icephys,ophys", {"icephys", "ophys"}),
        (" Ecephys , OPHYS ", {"ecephys", "ophys"}),
        ("ecephys,,icephys,", {"ecephys", "icephys"}),
    ],
)
def test_modality_selection(value, expected_modalities):
    assert _parse_incremental_slicing_benchmarks_config(value) == (True, expected_modalities)


@pytest.mark.parametrize("value", ["spikes", "icephys,spikes", "true,icephys"])
def test_invalid_values_raise(value):
    with pytest.raises(ValueError, match="Invalid RUN_INCREMENTAL_SLICING_BENCHMARKS value"):
        _parse_incremental_slicing_benchmarks_config(value)
