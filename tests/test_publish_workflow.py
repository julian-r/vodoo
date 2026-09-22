"""Release publication and staging must be gated by exact-source validation."""

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

    for job_name in ("validate-release", "build", "stage-on-npm"):
        assert _checkout_ref(jobs[job_name]) == "${{ github.sha }}"

    assert verification["if"] == "github.event_name == 'release'"
    assert verification["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in verification["run"]
    assert 'test "$(git rev-list -n 1 "$RELEASE_TAG")" = "$GITHUB_SHA"' in verification["run"]

    assert jobs["build"]["needs"] == "validate-release"
    assert jobs["stage-on-npm"]["needs"] == "validate-release"
    assert jobs["publish-to-pypi"]["needs"] == ["build"]
    assert jobs["publish-to-testpypi"]["needs"] == ["build"]


def test_npm_release_uses_staging_and_requires_manual_2fa_approval() -> None:
    npm_job = _publish_jobs()["stage-on-npm"]
    npm_install = next(
        step
        for step in npm_job["steps"]
        if step.get("name") == "Install npm with staged publishing support"
    )
    staging = next(
        step
        for step in npm_job["steps"]
        if step.get("name") == "Stage npm package for 2FA approval"
    )

    assert npm_install["run"] == "npm install --global npm@12.0.2"
    assert staging["run"] == "npm stage publish --access public --provenance"
    assert "env" not in staging
    assert npm_job["permissions"]["id-token"] == "write"
