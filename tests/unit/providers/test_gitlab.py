"""Tests for GitLab CI provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import GitLabConfig
from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)
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
def test_definition() -> TestDefinition:
    """Create test definition."""
    return TestDefinition(
        version="1.0",
        tests=[
            Test(
                name="smoke test",
                type="source-code",
                source=TestSource(
                    url="https://github.com/OWASP/NodeGoat.git",
                    ref="main",
                ),
                scan_paths=["."],
            )
        ],
    )


async def test_dispatch_scanner_tests_success(
    gitlab_config: GitLabConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests successfully creates pipeline."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"id": 789, "web_url": "https://gitlab.com/project/pipelines/789"},
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert pipeline_id == "789"


async def test_dispatch_scanner_tests_with_scan_configs(
    gitlab_config: GitLabConfig,
) -> None:
    """dispatch_scanner_tests includes scan_configs when provided."""
    test_def_with_configs = TestDefinition(
        version="1.0",
        tests=[
            Test(
                name="config test",
                type="source-code",
                source=TestSource(
                    url="https://github.com/OWASP/NodeGoat.git",
                    ref="main",
                ),
                scan_paths=["."],
                scan_configs=[{"key": "value"}],
            )
        ],
    )

    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"id": 789, "web_url": "https://gitlab.com/project/pipelines/789"},
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_def_with_configs,
            "main",
            "test/registry",
        )

    assert pipeline_id == "789"


async def test_dispatch_scanner_tests_failure(
    gitlab_config: GitLabConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError on API failure."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to create pipeline"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_scanner_tests_missing_pipeline_id(
    gitlab_config: GitLabConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError when pipeline ID is missing."""
    provider = GitLabProvider(gitlab_config)

    with aioresponses() as m:
        m.post(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/pipeline",
            status=201,
            payload={"web_url": "https://gitlab.com/project/pipelines/789"},
        )

        with pytest.raises(RuntimeError, match="Pipeline ID not found"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
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
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789/jobs",
            payload=[],
        )

        is_complete, results = await provider.poll_status("789")

    assert is_complete is False
    assert results == []


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
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789/jobs",
            payload=[
                {
                    "name": "run-test-smoke-test",
                    "status": "success",
                    "started_at": "2099-01-01T12:00:00Z",
                    "finished_at": "2099-01-01T12:01:30Z",
                }
            ],
        )

        is_complete, results = await provider.poll_status("789")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "success"
    assert results[0].provider == "gitlab"
    assert results[0].test_name == "smoke-test"


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
        m.get(
            f"https://gitlab.com/api/v4/projects/{gitlab_config.project_id}/"
            "pipelines/789/jobs",
            payload=[
                {
                    "name": "run-test-smoke-test",
                    "status": "failed",
                    "started_at": "2099-01-01T12:00:00Z",
                    "finished_at": "2099-01-01T12:01:30Z",
                }
            ],
        )

        is_complete, results = await provider.poll_status("789")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "failure"
    assert results[0].test_name == "smoke-test"


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


async def test_dispatch_scanner_tests_with_project_path(
    test_definition: TestDefinition,
) -> None:
    """dispatch_scanner_tests URL-encodes project path for API calls."""
    config = GitLabConfig(
        token="glpat-test123",
        project_id="boostsecurityio/martin/boostsec-registry-test-runner",
        ref="main",
    )
    provider = GitLabProvider(config)

    assert (
        provider._encoded_project_id
        == "boostsecurityio%2Fmartin%2Fboostsec-registry-test-runner"
    )

    with aioresponses() as m:
        m.post(
            "https://gitlab.com/api/v4/projects/boostsecurityio%2Fmartin%2Fboostsec-registry-test-runner/pipeline",
            status=201,
            payload={"id": 789, "web_url": "https://gitlab.com/project/pipelines/789"},
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert pipeline_id == "789"
