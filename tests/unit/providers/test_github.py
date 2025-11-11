"""Tests for GitHub Actions provider."""

from unittest.mock import patch

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import GitHubConfig
from boostsec.registry_test_action.models.test_definition import Test, TestSource
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
    github_config: GitHubConfig, test_definition: Test
) -> None:
    """dispatch_test successfully dispatches workflow and finds run."""
    provider = GitHubProvider(github_config)

    # Clear claimed runs from any previous tests
    GitHubProvider._claimed_runs.clear()

    with aioresponses() as m:
        # Mock workflow dispatch
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=204,
        )

        # Mock workflow run list (may be called multiple times due to retries)
        # Run created 5 seconds after dispatch
        for _ in range(10):
            m.get(
                f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
                "actions/runs?per_page=5",
                payload={
                    "workflow_runs": [
                        {
                            "id": 123456,
                            "status": "in_progress",
                            "created_at": "2099-01-01T12:00:05Z",
                        }
                    ]
                },
            )

        with patch("asyncio.sleep"), patch("time.time", return_value=4070952000.0):
            run_id = await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )

    assert run_id == "123456"


async def test_dispatch_test_with_scan_configs(github_config: GitHubConfig) -> None:
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

    provider = GitHubProvider(github_config)

    # Clear claimed runs from any previous tests
    GitHubProvider._claimed_runs.clear()

    with aioresponses() as m:
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=204,
        )
        # Run created 5 seconds after dispatch
        for _ in range(10):
            m.get(
                f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
                "actions/runs?per_page=5",
                payload={
                    "workflow_runs": [
                        {
                            "id": 123456,
                            "status": "in_progress",
                            "created_at": "2099-01-01T12:00:05Z",
                        }
                    ]
                },
            )

        with patch("asyncio.sleep"), patch("time.time", return_value=4070952000.0):
            run_id = await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_with_configs,
                "main",
                "test/registry",
            )

    assert run_id == "123456"


async def test_dispatch_test_failure(
    github_config: GitHubConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError on API failure."""
    provider = GitHubProvider(github_config)

    with aioresponses() as m:
        m.post(
            f"https://api.github.com/repos/{github_config.owner}/{github_config.repo}/"
            f"actions/workflows/{github_config.workflow_id}/dispatches",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to dispatch workflow"):
            await provider.dispatch_test(
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

        is_complete, result = await provider.poll_status("123456")

    assert is_complete is False
    assert result.provider == "github"
    assert result.status == "error"


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

        is_complete, result = await provider.poll_status("123456")

    assert is_complete is True
    assert result.status == "success"
    assert result.provider == "github"
    assert result.duration == 90.0  # 1 minute 30 seconds


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

        is_complete, result = await provider.poll_status("123456")

    assert is_complete is True
    assert result.status == "failure"
    assert result.duration == 345.0  # 5 minutes 45 seconds


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


async def test_calculate_duration_success(github_config: GitHubConfig) -> None:
    """_calculate_duration computes duration from timestamps."""
    provider = GitHubProvider(github_config)

    data = {
        "created_at": "2099-01-01T12:00:00Z",
        "updated_at": "2099-01-01T12:05:30Z",
    }

    duration = provider._calculate_duration(data)
    assert duration == 330.0  # 5 minutes 30 seconds


async def test_calculate_duration_missing_timestamps(
    github_config: GitHubConfig,
) -> None:
    """_calculate_duration returns 0.0 when timestamps are missing."""
    provider = GitHubProvider(github_config)

    # Missing both
    assert provider._calculate_duration({}) == 0.0

    # Missing updated_at
    assert provider._calculate_duration({"created_at": "2099-01-01T12:00:00Z"}) == 0.0

    # Missing created_at
    assert provider._calculate_duration({"updated_at": "2099-01-01T12:00:00Z"}) == 0.0


async def test_calculate_duration_invalid_format(github_config: GitHubConfig) -> None:
    """_calculate_duration returns 0.0 when timestamp format is invalid."""
    provider = GitHubProvider(github_config)

    data = {
        "created_at": "invalid-date",
        "updated_at": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_duration(data)
    assert duration == 0.0


async def test_calculate_duration_non_string_timestamps(
    github_config: GitHubConfig,
) -> None:
    """_calculate_duration returns 0.0 when timestamps are not strings."""
    provider = GitHubProvider(github_config)

    data = {
        "created_at": 123456,  # Not a string
        "updated_at": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_duration(data)
    assert duration == 0.0


async def test_find_workflow_run_not_found(github_config: GitHubConfig) -> None:
    """_find_workflow_run raises RuntimeError when run cannot be found."""
    provider = GitHubProvider(github_config)

    # Clear claimed runs from any previous tests
    GitHubProvider._claimed_runs.clear()

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
                    dispatch_time=0.0, correlation_id="test-uuid"
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

    # Clear claimed runs from any previous tests
    GitHubProvider._claimed_runs.clear()

    # Create a run at 2099-01-01T12:00:05Z (5 seconds after dispatch)
    dispatch_time = 4070952000.0  # 2099-01-01T12:00:00Z

    runs: list[object] = [
        "not a dict",  # Non-dict run
        {"status": "completed", "id": 111},  # Completed run
        {"status": "in_progress", "id": "not-an-int"},  # Non-integer ID
        {
            "status": "in_progress",
            "created_at": 123,
            "id": 222,
        },  # Non-string created_at
        {
            "status": "in_progress",
            "created_at": "2099-01-01T11:59:00Z",
            "id": 333,
        },  # Outside time window (60 seconds before)
        {
            "status": "in_progress",
            "created_at": "2099-01-01T12:00:05Z",
            "id": 123456,
        },  # Valid run
    ]

    run_id = await provider._find_matching_run(
        runs, dispatch_time=dispatch_time, correlation_id="test-uuid"
    )
    assert run_id == "123456"


async def test_find_matching_run_skips_claimed_runs(
    github_config: GitHubConfig,
) -> None:
    """_find_matching_run skips runs that have already been claimed."""
    provider = GitHubProvider(github_config)

    # Clear claimed runs from any previous tests
    GitHubProvider._claimed_runs.clear()

    # Pre-claim a run
    GitHubProvider._claimed_runs.add("999999")

    # Create a run at 2099-01-01T12:00:05Z (5 seconds after dispatch)
    dispatch_time = 4070952000.0  # 2099-01-01T12:00:00Z

    runs: list[object] = [
        {
            "status": "in_progress",
            "created_at": "2099-01-01T12:00:03Z",
            "id": 999999,
        },  # Already claimed (closer match)
        {
            "status": "in_progress",
            "created_at": "2099-01-01T12:00:05Z",
            "id": 123456,
        },  # Valid unclaimed run (further but still within window)
    ]

    run_id = await provider._find_matching_run(
        runs, dispatch_time=dispatch_time, correlation_id="test-uuid"
    )
    assert run_id == "123456"
