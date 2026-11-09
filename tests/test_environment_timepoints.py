import pytest

pl = pytest.importorskip("polars")

from nwb_benchmarks.database import BenchmarkDatabase
from nwb_benchmarks.database._processing import (
    ENVIRONMENT_TIMEPOINTS,
    PACKAGES_OF_INTEREST,
)


def test_environments_are_labeled_with_their_timepoint(tmp_path):
    timepoint, environment_id = next(iter(ENVIRONMENT_TIMEPOINTS.items()))
    environments = pl.LazyFrame(
        {
            "environment_id": [environment_id, "unknown-environment"],
            **{package: ["1.2.3=py_0", "4.5.6"] for package in PACKAGES_OF_INTEREST},
        }
    )

    database = BenchmarkDatabase(results_directory=tmp_path, db_directory=tmp_path)
    labeled = database._preprocess_environments(environments).collect()

    timepoints = dict(labeled.select(["environment_id", "environment_timepoint"]).unique().iter_rows())
    assert timepoints == {environment_id: timepoint, "unknown-environment": None}
    assert set(labeled["package_version"]) == {"1.2.3", "4.5.6"}
