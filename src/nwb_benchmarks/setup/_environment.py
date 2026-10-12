"""Capture the environment of the interpreter running the benchmarks, authoritatively and without silent errors."""

import importlib
import importlib.metadata
import json
import os
import pathlib
import platform
import shutil
import ssl
import subprocess
import sys
from typing import Any, Dict, List, Optional

CONDA_EXECUTABLES = ("conda", "mamba", "micromamba")
CONDA_TIMEOUT_IN_SECONDS = 120

# Native libraries that matter for I/O benchmarks, as (label, module, attribute path); all are optional.
RUNTIME_VERSION_SOURCES = (
    ("h5py", "h5py", "__version__"),
    ("hdf5", "h5py.version", "hdf5_version"),
    ("zarr", "zarr", "__version__"),
    ("numcodecs", "numcodecs", "__version__"),
    ("blosc", "numcodecs.blosc", "VERSION_STRING"),
    ("hdmf", "hdmf", "__version__"),
    ("pynwb", "pynwb", "__version__"),
    ("fsspec", "fsspec", "__version__"),
    ("remfile", "remfile", "__version__"),
    ("lindi", "lindi", "__version__"),
    ("s3fs", "s3fs", "__version__"),
    ("aiohttp", "aiohttp", "__version__"),
    ("requests", "requests", "__version__"),
)


def _normalize_name(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _collect_python_distributions() -> List[Dict[str, str]]:
    distributions = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name is None:  # Broken metadata directories
            continue
        distributions[_normalize_name(name)] = distribution.version
    return [dict(name=name, version=version) for name, version in sorted(distributions.items())]


def _collect_runtime_versions() -> Dict[str, Optional[str]]:
    runtime_versions: Dict[str, Optional[str]] = dict()
    for label, module_name, attribute in RUNTIME_VERSION_SOURCES:
        try:
            value = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError):
            continue
        runtime_versions[label] = None if value is None else str(value)
    runtime_versions["openssl"] = ssl.OPENSSL_VERSION
    return runtime_versions


def _find_conda_prefix() -> Optional[str]:
    """First of `sys.prefix` and `sys.base_prefix` that is a conda environment (e.g., a venv over a conda base)."""
    for prefix in (sys.prefix, sys.base_prefix):
        if (pathlib.Path(prefix) / "conda-meta").is_dir():
            return prefix
    return None


def _collect_conda(warnings_list: List[str]) -> Optional[Dict[str, Any]]:
    """Best-effort `conda list --json` of the prefix of this interpreter; never raises."""
    prefix = _find_conda_prefix()
    if prefix is None:
        warnings_list.append(f"No `conda-meta` directory in sys.prefix ({sys.prefix}) or sys.base_prefix.")
        return None

    executable = next((path for name in CONDA_EXECUTABLES if (path := shutil.which(name)) is not None), None)
    if executable is None:
        warnings_list.append(f"No {'/'.join(CONDA_EXECUTABLES)} executable found for conda prefix {prefix}.")
        return None

    try:
        process = subprocess.run(
            args=[executable, "list", "--prefix", prefix, "--json"],
            capture_output=True,
            text=True,
            timeout=CONDA_TIMEOUT_IN_SECONDS,
            check=False,
        )
        if process.returncode != 0:
            warnings_list.append(
                f"`{executable} list --prefix {prefix} --json` exited with code {process.returncode}: "
                f"{process.stderr.strip()}"
            )
            return None
        packages = json.loads(process.stdout)
        parsed_packages = [
            dict(
                name=package["name"],
                version=package["version"],
                build=package.get("build_string", ""),
                channel=package.get("channel", ""),
            )
            for package in packages
        ]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exception:
        warnings_list.append(f"Unable to list conda packages of {prefix} with {executable}: {exception!r}")
        return None

    return dict(executable=executable, prefix=prefix, packages=sorted(parsed_packages, key=lambda p: p["name"]))


def capture_environment() -> Dict[str, Any]:
    """
    Capture the environment of the running interpreter.

    The importlib.metadata listing is the baseline and always succeeds. Conda enrichment is best-effort, and the
    runtime-reported library versions need no subprocess. Raises if `pynwb` is not installed in this interpreter.
    """
    capture_warnings: List[str] = []
    python_distributions = _collect_python_distributions()

    if "pynwb" not in {distribution["name"] for distribution in python_distributions}:
        raise RuntimeError(
            "`pynwb` is not installed in the interpreter running the benchmarks "
            f"(sys.executable={sys.executable}, sys.prefix={sys.prefix})! Install the package in this environment."
        )

    conda = _collect_conda(warnings_list=capture_warnings)
    for warning in capture_warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    # Paths and CONDA_* variables are diagnostics only; they are never used to choose what to list.
    return dict(
        interpreter=dict(
            executable=sys.executable,
            prefix=sys.prefix,
            base_prefix=sys.base_prefix,
            version=sys.version,
            platform=platform.platform(),
            conda_prefix_env=os.environ.get("CONDA_PREFIX"),
            conda_default_env=os.environ.get("CONDA_DEFAULT_ENV"),
        ),
        python_distributions=python_distributions,
        conda=conda,
        runtime_versions=_collect_runtime_versions(),
        capture_warnings=capture_warnings,
    )


def stable_environment_content(raw_environment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce a raw capture to the content that identifies the environment.

    Only sorted package/version content is kept; absolute paths, executables, diagnostics and warnings are dropped so
    that the same environment on two checkouts produces the same ID.
    """
    conda = raw_environment.get("conda")
    return dict(
        python_version=raw_environment["interpreter"]["version"],
        python_distributions=sorted(
            ({"name": d["name"], "version": d["version"]} for d in raw_environment["python_distributions"]),
            key=lambda d: (d["name"], d["version"]),
        ),
        conda_packages=(
            None
            if conda is None
            else sorted(
                (
                    {key: package.get(key, "") for key in ("name", "version", "build", "channel")}
                    for package in conda["packages"]
                ),
                key=lambda p: tuple(p.values()),
            )
        ),
        runtime_versions=dict(sorted(raw_environment["runtime_versions"].items())),
    )
