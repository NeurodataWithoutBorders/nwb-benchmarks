import datetime

import numpy as np
import pytest
from pynwb import NWBFile, TimeSeries

from nwb_benchmarks.benchmarks import params
from nwb_benchmarks.benchmarks.track_incremental_slicing import (
    IncrementalSliceBenchmark,
)


def make_nwbfile() -> NWBFile:
    nwbfile = NWBFile(
        session_description="incremental slicing test",
        identifier="incremental-slicing-test",
        session_start_time=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    nwbfile.add_acquisition(TimeSeries(name="series", data=np.arange(40).reshape(10, 4), unit="V", rate=1.0))
    nwbfile.add_acquisition(TimeSeries(name="response", data=np.arange(5), unit="V", rate=1.0))
    nwbfile.add_stimulus(TimeSeries(name="stimulus", data=np.arange(3), unit="A", rate=1.0))
    return nwbfile


class InMemoryIncrementalSliceBenchmark(IncrementalSliceBenchmark):
    def __init__(self, nwbfile: NWBFile):
        self._nwbfile_to_open = nwbfile

    def _open_file(self, params):
        self.nwbfile = self._nwbfile_to_open


def test_time_axis_slices_cover_the_axis_and_keep_trailing_slices():
    data = np.zeros((10, 4))
    slices = list(IncrementalSliceBenchmark._iter_time_axis_slices(data, (slice(0, 4), slice(0, 2))))

    assert slices == [
        (slice(0, 4), slice(0, 2)),
        (slice(4, 8), slice(0, 2)),
        (slice(8, 10), slice(0, 2)),
    ]


def test_time_axis_slices_use_the_template_width_from_the_start_of_the_axis():
    slices = list(IncrementalSliceBenchmark._iter_time_axis_slices(np.zeros(7), (slice(2, 5),)))

    assert slices == [(slice(0, 3),), (slice(3, 6),), (slice(6, 7),)]


def test_time_axis_slices_reject_an_empty_template():
    with pytest.raises(ValueError, match="Invalid time-axis slice template"):
        list(IncrementalSliceBenchmark._iter_time_axis_slices(np.zeros(7), (slice(3, 3),)))


def test_time_axis_slices_reject_scalar_data():
    with pytest.raises(ValueError, match="at least one dimension"):
        list(IncrementalSliceBenchmark._iter_time_axis_slices(np.float64(1.0), (slice(0, 1),)))


def test_icephys_timeseries_iterates_acquisition_then_stimulus():
    names = [name for name, _ in IncrementalSliceBenchmark._iter_icephys_timeseries(make_nwbfile())]

    assert names == ["acquisition/series", "acquisition/response", "stimulus/stimulus"]


def assert_cumulative_times(result, expected_length):
    assert list(result) == ["cumulative_time_in_seconds"]
    cumulative_times = result["cumulative_time_in_seconds"]
    assert len(cumulative_times) == expected_length
    assert all(isinstance(value, float) for value in cumulative_times)
    assert cumulative_times == sorted(cumulative_times)


def test_cumulative_times_for_time_axis_strategy():
    benchmark = InMemoryIncrementalSliceBenchmark(nwbfile=make_nwbfile())
    result = benchmark._track_cumulative_slice_times(
        params=dict(object_name="series", slice_template=(slice(0, 4), slice(0, 4)), slice_strategy="iterate_time_axis")
    )

    # The open time, then one entry for each of the 3 slices covering the 10 time points.
    assert_cumulative_times(result=result, expected_length=1 + 3)
    np.testing.assert_array_equal(benchmark._temp, np.arange(32, 40).reshape(2, 4))


def test_cumulative_times_for_icephys_strategy():
    benchmark = InMemoryIncrementalSliceBenchmark(nwbfile=make_nwbfile())
    result = benchmark._track_cumulative_slice_times(params=dict(slice_strategy="iterate_icephys_timeseries"))

    # The open time, then one entry for each of the 3 time series.
    assert_cumulative_times(result=result, expected_length=1 + 3)
    np.testing.assert_array_equal(benchmark._temp, np.arange(3))


def test_tracked_result_is_wrapped_as_asv_samples():
    # ASV only writes a `track_` result to the samples column, which `reduce_results` reads, in this structure.
    benchmark = InMemoryIncrementalSliceBenchmark(nwbfile=make_nwbfile())
    result = benchmark.track_cumulative_slice_times(params=dict(slice_strategy="iterate_icephys_timeseries"))

    assert list(result) == ["samples", "number"]
    assert result["number"] is None
    assert_cumulative_times(result=result["samples"], expected_length=1 + 3)


def test_unsupported_strategy_raises():
    benchmark = InMemoryIncrementalSliceBenchmark(nwbfile=make_nwbfile())

    with pytest.raises(ValueError, match="Unsupported incremental slice strategy"):
        benchmark._track_cumulative_slice_times(params=dict(slice_strategy="iterate_backwards"))


def test_teardown_without_open_resources():
    InMemoryIncrementalSliceBenchmark(nwbfile=make_nwbfile()).teardown(params=dict())


def test_filter_keeps_all_parameter_sets_without_a_modality_selection(monkeypatch):
    monkeypatch.setattr(params, "RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES", None)
    parameter_sets = (dict(modality="ecephys"), dict(modality="ophys"), dict(modality="icephys"))

    assert params.filter_incremental_slice_params_by_modality(parameter_sets) == parameter_sets


def test_filter_keeps_only_selected_modalities(monkeypatch):
    monkeypatch.setattr(params, "RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES", {"icephys", "ophys"})
    parameter_sets = (dict(modality="ecephys"), dict(modality="ophys"), dict(modality="icephys"))

    assert params.filter_incremental_slice_params_by_modality(parameter_sets) == (
        dict(modality="ophys"),
        dict(modality="icephys"),
    )
