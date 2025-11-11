"""Tests for Bitbucket Pipelines provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import BitbucketConfig
from boostsec.registry_test_action.models.test_definition import Test, TestSource
from boostsec.registry_test_action.providers.bitbucket import BitbucketProvider


@pytest.fixture
def bitbucket_config() -> BitbucketConfig:
    """Create test Bitbucket configuration."""
    return BitbucketConfig(
        username="testuser",
        app_password="testpassword",
        workspace="test-workspace",
        repo_slug="test-repo",
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
    bitbucket_config: BitbucketConfig, test_definition: Test
) -> None:
    """dispatch_test successfully triggers pipeline."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={
                "uuid": "{abc-123-def}",
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        pipeline_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert pipeline_id == "abc-123-def"


async def test_dispatch_test_with_scan_configs(
    bitbucket_config: BitbucketConfig,
) -> None:
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

    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={
                "uuid": "{abc-123-def}",
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        pipeline_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_with_configs,
            "main",
            "test/registry",
        )

    assert pipeline_id == "abc-123-def"


async def test_dispatch_test_failure(
    bitbucket_config: BitbucketConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError on API failure."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to trigger pipeline"):
            await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_test_missing_uuid(
    bitbucket_config: BitbucketConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError when UUID is missing."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={"links": {"html": {"href": "https://bitbucket.org/test"}}},
        )

        with pytest.raises(RuntimeError, match="Pipeline UUID not found"):
            await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_poll_status_in_progress(bitbucket_config: BitbucketConfig) -> None:
    """poll_status returns not complete when pipeline is in progress."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "IN_PROGRESS"},
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is False
    assert result.provider == "bitbucket"
    assert result.status == "error"


async def test_poll_status_completed_success(bitbucket_config: BitbucketConfig) -> None:
    """poll_status returns complete with success status."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is True
    assert result.status == "success"
    assert result.provider == "bitbucket"


async def test_poll_status_completed_failure(bitbucket_config: BitbucketConfig) -> None:
    """poll_status returns complete with failure status."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": {"name": "FAILED"}},
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is True
    assert result.status == "failure"


async def test_poll_status_api_error(bitbucket_config: BitbucketConfig) -> None:
    """poll_status raises RuntimeError on API failure."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            status=404,
            body="Not Found",
        )

        with pytest.raises(RuntimeError, match="Failed to get pipeline"):
            await provider.poll_status("abc-123")


async def test_map_result_all_statuses(bitbucket_config: BitbucketConfig) -> None:
    """_map_result handles all Bitbucket result types."""
    provider = BitbucketProvider(bitbucket_config)

    assert provider._map_result("SUCCESSFUL") == "success"
    assert provider._map_result("FAILED") == "failure"
    assert provider._map_result("ERROR") == "error"
    assert provider._map_result("STOPPED") == "error"
    assert provider._map_result("unknown") == "error"


async def test_poll_status_no_links(bitbucket_config: BitbucketConfig) -> None:
    """poll_status handles missing links gracefully."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is True
    assert result.run_url == ""


async def test_poll_status_invalid_state(bitbucket_config: BitbucketConfig) -> None:
    """poll_status handles invalid state gracefully."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": "invalid",
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is False
    assert result.status == "error"


async def test_poll_status_result_not_dict(bitbucket_config: BitbucketConfig) -> None:
    """poll_status handles non-dict result gracefully."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": "SUCCESSFUL"},
                "links": {
                    "html": {
                        "href": "https://bitbucket.org/workspace/repo/pipelines/123"
                    }
                },
            },
        )

        is_complete, result = await provider.poll_status("abc-123")

    assert is_complete is True
    assert result.status == "error"
