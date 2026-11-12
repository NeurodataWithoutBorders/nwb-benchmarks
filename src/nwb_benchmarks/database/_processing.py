import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

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

# The LBL Mac (official benchmark machine) received a new machine ID when the benchmark environment moved to
# Python 3.13, because ASV's machine name and platform string changed. The hardware is identical.
# It received a third machine ID for the 2026-11-03 incremental slicing run because psutil's total_swap_memory changed
# from 0 to 1 GiB. macOS allocates swap dynamically, so this value is not a stable hardware property. All other
# machine info, including CPU, RAM, and OS version, is identical.
LBL_MAC_MACHINE_IDS = [
    "87fee773e425b4b1d3978fbf762d57effb0e8df8",
    "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
    "16b244cd5a970ac0d7fefcb46c6ab0476075e5b5",
]

ENVIRONMENT_TIMEPOINTS = {
    "2024-06-30": "9e225115ea6c99b60d419454a9457bb5db93c7b7",  # all timepoints based on lbl mac
    "2025-06-30": "15d059d5b6b9047f9bbeb4ac77bb4461411904c7",
    "2025-09-01": "052cb4d925793bbbc270d9384a60bc24023025b7",  # note - this environment was created after 2025-09-01 but exact date unknown
    "2026-10-07": "42bfe7119727f6ab276361065e27b6e5fa5bbdc9",  # Python 3.13 environment, first run on 2026-10-07
}

# Environment IDs that describe the same installed packages as a canonical environment in ENVIRONMENT_TIMEPOINTS.
# Results recorded under an alias ID are relabeled with the canonical ID during preprocessing.
EQUIVALENT_ENVIRONMENT_IDS = {
    # The environment file gained a `runtime` section in database version 5.0.0 (nwb_benchmarks #212), which changed
    # the environment ID. Its conda package list is identical to 42bfe711, and the runtime versions match it.
    # See https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results/pull/14
    "e833ef393e1bef9cf9915915b1604a87c7b004dc": "42bfe7119727f6ab276361065e27b6e5fa5bbdc9",
}

# Individual benchmark samples flagged for removal during review of the raw results.
# A sample is one benchmark test case within one results file, identified by the machine ID and timestamp from the
# results filename plus the benchmark and parameter case names. All variables recorded for the sample are dropped,
# while the remaining benchmarks of the same run are kept. The parquet `uuid` is per row, so it cannot identify a sample.
EXCLUDED_SAMPLES = [
    # Transient network stall. total_transfer_time_in_seconds was 138.0 s (network_total_time_in_seconds 138.2 s),
    # whereas the other five runs of this case in the same environment took 7.8-10.2 s. The transferred bytes and
    # packet counts match the other runs, so the slowdown reflects the network rather than the access method.
    # Keeping it inflated the mean to 30.5 +/- 52.7 s.
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-18-13-02-38",
        "benchmark_name": (
            "network_tracking_remote_slicing."
            "HDF5PyNWBFsspecHttpsPreloadedNoCacheContinuousSliceBenchmark.track_network_during_slice"
        ),
        "parameter_case_name": "OphysTestCase4",
    },
    # Failed packet capture. All packet, byte, and transfer-time metrics are 0 and mean_time_per_web_packet is NaN,
    # which is impossible for an uncached remote HTTPS read. The 2026-11-01 repeat with the same commit, environment,
    # and machine recorded 11,108,017 transferred bytes, consistent with the 10.3-11.2 MB of earlier runs.
    # See https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results/pull/11#discussion_r4448487419
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-30-23-20-18",
        "benchmark_name": (
            "network_tracking_remote_file_reading."
            "HDF5H5pyFileReadBenchmark.track_network_read_hdf5_h5py_fsspec_https_no_cache"
        ),
        "parameter_case_name": "EcephysTestCase",
    },
    # The following remote file-open timing samples are isolated network stalls. Each is at least 5x the median of
    # its benchmark and test case. The runs they belong to are otherwise normal (the median benchmark of each run is
    # within 10% of its usual time), so only the affected sample is dropped. A smaller slowdown (about 3x) is kept as
    # plausible network variance.
    # Icephys file open took 76.2 s, whereas the other five runs took 3.2-4.5 s.
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-16-17-01-16",
        "benchmark_name": ("time_remote_file_reading.HDF5H5pyFileReadBenchmark.time_read_hdf5_h5py_fsspec_s3_no_cache"),
        "parameter_case_name": "IcephysTestCase",
    },
    # Ophys file open took 22.3 s, whereas the other five runs took 2.9-4.2 s.
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-13-14-34-49",
        "benchmark_name": ("time_remote_file_reading.HDF5H5pyFileReadBenchmark.time_read_hdf5_h5py_fsspec_s3_no_cache"),
        "parameter_case_name": "OphysTestCase",
    },
    # Ophys file open took 278.6 s, whereas the other five runs took 45.1-57.1 s.
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-16-17-01-16",
        "benchmark_name": (
            "time_remote_file_reading.HDF5PyNWBFileReadBenchmark.time_read_hdf5_pynwb_fsspec_https_no_cache"
        ),
        "parameter_case_name": "OphysTestCase",
    },
    # Ophys file open took 97.6 s, whereas the other five runs took 6.3-7.3 s.
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-16-17-01-16",
        "benchmark_name": (
            "time_remote_file_reading.HDF5PyNWBFileReadBenchmark.time_read_hdf5_pynwb_fsspec_https_with_cache"
        ),
        "parameter_case_name": "OphysTestCase",
    },
    # Ophys file open took 6.77 s, whereas the other five runs took 0.83-2.89 s (median 0.93 s).
    {
        "machine_id": "a853f2f47d9930a78fdcf0766673deebc3fcd14f",
        "timestamp": "2026-10-29-18-20-35",
        "benchmark_name": (
            "time_remote_file_reading.HDF5PyNWBRos3PreloadedFileReadBenchmark.time_read_hdf5_pynwb_ros3_preloaded_with_cache"
        ),
        "parameter_case_name": "OphysTestCase",
    },
]


class BenchmarkDatabase:
    """Handles database preprocessing and loading for NWB benchmarks."""

    def __init__(
        self,
        results_directory: Optional[Path] = None,
        db_directory: Optional[Path] = None,
        machine_id: str = None,
        machine_ids: Optional[List[str]] = None,
        exclude_older: str = None,
        environment_id: str = None,
        environment_ids: Optional[List[str]] = None,
    ):
        """Initialize database handler with directories and machine ID.

        Args:
            results_directory: Directory containing benchmark results
            db_directory: Directory for database storage
            machine_id: Machine ID for filtering results
            machine_ids: Machine IDs for filtering results, for a machine whose ID changed over time
        """
        self.machine_id = machine_id
        self.machine_ids = machine_ids
        self.packages_of_interest = PACKAGES_OF_INTEREST
        self.environment_timepoints = ENVIRONMENT_TIMEPOINTS
        self.exclude_older = exclude_older
        self.environment_id = environment_id
        self.environment_ids = environment_ids

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
            .replace("IncrementalSliceBenchmark", "")
        )
        return self.split_camel_case(short_name).lower()

    @staticmethod
    def _excluded_sample_exprs() -> List[pl.Expr]:
        """Build one expression per entry in EXCLUDED_SAMPLES that is true for rows belonging to that sample."""
        sample_exprs = [
            pl.all_horizontal(
                pl.col("machine_id") == sample["machine_id"],
                pl.col("timestamp") == pl.lit(sample["timestamp"]).str.to_datetime("%Y-%m-%d-%H-%M-%S"),
                pl.col("benchmark_name") == sample["benchmark_name"],
                pl.col("parameter_case_name") == sample["parameter_case_name"],
            )
            for sample in EXCLUDED_SAMPLES
        ]
        return sample_exprs

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
            .filter(pl.col("machine_id").is_in(self.machine_ids) if self.machine_ids is not None else pl.lit(True))
            .with_columns(pl.col("environment_id").replace(EQUIVALENT_ENVIRONMENT_IDS))
            # Filter for timestamp early to reduce data volume
            .filter(
                pl.col("timestamp") >= pl.lit(self.exclude_older).str.to_datetime()
                if self.exclude_older is not None
                else pl.lit(True)
            )
            .filter(
                pl.col("environment_id") == self.environment_id if self.environment_id is not None else pl.lit(True)
            )
            .filter(
                pl.col("environment_id").is_in(self.environment_ids)
                if self.environment_ids is not None
                else pl.lit(True)
            )
            # Drop samples flagged as invalid during review of the raw results
            .filter(~pl.any_horizontal(pl.lit(False), *self._excluded_sample_exprs()))
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
                    .str.extract(
                        r"(IncrementalSliceBenchmark|ContinuousSliceBenchmark|FileReadBenchmark|DownloadBenchmark)"
                    )
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
                .replace_strict({v: k for k, v in ENVIRONMENT_TIMEPOINTS.items()}, default=None)
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

    def with_environment_id(self, environment_id: Optional[str]) -> "BenchmarkDatabase":
        """Return a database view filtered to a single environment ID."""
        return BenchmarkDatabase(
            results_directory=self.results_directory,
            db_directory=self.db_directory,
            machine_id=self.machine_id,
            machine_ids=self.machine_ids,
            exclude_older=self.exclude_older,
            environment_id=environment_id,
        )

    def with_environment_ids(self, environment_ids: Optional[List[str]]) -> "BenchmarkDatabase":
        """Return a database view filtered to a set of environment IDs."""
        return BenchmarkDatabase(
            results_directory=self.results_directory,
            db_directory=self.db_directory,
            machine_id=self.machine_id,
            machine_ids=self.machine_ids,
            exclude_older=self.exclude_older,
            environment_ids=environment_ids,
        )

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

    def get_incremental_slicing_results(self) -> pl.LazyFrame:
        """Get cumulative open + incremental slice times, with one row per run and slice index."""
        return (
            self.filter_tests("track_incremental_slicing")
            .filter(pl.col("variable") == "cumulative_time_in_seconds")
            .with_columns(
                [
                    pl.when(pl.col("benchmark_name").str.contains("LocalIncrementalSliceBenchmark"))
                    .then(pl.lit("local"))
                    .otherwise(pl.lit("remote"))
                    .alias("access_mode"),
                    pl.col("benchmark_name_clean").str.replace("hdf5 pynwb lindi", "lindi pynwb"),
                    pl.col("value_index").alias("slice_index"),
                ]
            )
            .with_columns(
                pl.when(pl.col("benchmark_name_clean").str.starts_with("zarr"))
                .then(pl.lit("zarr"))
                .otherwise(pl.lit("hdf5"))
                .alias("format_family")
            )
        )

    def combine_incremental_slicing_and_download_times(self) -> pl.LazyFrame:
        """Combine incremental slicing times with the download times needed before the first read.

        Local benchmarks read an already-downloaded file, so the mean download time of the full file is added. LINDI
        downloads its JSON reference file outside the timed region, so the mean LINDI JSON download time is added.
        Other streaming methods need no download, and their first entry already includes the file open time.
        """
        download_df = (
            self.filter_tests("time_download")
            .with_columns(pl.col("benchmark_name_clean").str.replace("dandi api", "pynwb").alias("download_match_name"))
            .group_by(["modality", "download_match_name"])
            .agg(pl.col("value").mean().alias("avg_download_time"))
        )
        incremental_df = self.get_incremental_slicing_results().with_columns(
            pl.when(pl.col("access_mode") == "local")
            .then(pl.col("benchmark_name_clean"))
            .when(pl.col("benchmark_name_clean") == "lindi pynwb")
            .then(pl.lit("lindi pynwb"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("download_match_name")
        )

        return (
            incremental_df.join(download_df, on=["modality", "download_match_name"], how="left")
            # Local results without a matching download cannot be compared fairly with streaming.
            .filter(pl.col("download_match_name").is_null() | pl.col("avg_download_time").is_not_null())
            .with_columns(pl.col("avg_download_time").fill_null(0.0))
            .with_columns((pl.col("value") + pl.col("avg_download_time")).alias("total_time"))
        )
