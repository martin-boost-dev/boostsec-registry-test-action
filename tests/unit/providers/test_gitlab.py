"""Tests for GitLab CI provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import GitLabConfig
from boostsec.registry_test_action.models.test_definition import Test, TestSource
from boostsec.registry_test_action.providers.gitlab import GitLabProvider


@pytest.fixture
def gitlab_config() -> GitLabConfig:
    """Create test GitLab configuration."""
    return GitLabConfig(
        token="glpat-test123",
        project_id="12345",
        ref="main",
    )


@pytest.fixture
def test_definition() -> Test:
    """Create test definition."""
    return Test(
        name="smoke test",
        type="source-code",
        source=TestSource(
            url="https://github.com/OWASP/NodeGoat.git",
            ref="main",
        ),
        scan_paths=["."],
    )


async def test_dispatch_test_success(
    gitlab_config: GitLabConfig, test_definition: Test
) -> None:
    """dispatch_test successfully creates pipeline."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"id": 789, "web_url": "https://gitlab.com/project/pipelines/789"},
        )

        pipeline_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "https://github.com/test/registry",
        )

    assert pipeline_id == "789"


async def test_dispatch_test_with_scan_configs(gitlab_config: GitLabConfig) -> None:
    """dispatch_test includes scan_configs when provided."""
    test_with_configs = Test(
        name="config test",
        type="source-code",
        source=TestSource(
            url="https://github.com/OWASP/NodeGoat.git",
            ref="main",
        ),
        scan_paths=["."],
        scan_configs=[{"key": "value"}],
    )

    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"id": 789, "web_url": "https://gitlab.com/project/pipelines/789"},
        )

        pipeline_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_with_configs,
            "main",
            "https://github.com/test/registry",
        )

    assert pipeline_id == "789"


async def test_dispatch_test_failure(
    gitlab_config: GitLabConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError on API failure."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to create pipeline"):
            await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "https://github.com/test/registry",
            )


async def test_dispatch_test_missing_pipeline_id(
    gitlab_config: GitLabConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError when pipeline ID is missing."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"web_url": "https://gitlab.com/project/pipelines/789"},
        )

        with pytest.raises(RuntimeError, match="Pipeline ID not found"):
            await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "https://github.com/test/registry",
            )


async def test_poll_status_running(gitlab_config: GitLabConfig) -> None:
    """poll_status returns not complete when pipeline is running."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789",
            payload={
                "status": "running",
                "web_url": "https://gitlab.com/project/pipelines/789",
            },
        )

        is_complete, result = await provider.poll_status("789")

    assert is_complete is False
    assert result.provider == "gitlab"
    assert result.status == "error"


async def test_poll_status_completed_success(gitlab_config: GitLabConfig) -> None:
    """poll_status returns complete with success status."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789",
            payload={
                "status": "success",
                "web_url": "https://gitlab.com/project/pipelines/789",
            },
        )

        is_complete, result = await provider.poll_status("789")

    assert is_complete is True
    assert result.status == "success"
    assert result.provider == "gitlab"


async def test_poll_status_completed_failure(gitlab_config: GitLabConfig) -> None:
    """poll_status returns complete with failure status."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789",
            payload={
                "status": "failed",
                "web_url": "https://gitlab.com/project/pipelines/789",
            },
        )

        is_complete, result = await provider.poll_status("789")

    assert is_complete is True
    assert result.status == "failure"


async def test_poll_status_api_error(gitlab_config: GitLabConfig) -> None:
    """poll_status raises RuntimeError on API failure."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789",
            status=404,
            body="Not Found",
        )

        with pytest.raises(RuntimeError, match="Failed to get pipeline"):
            await provider.poll_status("789")


async def test_map_status_all_statuses(gitlab_config: GitLabConfig) -> None:
    """_map_status handles all GitLab status types."""
    provider = GitLabProvider(gitlab_config)

    assert provider._map_status("success") == "success"
    assert provider._map_status("failed") == "failure"
    assert provider._map_status("canceled") == "error"
    assert provider._map_status("skipped") == "error"
    assert provider._map_status("manual") == "error"
    assert provider._map_status("unknown") == "error"
