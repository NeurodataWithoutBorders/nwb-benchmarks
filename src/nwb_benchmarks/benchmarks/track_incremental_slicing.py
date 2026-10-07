"""Benchmarks for cumulative open + repeated slice access patterns.

These benchmarks explicitly measure the use case that is extrapolated in the download-vs-streaming plots:
open a file, read one slice, read the next slice, read the next slice, and so on. Each benchmark returns
``{"cumulative_time_in_seconds": [...]}``, a single list of cumulative timings in read order: the first entry is the
open time only and entry ``N`` includes opening the file and reading the first ``N`` slices/items.

The benchmarks are opt-in and are skipped unless RUN_INCREMENTAL_SLICING_BENCHMARKS is set in the environment.
"""

import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Tuple

from asv_runner.benchmarks.mark import SkipNotImplemented, skip_benchmark_if
from pynwb import NWBHDF5IO

from nwb_benchmarks import RUN_INCREMENTAL_SLICING_BENCHMARKS
from nwb_benchmarks.core import (
    BaseBenchmark,
    download_asset_if_not_exists,
    get_asset_path_from_url,
    get_object_by_name,
    read_hdf5_pynwb_fsspec_https_with_cache,
    read_hdf5_pynwb_lindi,
    read_hdf5_pynwb_remfile_with_cache,
    read_hdf5_pynwb_ros3,
    read_zarr_pynwb_https,
    read_zarr_pynwb_s3,
)
from nwb_benchmarks.setup import get_persistent_download_directory

from .params import (
    hdf5_no_redirect_download_incremental_slice_params,
    hdf5_redirected_read_incremental_slice_params,
    lindi_no_redirect_download_incremental_slice_params,
    zarr_direct_read_incremental_slice_params,
    zarr_no_redirect_download_incremental_slice_params,
)


class IncrementalSliceBenchmark(BaseBenchmark, ABC):
    """Base class for cumulative open + repeated slice benchmarks."""

    # Some full-axis incremental reads may be long-running.
    timeout = 60 * 60 * 12

    @abstractmethod
    def _open_file(self, params: dict[str, Any]) -> None:
        """Open the file and assign ``self.nwbfile`` plus any closeable resources."""
        pass

    def teardown(self, params: dict[str, Any]) -> None:
        if hasattr(self, "io"):
            self.io.close()
        if hasattr(self, "file"):
            self.file.close()
        if hasattr(self, "bytestream"):
            self.bytestream.close()
        if hasattr(self, "client"):
            self.client.close()
        if hasattr(self, "tmpdir"):
            shutil.rmtree(path=self.tmpdir.name, ignore_errors=True)
            self.tmpdir.cleanup()

    @staticmethod
    def _iter_time_axis_slices(data: Any, slice_template: Tuple[slice, ...]) -> Iterable[Tuple[slice, ...]]:
        """Yield adjacent slices along axis 0 using the first slice range as a template."""
        if not hasattr(data, "shape") or len(data.shape) == 0:
            raise ValueError("Expected array-like data with at least one dimension for time-axis slicing.")

        time_axis_length = data.shape[0]
        first_axis_template = slice_template[0]
        chunk_size = first_axis_template.stop - (first_axis_template.start or 0)
        if chunk_size <= 0:
            raise ValueError(f"Invalid time-axis slice template: {slice_template}")

        trailing_slices = slice_template[1:]
        for start in range(0, time_axis_length, chunk_size):
            stop = min(start + chunk_size, time_axis_length)
            yield (slice(start, stop), *trailing_slices)

    @staticmethod
    def _iter_icephys_timeseries(nwbfile: Any) -> Iterable[tuple[str, Any]]:
        """Yield all TimeSeries-like objects from acquisition and stimulus/presentation with readable data."""
        containers = [("acquisition", nwbfile.acquisition), ("stimulus", nwbfile.stimulus)]
        for container_name, container in containers:
            for object_name, neurodata_object in container.items():
                data = getattr(neurodata_object, "data", None)
                if data is None:
                    continue
                if not hasattr(data, "__getitem__"):
                    continue
                yield f"{container_name}/{object_name}", data

    def _track_cumulative_slice_times(self, params: dict[str, Any]) -> dict[str, list[float]]:
        """Track cumulative open + slice timings for the configured slice strategy."""
        start_time = time.perf_counter()

        self._open_file(params=params)
        cumulative_times = [time.perf_counter() - start_time]

        slice_strategy = params["slice_strategy"]
        if slice_strategy == "iterate_time_axis":
            object_name = params["object_name"]
            self.neurodata_object = get_object_by_name(nwbfile=self.nwbfile, object_name=object_name)
            self.data_to_slice = self.neurodata_object.data

            for slice_range in self._iter_time_axis_slices(
                data=self.data_to_slice, slice_template=params["slice_template"]
            ):
                self._temp = self.data_to_slice[slice_range]
                cumulative_times.append(time.perf_counter() - start_time)
        elif slice_strategy == "iterate_icephys_timeseries":
            for _, data in self._iter_icephys_timeseries(nwbfile=self.nwbfile):
                self._temp = data[:]
                cumulative_times.append(time.perf_counter() - start_time)
        else:
            raise ValueError(f"Unsupported incremental slice strategy: {slice_strategy}")

        return {"cumulative_time_in_seconds": cumulative_times}

    @skip_benchmark_if(not RUN_INCREMENTAL_SLICING_BENCHMARKS)
    def track_cumulative_slice_times(self, params: dict[str, Any]) -> dict[str, list[float]]:
        """Track cumulative open + repeated slice timing."""
        return self._track_cumulative_slice_times(params=params)


class HDF5PyNWBRemfileWithCacheIncrementalSliceBenchmark(IncrementalSliceBenchmark):
    """Track cumulative slicing of remote HDF5 NWB files using PyNWB and remfile with cache."""

    params = hdf5_redirected_read_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io, self.file, self.bytestream, self.tmpdir = read_hdf5_pynwb_remfile_with_cache(
            https_url=params["https_url"]
        )


class HDF5PyNWBFsspecHttpsWithCacheIncrementalSliceBenchmark(IncrementalSliceBenchmark):
    """Track cumulative slicing of remote HDF5 NWB files using PyNWB and fsspec HTTPS with cache."""

    params = hdf5_redirected_read_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io, self.file, self.bytestream, self.tmpdir = read_hdf5_pynwb_fsspec_https_with_cache(
            https_url=params["https_url"]
        )


class HDF5PyNWBROS3IncrementalSliceBenchmark(IncrementalSliceBenchmark):
    """Track cumulative slicing of remote HDF5 NWB files using PyNWB and ROS3."""

    params = hdf5_redirected_read_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io, _ = read_hdf5_pynwb_ros3(https_url=params["https_url"])


class HDF5PyNWBLindiIncrementalSliceBenchmark(IncrementalSliceBenchmark):
    """Track cumulative slicing of HDF5 NWB files using PyNWB and a local LINDI reference file."""

    params = lindi_no_redirect_download_incremental_slice_params

    def setup(self, params: dict[str, Any]) -> None:
        # Downloading the small LINDI JSON is not part of the tracked open + slice timing.
        self.lindi_file = download_asset_if_not_exists(https_url=params["https_url"])

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io, self.client = read_hdf5_pynwb_lindi(rfs=self.lindi_file)


class ZarrPyNWBS3IncrementalSliceBenchmark(IncrementalSliceBenchmark):
    """Track cumulative slicing of remote Zarr NWB files using PyNWB with S3 and consolidated metadata."""

    params = zarr_direct_read_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io = read_zarr_pynwb_s3(https_url=params["https_url"], mode="r")


class LocalIncrementalSliceBenchmark(IncrementalSliceBenchmark, ABC):
    """Base class for local cumulative open + repeated slice benchmarks."""

    def setup(self, params: dict[str, Any]) -> None:
        self.download_dir = get_persistent_download_directory()
        self.file_name = get_asset_path_from_url(https_url=params["https_url"])
        self.file_path = self.download_dir / self.file_name
        if not self.file_path.exists():
            raise SkipNotImplemented(
                f"Expected file {self.file_path} to exist for local incremental slicing benchmark."
            )


class HDF5PyNWBLocalIncrementalSliceBenchmark(LocalIncrementalSliceBenchmark):
    """Track cumulative slicing of local HDF5 NWB files using PyNWB."""

    params = hdf5_no_redirect_download_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.io = NWBHDF5IO(str(self.file_path), mode="r")
        self.nwbfile = self.io.read()


class ZarrPyNWBLocalIncrementalSliceBenchmark(LocalIncrementalSliceBenchmark):
    """Track cumulative slicing of local Zarr NWB files using PyNWB with consolidated metadata."""

    params = zarr_no_redirect_download_incremental_slice_params

    def _open_file(self, params: dict[str, Any]) -> None:
        self.nwbfile, self.io = read_zarr_pynwb_https(https_url=self.file_path, mode="r")
