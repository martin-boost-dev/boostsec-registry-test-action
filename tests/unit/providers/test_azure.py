"""Tests for Azure DevOps Pipelines provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import AzureDevOpsConfig
from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)
from boostsec.registry_test_action.providers.azure import AzureDevOpsProvider


@pytest.fixture
def azure_config() -> AzureDevOpsConfig:
    """Create test Azure DevOps configuration."""
    return AzureDevOpsConfig(
        token="test_token_encoded",
        organization="test-org",
        project="test-project",
        pipeline_id=42,
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
    azure_config: AzureDevOpsConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests successfully runs pipeline."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.post(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs?api-version=7.1",
            status=200,
            payload={
                "id": 999,
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        run_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert run_id == "999"


async def test_dispatch_scanner_tests_with_scan_configs(
    azure_config: AzureDevOpsConfig,
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

    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.post(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs?api-version=7.1",
            status=200,
            payload={
                "id": 999,
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        run_id = await provider.dispatch_scanner_tests(
            "boostsecurityio/trivy-fs",
            test_def_with_configs,
            "main",
            "test/registry",
        )

    assert run_id == "999"


async def test_dispatch_scanner_tests_failure(
    azure_config: AzureDevOpsConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError on API failure."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.post(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs?api-version=7.1",
            status=400,
            body="Bad Request",
        )

        with pytest.raises(RuntimeError, match="Failed to run pipeline"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_scanner_tests_missing_run_id(
    azure_config: AzureDevOpsConfig, test_definition: TestDefinition
) -> None:
    """dispatch_scanner_tests raises RuntimeError when run ID is missing."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.post(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs?api-version=7.1",
            status=200,
            payload={"_links": {"web": {"href": "https://dev.azure.com/test"}}},
        )

        with pytest.raises(RuntimeError, match="Run ID not found"):
            await provider.dispatch_scanner_tests(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_poll_status_in_progress(azure_config: AzureDevOpsConfig) -> None:
    """poll_status returns not complete when pipeline is in progress."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "inProgress",
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/build/builds/999/timeline?api-version=7.1",
            payload={"records": []},
        )

        is_complete, results = await provider.poll_status("999")

    assert is_complete is False
    assert results == []


async def test_poll_status_completed_success(azure_config: AzureDevOpsConfig) -> None:
    """poll_status returns complete with aggregated success status."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "succeeded",
                "name": "Scanner Pipeline",
                "createdDate": "2099-01-01T12:00:00Z",
                "finishedDate": "2099-01-01T12:01:30Z",
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        is_complete, results = await provider.poll_status("999")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "success"
    assert results[0].provider == "azure"
    assert results[0].test_name == "Scanner Pipeline"
    assert results[0].duration == 90.0


async def test_poll_status_completed_failure(azure_config: AzureDevOpsConfig) -> None:
    """poll_status returns complete with aggregated failure status."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "failed",
                "name": "Scanner Pipeline",
                "createdDate": "2099-01-01T12:00:00Z",
                "finishedDate": "2099-01-01T12:05:45Z",
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        is_complete, results = await provider.poll_status("999")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].status == "failure"
    assert results[0].test_name == "Scanner Pipeline"
    assert results[0].duration == 345.0


async def test_poll_status_api_error(azure_config: AzureDevOpsConfig) -> None:
    """poll_status raises RuntimeError on API failure."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            status=404,
            body="Not Found",
        )

        with pytest.raises(RuntimeError, match="Failed to get pipeline run"):
            await provider.poll_status("999")


async def test_map_result_all_statuses(azure_config: AzureDevOpsConfig) -> None:
    """_map_result handles all Azure DevOps result types."""
    provider = AzureDevOpsProvider(azure_config)

    assert provider._map_result("succeeded") == "success"
    assert provider._map_result("failed") == "failure"
    assert provider._map_result("canceled") == "error"
    assert provider._map_result("skipped") == "error"
    assert provider._map_result("unknown") == "error"


async def test_poll_status_no_links(azure_config: AzureDevOpsConfig) -> None:
    """poll_status handles missing _links gracefully."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "succeeded",
                "name": "Scanner Pipeline",
                "createdDate": "2099-01-01T12:00:00Z",
                "finishedDate": "2099-01-01T12:01:30Z",
            },
        )

        is_complete, results = await provider.poll_status("999")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].run_url == ""  # Empty when _links is missing


async def test_poll_status_invalid_links(azure_config: AzureDevOpsConfig) -> None:
    """poll_status handles invalid _links structure gracefully."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "succeeded",
                "name": "Scanner Pipeline",
                "createdDate": "2099-01-01T12:00:00Z",
                "finishedDate": "2099-01-01T12:01:30Z",
                "_links": "invalid",
            },
        )

        is_complete, results = await provider.poll_status("999")

    assert is_complete is True
    assert len(results) == 1
    assert results[0].run_url == ""  # Empty when _links is invalid


async def test_calculate_run_duration_success(azure_config: AzureDevOpsConfig) -> None:
    """_calculate_run_duration computes duration from timestamps."""
    provider = AzureDevOpsProvider(azure_config)

    data = {
        "createdDate": "2099-01-01T12:00:00Z",
        "finishedDate": "2099-01-01T12:05:30Z",
    }

    duration = provider._calculate_run_duration(data)
    assert duration == 330.0  # 5 minutes 30 seconds


async def test_calculate_run_duration_missing_timestamps(
    azure_config: AzureDevOpsConfig,
) -> None:
    """_calculate_run_duration returns 0.0 when timestamps are missing."""
    provider = AzureDevOpsProvider(azure_config)

    # Missing both
    assert provider._calculate_run_duration({}) == 0.0

    # Missing finishedDate
    assert (
        provider._calculate_run_duration({"createdDate": "2099-01-01T12:00:00Z"}) == 0.0
    )

    # Missing createdDate
    assert (
        provider._calculate_run_duration({"finishedDate": "2099-01-01T12:00:00Z"})
        == 0.0
    )


async def test_calculate_run_duration_invalid_format(
    azure_config: AzureDevOpsConfig,
) -> None:
    """_calculate_run_duration returns 0.0 when timestamp format is invalid."""
    provider = AzureDevOpsProvider(azure_config)

    data = {
        "createdDate": "invalid-date",
        "finishedDate": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_run_duration(data)
    assert duration == 0.0


async def test_calculate_run_duration_non_string_timestamps(
    azure_config: AzureDevOpsConfig,
) -> None:
    """_calculate_run_duration returns 0.0 when timestamps are not strings."""
    provider = AzureDevOpsProvider(azure_config)

    data = {
        "createdDate": 123456,  # Not a string
        "finishedDate": "2099-01-01T12:00:00Z",
    }

    duration = provider._calculate_run_duration(data)
    assert duration == 0.0
