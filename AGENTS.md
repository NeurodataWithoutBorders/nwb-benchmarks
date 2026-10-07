# Instructions for coding agents

## Version bumps

The repository carries three version numbers. Decide for every change which of them it affects.

- **Package version** (`version` in `pyproject.toml`). Bump it in any pull request that changes code under
  `src/nwb_benchmarks/`, including the benchmark parameters. Use a patch bump (for example `0.1.1` to `0.1.2`) for
  fixes and internal changes that leave what the benchmarks measure alone, and a minor bump for new benchmarks, new
  commands or changed command-line behavior. Changes that only touch documentation or the CI workflows do not bump it.
  The version is part of the `conda list` output recorded with every results file, so a bump also starts a new
  environment record.
- **`DATABASE_VERSION`** (`src/nwb_benchmarks/globals.py`). Bump it only when the structure or meaning of the reduced
  results JSON written by `reduce_results` changes: its keys, how parameter sets are serialized, or what the values
  mean. The readers in `nwb_benchmarks.database` gate on it.
- **`MACHINE_FILE_VERSION`** (`src/nwb_benchmarks/globals.py`). Bump it only when the content of the machine file
  written by `collect_machine_info` changes.

Changes to how the suite is run or imported (which benchmarks CI selects, environment caching, how parameters are
resolved) do not change either file format and need only the package version bump.
