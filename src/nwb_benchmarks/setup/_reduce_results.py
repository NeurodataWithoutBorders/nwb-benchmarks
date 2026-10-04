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

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    reduced_results = dict()
    for test_case, raw_results_list in raw_results_info["results"].items():

        # Only successful runs have a results field of length 12
        if len(raw_results_list) != 12:
            continue

        # This code assumes that test cases are only run with one parameter
        assert len(raw_results_list[1]) == 1, "Unexpected length of serialized parameters list!"
        serialized_params = raw_results_list[1][0]

        # ASV records every parameter set of a benchmark, including those a `--bench` pattern did not select.
        # Those were never run and have a NaN result, so leave them out before pairing parameters with samples.
        selected = [
            (params, samples)
            for params, result, samples in zip(serialized_params, raw_results_list[0], raw_results_list[11])
            if not (isinstance(result, float) and math.isnan(result))
        ]
        if len(selected) == 0:
            continue
        selected_params = [params for params, _ in selected]

        # Samples of parameter sets that failed are written as `null` and read back into Python as `None`
        non_skipped_results = [samples for _, samples in selected if samples is not None]
        if len(selected_params) != len(non_skipped_results):
            message = (
                f"In intermediate results for test case {test_case}: \n"
                f"\tLength mismatch between parameters ({len(selected_params)}) and "
                f"result samples ({len(non_skipped_results)})!\n\n"
                "Please raise an issue and share your intermediate results file."
            )
            warnings.warn(message=message)
        else:
            reduced_results.update(
                {test_case: {params: raw_result for params, raw_result in zip(selected_params, non_skipped_results)}}
            )

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
