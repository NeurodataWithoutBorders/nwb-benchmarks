import re

import pytest

from nwb_benchmarks.setup import generate_machine_name


@pytest.fixture
def outside_github_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("RUNNER_NAME", raising=False)


def test_self_hosted_runner_name_is_used(monkeypatch, outside_github_actions):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_NAME", "ackermann")
    assert generate_machine_name() == "ackermann"


@pytest.mark.parametrize("runner_name", [None, "", "GitHub Actions 12"])
def test_hosted_or_unnamed_runner_gets_a_timestamp_name(monkeypatch, outside_github_actions, runner_name):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    if runner_name is not None:
        monkeypatch.setenv("RUNNER_NAME", runner_name)
    assert re.fullmatch(r"github-\d{14}", generate_machine_name())


def test_outside_github_actions_the_name_is_human_readable(monkeypatch, outside_github_actions):
    monkeypatch.setenv("RUNNER_NAME", "ackermann")  # Ignored without GITHUB_ACTIONS.
    name = generate_machine_name()
    assert name != "ackermann"
    assert re.fullmatch(r"[A-Za-z]+", name)
