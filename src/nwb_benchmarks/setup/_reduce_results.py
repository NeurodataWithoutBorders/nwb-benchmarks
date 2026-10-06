"""Default ASV result file is very inefficient - this routine simplifies it for sharing."""

import collections
import datetime
import hashlib
import itertools
import json
import pathlib
import shutil
import subprocess
import sys
import warnings
from typing import Dict, List

from ..globals import DATABASE_VERSION, ENVIRONMENTS_DIR, MACHINES_DIR, RESULTS_DIR
from ..utils import get_dictionary_checksum


def _serialize_parameter_cases(serialized_params: list) -> list[str]:
    """Return one serialized parameter-case key per ASV result.

    ASV stores parameters as a list of parameter axes. Preserve the historical
    single-axis keys used by nwb_benchmarks results, while supporting ASV's
    general zero-axis and multi-axis parameter layouts.
    """

    if len(serialized_params) == 0:
        return ["()"]
    if len(serialized_params) == 1:
        return serialized_params[0]

    return [str(parameter_case) for parameter_case in itertools.product(*serialized_params)]


def _extract_successful_results(test_case: str, raw_results_list: list, result_columns: list[str] | None) -> dict:
    """Extract successful ASV benchmark results keyed by serialized parameter case.

    ASV has used multiple result serialization layouts. Older result files store a
    fixed-length list where parameters are at index 1 and samples are at index 11.
    Newer result files include a top-level ``result_columns`` list and each result
    row follows that column order. This helper normalizes both layouts to the
    reduced results format used by nwb_benchmarks.
    """

    # Older ASV layout used by the original reducer implementation.
    if len(raw_results_list) == 12:
        serialized_params = raw_results_list[1]
        raw_results = raw_results_list[11]
    elif result_columns is not None:
        column_index = {column_name: index for index, column_name in enumerate(result_columns)}
        if "result" not in column_index or "params" not in column_index:
            return {}

        serialized_params = raw_results_list[column_index["params"]]
        raw_results = raw_results_list[column_index["result"]]
        if "samples" in column_index:
            samples_index = column_index["samples"]
            if samples_index < len(raw_results_list) and raw_results_list[samples_index] is not None:
                raw_results = raw_results_list[samples_index]
    else:
        return {}

    # Skipped results in JSON are written as `null` and read back into Python as `None`.
    if raw_results is None:
        return {}
    if len(serialized_params) > 0 and not isinstance(raw_results, list):
        raw_results = [raw_results]
    serialized_params = _serialize_parameter_cases(serialized_params=serialized_params)

    if len(serialized_params) != len(raw_results):
        message = (
            f"In intermediate results for test case {test_case}: \n"
            f"\tLength mismatch between parameters ({len(serialized_params)}) and "
            f"result samples ({len(raw_results)})!\n\n"
            "Please raise an issue and share your intermediate results file."
        )
        warnings.warn(message=message)
        return {}

    return {params: raw_result for params, raw_result in zip(serialized_params, raw_results) if raw_result is not None}


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
    result_columns = raw_results_info.get("result_columns")
    for test_case, raw_results_list in raw_results_info["results"].items():
        extracted_results = _extract_successful_results(
            test_case=test_case,
            raw_results_list=raw_results_list,
            result_columns=result_columns,
        )
        if extracted_results:
            reduced_results.update({test_case: extracted_results})

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
