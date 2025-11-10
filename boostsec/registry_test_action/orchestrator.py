"""Test orchestrator for coordinating test execution on a single provider."""

import asyncio
import logging
from collections.abc import Awaitable
from pathlib import Path

from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
)
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider
from boostsec.registry_test_action.scanner_detector import detect_changed_scanners
from boostsec.registry_test_action.test_loader import load_all_tests

logger = logging.getLogger(__name__)


class TestOrchestrator:
    """Orchestrates test execution on a single provider."""

    __test__ = False

    def __init__(self, provider: PipelineProvider) -> None:
        """Initialize orchestrator with a single provider."""
        self.provider = provider

    async def run_tests(
        self,
        registry_path: Path,
        base_ref: str,
        head_ref: str,
        registry_ref: str,
    ) -> list[TestResult]:
        """Run all tests for changed scanners on the configured provider."""
        logger.info("Orchestrator: Detecting changed scanners...")
        scanner_ids = await detect_changed_scanners(registry_path, base_ref, head_ref)

        if not scanner_ids:
            logger.info("No changed scanners detected")
            return []

        logger.info(f"Loading test definitions for {len(scanner_ids)} scanners...")
        test_definitions = await load_all_tests(registry_path, scanner_ids)
        logger.info(f"Loaded {len(test_definitions)} test definitions")

        logger.info("Building test tasks...")
        tasks = self._build_test_tasks(test_definitions, scanner_ids, registry_ref)
        logger.info(f"Built {len(tasks)} test tasks")

        logger.info("Executing tests...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Test execution completed")

        return self._process_results(list(results))

    def _build_test_tasks(
        self,
        test_definitions: dict[str, TestDefinition],
        scanner_ids: list[str],
        registry_ref: str,
    ) -> list[Awaitable[TestResult]]:
        """Build list of test tasks to execute."""
        tasks: list[Awaitable[TestResult]] = []
        for scanner_id in scanner_ids:
            test_def = test_definitions.get(scanner_id)
            if not test_def:
                continue

            for test in test_def.tests:
                task = self._run_single_test(scanner_id, test, registry_ref)
                tasks.append(task)

        return tasks

    def _process_results(
        self, results: list[TestResult | BaseException]
    ) -> list[TestResult]:
        """Process results from test execution."""
        final_results: list[TestResult] = []
        for result in results:
            if isinstance(result, TestResult):
                test_id = f"{result.scanner}/{result.test_name}"
                logger.info(f"Test result: {test_id} = {result.status}")
                final_results.append(result)
            elif isinstance(result, Exception):
                logger.error(
                    f"Test execution error: {type(result).__name__}: {result}",
                    exc_info=result,
                )
                error_result = TestResult(
                    provider="unknown",
                    scanner="unknown",
                    test_name="unknown",
                    status="error",
                    duration=0.0,
                    message=str(result),
                )
                final_results.append(error_result)
        return final_results

    async def _run_single_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str,
    ) -> TestResult:
        """Run a single test on the provider and wait for completion."""
        logger.info(f"Dispatching test: {scanner_id}/{test.name}")
        run_id = await self.provider.dispatch_test(scanner_id, test, registry_ref)
        logger.info(f"Test dispatched with run_id: {run_id}")

        logger.info(f"Waiting for test completion: {scanner_id}/{test.name}")
        result = await self.provider.wait_for_completion(run_id)

        result.scanner = scanner_id
        result.test_name = test.name

        return result
