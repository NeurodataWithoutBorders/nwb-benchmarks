import json
import math
import pathlib

import pytest

from nwb_benchmarks.setup import _reduce_results
from nwb_benchmarks.setup._reduce_results import reduce_results

# Written by `asv run --record-samples` (as `nwb_benchmarks run` calls it) with asv 0.6.1, trimmed to the keys the
# reducer reads. It holds one benchmark of each result shape below:
#   - `Incremental`: a `track_` benchmark returning `dict(samples=..., number=None)` with a list of cumulative times, as
#     `track_incremental_slicing` does. Parameter set B raised, so its samples are `null`.
#   - `Network`: a `track_` benchmark returning `dict(samples=..., number=None)`, as the network tracking benchmarks do.
#   - `Timed`: a `time_` benchmark run with a `--bench` pattern selecting only parameter set A, so B's result is NaN.
#   - `Unwrapped`: a `track_` benchmark returning a plain dict, which ASV stores in the `result` column without samples.
RAW_RESULTS_FILE_PATH = pathlib.Path(__file__).parent / "data" / "asv_0.6.1_raw_results.json"

INCREMENTAL = "bench.Incremental.track_cumulative_slice_times"
NETWORK = "bench.Network.track_network"
TIMED = "bench.Timed.time_read"
UNWRAPPED = "bench.Unwrapped.track_unwrapped"

NETWORK_STATISTICS = {
    "total_transfer_in_bytes": 100,
    "total_traffic_in_number_of_web_packets": 4,
    "total_transfer_time_in_seconds": 2.0,
}


@pytest.fixture
def raw_results_info() -> dict:
    with open(RAW_RESULTS_FILE_PATH) as file_stream:
        return json.load(fp=file_stream)


@pytest.fixture
def reduce(tmp_path, monkeypatch):
    """Return a function that runs `reduce_results` on raw results, writing into a temporary home directory."""
    for name in ("RESULTS_DIR", "ENVIRONMENTS_DIR", "MACHINES_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(_reduce_results, name, directory)
    (tmp_path / "machines_dir" / "machine-test.json").write_text("{}")

    raw_environment_info_file_path = tmp_path / "environment.txt"
    raw_environment_info_file_path.write_text(
        "# packages in environment at /conda/envs/nwb_benchmarks:\n"
        "#\n"
        "# Name                    Version                   Build  Channel\n"
        "pynwb                     3.1.0                    pypi_0    pypi\n"
    )

    def _reduce(raw_results_info: dict) -> pathlib.Path:
        raw_results_file_path = tmp_path / "raw_results.json"
        with open(raw_results_file_path, mode="w") as file_stream:
            json.dump(obj=raw_results_info, fp=file_stream)

        reduce_results(
            machine_id="test",
            raw_results_file_path=raw_results_file_path,
            raw_environment_info_file_path=raw_environment_info_file_path,
        )

        assert not raw_results_file_path.exists()
        (reduced_results_file_path,) = (tmp_path / "results_dir").glob("*_machine-test_results.json")
        return reduced_results_file_path

    return _reduce


def reduced_results(reduced_results_file_path: pathlib.Path) -> dict:
    with open(reduced_results_file_path) as file_stream:
        return json.load(fp=file_stream)["results"]


def test_incremental_results_keep_the_successful_parameter_set(reduce, raw_results_info):
    results = reduced_results(reduce(raw_results_info))

    assert results[INCREMENTAL] == {"{'name': 'A'}": {"cumulative_time_in_seconds": [0.5, 1.0, 1.5]}}


def test_network_results(reduce, raw_results_info):
    results = reduced_results(reduce(raw_results_info))

    assert results[NETWORK] == {"{'name': 'A'}": NETWORK_STATISTICS, "{'name': 'B'}": NETWORK_STATISTICS}


def test_time_results_leave_out_parameter_sets_that_did_not_run(reduce, raw_results_info):
    timed_samples = raw_results_info["results"][TIMED][11]

    results = reduced_results(reduce(raw_results_info))

    assert results[TIMED] == {"{'name': 'A'}": timed_samples[0]}


def test_track_results_without_samples_are_left_out(reduce, raw_results_info):
    results = reduced_results(reduce(raw_results_info))

    assert sorted(results) == [INCREMENTAL, NETWORK, TIMED]


def test_length_mismatch_warns_and_leaves_out_only_that_benchmark(reduce, raw_results_info):
    raw_results_info["results"][NETWORK][11] = raw_results_info["results"][NETWORK][11][:1]

    with pytest.warns(UserWarning, match=f"test case {NETWORK}: \n\tLength mismatch"):
        results = reduced_results(reduce(raw_results_info))

    assert sorted(results) == [INCREMENTAL, TIMED]


def test_no_successful_results_raises(reduce, raw_results_info):
    raw_results_info["results"] = {UNWRAPPED: raw_results_info["results"][UNWRAPPED]}

    with pytest.raises(ValueError, match="failed to find any successful results"):
        reduce(raw_results_info)


def test_reduced_results_file(reduce, raw_results_info):
    with open(reduce(raw_results_info)) as file_stream:
        reduced_results_info = json.load(fp=file_stream)

    assert reduced_results_info["commit_hash"] == "0123456789abcdef0123456789abcdef01234567"
    assert reduced_results_info["machine_id"] == "test"


def test_database_reads_the_reduced_results(reduce, raw_results_info):
    pytest.importorskip("polars")
    pytest.importorskip("seaborn")
    from nwb_benchmarks.database import Results

    data_frame = Results.safe_load_from_json(file_path=reduce(raw_results_info)).to_dataframe()

    incremental = data_frame.filter(data_frame["benchmark_name"] == INCREMENTAL)
    assert incremental["variable"].to_list() == ["cumulative_time_in_seconds"] * 3
    assert incremental["value"].to_list() == [0.5, 1.0, 1.5]

    network = data_frame.filter(data_frame["benchmark_name"] == NETWORK)
    mean_time_per_web_packet = network.filter(network["variable"] == "mean_time_per_web_packet")["value"].to_list()
    assert mean_time_per_web_packet == [0.5, 0.5]

    timed = data_frame.filter(data_frame["benchmark_name"] == TIMED)
    assert timed["variable"].to_list() == ["time"]
    assert not math.isnan(timed["value"][0])
