import datetime

import numpy as np
import pytest

pl = pytest.importorskip("polars")
pytest.importorskip("seaborn")

from nwb_benchmarks.database import BenchmarkDatabase, BenchmarkVisualizer

INCREMENTAL_BENCHMARK_CLASSES = {
    "HDF5PyNWBRemfileWithCacheIncrementalSliceBenchmark": ("hdf5 pynwb remfile with cache", "remote", "hdf5"),
    "HDF5PyNWBFsspecHttpsWithCacheIncrementalSliceBenchmark": ("hdf5 pynwb fsspec https with cache", "remote", "hdf5"),
    "HDF5PyNWBROS3IncrementalSliceBenchmark": ("hdf5 pynwb ros3", "remote", "hdf5"),
    "HDF5PyNWBLindiIncrementalSliceBenchmark": ("lindi pynwb", "remote", "hdf5"),
    "ZarrPyNWBS3IncrementalSliceBenchmark": ("zarr pynwb s3", "remote", "zarr"),
    "HDF5PyNWBLocalIncrementalSliceBenchmark": ("hdf5 pynwb", "local", "hdf5"),
    "ZarrPyNWBLocalIncrementalSliceBenchmark": ("zarr pynwb", "local", "zarr"),
}

DOWNLOAD_BENCHMARKS = {
    "time_download.HDF5DandiAPIDownloadBenchmark.time_download_hdf5_dandi_api": 100.0,
    "time_download.ZarrDandiAPIDownloadBenchmark.time_download_zarr_dandi_api": 200.0,
    "time_download.LindiDandiAPIDownloadBenchmark.time_download_lindi_dandi_api": 3.0,
}


def make_database(tmp_path) -> BenchmarkDatabase:
    rows = [
        dict(
            benchmark_name=f"track_incremental_slicing.{class_name}.track_cumulative_slice_times",
            variable="cumulative_time_in_seconds",
            value=float(value_index + 1),
            value_index=value_index,
        )
        for class_name in INCREMENTAL_BENCHMARK_CLASSES
        for value_index in range(3)
    ]
    rows += [
        dict(benchmark_name=benchmark_name, variable="time", value=value, value_index=0)
        for benchmark_name, value in DOWNLOAD_BENCHMARKS.items()
    ]
    data_frame = pl.DataFrame(rows).with_columns(
        [
            pl.lit("a").alias("machine_id"),
            pl.lit("e").alias("environment_id"),
            pl.lit(datetime.datetime(2026, 11, 2)).alias("timestamp"),
            pl.lit("EcephysIncrementalSliceTestCase").alias("parameter_case_name"),
            pl.lit(None, dtype=pl.List(pl.String)).alias("parameter_case_slice_range"),
        ]
    )
    data_frame.write_parquet(tmp_path / "results.parquet")
    return BenchmarkDatabase(results_directory=tmp_path, db_directory=tmp_path)


def test_incremental_results_get_method_names_access_modes_and_formats(tmp_path):
    results = make_database(tmp_path).get_incremental_slicing_results().collect()

    methods = set(results.select(["benchmark_name_clean", "access_mode", "format_family"]).unique().iter_rows())
    assert methods == set(INCREMENTAL_BENCHMARK_CLASSES.values())
    assert results["slice_index"].to_list() == results["value_index"].to_list()


def test_download_times_are_added_to_local_and_lindi_results_only(tmp_path):
    combined = make_database(tmp_path).combine_incremental_slicing_and_download_times().collect()

    download_times = dict(combined.select(["benchmark_name_clean", "avg_download_time"]).unique().iter_rows())
    assert download_times == {
        "hdf5 pynwb remfile with cache": 0.0,
        "hdf5 pynwb fsspec https with cache": 0.0,
        "hdf5 pynwb ros3": 0.0,
        "lindi pynwb": 3.0,
        "zarr pynwb s3": 0.0,
        "hdf5 pynwb": 100.0,
        "zarr pynwb": 200.0,
    }
    assert (combined["total_time"] == combined["value"] + combined["avg_download_time"]).all()


@pytest.mark.parametrize(
    ("stream_times", "download_times", "expected"),
    [
        ([1.0, 2.0, 3.0, 4.0], [2.5, 2.6, 2.7, 2.8], 2),
        ([1.0, 2.0], [5.0, 6.0], None),
        ([3.0, 4.0], [2.0, 2.5], 0),
        ([1.0, 2.0, 3.0], [1.5, 1.6], 1),
    ],
)
def test_first_crossover_index(stream_times, download_times, expected):
    crossover_index = BenchmarkVisualizer._first_crossover_index(
        stream_times=np.array(stream_times), download_times=np.array(download_times)
    )

    assert crossover_index == expected


def test_summary_tables_have_one_column_per_curve_and_one_overview_row_per_curve(tmp_path):
    pd = pytest.importorskip("pandas")
    tables_directory = tmp_path / "tables"
    visualizer = BenchmarkVisualizer(output_directory=tmp_path / "figures", summary_tables_directory=tables_directory)

    visualizer.plot_incremental_slicing_benchmarks(make_database(tmp_path))

    curve_table = pd.read_csv(tables_directory / "incremental_slicing_cumulative_time_ecephys.csv")
    expected_curves = [
        "HDF5 download + local",
        "Zarr download + local",
        "HDF5 remfile cache",
        "HDF5 fsspec HTTPS cache",
        "HDF5 ROS3",
        "LINDI",
        "Zarr",
    ]
    assert curve_table.columns.to_list() == [
        "slice_index",
        "fraction_of_time_axis_read",
        *[f"{curve} (s)" for curve in expected_curves],
    ]
    assert curve_table["slice_index"].to_list() == [0, 1, 2]

    overview = pd.read_csv(tables_directory / "incremental_slicing_overview.csv").set_index("method")
    assert overview.index.to_list() == expected_curves
    for curve in expected_curves:
        assert overview.loc[curve, "total_time_s"] == curve_table[f"{curve} (s)"].iloc[-1]
    assert overview.loc["LINDI", "open_time_s"] == 1.0
    assert overview.loc["LINDI", "download_time_s"] == 3.0
    assert overview.loc["HDF5 remfile cache", "mean_time_per_slice_s"] == 1.0
    assert pd.isna(overview.loc["HDF5 remfile cache", "crossover_slice_index"])
    assert pd.isna(overview.loc["HDF5 download + local", "crossover_slice_index"])
    assert not (tables_directory / "incremental_slicing_cumulative_time_summary.csv").exists()
