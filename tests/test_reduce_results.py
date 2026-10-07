import json
import math
import pathlib
import shutil

import pytest

from nwb_benchmarks.setup import _reduce_results
from nwb_benchmarks.setup._reduce_results import (
    _extract_successful_results,
    _serialize_parameter_cases,
    reduce_results,
)

# Written by `asv run --record-samples` (as `nwb_benchmarks run` calls it) with asv 0.6.1, trimmed to the keys the
# reducer reads. It holds one benchmark of each result shape the suite produces:
#   - `Incremental`: a `track_` benchmark returning a plain dict, as `track_incremental_slicing` does. ASV stores it in
#     the `result` column without samples. Parameter set B raised, so its result is `null`.
#   - `Network`: a `track_` benchmark returning `dict(samples=..., number=None)`, as the network tracking benchmarks do.
#   - `Timed`: a `time_` benchmark run with a `--bench` pattern selecting only parameter set A, so B's result is NaN.
RAW_RESULTS_FILE_PATH = pathlib.Path(__file__).parent / "data" / "asv_0.6.1_raw_results.json"

INCREMENTAL = "bench.Incremental.track_cumulative_slice_times"
NETWORK = "bench.Network.track_network"
TIMED = "bench.Timed.time_read"


@pytest.fixture
def raw_results_info() -> dict:
    with open(RAW_RESULTS_FILE_PATH) as file_stream:
        return json.load(fp=file_stream)


def extract(raw_results_info: dict, test_case: str, result_columns="from file") -> dict:
    return _extract_successful_results(
        test_case=test_case,
        raw_results_list=raw_results_info["results"][test_case],
        result_columns=raw_results_info["result_columns"] if result_columns == "from file" else result_columns,
    )


def test_incremental_results_keep_the_successful_parameter_set(raw_results_info):
    assert extract(raw_results_info, INCREMENTAL) == {"{'name': 'A'}": {"cumulative_time_in_seconds": [0.5, 1.0, 1.5]}}


def test_network_results_are_read_from_the_samples(raw_results_info):
    network_statistics = {
        "total_transfer_in_bytes": 100,
        "total_traffic_in_number_of_web_packets": 4,
        "total_transfer_time_in_seconds": 2.0,
    }

    assert extract(raw_results_info, NETWORK) == {
        "{'name': 'A'}": network_statistics,
        "{'name': 'B'}": network_statistics,
    }


def test_time_results_leave_out_parameter_sets_that_did_not_run(raw_results_info):
    timed_samples = raw_results_info["results"][TIMED][11]

    assert extract(raw_results_info, TIMED) == {"{'name': 'A'}": timed_samples[0]}


def test_rows_without_result_columns_use_the_fixed_layout(raw_results_info):
    # Rows with samples have 12 entries and are read the same way; the incremental row has none, so it is left out.
    assert extract(raw_results_info, NETWORK, result_columns=None) == extract(raw_results_info, NETWORK)
    assert extract(raw_results_info, TIMED, result_columns=None) == extract(raw_results_info, TIMED)
    assert extract(raw_results_info, INCREMENTAL, result_columns=None) == {}


def test_missing_and_skipped_rows_are_left_out(raw_results_info):
    result_columns = raw_results_info["result_columns"]

    assert _extract_successful_results(test_case="x", raw_results_list=None, result_columns=result_columns) == {}
    assert (
        _extract_successful_results(test_case="x", raw_results_list=[None, [["a"]]], result_columns=result_columns)
        == {}
    )


def test_length_mismatch_warns_and_is_left_out(raw_results_info):
    raw_results_list = [[1.0], [["{'name': 'A'}", "{'name': 'B'}"]]]

    with pytest.warns(UserWarning, match="Length mismatch"):
        result = _extract_successful_results(
            test_case="x", raw_results_list=raw_results_list, result_columns=raw_results_info["result_columns"]
        )
    assert result == {}


@pytest.mark.parametrize(
    ("serialized_params", "expected"),
    [
        ([], ["()"]),
        ([["'a'", "'b'"]], ["'a'", "'b'"]),
        ([["'a'", "'b'"], ["1"]], ["(\"'a'\", '1')", "(\"'b'\", '1')"]),
    ],
)
def test_serialize_parameter_cases(serialized_params, expected):
    assert _serialize_parameter_cases(serialized_params=serialized_params) == expected


@pytest.fixture
def reduced_results_file_path(tmp_path, monkeypatch) -> pathlib.Path:
    """Run `reduce_results` on a copy of the raw results, writing into a temporary home directory."""
    for name in ("RESULTS_DIR", "ENVIRONMENTS_DIR", "MACHINES_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(_reduce_results, name, directory)
    (tmp_path / "machines_dir" / "machine-test.json").write_text("{}")

    raw_results_file_path = tmp_path / "raw_results.json"
    shutil.copy(RAW_RESULTS_FILE_PATH, raw_results_file_path)
    raw_environment_info_file_path = tmp_path / "environment.txt"
    raw_environment_info_file_path.write_text(
        "# packages in environment at /conda/envs/nwb_benchmarks:\n"
        "#\n"
        "# Name                    Version                   Build  Channel\n"
        "pynwb                     3.1.0                    pypi_0    pypi\n"
    )

    reduce_results(
        machine_id="test",
        raw_results_file_path=raw_results_file_path,
        raw_environment_info_file_path=raw_environment_info_file_path,
    )

    assert not raw_results_file_path.exists()
    (reduced_results_file_path,) = (tmp_path / "results_dir").glob("*_machine-test_results.json")
    return reduced_results_file_path


def test_reduce_results_writes_every_successful_result(reduced_results_file_path):
    with open(reduced_results_file_path) as file_stream:
        reduced_results_info = json.load(fp=file_stream)

    assert reduced_results_info["commit_hash"] == "0123456789abcdef0123456789abcdef01234567"
    assert reduced_results_info["machine_id"] == "test"
    assert sorted(reduced_results_info["results"]) == [INCREMENTAL, NETWORK, TIMED]
    assert reduced_results_info["results"][INCREMENTAL] == {
        "{'name': 'A'}": {"cumulative_time_in_seconds": [0.5, 1.0, 1.5]}
    }


def test_database_reads_the_reduced_results(reduced_results_file_path):
    pytest.importorskip("polars")
    pytest.importorskip("seaborn")
    from nwb_benchmarks.database import Results

    results = Results.safe_load_from_json(file_path=reduced_results_file_path)
    data_frame = results.to_dataframe()

    incremental = data_frame.filter(data_frame["benchmark_name"] == INCREMENTAL)
    assert incremental["variable"].to_list() == ["cumulative_time_in_seconds"] * 3
    assert incremental["value"].to_list() == [0.5, 1.0, 1.5]

    network = data_frame.filter(data_frame["benchmark_name"] == NETWORK)
    mean_time_per_web_packet = network.filter(network["variable"] == "mean_time_per_web_packet")["value"].to_list()
    assert mean_time_per_web_packet == [0.5, 0.5]

    timed = data_frame.filter(data_frame["benchmark_name"] == TIMED)
    assert timed["variable"].to_list() == ["time"]
    assert not math.isnan(timed["value"][0])
