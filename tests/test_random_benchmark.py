import os
import random
import re
from types import SimpleNamespace

import pytest

from nwb_benchmarks.setup import (
    benchmark_name_pattern,
    discover_benchmarks,
    select_random_benchmark,
)


def fake_benchmark(name: str, params=None) -> SimpleNamespace:
    return SimpleNamespace(name=name, params=params or [])


def test_selection_is_deterministic_with_a_seed_and_covers_every_candidate():
    benchmarks = [fake_benchmark(f"module.Class.time_{index}") for index in range(5)]
    chosen = {select_random_benchmark(benchmarks, random.Random(seed)) for seed in range(50)}
    assert chosen == {benchmark.name for benchmark in benchmarks}
    assert select_random_benchmark(benchmarks, random.Random(1)) == select_random_benchmark(
        benchmarks, random.Random(1)
    )


def test_benchmarks_without_parameter_sets_are_never_chosen():
    benchmarks = [
        fake_benchmark("module.Class.time_filtered_out", params=[[]]),
        fake_benchmark("module.Class.time_parameterized", params=[["{'name': 'x'}", "{'name': 'y'}"]]),
    ]
    assert select_random_benchmark(benchmarks, random.Random(0)) == "module.Class.time_parameterized"


def test_no_candidate_raises():
    with pytest.raises(RuntimeError, match="No benchmark"):
        select_random_benchmark([fake_benchmark("module.Class.time_filtered_out", params=[[]])])


def test_pattern_selects_exactly_the_named_benchmark():
    pattern = re.compile(benchmark_name_pattern("module.Class.time_read"))
    assert pattern.search("module.Class.time_read({'name': 'x', 'https_url': 'https://x/y'})")
    assert pattern.search("module.Class.time_read")
    assert not pattern.search("module.Class.time_read_with_cache({'name': 'x'})")
    assert not pattern.search("other.module.Class.time_read({'name': 'x'})")


def test_discovery_finds_the_suite_and_leaves_out_skipped_benchmarks():
    names = {benchmark.name for benchmark in discover_benchmarks()}
    assert "time_remote_file_reading.HDF5H5pyFileReadBenchmark.time_read_hdf5_h5py_remfile_no_cache" in names
    # Discovery evaluates the suite's `skip_benchmark_if` marks, which depend on the environment at import.
    if not os.environ.get("RUN_DOWNLOAD_BENCHMARKS"):
        assert "time_download.HDF5DandiAPIDownloadBenchmark.time_download_hdf5_dandi_api" not in names
    if not os.environ.get("RUN_INCREMENTAL_SLICING_BENCHMARKS"):
        assert not any(name.startswith("track_incremental_slicing.") for name in names)
