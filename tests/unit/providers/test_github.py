"""Tests for GitHub Actions provider."""

from unittest.mock import patch

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import GitHubConfig
from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)
from boostsec.registry_test_action.providers.github import GitHubProvider


@pytest.fixture
def github_config() -> GitHubConfig:
    """Create test GitHub configuration."""
    return GitHubConfig(
        token="ghp_test123",
        owner="boostsecurityio",
        repo="test-repo",
        workflow_id="test.yml",
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
    github_config: GitHubConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests successfully dispatches workflow and finds run."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        # Mock workflow dispatch
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=204,
        )

        # Mock workflow run list
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs?per_page=5",
            payload={
                "workflow_runs": [
                    {
                        "id": 123456,
                        "status": "in_progress",
                        "created_at": "2099-01-01T12:00:00Z",
                        "display_title": "[boostsecurityio/trivy-fs]",
                    }
                ]
            },
        )

        with patch("asyncio.sleep"):
            run_id = await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )

    assert run_id == "123456"


async def test_dispatch_scanner_tests_with_scan_configs(
    github_config: GitHubConfig,
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

    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=204,
        )
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs?per_page=5",
            payload={
                "workflow_runs": [
                    {
                        "id": 123456,
                        "status": "in_progress",
                        "created_at": "2099-01-01T12:00:00Z",
                        "display_title": "[boostsecurityio/trivy-fs]",
                    }
                ]
            },
        )

        with patch("asyncio.sleep"):
            run_id = await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_def_with_configs,
                "main",
                "test/registry",
            )

    assert run_id == "123456"


async def test_dispatch_scanner_tests_failure(
    github_config: GitHubConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError on API failure."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to dispatch workflow"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_poll_status_in_progress(github_config: GitHubConfig) -> None:
    """poll_status returns not complete when run is in progress."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456",
            payload={
                "status": "in_progress",
                "conclusion": None,
                "html_url": "https://github.com/owner/repo/actions/runs/123",
            },
        )
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456/jobs",
            payload={"jobs": []},
        )

        is_complete, results = await provider.poll_status("123456")

    assert is_complete is False
    assert results == []


async def test_poll_status_completed_success(github_config: GitHubConfig) -> None:
    """poll_status returns complete with success status."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456",
            payload={
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/owner/repo/actions/runs/123",
                "created_at": "2099-01-01T12:00:00Z",
                "updated_at": "2099-01-01T12:01:30Z",
            },
        )
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456/jobs",
            payload={
                "jobs": [
                    {
                        "name": "run-tests (smoke test, .)",
                        "conclusion": "success",
                        "started_at": "2099-01-01T12:00:00Z",
                        "completed_at": "2099-01-01T12:01:30Z",
                    }
                ]
            },
        )

        is_complete, results = await provider.poll_status("123456")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "success"
    assert results[0].provider == "github"
    assert results[0].test_name == "smoke test"
    assert results[0].duration == 90.0


async def test_poll_status_completed_failure(github_config: GitHubConfig) -> None:
    """poll_status returns complete with failure status."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456",
            payload={
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/owner/repo/actions/runs/123",
                "created_at": "2099-01-01T12:00:00Z",
                "updated_at": "2099-01-01T12:05:45Z",
            },
        )
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456/jobs",
            payload={
                "jobs": [
                    {
                        "name": "run-tests (smoke test, .)",
                        "conclusion": "failure",
                        "started_at": "2099-01-01T12:00:00Z",
                        "completed_at": "2099-01-01T12:05:45Z",
                    }
                ]
            },
        )

        is_complete, results = await provider.poll_status("123456")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "failure"
    assert results[0].duration == 345.0


async def test_poll_status_api_error(github_config: GitHubConfig) -> None:
    """poll_status raises RuntimeError on API failure."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs/123456",
            status=404,
            body="Not Found",
        )

        with pytest.raises(RuntimeError, match="Failed to get workflow run"):
            await provider.poll_status("123456")


async def test_map_conclusion_all_statuses(github_config: GitHubConfig) -> None:
    """_map_conclusion handles all GitHub conclusion types."""
    provider = GitHubProvider(github_config)

    assert provider._map_conclusion("success") == "success"
    assert provider._map_conclusion("failure") == "failure"
    assert provider._map_conclusion("cancelled") == "error"
    assert provider._map_conclusion("timed_out") == "timeout"
    assert provider._map_conclusion("action_required") == "error"
    assert provider._map_conclusion("neutral") == "success"
    assert provider._map_conclusion("skipped") == "error"
    assert provider._map_conclusion("stale") == "error"
    assert provider._map_conclusion("unknown") == "error"


async def test_calculate_job_duration_success(github_config: GitHubConfig) -> None:
    """_calculate_job_duration computes duration from timestamps."""
    provider = GitHubProvider(github_config)

    data = {
        "started_at": "2099-01-01T12:00:00Z",
        "completed_at": "2099-01-01T12:05:30Z",
    }

    duration = provider._calculate_job_duration(data)
    assert duration == 330.0  # 5 minutes 30 seconds


async def test_calculate_job_duration_missing_timestamps(
    github_config: GitHubConfig,
) -> None:
    """_calculate_job_duration returns 0.0 when timestamps are missing."""
    provider = GitHubProvider(github_config)

    # Missing both
    assert provider._calculate_job_duration({}) == 0.0

    # Missing completed_at
    assert provider._calculate_job_duration({"started_at": "2099-01-01T12:00:00Z"}) == 0.0

    # Missing started_at
    assert provider._calculate_job_duration({"completed_at": "2099-01-01T12:00:00Z"}) == 0.0


async def test_calculate_job_duration_invalid_format(github_config: GitHubConfig) -> None:
    """_calculate_job_duration returns 0.0 when timestamp format is invalid."""
    provider = GitHubProvider(github_config)

    data = {
        "started_at": "invalid-date",
        "completed_at": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_job_duration(data)
    assert duration == 0.0


async def test_calculate_job_duration_non_string_timestamps(
    github_config: GitHubConfig,
) -> None:
    """_calculate_job_duration returns 0.0 when timestamps are not strings."""
    provider = GitHubProvider(github_config)

    data = {
        "started_at": 123456,  # Not a string
        "completed_at": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_job_duration(data)
    assert duration == 0.0


async def test_find_workflow_run_not_found(github_config: GitHubConfig) -> None:
    """_find_workflow_run raises RuntimeError when run cannot be found."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        # Mock empty workflow runs list for all attempts
        for _ in range(10):
            m.get(
                f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
                "actions/runs?per_page=5",
                payload={"workflow_runs": []},
            )

        with patch("asyncio.sleep"):
            with pytest.raises(
                RuntimeError, match="Could not find dispatched workflow run"
            ):
                await provider._find_workflow_run(
                    dispatch_time=0.0,
                    scanner_id="boostsecurityio/trivy-fs",
                )


async def test_fetch_recent_runs_api_error(github_config: GitHubConfig) -> None:
    """_fetch_recent_runs raises RuntimeError on API failure."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.get(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            "actions/runs?per_page=5",
            status=500,
            body="Internal Server Error",
        )

        with pytest.raises(RuntimeError, match="Failed to list workflow runs"):
            await provider._fetch_recent_runs()


async def test_find_matching_run_skips_invalid_runs(
    github_config: GitHubConfig,
) -> None:
    """_find_matching_run handles invalid run data gracefully."""
    provider = GitHubProvider(github_config)

    runs: list[object] = [
        "not a dict",  # Non-dict run
        {"status": "completed", "id": 111},  # Completed run
        {
            "status": "in_progress",
            "display_title": 123,
            "id": 222,
        },  # Non-string display_title
        {
            "status": "in_progress",
            "display_title": "[other-scanner/tool]",
            "created_at": "2099-01-01T12:00:00Z",
            "id": 333,
        },  # Wrong scanner_id
        {
            "status": "in_progress",
            "display_title": "[boostsecurityio/trivy-fs]",
            "created_at": 123,
            "id": 555,
        },  # Non-string created_at
        {
            "status": "in_progress",
            "display_title": "[boostsecurityio/trivy-fs]",
            "created_at": "2099-01-01T12:00:00Z",
            "id": 123456,
        },  # Valid run
    ]

    run_id = provider._find_matching_run(
        runs,
        dispatch_time=0.0,
        scanner_id="boostsecurityio/trivy-fs",
    )
    assert run_id == "123456"


async def test_extract_test_name_with_full_matrix(github_config: GitHubConfig) -> None:
    """_extract_test_name_from_job extracts test name and scan path from full matrix format."""
    provider = GitHubProvider(github_config)

    # Full matrix format with all fields
    job_name = "run-tests (smoke test, source-code, https://github.com/OWASP/NodeGoat.git, main, src/app, 300s)"
    result = provider._extract_test_name_from_job(job_name)
    assert result == "smoke test [src/app]"

    # Another test with different scan path
    job_name2 = "run-tests (integration test, docker-image, https://github.com/test/repo.git, develop, ., 600s)"
    result2 = provider._extract_test_name_from_job(job_name2)
    assert result2 == "integration test [.]"
