"""Add information to the ASV machine parameters."""

import copy
import datetime
import hashlib
import json
import os
import pathlib
import platform
import sys
from typing import Any, Dict

import friendlywords
import psutil
from numba import cuda

from ..globals import MACHINE_FILE_VERSION, MACHINES_DIR
from ..setup import read_config
from ..utils import get_dictionary_checksum


def collect_machine_info() -> Dict[str, Dict[str, Any]]:
    """Collect attributes for uniquely identifying a system and providing metadata associated with performance."""
    machine_info = dict()

    machine_info["name"] = generate_machine_name()
    machine_info["version"] = MACHINE_FILE_VERSION

    # Hardware info from various Python libraries
    machine_info["os"] = dict(cpu_count=os.cpu_count())
    machine_info["sys"] = dict(platform=sys.platform)
    machine_info["platform"] = dict(
        architecture=list(platform.architecture()),  # Must be cast as a list for later assertions against JSON
        machine=platform.machine(),
        platform=platform.platform(),
        processor=platform.processor(),
        system=platform.system(),
    )
    machine_info["psutil"] = dict(
        number_of_processes=psutil.cpu_count(logical=False),
        number_of_threads=psutil.cpu_count(logical=True),
        total_virtual_memory=psutil.virtual_memory().total,
        total_swap_memory=psutil.swap_memory().total,
        disk_partitions=[disk_partition._asdict() for disk_partition in psutil.disk_partitions()],
    )
    # TODO: psutil does have some socket stuff in .net_connections, is that useful at all?

    # GPU info - mostly taken from https://stackoverflow.com/a/62459332
    machine_info["cuda"] = dict()
    try:
        device = cuda.get_current_device()
        gpu_attributes = [
            name.replace("CU_DEVICE_ATTRIBUTE_", "")
            for name in dir(cuda.cudadrv.enums)
            if name.startswith("CU_DEVICE_ATTRIBUTE_")
        ]
        gpu_specifications = {gpu_attribute: getattr(device, gpu_attribute) for gpu_attribute in gpu_attributes}
        machine_info["cuda"] = dict(gpu_name=device.name.decode("utf-8"), gpu_specifications=gpu_specifications)
    except cuda.cudadrv.error.CudaSupportError:
        # No GPU detected by cuda; skipping section of custom machine info
        pass
    except Exception as exception:
        raise exception
    if len(machine_info["cuda"]) == 0:
        del machine_info["cuda"]

    # Config info
    config = read_config()

    ## Anonymize paths in config
    if config.get("cache_directory", None) is not None:
        config["cache_directory"] = str(pathlib.Path(config["cache_directory"]).parents[0])

    machine_info["config"] = config

    # ASV info
    default_asv_machine_file_path = pathlib.Path.home() / ".asv-machine.json"
    if default_asv_machine_file_path.exists():
        with open(file=default_asv_machine_file_path, mode="r") as file_stream:
            asv_machine_info = json.load(fp=file_stream)
        machine_info["asv"] = asv_machine_info

        # Some info in ASV may be considered 'private'
        if len(asv_machine_info.keys()) != 2:
            message = (
                f"\nThe ASV machine file at {default_asv_machine_file_path} should only contain two keys: "
                "'version' and the machine name. "
                f"Found {len(asv_machine_info.keys())} keys: {list(asv_machine_info.keys())}' "
                "Please raise an issue at https://github.com/NeurodataWithoutBorders/nwb_benchmarks/issues/new to report."
            )
            raise ValueError(message)

        asv_machine_key = next(key for key in asv_machine_info.keys() if key != "version")
        asv_machine_details = asv_machine_info[asv_machine_key]
        del asv_machine_details["machine"]
        machine_info["asv"] = asv_machine_details

    return machine_info


def get_machine_file_checksum(machine_info: dict) -> str:
    """Get the checksum of the machine info after removing the machine name."""
    stable_machine_info = copy.deepcopy(x=machine_info)
    stable_machine_info["name"] = ""
    checksum = get_dictionary_checksum(dictionary=stable_machine_info)

    return checksum


def generate_machine_file() -> str:
    """Generate a custom machine file and store in the NWB Benchmarks home directory."""
    machine_info = collect_machine_info()

    checksum = get_machine_file_checksum(machine_info=machine_info)

    machine_info_file_path = MACHINES_DIR / f"machine-{checksum}.json"
    if machine_info_file_path.exists():
        # The name is not part of the checksum, so a machine that was renamed (for example a self-hosted
        # runner that now reports its runner name) keeps its id; its file is rewritten only when the name changed.
        with open(file=machine_info_file_path, mode="r") as file_stream:
            existing_name = json.load(fp=file_stream).get("name")
        if existing_name == machine_info["name"]:
            print(f"\nMachine info exists at:        {machine_info_file_path}\n")
            return checksum
        print(f"\nMachine name changed from '{existing_name}' to '{machine_info['name']}'.")

    with open(file=machine_info_file_path, mode="w") as file_stream:
        json.dump(obj=machine_info, fp=file_stream, indent=1)
    print(f"\nMachine info written to:        {machine_info_file_path}\n")

    return checksum


def generate_machine_name() -> str:
    """
    Choose the name recorded in the machine file.

    Under GitHub Actions the name is the runner's name (`RUNNER_NAME`), which identifies a self-hosted runner such
    as `ackermann` across runs. Hosted runners get a unique name instead (`github-<timestamp>`), and so does any
    run where the variable is missing. Outside GitHub Actions the name is a random human-readable one.
    """
    if os.getenv("GITHUB_ACTIONS"):
        runner_name = os.getenv("RUNNER_NAME", "")
        if runner_name and not runner_name.startswith("GitHub Actions"):
            return runner_name
        timestamp = datetime.datetime.now().strftime(format="%Y%m%d%H%M%S")
        return f"github-{timestamp}"
    return generate_human_readable_machine_name()


def generate_human_readable_machine_name() -> str:
    """
    There are about 4 million possible combinations of predicate/objects in `friendlywords`.

    Natural collisions should be able to be disambiguated by the peripheral machine info.
    """
    name = "".join(word.capitalize() for word in friendlywords.generate(command="po", as_list=True))
    return name
