import datetime

import pytest

pl = pytest.importorskip("polars")

from nwb_benchmarks.database import BenchmarkDatabase
from nwb_benchmarks.database._processing import EQUIVALENT_ENVIRONMENT_IDS


def make_row(*, environment_id: str, variable: str) -> dict:
    row = dict(
        uuid=variable,
        version="5.0.0",
        commit_hash="abc",
        environment_id=environment_id,
        machine_id="machine",
        timestamp=datetime.datetime(2026, 11, 6),
        benchmark_name="time_remote_slicing.HDF5PyNWBRos3ContinuousSliceBenchmark.time_slice",
        parameter_case_name="EcephysTestCase",
        parameter_case_slice_range=["slice(0, 80, None)"],
        value=1.0,
        variable=variable,
        value_index=0,
    )
    return row


def test_equivalent_environment_ids_are_relabeled():
    alias_id, canonical_id = next(iter(EQUIVALENT_ENVIRONMENT_IDS.items()))
    rows = [
        make_row(environment_id=alias_id, variable="a"),
        make_row(environment_id=canonical_id, variable="b"),
        make_row(environment_id="other", variable="c"),
    ]
    lazy_df = pl.DataFrame(rows).lazy()

    database = BenchmarkDatabase(environment_ids=[canonical_id])
    result = database._preprocess_results(lazy_df).collect()

    assert sorted(result["variable"].to_list()) == ["a", "b"]
    assert set(result["environment_id"].to_list()) == {canonical_id}
