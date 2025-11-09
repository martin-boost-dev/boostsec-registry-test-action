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
                    }
                ]
            },
        )

        with patch("asyncio.sleep"):
            run_id = await provider.dispatch_test(
                "boostsecurityio/trivy-fs", test_definition, "main"
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
                "boostsecurityio/trivy-fs", test_definition, "main"
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
            },
        )

        is_complete, result = await provider.poll_status("123456")

    assert is_complete is True
    assert result.status == "success"
    assert result.provider == "github"


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
            },
        )

        is_complete, result = await provider.poll_status("123456")

    assert is_complete is True
    assert result.status == "failure"


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
                await provider._find_workflow_run(dispatch_time=0.0)


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
        {"status": "in_progress", "created_at": 123},  # Non-string created_at
        {
            "status": "in_progress",
            "created_at": "2099-01-01T12:00:00Z",
            "id": 123456,
        },  # Valid run
    ]

    run_id = provider._find_matching_run(runs, dispatch_time=0.0)
    assert run_id == "123456"
