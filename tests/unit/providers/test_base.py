"""Tests for base pipeline provider."""

from unittest.mock import AsyncMock

import pytest

from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class TestPipelineProvider(PipelineProvider):
    """Concrete implementation for testing."""

    def __init__(self) -> None:
        """Initialize test provider with mocks."""
        self.dispatch_test_mock = AsyncMock()
        self.poll_status_mock = AsyncMock()

    async def dispatch_test(  # pragma: no cover
        self, scanner_id: str, test: Test, registry_ref: str
    ) -> str:
        """Mock implementation."""
        result: str = await self.dispatch_test_mock(scanner_id, test, registry_ref)
        return result

    async def poll_status(  # pragma: no cover
        self, run_id: str
    ) -> tuple[bool, TestResult]:
        """Mock implementation."""
        result: tuple[bool, TestResult] = await self.poll_status_mock(run_id)
        return result


async def test_wait_for_completion_immediate() -> None:
    """wait_for_completion returns immediately when test is complete."""
    provider = TestPipelineProvider()
    result = TestResult(
        provider="test",
        scanner="org/scanner",
        test_name="test1",
        status="success",
        duration=10.0,
    )

    provider.poll_status_mock.return_value = (True, result)

    final_result = await provider.wait_for_completion("run123")

    assert final_result == result
    provider.poll_status_mock.assert_called_once_with("run123")


async def test_wait_for_completion_after_polling() -> None:
    """wait_for_completion polls until test completes."""
    provider = TestPipelineProvider()
    result = TestResult(
        provider="test",
        scanner="org/scanner",
        test_name="test1",
        status="success",
        duration=10.0,
    )

    provider.poll_status_mock.side_effect = [
        (False, result),
        (False, result),
        (True, result),
    ]

    final_result = await provider.wait_for_completion("run123", poll_interval=0.01)

    assert final_result == result
    assert provider.poll_status_mock.call_count == 3


async def test_wait_for_completion_timeout() -> None:
    """wait_for_completion raises TimeoutError when timeout exceeded."""
    provider = TestPipelineProvider()
    result = TestResult(
        provider="test",
        scanner="org/scanner",
        test_name="test1",
        status="success",
        duration=10.0,
    )

    provider.poll_status_mock.return_value = (False, result)

    with pytest.raises(TimeoutError, match="did not complete within 1 seconds"):
        await provider.wait_for_completion("run123", timeout=1, poll_interval=0.5)


async def test_wait_for_completion_custom_timeout() -> None:
    """wait_for_completion respects custom timeout."""
    provider = TestPipelineProvider()
    result = TestResult(
        provider="test",
        scanner="org/scanner",
        test_name="test1",
        status="success",
        duration=10.0,
    )

    call_count = 0

    async def side_effect(_run_id: str) -> tuple[bool, TestResult]:
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            return (True, result)
        return (False, result)

    provider.poll_status_mock.side_effect = side_effect

    final_result = await provider.wait_for_completion(
        "run123", timeout=10, poll_interval=0.01
    )

    assert final_result == result
    assert call_count == 3
