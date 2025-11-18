"""Test orchestrator for coordinating test execution on a single provider."""

import asyncio
import logging
import subprocess
from collections.abc import Awaitable
from pathlib import Path

from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider
from boostsec.registry_test_action.scanner_detector import detect_changed_scanners
from boostsec.registry_test_action.test_loader import load_all_tests

logger = logging.getLogger(__name__)


def get_repository_identifier(registry_path: Path) -> str:
    """Get the repository identifier (org/repo) from the git repository.

    Args:
        registry_path: Path to the git repository

    Returns:
        Repository identifier in org/repo format

    Raises:
        RuntimeError: If unable to get repository URL or parse it

    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],  # noqa: S607
            cwd=registry_path,
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to get repository URL from {registry_path}: {e.stderr}"
        )

    # Parse org/repo from URL
    # Supports: https://github.com/org/repo.git, git@github.com:org/repo.git
    if "github.com" in url or "gitlab.com" in url or "@" in url:
        # Remove .git suffix if present
        if url.endswith(".git"):
            url = url[:-4]

        # Extract org/repo from different URL formats
        if url.startswith("https://") or url.startswith("http://"):
            # https://github.com/org/repo
            parts = url.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
        elif "@" in url and ":" in url:
            # git@github.com:org/repo
            repo_part = url.split(":")[-1]
            return repo_part

    raise RuntimeError(f"Unable to parse repository identifier from URL: {url}")


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
        logger.info("Getting registry identifier...")
        registry_repo = get_repository_identifier(registry_path)
        logger.info(f"Registry repository: {registry_repo}")

        logger.info("Detecting changed scanners...")
        scanner_ids = await detect_changed_scanners(registry_path, base_ref, head_ref)

        if not scanner_ids:
            logger.info("No changed scanners detected")
            return []

        logger.info(f"Loading test definitions for {len(scanner_ids)} scanners...")
        test_definitions = await load_all_tests(registry_path, scanner_ids)
        logger.info(f"Loaded {len(test_definitions)} test definitions")

        logger.info("Building test tasks...")
        tasks = self._build_test_tasks(
            test_definitions, scanner_ids, registry_ref, registry_repo
        )
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
        registry_repo: str,
    ) -> list[Awaitable[list[TestResult]]]:
        """Build list of scanner test tasks to execute."""
        tasks: list[Awaitable[list[TestResult]]] = []
        for scanner_id in scanner_ids:
            test_def = test_definitions.get(scanner_id)
            if not test_def:
                continue

            task = self._run_scanner_tests(
                scanner_id, test_def, registry_ref, registry_repo
            )
            tasks.append(task)

        return tasks

    def _process_results(
        self, results: list[list[TestResult] | BaseException]
    ) -> list[TestResult]:
        """Process results from test execution."""
        final_results: list[TestResult] = []
        for result in results:
            if isinstance(result, list):
                for test_result in result:
                    test_id = f"{test_result.scanner}/{test_result.test_name}"
                    logger.info(f"Test result: {test_id} = {test_result.status}")
                    final_results.append(test_result)
            elif isinstance(result, Exception):
                logger.error(
                    f"Scanner test execution error: {type(result).__name__}: {result}",
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

    async def _run_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> list[TestResult]:
        """Run all tests for a scanner and wait for completion."""
        matrix_entries = test_definition.to_matrix_entries()
        logger.info(
            f"Dispatching scanner tests: {scanner_id} "
            f"({len(matrix_entries)} matrix jobs)"
        )

        run_id = await self.provider.dispatch_scanner_tests(
            scanner_id, test_definition, registry_ref, registry_repo
        )
        logger.info(f"Scanner tests dispatched with run_id: {run_id}")

        logger.info(f"Waiting for scanner tests completion: {scanner_id}")
        results = await self.provider.wait_for_completion(run_id)

        for result in results:
            result.scanner = scanner_id

        return results
