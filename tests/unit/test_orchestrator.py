"""Tests for test orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.orchestrator import TestOrchestrator
from boostsec.registry_test_action.providers.base import PipelineProvider


class TestProvider(PipelineProvider):
    """Test provider implementation."""

    __test__ = False

    def __init__(self) -> None:
        """Initialize test provider with mocks."""
        self.dispatch_test_mock = AsyncMock()
        self.wait_for_completion_mock = AsyncMock()

    async def dispatch_test(
        self, scanner_id: str, test: Test, registry_ref: str
    ) -> str:
        """Mock dispatch."""
        result: str = await self.dispatch_test_mock(scanner_id, test, registry_ref)
        return result

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Mock poll status."""
        return (
            True,
            TestResult(
                provider="test",
                scanner="",
                test_name="",
                status="success",
                duration=0.0,
            ),
        )  # pragma: no cover

    async def wait_for_completion(
        self, run_id: str, timeout: float = 1800, poll_interval: float = 30
    ) -> TestResult:
        """Mock wait for completion."""
        result: TestResult = await self.wait_for_completion_mock(
            run_id, timeout, poll_interval
        )
        return result


@pytest.fixture
def test_provider() -> TestProvider:
    """Create test provider."""
    return TestProvider()


async def test_run_tests_no_changed_scanners(test_provider: TestProvider) -> None:
    """run_tests returns empty list when no scanners changed."""
    orchestrator = TestOrchestrator(test_provider)

    with patch(
        "boostsec.registry_test_action.orchestrator.detect_changed_scanners"
    ) as mock_detect:
        mock_detect.return_value = []

        results = await orchestrator.run_tests(
            Path("/test/registry"), "main", "feature", "feature"
        )

    assert results == []
    test_provider.dispatch_test_mock.assert_not_called()


async def test_run_tests_single_scanner_single_test(
    test_provider: TestProvider,
) -> None:
    """run_tests executes single test for single scanner."""
    orchestrator = TestOrchestrator(test_provider)

    test = Test(
        name="test1",
        type="source-code",
        source=TestSource(url="https://github.com/test/repo.git", ref="main"),
        scan_paths=["."],
    )
    test_def = TestDefinition(version="1.0", tests=[test])

    test_provider.dispatch_test_mock.return_value = "run123"
    test_provider.wait_for_completion_mock.return_value = TestResult(
        provider="test",
        scanner="",
        test_name="",
        status="success",
        duration=10.0,
    )

    with (
        patch(
            "boostsec.registry_test_action.orchestrator.detect_changed_scanners"
        ) as mock_detect,
        patch("boostsec.registry_test_action.orchestrator.load_all_tests") as mock_load,
    ):
        mock_detect.return_value = ["scanner1"]
        mock_load.return_value = {"scanner1": test_def}

        results = await orchestrator.run_tests(
            Path("/test/registry"), "main", "feature", "feature"
        )

    assert len(results) == 1
    assert results[0].scanner == "scanner1"
    assert results[0].test_name == "test1"
    assert results[0].status == "success"
    test_provider.dispatch_test_mock.assert_called_once_with(
        "scanner1", test, "feature"
    )


async def test_run_tests_multiple_scanners_multiple_tests(
    test_provider: TestProvider,
) -> None:
    """run_tests executes all tests for all scanners in parallel."""
    orchestrator = TestOrchestrator(test_provider)

    test1 = Test(
        name="test1",
        type="source-code",
        source=TestSource(url="https://github.com/test/repo.git", ref="main"),
        scan_paths=["."],
    )
    test2 = Test(
        name="test2",
        type="docker-image",
        source=TestSource(url="https://github.com/test/repo2.git", ref="main"),
        scan_paths=["."],
    )
    test_def1 = TestDefinition(version="1.0", tests=[test1, test2])
    test_def2 = TestDefinition(version="1.0", tests=[test1])

    test_provider.dispatch_test_mock.side_effect = ["run1", "run2", "run3"]
    test_provider.wait_for_completion_mock.side_effect = [
        TestResult(
            provider="test", scanner="", test_name="", status="success", duration=10.0
        ),
        TestResult(
            provider="test", scanner="", test_name="", status="failure", duration=15.0
        ),
        TestResult(
            provider="test", scanner="", test_name="", status="success", duration=20.0
        ),
    ]

    with (
        patch(
            "boostsec.registry_test_action.orchestrator.detect_changed_scanners"
        ) as mock_detect,
        patch("boostsec.registry_test_action.orchestrator.load_all_tests") as mock_load,
    ):
        mock_detect.return_value = ["scanner1", "scanner2"]
        mock_load.return_value = {"scanner1": test_def1, "scanner2": test_def2}

        results = await orchestrator.run_tests(
            Path("/test/registry"), "main", "feature", "feature"
        )

    assert len(results) == 3
    assert test_provider.dispatch_test_mock.call_count == 3
    assert test_provider.wait_for_completion_mock.call_count == 3


async def test_run_tests_handles_exceptions(test_provider: TestProvider) -> None:
    """run_tests handles exceptions and returns error results."""
    orchestrator = TestOrchestrator(test_provider)

    test = Test(
        name="test1",
        type="source-code",
        source=TestSource(url="https://github.com/test/repo.git", ref="main"),
        scan_paths=["."],
    )
    test_def = TestDefinition(version="1.0", tests=[test])

    test_provider.dispatch_test_mock.return_value = "run123"
    test_provider.wait_for_completion_mock.side_effect = RuntimeError("API Error")

    with (
        patch(
            "boostsec.registry_test_action.orchestrator.detect_changed_scanners"
        ) as mock_detect,
        patch("boostsec.registry_test_action.orchestrator.load_all_tests") as mock_load,
    ):
        mock_detect.return_value = ["scanner1"]
        mock_load.return_value = {"scanner1": test_def}

        results = await orchestrator.run_tests(
            Path("/test/registry"), "main", "feature", "feature"
        )

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].message == "API Error"


async def test_run_tests_skips_scanners_without_test_definitions(
    test_provider: TestProvider,
) -> None:
    """run_tests skips scanners that don't have test definitions."""
    orchestrator = TestOrchestrator(test_provider)

    with (
        patch(
            "boostsec.registry_test_action.orchestrator.detect_changed_scanners"
        ) as mock_detect,
        patch("boostsec.registry_test_action.orchestrator.load_all_tests") as mock_load,
    ):
        mock_detect.return_value = ["scanner1", "scanner2"]
        mock_load.return_value = {}

        results = await orchestrator.run_tests(
            Path("/test/registry"), "main", "feature", "feature"
        )

    assert results == []
    test_provider.dispatch_test_mock.assert_not_called()
