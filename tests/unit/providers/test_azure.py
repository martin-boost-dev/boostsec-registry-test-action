"""Tests for Azure DevOps Pipelines provider."""

import pytest
from aioresponses import aioresponses

from boostsec.registry_test_action.models.provider_config import AzureDevOpsConfig
from boostsec.registry_test_action.models.test_definition import Test, TestSource
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
    azure_config: AzureDevOpsConfig, test_definition: Test
) -> None:
    """dispatch_test successfully runs pipeline."""
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

        run_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_definition,
            "main",
            "test/registry",
        )

    assert run_id == "999"


async def test_dispatch_test_with_scan_configs(azure_config: AzureDevOpsConfig) -> None:
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

        run_id = await provider.dispatch_test(
            "boostsecurityio/trivy-fs",
            test_with_configs,
            "main",
            "test/registry",
        )

    assert run_id == "999"


async def test_dispatch_test_failure(
    azure_config: AzureDevOpsConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError on API failure."""
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
            await provider.dispatch_test(
                "boostsecurityio/trivy-fs",
                test_definition,
                "main",
                "test/registry",
            )


async def test_dispatch_test_missing_run_id(
    azure_config: AzureDevOpsConfig, test_definition: Test
) -> None:
    """dispatch_test raises RuntimeError when run ID is missing."""
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
            await provider.dispatch_test(
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

        is_complete, result = await provider.poll_status("999")

    assert is_complete is False
    assert result.provider == "azure"
    assert result.status == "error"


async def test_poll_status_completed_success(azure_config: AzureDevOpsConfig) -> None:
    """poll_status returns complete with success status."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "succeeded",
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        is_complete, result = await provider.poll_status("999")

    assert is_complete is True
    assert result.status == "success"
    assert result.provider == "azure"


async def test_poll_status_completed_failure(azure_config: AzureDevOpsConfig) -> None:
    """poll_status returns complete with failure status."""
    provider = AzureDevOpsProvider(azure_config)

    with aioresponses() as m:
        m.get(
            f"https://dev.azure.com/{azure_config.organization}/"
            f"{azure_config.project}/_apis/pipelines/{azure_config.pipeline_id}/"
            "runs/999?api-version=7.1",
            payload={
                "state": "completed",
                "result": "failed",
                "_links": {
                    "web": {"href": "https://dev.azure.com/test-org/pipelines/999"}
                },
            },
        )

        is_complete, result = await provider.poll_status("999")

    assert is_complete is True
    assert result.status == "failure"


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
            },
        )

        is_complete, result = await provider.poll_status("999")

    assert is_complete is True
    assert result.run_url == ""


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
                "_links": "invalid",
            },
        )

        is_complete, result = await provider.poll_status("999")

    assert is_complete is True
    assert result.run_url == ""
