"""Pick one benchmark of the suite at random, for runs that are too short to run the whole suite."""

import pathlib
import random
import re
from typing import Iterable, Optional

from asv_runner.discovery import disc_benchmarks, update_sys_path

BENCHMARK_DIRECTORY = pathlib.Path(__file__).parent.parent / "benchmarks"


def discover_benchmarks(benchmark_directory: pathlib.Path = BENCHMARK_DIRECTORY) -> list:
    """
    Discover the benchmarks of the suite the way `asv run` does.

    This imports the benchmark modules, so the environment variables that configure the suite (such as
    `RUN_DOWNLOAD_BENCHMARKS`) apply, and the benchmarks they mark as skipped are left out.
    """
    update_sys_path(str(benchmark_directory))
    return list(disc_benchmarks(str(benchmark_directory)))


def select_random_benchmark(benchmarks: Iterable, rng: Optional[random.Random] = None) -> str:
    """
    Return the name (`module.Class.method`) of one benchmark chosen uniformly at random.

    A parameterized benchmark with no parameter set left (for example after a modality filter) is never chosen,
    because running it produces nothing.
    """
    candidates = sorted(benchmark.name for benchmark in benchmarks if not benchmark.params or all(benchmark.params))
    if not candidates:
        raise RuntimeError("No benchmark is available to choose from.")
    return (rng or random).choice(candidates)


def benchmark_name_pattern(name: str) -> str:
    """A `--bench` pattern that selects exactly the named benchmark; ASV matches it against `module.Class.method(parameters)`."""
    return f"^{re.escape(name)}(?:\\(|$)"
