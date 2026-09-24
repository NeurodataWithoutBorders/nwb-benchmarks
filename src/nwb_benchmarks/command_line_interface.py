"""Simple wrapper around `asv run` for convenience."""

import argparse
import datetime
import locale
import pathlib
import shutil
import subprocess
import sys
import warnings

from .core import clean_results, upload_results
from .globals import LOGS_DIR
from .setup import (
    clean_cache,
    generate_machine_file,
    reduce_results,
    set_cache_directory,
)

# Machine ID for LBL Mac (official benchmark machine)
LBL_MAC_MACHINE_ID = "87fee773e425b4b1d3978fbf762d57effb0e8df8"


def clone_results_repo(repo_path: pathlib.Path) -> pathlib.Path:
    """
    Clone the nwb-benchmarks-results repository if needed.

    Returns:
        Path to the results repository directory.
    """

    command = "git clone https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results"
    subprocess.run(
        args=command,
        cwd=repo_path.parent,
        capture_output=True,
        shell=True,
    )


def generate_figures_command(args: argparse.Namespace) -> None:
    """
    Generate manuscript figures from benchmark results.

    Args:
        args: Parsed command-line arguments from argparse
    """
    from nwb_benchmarks.database import BenchmarkDatabase, BenchmarkVisualizer

    # Determine results directory
    if args.results_dir:
        results_dir = pathlib.Path(args.results_dir)
        if not results_dir.exists():
            raise FileNotFoundError(f"Results directory not found: {results_dir}")
    else:
        # Use default cache location
        cache_directory = pathlib.Path.home() / ".cache" / "nwb-benchmarks"
        cache_directory.mkdir(parents=True, exist_ok=True)
        repo_path = cache_directory / "nwb-benchmarks-results"
        if not repo_path.exists():
            warnings.warn(f"No results repository found at {repo_path}, attempting to clone from GitHub...")
            results_dir = clone_results_repo(repo_path)
        else:
            results_dir = repo_path

    # Set default output directory if not specified
    output_dir = pathlib.Path(args.output_dir) if args.output_dir else pathlib.Path.cwd() / "figures"
    print(f"\nGenerating figures in {output_dir}...")

    # Initialize database handler and create parquet file
    # TODO _ make LBL mac machine ID configurable
    db = BenchmarkDatabase(
        results_directory=results_dir, machine_id=LBL_MAC_MACHINE_ID, exclude_older=args.exclude_older or "2025-11-01"
    )
    db.create_database()

    # Initialize visualizer and generate plots
    summary_tables_dir = pathlib.Path(args.summary_tables_dir) if args.summary_tables_dir else None
    visualizer = BenchmarkVisualizer(output_directory=output_dir, summary_tables_directory=summary_tables_dir)
    visualizer.plot_all(db)


def main() -> None:
    """Simple wrapper around `asv run` for convenience."""
    # TODO: swap to click
    if len(sys.argv) <= 1:
        print("No command provided. Please specify a command (e.g. 'run').")
        return

    command = sys.argv[1]
    flags_list = sys.argv[2:]

    debug_mode = "--debug" in flags_list
    bench_mode = "--bench" in flags_list
    if bench_mode:
        specific_benchmark_pattern = flags_list[flags_list.index("--bench") + 1]

    if command == "run":
        try:
            # Create .asv directory at GitHub repository root
            asv_root = pathlib.Path(__file__).parent.parent.parent / ".asv"
            asv_root.mkdir(exist_ok=True)
            intermediate_results_folder = asv_root / "intermediate_results"

            if intermediate_results_folder.exists():
                try:
                    shutil.rmtree(path=intermediate_results_folder)
                except:
                    message = (
                        f"Unable to automatically remove {intermediate_results_folder} - please manually delete by running "
                        "`nwb_benchmarks clean` and try again."
                    )
                    raise FileExistsError(message)

            aws_machine_process = subprocess.Popen(["asv", "machine", "--yes"], stdout=subprocess.PIPE)
            aws_machine_process.wait()
            machine_id = generate_machine_file()

            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("ascii").strip()

            # Save latest environment list from conda (most thorough)
            # subprocess tends to have issues inheriting `conda` entrypoint
            shell = sys.platform == "win32"  # Use shell on Windows
            raw_environment_info_file_path = asv_root / ".raw_environment_info.txt"
            with open(file=raw_environment_info_file_path, mode="w") as stdout:
                environment_info_process = subprocess.Popen(args=["conda", "list"], stdout=stdout, shell=shell)
                environment_info_process.wait()

            if not raw_environment_info_file_path.exists():
                raise FileNotFoundError(f"Unable to create environment file at {raw_environment_info_file_path}!")

            # Create log file path to capture all output from the ASV run
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            log_file_path = LOGS_DIR / f"timestamp-{timestamp}_commit-{commit_hash}.txt"

            # Deploy ASV
            cmd = [
                "asv",
                "run",
                "--python=same",
                "--record-samples",
                "--set-commit-hash",
                commit_hash,
            ]
            if debug_mode:
                cmd.extend(["--verbose", "--show-stderr"])
            if bench_mode:
                cmd.extend(["--bench", specific_benchmark_pattern])

            # Run ASV with all the desired flags and reroute the output to our main console
            asv_process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            encoding = locale.getpreferredencoding()  # This is how ASV chooses to encode the output

            if debug_mode:
                # Print output to both stdout and log file
                with open(log_file_path, "w", encoding=encoding) as log_file:
                    for line in iter(asv_process.stdout.readline, b""):
                        decoded_line = line.decode(encoding).strip("\n")
                        print(decoded_line, flush=True)  # Print to stdout
                        log_file.write(decoded_line + "\n")  # Write to log file
                        log_file.flush()  # Ensure immediate writing

                    print(f"ASV output has been saved to: {log_file_path}\n")
            else:
                # Print output only to stdout
                for line in iter(asv_process.stdout.readline, b""):
                    decoded_line = line.decode(encoding).strip("\n")
                    print(decoded_line, flush=True)  # Print to stdout

            asv_process.stdout.close()
            asv_process.wait()

            # Consider the raw ASV output as 'intermediate' and perform additional parsing
            globbed_json_file_paths = [
                path
                for path in intermediate_results_folder.rglob("*.json")
                if not any(path.stem == skip_stems for skip_stems in ["benchmarks", "machine"])
            ]
            assert (
                len(globbed_json_file_paths) != 0
            ), f"No intermediate result was found in {intermediate_results_folder}, likely as a result of a failure in the benchmarks."
            assert (
                len(globbed_json_file_paths) == 1
            ), f"A single intermediate result was not found in {intermediate_results_folder}. Please raise an issue."
            raw_results_file_path = globbed_json_file_paths[0]

            reduce_results(
                machine_id=machine_id,
                raw_results_file_path=raw_results_file_path,
                raw_environment_info_file_path=raw_environment_info_file_path,
            )

            if not debug_mode:
                upload_results()
        finally:
            clean_cache()
    elif command == "upload":
        upload_results()
    elif command == "clean":
        clean_results()
        clean_cache()
    elif command == "config_set_cache":
        cache_directory = pathlib.Path(sys.argv[2])
        set_cache_directory(cache_directory=cache_directory)
    elif command == "generate_figures":
        parser = argparse.ArgumentParser(
            prog="nwb_benchmarks generate_figures", description="Generate manuscript figures from benchmark results"
        )
        parser.add_argument("--output-dir", type=str, help="Directory for output figures (default: ./figures)")
        parser.add_argument(
            "--results-dir",
            type=str,
            help="Path to benchmark results directory (default: ~/.cache/nwb-benchmarks/nwb-benchmarks-results or auto-clone from GitHub)",
        )
        parser.add_argument(
            "--exclude-older",
            type=str,
            help="Exclude results older than this date (format: YYYY-MM-DD, default: '2025-11-01')",
        )
        parser.add_argument(
            "--summary-tables-dir",
            type=str,
            help="Optional directory for CSV summary tables aligned with the generated figures. If omitted, no summary tables are written.",
        )

        args = parser.parse_args(sys.argv[2:])
        generate_figures_command(args)
    else:
        print(f"{command} is an invalid command.")
        print("\nAvailable commands:")
        print("  run                - Run benchmarks")
        print("  upload             - Upload results")
        print("  clean              - Clean results and cache")
        print("  config_set_cache   - Set cache directory")
        print("  generate_figures   - Generate manuscript figures")


if __name__ == "__main__":
    main()
