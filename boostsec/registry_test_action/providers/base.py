"""Abstract base class for CI/CD pipeline providers."""

import asyncio
from abc import ABC, abstractmethod

from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult


class PipelineProvider(ABC):
    """Abstract base for CI/CD pipeline providers."""

    @abstractmethod
    async def dispatch_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Dispatch all tests for a scanner and return a run identifier.

        Args:
            scanner_id: Scanner identifier (e.g., "boostsecurityio/trivy-fs")
            test_definition: Complete test definition with all tests
            registry_ref: Git ref of the registry (for checking out scanner)
            registry_repo: Registry repository in org/repo format

        Returns:
            Run identifier for polling status

        """

    @abstractmethod
    async def poll_status(self, run_id: str) -> tuple[bool, list[TestResult]]:
        """Check if all tests are complete and get results.

        Args:
            run_id: Run identifier from dispatch_scanner_tests

        Returns:
            Tuple of (is_complete, list of results from all matrix jobs)

        """

    async def wait_for_completion(
        self,
        run_id: str,
        timeout: float = 1800,
        poll_interval: float = 30,
    ) -> list[TestResult]:
        """Wait for all tests to complete.

        Args:
            run_id: Run identifier from dispatch_scanner_tests
            timeout: Maximum wait time in seconds (default: 30 minutes)
            poll_interval: Seconds between polls (default: 30)

        Returns:
            List of test results (one per matrix entry)

        Raises:
            TimeoutError: If run doesn't complete within timeout

        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout

        while True:
            is_complete, results = await self.poll_status(run_id)

            if is_complete:
                return results

            current_time = asyncio.get_event_loop().time()
            if current_time >= end_time:
                raise TimeoutError(
                    f"Test run {run_id} did not complete within {timeout} seconds"
                )

            await asyncio.sleep(poll_interval)
