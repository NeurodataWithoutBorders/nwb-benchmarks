import ast
import dataclasses
import json
import pathlib
import re
import uuid
from datetime import datetime

import packaging.version
import typing_extensions


@dataclasses.dataclass
class Result:
    uuid: str
    version: str
    timestamp: datetime
    commit_hash: str
    environment_id: str
    machine_id: str
    benchmark_name: str
    parameter_case: dict
    value: float
    variable: str


@dataclasses.dataclass
class Results:
    results: list[Result]

    @staticmethod
    def normalize_time_and_network_results(benchmark_results) -> dict:
        """Convert benchmark results to a consistent dict format with list values."""

        def process_network_results(benchmark_results: dict) -> dict:
            """Add additional network metrics."""
            results = benchmark_results.copy()

            if "total_traffic_in_number_of_web_packets" not in results:
                return results

            if results["total_traffic_in_number_of_web_packets"] != 0:
                results["mean_time_per_web_packet"] = (
                    results["total_transfer_time_in_seconds"] / results["total_traffic_in_number_of_web_packets"]
                )
            else:
                results["mean_time_per_web_packet"] = float("nan")

            return results

        if isinstance(benchmark_results, dict):
            value_dict = process_network_results(benchmark_results)
        else:
            value_dict = dict(time=benchmark_results)

        # Ensure all values are lists
        return {k: v if isinstance(v, list) else [float(v)] for k, v in value_dict.items()}

    @staticmethod
    def parse_parameter_case(s):
        # replace any slice(...) with "slice(...)" for safe parsing
        modified_s = re.sub(r"slice\([^)]+\)", r'"\g<0>"', s)
        output = ast.literal_eval(modified_s)

        # if the parsed string is not a dict (older benchmarks results), convert it to one
        if not isinstance(output, dict):
            output = {"https_url": output[0].strip("'")}

        return output

    @classmethod
    def safe_load_from_json(cls, file_path: pathlib.Path) -> typing_extensions.Self | None:
        with file_path.open(mode="r") as file_stream:
            data = json.load(fp=file_stream)

        database_version = data.get("database_version", None)
        if database_version is None or packaging.version.Version(data["database_version"]) < packaging.version.Version(
            version="1.0.0"
        ):
            return None

        timestamp = data["timestamp"]
        commit_hash = data["commit_hash"]
        environment_id = data["environment_id"]
        machine_id = data["machine_id"]

        results = [
            Result(
                uuid=str(uuid.uuid4()),  # TODO: add this to each results file so it is persistent
                version=database_version,
                timestamp=datetime.strptime(timestamp, "%Y-%m-%d-%H-%M-%S"),
                commit_hash=commit_hash,
                environment_id=environment_id,
                machine_id=machine_id,
                benchmark_name=benchmark_name,
                parameter_case=cls.parse_parameter_case(parameter_case),
                value=value,
                variable=variable_name,
            )
            for benchmark_name, parameter_cases in data["results"].items()
            for parameter_case, benchmark_results in parameter_cases.items()
            for variable_name, values in cls.normalize_time_and_network_results(benchmark_results).items()
            for value in values
        ]

        return cls(results=results)

    def to_dataframe(self) -> "polars.DataFrame":
        import polars

        data = {
            "uuid": [result.uuid for result in self.results],
            "version": [result.version for result in self.results],
            "commit_hash": [result.commit_hash for result in self.results],
            "environment_id": [result.environment_id for result in self.results],
            "machine_id": [result.machine_id for result in self.results],
            "timestamp": [result.timestamp for result in self.results],
            "benchmark_name": [result.benchmark_name for result in self.results],
            "parameter_case_name": [result.parameter_case.get("name") for result in self.results],
            "parameter_case_https_url": [result.parameter_case.get("https_url") for result in self.results],
            "parameter_case_object_name": [result.parameter_case.get("object_name") for result in self.results],
            "parameter_case_slice_range": [result.parameter_case.get("slice_range") for result in self.results],
            "parameter_case_slice_template": [result.parameter_case.get("slice_template") for result in self.results],
            "parameter_case_slice_strategy": [result.parameter_case.get("slice_strategy") for result in self.results],
            "value": [result.value for result in self.results],
            "variable": [result.variable for result in self.results],
        }

        data_frame = polars.DataFrame(data=data)
        return data_frame


@dataclasses.dataclass
class Machine:
    id: str
    name: str
    version: str
    os: dict
    sys: dict
    platform: dict
    psutil: dict
    cuda: dict
    asv: dict

    @classmethod
    def safe_load_from_json(cls, file_path: pathlib.Path) -> typing_extensions.Self | None:
        with file_path.open(mode="r") as file_stream:
            data = json.load(file_stream)

        version = str(data.get("version", None))
        if version is None or packaging.version.Version(version) < packaging.version.Version(version="1.1.0"):
            return None

        machine_id = file_path.stem.removeprefix("machine-")

        return cls(
            id=machine_id,
            name=data.get("name", ""),
            version=version,
            os=data.get("os", {}),
            sys=data.get("sys", {}),
            platform=data.get("platform", {}),
            psutil=data.get("psutil", {}),
            cuda=data.get("cuda", {}),
            asv=data.get("asv", {}),
        )

    def to_dataframe(self) -> "polars.DataFrame":
        import polars

        data = {
            "machine_id": self.id,
            "name": self.name,
            "version": self.version,
            "os": json.dumps(self.os),
            "sys": json.dumps(self.sys),
            "platform": json.dumps(self.platform),
            "psutil": json.dumps(self.psutil),
            "cuda": json.dumps(self.cuda),
            "asv": json.dumps(self.asv),
        }

        data_frame = polars.DataFrame(data=data)
        return data_frame


@dataclasses.dataclass
class Environment:
    environment_id: str
    preamble: str

    # Allow arbitrary fields
    def __init__(self, environment_id: str, preamble: str, **kwargs) -> None:
        self.environment_id = environment_id
        self.preamble = preamble
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def safe_load_from_json(cls, file_path: pathlib.Path) -> typing_extensions.Self | None:
        with file_path.open(mode="r") as file_stream:
            data = json.load(fp=file_stream)

        if len(data) > 1:
            return None

        environment_id = file_path.stem.removeprefix("environment-")
        preamble = next(iter(data.keys()))

        packages = {
            package["name"]: f'{package["version"]} ({package["build"]})'
            for package in data[preamble]
            if len(package) >= 3
        }

        if not any(packages):
            return None

        return cls(environment_id=environment_id, preamble=preamble, **packages)

    def to_dataframe(self) -> "polars.DataFrame":
        import polars

        data = {
            "environment_id": self.environment_id,
            "preamble": self.preamble,
        }
        for package_name, package_details in self.__dict__.items():
            if package_name not in ["environment_id", "preamble"]:
                data[package_name] = package_details

        data_frame = polars.DataFrame(data=data, orient="col")
        return data_frame
