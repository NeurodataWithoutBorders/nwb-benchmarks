"""Outermost exposed imports; including global environment variables."""

import os
import shutil
import warnings

from .command_line_interface import main

# Determine the path for running tshark
TSHARK_PATH = os.environ.get("TSHARK_PATH", None)
NETWORK_INTERFACE = os.environ.get("NWB_BENCHMARKS_NETWORK_INTERFACE", None)
RUN_DOWNLOAD_BENCHMARKS = os.environ.get("RUN_DOWNLOAD_BENCHMARKS", None)
RUN_INCREMENTAL_SLICING_BENCHMARKS_RAW = os.environ.get("RUN_INCREMENTAL_SLICING_BENCHMARKS", None)


def _parse_incremental_slicing_benchmarks_config(value: str | None) -> tuple[bool, set[str] | None]:
    """Parse RUN_INCREMENTAL_SLICING_BENCHMARKS into enabled state and selected modalities."""
    if value is None:
        return False, None

    normalized_value = value.strip().lower()
    if normalized_value in {"", "false", "0", "no", "off"}:
        return False, None

    if normalized_value in {"true", "1", "yes", "on", "all"}:
        return True, None

    selected_modalities = {modality.strip().lower() for modality in normalized_value.split(",") if modality.strip()}
    valid_modalities = {"ecephys", "ophys", "icephys"}
    invalid_modalities = selected_modalities - valid_modalities
    if invalid_modalities:
        raise ValueError(
            f"Invalid RUN_INCREMENTAL_SLICING_BENCHMARKS value {value!r}. "
            "Expected true, all, ecephys, ophys, icephys, or a comma-separated list of modalities."
        )

    return True, selected_modalities


(
    RUN_INCREMENTAL_SLICING_BENCHMARKS,
    RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES,
) = _parse_incremental_slicing_benchmarks_config(RUN_INCREMENTAL_SLICING_BENCHMARKS_RAW)

if TSHARK_PATH is None:
    TSHARK_PATH = shutil.which("tshark")

if TSHARK_PATH is None:
    warnings.warn("tshark not found. Set TSHARK_PATH in the environment or install tshark on the default path.")
else:
    if NETWORK_INTERFACE is None:
        warnings.warn("NWB_BENCHMARKS_NETWORK_INTERFACE not found. Set it in the environment.")
    print(f"Using tshark at: {TSHARK_PATH} on {NETWORK_INTERFACE}")

if RUN_DOWNLOAD_BENCHMARKS:
    warnings.warn(
        "RUN_DOWNLOAD_BENCHMARKS is set. Benchmarks that download the entire test file will be run, which may take a long time."
    )

if RUN_INCREMENTAL_SLICING_BENCHMARKS:
    if RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES is None:
        incremental_slicing_benchmark_description = "all incremental slicing benchmarks"
    else:
        incremental_slicing_benchmark_description = (
            "incremental slicing benchmarks for modalities "
            f"{', '.join(sorted(RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES))}"
        )
    warnings.warn(
        "RUN_INCREMENTAL_SLICING_BENCHMARKS is set. "
        f"{incremental_slicing_benchmark_description} will be run, which may take a long time."
    )

__all__ = [
    "main",
    "TSHARK_PATH",
    "NETWORK_INTERFACE",
    "RUN_DOWNLOAD_BENCHMARKS",
    "RUN_INCREMENTAL_SLICING_BENCHMARKS",
    "RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES",
]
