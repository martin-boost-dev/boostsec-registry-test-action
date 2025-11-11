"""Abstract base class for CI/CD pipeline providers."""

import asyncio
from abc import ABC, abstractmethod

from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult


class PipelineProvider(ABC):
    """Abstract base for CI/CD pipeline providers."""

    @abstractmethod
    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str,
        registry_url: str,
    ) -> str:
        """Dispatch a test run and return a run identifier.

        Args:
            scanner_id: Scanner identifier (e.g., "boostsecurityio/trivy-fs")
            test: Test definition to execute
            registry_ref: Git ref of the registry (for checking out scanner)
            registry_url: Git URL of the registry repository

        Returns:
            Run identifier for polling status

        """

    @abstractmethod
    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if test run is complete and get result.

        Args:
            run_id: Run identifier from dispatch_test

        Returns:
            Tuple of (is_complete, result)

        """

    async def wait_for_completion(
        self,
        run_id: str,
        timeout: float = 1800,
        poll_interval: float = 30,
    ) -> TestResult:
        """Wait for test run to complete.

        Args:
            run_id: Run identifier from dispatch_test
            timeout: Maximum wait time in seconds (default: 30 minutes)
            poll_interval: Seconds between polls (default: 30)

        Returns:
            Final test result

        Raises:
            TimeoutError: If run doesn't complete within timeout

        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout

        while True:
            is_complete, result = await self.poll_status(run_id)

            if is_complete:
                return result

            current_time = asyncio.get_event_loop().time()
            if current_time >= end_time:
                raise TimeoutError(
                    f"Test run {run_id} did not complete within {timeout} seconds"
                )

            await asyncio.sleep(poll_interval)
