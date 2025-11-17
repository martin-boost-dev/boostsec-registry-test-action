"""Tests for base pipeline provider."""

from unittest.mock import AsyncMock

import pytest

from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class TestPipelineProvider(PipelineProvider):
    """Concrete implementation for testing."""

    __test__ = False

    def __init__(self) -> None:
        """Initialize test provider with mocks."""
        self.dispatch_scanner_tests_mock = AsyncMock()
        self.poll_status_mock = AsyncMock()

    async def dispatch_scanner_tests(  # pragma: no cover
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Mock implementation."""
        result: str = await self.dispatch_scanner_tests_mock(
            scanner_id, test_definition, registry_ref, registry_repo
        )
        return result

    async def poll_status(  # pragma: no cover
        self, run_id: str
    ) -> tuple[bool, list[TestResult]]:
        """Mock implementation."""
        result: tuple[bool, list[TestResult]] = await self.poll_status_mock(run_id)
        return result


async def test_wait_for_completion_immediate() -> None:
    """wait_for_completion returns immediately when test is complete."""
    provider = TestPipelineProvider()
    results = [
        TestResult(
            provider="test",
            scanner="org/scanner",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    provider.poll_status_mock.return_value = (True, results)

    final_results = await provider.wait_for_completion("run123")

    assert final_results == results
    provider.poll_status_mock.assert_called_once_with("run123")


async def test_wait_for_completion_after_polling() -> None:
    """wait_for_completion polls until test completes."""
    provider = TestPipelineProvider()
    results = [
        TestResult(
            provider="test",
            scanner="org/scanner",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    provider.poll_status_mock.side_effect = [
        (False, results),
        (False, results),
        (True, results),
    ]

    final_results = await provider.wait_for_completion("run123", poll_interval=0.01)

    assert final_results == results
    assert provider.poll_status_mock.call_count == 3


async def test_wait_for_completion_timeout() -> None:
    """wait_for_completion raises TimeoutError when timeout exceeded."""
    provider = TestPipelineProvider()
    results = [
        TestResult(
            provider="test",
            scanner="org/scanner",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    provider.poll_status_mock.return_value = (False, results)

    with pytest.raises(TimeoutError, match="did not complete within 1 seconds"):
        await provider.wait_for_completion("run123", timeout=1, poll_interval=0.5)


async def test_wait_for_completion_custom_timeout() -> None:
    """wait_for_completion respects custom timeout."""
    provider = TestPipelineProvider()
    results = [
        TestResult(
            provider="test",
            scanner="org/scanner",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    call_count = 0

    async def side_effect(_run_id: str) -> tuple[bool, list[TestResult]]:
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            return (True, results)
        return (False, results)

    provider.poll_status_mock.side_effect = side_effect

    final_results = await provider.wait_for_completion(
        "run123", timeout=10, poll_interval=0.01
    )

    assert final_results == results
    assert call_count == 3
