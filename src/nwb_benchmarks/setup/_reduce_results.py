"""Default ASV result file is very inefficient - this routine simplifies it for sharing."""

import collections
import datetime
import hashlib
import json
import math
import pathlib
import shutil
import subprocess
import sys
import warnings
from typing import Dict, List

from ..globals import DATABASE_VERSION, ENVIRONMENTS_DIR, MACHINES_DIR, RESULTS_DIR
from ..utils import get_dictionary_checksum


def _parse_environment_info(raw_environment_info: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """Turn the results of `conda list` printout to a JSON dictionary."""
    header_stripped = raw_environment_info[3:]
    newline_stripped = [line.rstrip("\n") for line in header_stripped]
    # Tried several regex but none quite did the trick in all cases
    spacing_stripped = [[x for x in line.split(" ") if x] for line in newline_stripped]

    keys = ["name", "version", "build", "channel"]
    parsed_environment = {
        sys.version: [{key: value for key, value in zip(keys, values)} for values in spacing_stripped]
    }

    return parsed_environment


def reduce_results(machine_id: str, raw_results_file_path: pathlib.Path, raw_environment_info_file_path: pathlib.Path):
    """Default ASV result file is very inefficient - this routine simplifies it for sharing."""
    with open(file=raw_results_file_path, mode="r") as io:
        raw_results_info = json.load(fp=io)
    with open(file=raw_environment_info_file_path, mode="r") as io:
        raw_environment_info = io.readlines()
    parsed_environment_info = _parse_environment_info(raw_environment_info=raw_environment_info)
    environment_id = get_dictionary_checksum(dictionary=parsed_environment_info)

    # Only warn, since failing here would discard the results of a long benchmark run
    recorded_package_names = {package.get("name") for package in parsed_environment_info[sys.version]}
    if "pynwb" not in recorded_package_names:
        message = (
            f"The recorded environment info at {raw_environment_info_file_path} does not list 'pynwb', so it likely "
            f"describes a different conda environment than the one running the benchmarks ({sys.prefix}). "
            f"The results will still be saved under environment ID {environment_id}."
        )
        warnings.warn(message=message)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    reduced_results = dict()
    for test_case, raw_results_list in raw_results_info["results"].items():

        # Only successful runs have a results field of length 12
        if len(raw_results_list) != 12:
            continue

        # This code assumes that test cases are only run with one parameter
        assert len(raw_results_list[1]) == 1, "Unexpected length of serialized parameters list!"
        serialized_params = raw_results_list[1][0]

        aggregate_results = raw_results_list[0]
        samples_per_parameter_set = raw_results_list[11]
        if not len(serialized_params) == len(aggregate_results) == len(samples_per_parameter_set):
            message = (
                f"In intermediate results for test case {test_case}: \n"
                f"\tLength mismatch between parameters ({len(serialized_params)}), results "
                f"({len(aggregate_results)}) and result samples ({len(samples_per_parameter_set)})!\n\n"
                "Please raise an issue and share your intermediate results file."
            )
            warnings.warn(message=message)
            continue

        # ASV records every parameter set of a benchmark, including those a `--bench` pattern did not select.
        # Those were never run and have a NaN result. Samples of parameter sets that failed are written as `null`
        # and read back into Python as `None`. Leave both out, keeping the parameter sets that succeeded.
        successful_results = {
            params: samples
            for params, result, samples in zip(serialized_params, aggregate_results, samples_per_parameter_set)
            if not (isinstance(result, float) and math.isnan(result)) and samples is not None
        }
        if len(successful_results) > 0:
            reduced_results.update({test_case: successful_results})

    if len(reduced_results) == 0:
        raise ValueError(
            "The results parser failed to find any successful results! "
            "Please raise an issue and share your intermediate results file."
        )

    reduced_results_info = dict(
        database_version=DATABASE_VERSION,
        timestamp=timestamp,
        commit_hash=raw_results_info["commit_hash"],
        environment_id=environment_id,
        machine_id=machine_id,
        results=reduced_results,
    )

    parsed_results_file = (
        RESULTS_DIR / f"timestamp-{timestamp}_environment-{environment_id}_machine-{machine_id}_results.json"
    )
    with open(file=parsed_results_file, mode="w") as io:
        json.dump(obj=reduced_results_info, fp=io, indent=1)  # At least one level of indent makes it easier to read
    print(f"\nResults written to:        {parsed_results_file}")

    # Save parsed environment info within machine subdirectory of .asv
    parsed_environment_file_path = ENVIRONMENTS_DIR / f"environment-{environment_id}.json"
    if not parsed_environment_file_path.exists():
        with open(file=parsed_environment_file_path, mode="w") as io:
            json.dump(obj=parsed_environment_info, fp=io, indent=1)
    print(f"\nEnvironment info written to:        {parsed_environment_file_path}\n")

    # Network tests require admin permissions, which can alter write permissions of any files created
    machine_file_path = MACHINES_DIR / f"machine-{machine_id}.json"
    if sys.platform in ["darwin", "linux"]:
        subprocess.run(["chmod", "-R", "+rw", parsed_results_file.absolute()])
        subprocess.run(["chmod", "-R", "+rw", machine_file_path.absolute()])
        subprocess.run(["chmod", "-R", "+rw", parsed_environment_file_path.absolute()])

    raw_results_file_path.unlink()
