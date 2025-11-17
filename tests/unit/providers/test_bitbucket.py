"""Tests for Bitbucket Pipelines provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import BitbucketConfig
from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)
from boostsec.registry_test_action.providers.bitbucket import BitbucketProvider


@pytest.fixture
def bitbucket_config() -> BitbucketConfig:
    """Create test Bitbucket configuration."""
    return BitbucketConfig(
        username="testuser",
        api_token="testtoken",
        workspace="test-workspace",
        repo_slug="test-repo",
        branch="main",
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
    bitbucket_config: BitbucketConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests successfully triggers pipeline."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={
                "uuid": "{abc-123-def}",
                "build_number": 17,
            },
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert pipeline_id == "abc-123-def"


async def test_dispatch_scanner_tests_with_scan_configs(
    bitbucket_config: BitbucketConfig,
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

    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={
                "uuid": "{abc-123-def}",
                "build_number": 17,
            },
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_def_with_configs,
            "main",
            "test/registry",
        )

    assert pipeline_id == "abc-123-def"


async def test_dispatch_scanner_tests_failure(
    bitbucket_config: BitbucketConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError on API failure."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to trigger pipeline"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_scanner_tests_missing_uuid(
    bitbucket_config: BitbucketConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError when UUID is missing."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={"links": {"html": {"href": "https://bitbucket.org/test"}}},
        )

        with pytest.raises(RuntimeError, match="Pipeline UUID not found"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_scanner_tests_missing_build_number(
    bitbucket_config: BitbucketConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests handles missing build_number gracefully."""
    provider = BitbucketProvider(bitbucket_config)

    with aioresponses() as m:
        m.post(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/pipelines/",
            status=201,
            payload={
                "uuid": "{abc-123-def}",
            },
        )

        pipeline_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert pipeline_id == "abc-123-def"


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
            },
        )

        is_complete, results = await provider.poll_status("abc-123")

    assert is_complete is False
    assert results == []


async def test_poll_status_completed_success(bitbucket_config: BitbucketConfig) -> None:
    """poll_status returns complete with success status."""
    provider = BitbucketProvider(bitbucket_config)
    provider._run_urls["abc-123"] = (
        "https://bitbucket.org/test-workspace/test-repo/pipelines/results/17"
    )

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
            },
        )

        is_complete, results = await provider.poll_status("abc-123")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "success"
    assert results[0].provider == "bitbucket"
    assert results[0].test_name == "matrix-tests"
    assert (
        results[0].run_url
        == "https://bitbucket.org/test-workspace/test-repo/pipelines/results/17"
    )


async def test_poll_status_completed_failure(bitbucket_config: BitbucketConfig) -> None:
    """poll_status returns complete with failure status."""
    provider = BitbucketProvider(bitbucket_config)
    provider._run_urls["abc-123"] = (
        "https://bitbucket.org/test-workspace/test-repo/pipelines/results/17"
    )

    with aioresponses() as m:
        m.get(
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{bitbucket_config.workspace}/{bitbucket_config.repo_slug}/"
            "pipelines/{abc-123}",
            payload={
                "state": {"name": "COMPLETED", "result": {"name": "FAILED"}},
            },
        )

        is_complete, results = await provider.poll_status("abc-123")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "failure"
    assert (
        results[0].run_url
        == "https://bitbucket.org/test-workspace/test-repo/pipelines/results/17"
    )


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
            },
        )

        is_complete, results = await provider.poll_status("abc-123")

    assert is_complete is False
    assert results == []


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
            },
        )

        is_complete, results = await provider.poll_status("abc-123")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].test_name == "matrix-tests"
