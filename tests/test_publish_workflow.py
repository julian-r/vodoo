"""Release publication must be gated by validation of the release source."""

from pathlib import Path
from typing import Any

import yaml


def _publish_jobs() -> dict[str, Any]:
    workflow = yaml.safe_load(Path(".github/workflows/publish.yml").read_text(encoding="utf-8"))
    jobs: dict[str, Any] = workflow["jobs"]
    return jobs


def _checkout_ref(job: dict[str, Any]) -> str:
    checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v4")
    ref: str = checkout["with"]["ref"]
    return ref


def test_release_publishers_depend_on_exact_source_validation() -> None:
    jobs = _publish_jobs()
    validation = jobs["validate-release"]
    verification = next(
        step for step in validation["steps"] if step.get("name") == "Verify release tag checkout"
    )

    for job_name in ("validate-release", "build", "publish-to-npm"):
        assert _checkout_ref(jobs[job_name]) == "${{ github.sha }}"

    assert verification["if"] == "github.event_name == 'release'"
    assert verification["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in verification["run"]
    assert 'test "$(git rev-list -n 1 "$RELEASE_TAG")" = "$GITHUB_SHA"' in verification["run"]

    assert jobs["build"]["needs"] == "validate-release"
    assert jobs["publish-to-npm"]["needs"] == "validate-release"
    assert jobs["publish-to-pypi"]["needs"] == ["build"]
    assert jobs["publish-to-testpypi"]["needs"] == ["build"]
