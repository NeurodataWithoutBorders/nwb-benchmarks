import copy
import importlib.metadata
import json
import subprocess
import sys

import pytest

from nwb_benchmarks.setup import _environment
from nwb_benchmarks.setup._environment import (
    capture_environment,
    stable_environment_content,
)
from nwb_benchmarks.utils import get_dictionary_checksum

CONDA_JSON = [
    {"name": "hdf5", "version": "1.14.3", "build_string": "nompi_h4", "channel": "conda-forge"},
    {"name": "python", "version": "3.11.9", "build_string": "h1", "channel": "conda-forge"},
]


class FakeDistribution:
    def __init__(self, name: str, version: str):
        self.metadata = {"Name": name}
        self.version = version


@pytest.fixture
def fake_distributions(monkeypatch):
    def _set(names=("pynwb", "Numpy")):
        monkeypatch.setattr(
            importlib.metadata,
            "distributions",
            lambda: [FakeDistribution(name, "1.0") for name in names],
        )

    _set()
    return _set


@pytest.fixture
def conda_prefix(tmp_path, monkeypatch):
    prefix = tmp_path / "conda_env"
    (prefix / "conda-meta").mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    return prefix


def fake_run(returncode=0, stdout=json.dumps(CONDA_JSON), stderr="", calls=None):
    def _run(args, **kwargs):
        if calls is not None and args[0] == "/bin/conda":
            calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)

    return _run


def test_conda_available(fake_distributions, conda_prefix, monkeypatch):
    calls = []
    monkeypatch.setattr(_environment.shutil, "which", lambda name: "/bin/conda" if name == "conda" else None)
    monkeypatch.setattr(_environment.subprocess, "run", fake_run(calls=calls))

    captured = capture_environment()

    assert calls == [["/bin/conda", "list", "--prefix", str(conda_prefix), "--json"]]
    assert captured["conda"]["prefix"] == str(conda_prefix)
    assert captured["conda"]["executable"] == "/bin/conda"
    assert [package["name"] for package in captured["conda"]["packages"]] == ["hdf5", "python"]
    assert captured["conda"]["packages"][0]["build"] == "nompi_h4"
    assert captured["capture_warnings"] == []
    assert [d["name"] for d in captured["python_distributions"]] == ["numpy", "pynwb"]
    assert captured["interpreter"]["executable"] == sys.executable


def test_conda_executable_absent(fake_distributions, conda_prefix, monkeypatch):
    monkeypatch.setattr(_environment.shutil, "which", lambda name: None)

    captured = capture_environment()

    assert captured["conda"] is None
    assert len(captured["capture_warnings"]) == 1
    assert "No conda/mamba/micromamba executable" in captured["capture_warnings"][0]


def test_venv_over_conda_base_falls_back_to_base_prefix(fake_distributions, tmp_path, monkeypatch):
    base = tmp_path / "base"
    (base / "conda-meta").mkdir(parents=True)
    venv = tmp_path / "venv"
    venv.mkdir()
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.setattr(_environment.shutil, "which", lambda name: "/bin/conda")
    monkeypatch.setattr(_environment.subprocess, "run", fake_run())

    assert capture_environment()["conda"]["prefix"] == str(base)


def test_no_conda_prefix(fake_distributions, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))

    captured = capture_environment()

    assert captured["conda"] is None
    assert "conda-meta" in captured["capture_warnings"][0]


@pytest.mark.parametrize(
    "run",
    [
        fake_run(returncode=1, stderr="boom"),
        fake_run(stdout="not json"),
        fake_run(stdout='{"unexpected": 1}'),
        lambda args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd=args, timeout=1)),
        lambda args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("conda")),
    ],
)
def test_conda_failure_is_handled(fake_distributions, conda_prefix, monkeypatch, run):
    monkeypatch.setattr(_environment.shutil, "which", lambda name: "/bin/conda")
    monkeypatch.setattr(_environment.subprocess, "run", run)

    captured = capture_environment()

    assert captured["conda"] is None
    assert len(captured["capture_warnings"]) == 1
    assert captured["python_distributions"]


def test_nonzero_exit_records_stderr(fake_distributions, conda_prefix, monkeypatch):
    monkeypatch.setattr(_environment.shutil, "which", lambda name: "/bin/conda")
    monkeypatch.setattr(_environment.subprocess, "run", fake_run(returncode=1, stderr="boom"))

    assert "boom" in capture_environment()["capture_warnings"][0]


def test_missing_pynwb_raises_before_conda_is_called(fake_distributions, conda_prefix, monkeypatch):
    fake_distributions(names=("numpy",))
    monkeypatch.setattr(_environment.subprocess, "run", lambda *args, **kwargs: pytest.fail("conda was called"))

    with pytest.raises(RuntimeError, match="pynwb") as exception_info:
        capture_environment()

    assert sys.executable in str(exception_info.value)
    assert sys.prefix in str(exception_info.value)


def test_checksum_is_stable(fake_distributions, conda_prefix, monkeypatch):
    monkeypatch.setattr(_environment.shutil, "which", lambda name: "/bin/conda")
    monkeypatch.setattr(_environment.subprocess, "run", fake_run())
    captured = capture_environment()
    checksum = get_dictionary_checksum(stable_environment_content(captured))

    changed = copy.deepcopy(captured)
    changed["python_distributions"].reverse()
    changed["conda"]["packages"].reverse()
    changed["runtime_versions"] = dict(reversed(list(changed["runtime_versions"].items())))
    changed["conda"]["executable"] = "/elsewhere/bin/mamba"
    changed["conda"]["prefix"] = "/elsewhere/env"
    changed["interpreter"].update(executable="/x/python", prefix="/x", base_prefix="/x", platform="other")
    changed["interpreter"]["conda_prefix_env"] = "/y"
    changed["capture_warnings"] = ["a different warning"]

    assert get_dictionary_checksum(stable_environment_content(changed)) == checksum

    changed["python_distributions"][0]["version"] = "2.0"
    assert get_dictionary_checksum(stable_environment_content(changed)) != checksum
