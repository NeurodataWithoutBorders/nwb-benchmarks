import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import polars as pl

from nwb_benchmarks.database._parquet import repackage_as_parquet

PACKAGES_OF_INTEREST = [
    "h5py",
    "dandi",
    "zarr",
    "fsspec",
    "lindi",
    "s3fs",
    "aiohttp",
    "boto3",
    "hdmf-zarr",
    "hdmf",
    "pynwb",
]

ENVIRONMENT_TIMEPOINTS = {
    "2024-06-30": "9e225115ea6c99b60d419454a9457bb5db93c7b7",  # all timepoints based on lbl mac
    "2025-06-30": "15d059d5b6b9047f9bbeb4ac77bb4461411904c7",
    "2025-09-01": "052cb4d925793bbbc270d9384a60bc24023025b7",  # note - this environment was created after 2025-09-01 but exact date unknown
}


class BenchmarkDatabase:
    """Handles database preprocessing and loading for NWB benchmarks."""

    def __init__(
        self,
        results_directory: Optional[Path] = None,
        db_directory: Optional[Path] = None,
        machine_id: str = None,
        exclude_older: str = None,
    ):
        """Initialize database handler with directories and machine ID.

        Args:
            results_directory: Directory containing benchmark results
            db_directory: Directory for database storage
            machine_id: Machine ID for filtering results
        """
        self.machine_id = machine_id
        self.packages_of_interest = PACKAGES_OF_INTEREST
        self.environment_timepoints = ENVIRONMENT_TIMEPOINTS
        self.exclude_older = exclude_older

        # Set default directories if not provided
        cache_dir = Path.home() / ".cache" / "nwb-benchmarks"
        self.results_directory = results_directory or cache_dir / "nwb-benchmarks-results"
        self.db_directory = db_directory or cache_dir

        self._results_df = None
        self._environments_df = None

    def create_database(self, minimum_results_version: str = "3.0.0", minimum_machines_version: str = "1.4.0") -> None:
        """Create new database file with latest results."""
        repackage_as_parquet(
            directory=self.results_directory,
            output_directory=self.db_directory,
            minimum_results_version=minimum_results_version,
            minimum_machines_version=minimum_machines_version,
        )

    @staticmethod
    @lru_cache(maxsize=128)
    def split_camel_case(text: str) -> str:
        """Split camel case text into words."""
        text = re.sub(r"PyNWBS3", "PyNWB S3", text)
        text = re.sub(r"NWBROS3", "NWB ROS3", text)
        result = re.sub("([a-z0-9])([A-Z])", r"\1 \2", text)
        result = re.sub("([A-Z]+)([A-Z][a-z])", r"\1 \2", result)
        result = re.sub("Py NWB", "PyNWB", result)
        return result

    @lru_cache(maxsize=128)
    def clean_benchmark_name_test(self, name: str) -> str:
        """Clean benchmark test names."""
        short_name = (
            name.replace("ContinuousSliceBenchmark", "")
            .replace("FileReadBenchmark", "")
            .replace("DownloadBenchmark", "")
        )
        return self.split_camel_case(short_name).lower()

    def _preprocess_results(self, df: pl.LazyFrame) -> pl.DataFrame:
        """Apply all preprocessing transformations to the results dataframe."""
        print("Preprocessing benchmark results...")

        # clean benchmark expression
        clean_benchmark_operation_expr = (
            pl.col("benchmark_name_operation")
            .str.replace("time_read_", "")
            .str.replace("track_network_read_", "")
            .str.replace("time_download_", "")
            .str.replace("zarrpython", "zarr")
            .str.replace_all("_", " ")
        )

        return (
            df
            # Filter for specific machine early to reduce data volume
            .filter(pl.col("machine_id") == self.machine_id if self.machine_id is not None else pl.lit(True))
            # Filter for timestamp early to reduce data volume
            .filter(
                pl.col("timestamp") >= pl.lit(self.exclude_older).str.to_datetime()
                if self.exclude_older is not None
                else pl.lit(True)
            )
            # Extract benchmark name components
            .with_columns(
                [
                    pl.col("parameter_case_name").str.extract(r"^(Ophys|Ecephys|Icephys)").alias("modality"),
                    pl.col("benchmark_name").str.split(".").list.get(0).alias("benchmark_name_type"),
                    pl.col("benchmark_name").str.split(".").list.get(1).alias("benchmark_name_test"),
                    pl.col("benchmark_name").str.split(".").list.get(2).alias("benchmark_name_operation"),
                ]
            )
            # Clean operation names using expressions
            .with_columns(clean_benchmark_operation_expr.alias("benchmark_name_operation"))
            # Extract benchmark labels and clean test names
            .with_columns(
                [
                    pl.col("benchmark_name_test")
                    .str.extract(r"(ContinuousSliceBenchmark|FileReadBenchmark|DownloadBenchmark)")
                    .alias("benchmark_name_label"),
                    pl.col("benchmark_name_test")
                    .map_elements(self.clean_benchmark_name_test, return_dtype=pl.String)
                    .alias("benchmark_name_test"),
                ]
            )
            # Handle preloaded and local information
            .with_columns(
                [
                    pl.col("benchmark_name_test").str.contains("preloaded").alias("is_preloaded"),
                    pl.col("benchmark_name_test").str.replace(" preloaded", "").alias("benchmark_name_test"),
                ]
            )
            .with_columns(
                [
                    pl.col("benchmark_name").str.contains("local").alias("is_local"),
                    pl.col("benchmark_name_test")
                    .str.replace(" local", "")
                    .str.replace("json", "pynwb")
                    .alias("benchmark_name_test"),
                    pl.when(pl.col("benchmark_name_operation").str.contains("local"))
                    .then(
                        pl.col("benchmark_name_operation").str.replace(
                            r"local (.*)", pl.col("benchmark_name_test") + " $1"
                        )
                    )
                    .otherwise(pl.col("benchmark_name_operation"))
                    .alias("benchmark_name_operation"),
                ]
            )
            # Extract scaling information
            .with_columns(
                pl.col("parameter_case_slice_range")
                .list.first()
                .str.extract(r"slice\(0, (\d+),", group_index=1)
                .cast(pl.Int64)
                .alias("scaling_value"),
            )
            .with_columns((pl.col("scaling_value").rank(method="dense")).over("modality").alias("slice_number"))
            # Create unified cleaned benchmark name
            .with_columns(
                pl.when(pl.col("benchmark_name_label") == "ContinuousSliceBenchmark")
                .then(pl.col("benchmark_name_test"))
                .when(pl.col("benchmark_name_label").is_in(["FileReadBenchmark", "DownloadBenchmark"]))
                .then(pl.col("benchmark_name_operation"))
                .otherwise(pl.col("benchmark_name_test"))  # fallback
                .alias("benchmark_name_clean")
            )
        )

    def _preprocess_environments(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Apply all preprocessing transformations to the environments dataframe."""

        return (
            df
            # get only relevant package columns
            .select(["environment_id", *self.packages_of_interest])
            # remove build information
            .with_columns([pl.col(pkg).str.extract(r"^([\d.]+)", group_index=1) for pkg in self.packages_of_interest])
            # unpivot packages into long format for plotting
            .unpivot(
                index="environment_id",
                on=self.packages_of_interest,
                variable_name="package_name",
                value_name="package_version",
            )
            .filter(pl.col("package_version").is_not_null())
            .with_columns(
                pl.col("environment_id")
                .replace({v: k for k, v in ENVIRONMENT_TIMEPOINTS.items()}, default=None)
                .alias("environment_timepoint")
            )
        )

    def get_results(self) -> pl.LazyFrame:
        """
        Load and preprocess benchmark results with caching.

        Returns:
            Preprocessed benchmark results as a DataFrame
        """
        if self._results_df is None:
            lazy_df = pl.scan_parquet(self.db_directory / "results.parquet")
            self._results_df = self._preprocess_results(lazy_df)

        return self._results_df

    def get_environments(self) -> pl.LazyFrame:
        """
        Load and preprocess benchmark environments with caching.

        Returns:
            Preprocessed benchmark environments as a DataFrame
        """
        if self._environments_df is None:
            lazy_df = pl.scan_parquet(self.db_directory / "environments.parquet")
            self._environments_df = self._preprocess_environments(lazy_df)

        return self._environments_df

    def join_results_with_environments(self) -> pl.LazyFrame:
        """Join streaming package versions with results using the environments table."""
        return self.get_results().join(
            self.get_environments(),
            on="environment_id",
            how="left",
        )

    def filter_results_for_environment_timepoints(self) -> pl.LazyFrame:
        """Filter environments to only include those matching specified timepoints."""
        return self.join_results_with_environments().filter(
            pl.col("environment_id").is_in(list(self.environment_timepoints.values()))
        )

    def filter_tests(self, benchmark_type: str) -> pl.LazyFrame:
        """Filter benchmark tests."""
        results_df = self.get_results()
        return results_df.filter(pl.col("benchmark_name_type") == benchmark_type)

    def combine_read_and_slice_times(
        self, read_col_name: str, slice_col_name: str, with_baseline: bool = False
    ) -> pl.LazyFrame:
        if with_baseline:
            # add artificial baseline of slice_number 0 with value = 0
            df_a = pl.concat(
                [
                    self.filter_tests(read_col_name).with_columns(
                        [
                            pl.lit(0).cast(pl.UInt32).alias("slice_number"),
                            pl.lit(0.0).alias("value"),
                        ]
                    ),
                    self.filter_tests(slice_col_name),
                ]
            )
        else:
            df_a = self.filter_tests(slice_col_name)

        return (
            df_a.join(
                # get average file read time
                self.filter_tests(read_col_name)
                .group_by(["modality", "benchmark_name_clean"])
                .agg(pl.col("value").mean().alias("avg_file_open_time")),  # TODO check what average includes
                # match on benchmark_name_clean + parameter_case_name
                on=["modality", "benchmark_name_clean"],
                how="left",
            )
            # add average file open time to each slice time
            .with_columns((pl.col("value") + pl.col("avg_file_open_time")).alias("total_time"))
        )

    def combine_download_read_and_slice_times(
        self, read_col_name: str, slice_col_name: str, with_baseline: bool = False
    ) -> pl.LazyFrame:
        download_df = self.filter_tests("time_download")
        local_read_and_slice_df = self.combine_read_and_slice_times(
            read_col_name=read_col_name, slice_col_name=slice_col_name, with_baseline=with_baseline
        )

        # Match download benchmarks to the local PyNWB read/slice benchmarks without
        # overwriting benchmark_name_clean. Download benchmarks are named like
        # "hdf5 dandi api" and "zarr dandi api", while the comparable local slicing
        # benchmarks are named "hdf5 pynwb" and "zarr pynwb". A dedicated match column
        # preserves the original labels and avoids relying on trailing spaces in plots.
        local_read_and_slice_df = local_read_and_slice_df.with_columns(
            [
                pl.col("benchmark_name_clean").alias("download_match_name"),
                pl.col("benchmark_name_clean").str.split(" ").list.first().alias("format_family"),
            ]
        )
        download_df = download_df.with_columns(
            [
                pl.col("benchmark_name_clean").str.replace("dandi api", "pynwb").alias("download_match_name"),
                pl.col("benchmark_name_clean").str.split(" ").list.first().alias("format_family"),
            ]
        )

        return (
            local_read_and_slice_df.join(
                download_df.group_by(["modality", "download_match_name", "format_family"]).agg(
                    pl.col("value").mean().alias("avg_download_time")
                ),
                on=["modality", "download_match_name", "format_family"],
                how="left",
            )
            .filter(pl.col("avg_download_time").is_not_null())
            .with_columns(
                [
                    (pl.col("avg_download_time") + pl.col("total_time")).alias("total_time"),
                    pl.col("format_family").alias("benchmark_name_clean"),
                ]
            )
        )
