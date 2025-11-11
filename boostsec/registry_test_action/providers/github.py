"""GitHub Actions provider implementation."""

import asyncio
import json
import time
import uuid
from collections.abc import Mapping
from typing import ClassVar, Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import GitHubConfig
from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class GitHubProvider(PipelineProvider):
    """GitHub Actions pipeline provider."""

    # Class-level set to track claimed run IDs across concurrent dispatches
    _claimed_runs: ClassVar[set[str]] = set()
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, config: GitHubConfig) -> None:
        """Initialize GitHub provider with configuration."""
        self.config = config
        self.base_url = config.base_url

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Dispatch workflow and return run ID."""
        dispatch_time = time.time()
        correlation_id = str(uuid.uuid4())

        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repos/{self.config.owner}/{self.config.repo}/"
                f"actions/workflows/{self.config.workflow_id}/dispatches"
            )
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/vnd.github+json",
            }
            inputs = {
                "correlation_id": correlation_id,
                "scanner_id": scanner_id,
                "test_name": test.name,
                "test_type": test.type,
                "source_url": test.source.url,
                "source_ref": test.source.ref,
                "registry_ref": registry_ref,
                "registry_repo": registry_repo,
                "scan_paths": json.dumps(test.scan_paths),
                "timeout": test.timeout,
            }

            if test.scan_configs is not None:
                inputs["scan_configs"] = json.dumps(test.scan_configs)

            payload = {
                "ref": self.config.ref,
                "inputs": inputs,
            }

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 204:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to dispatch workflow: {response.status} {text}"
                    )

        await asyncio.sleep(5)

        run_id = await self._find_workflow_run(dispatch_time, correlation_id)
        return run_id

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if test run is complete and get result."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repos/{self.config.owner}/{self.config.repo}/"
                f"actions/runs/{run_id}"
            )
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/vnd.github+json",
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get workflow run: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        status_str = data.get("status")
        conclusion_str = data.get("conclusion")
        html_url = str(data.get("html_url", ""))

        is_complete = status_str == "completed"

        if not is_complete:
            result = TestResult(
                provider="github",
                scanner="unknown",
                test_name="unknown",
                status="error",
                duration=0.0,
                run_url=html_url,
            )
            return (False, result)

        # Calculate duration from workflow run timestamps
        duration = self._calculate_duration(data)
        test_status = self._map_conclusion(str(conclusion_str))

        result = TestResult(
            provider="github",
            scanner="unknown",
            test_name="unknown",
            status=test_status,
            duration=duration,
            run_url=html_url,
        )

        return (True, result)

    async def _find_workflow_run(
        self, dispatch_time: float, correlation_id: str
    ) -> str:
        """Find the workflow run that was just dispatched."""
        for attempt in range(10):
            runs = await self._fetch_recent_runs()
            run_id = await self._find_matching_run(runs, dispatch_time, correlation_id)

            if run_id:
                return run_id

            if attempt < 9:
                await asyncio.sleep(2)

        raise RuntimeError("Could not find dispatched workflow run")

    async def _fetch_recent_runs(self) -> list[object]:
        """Fetch recent workflow runs."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repos/{self.config.owner}/{self.config.repo}/"
                "actions/runs"
            )
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/vnd.github+json",
            }
            params = {"per_page": "5"}

            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to list workflow runs: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        runs = data.get("workflow_runs", [])
        return runs if isinstance(runs, list) else []

    def _validate_and_extract_run(
        self, run: object, dispatch_time: float
    ) -> tuple[str, float] | None:
        """Validate run data and extract run ID with time difference.

        Returns tuple of (run_id, time_diff) or None if invalid.
        """
        from datetime import datetime

        if not isinstance(run, dict):
            return None

        if run.get("status") == "completed":
            return None

        run_id_int = run.get("id")
        if not isinstance(run_id_int, int):
            return None

        run_id = str(run_id_int)

        # Skip already claimed runs
        if run_id in GitHubProvider._claimed_runs:
            return None

        created_at = run.get("created_at")
        if not isinstance(created_at, str):
            return None

        created_time = datetime.fromisoformat(
            created_at.replace("Z", "+00:00")
        ).timestamp()

        # Use tighter time window (10 seconds) to reduce false matches
        time_diff = abs(created_time - dispatch_time)
        if time_diff <= 10:
            return (run_id, time_diff)

        return None

    async def _find_matching_run(
        self, runs: list[object], dispatch_time: float, correlation_id: str
    ) -> str | None:
        """Find a run that matches the dispatch time.

        Uses a class-level lock and claimed runs set to prevent concurrent
        tests from matching the same run. The correlation_id is passed to
        the workflow but cannot be verified via GitHub API.
        """
        # Build list of candidate runs with their created times
        candidates: list[tuple[str, float]] = []

        async with GitHubProvider._lock:
            for run in runs:
                result = self._validate_and_extract_run(run, dispatch_time)
                if result:
                    candidates.append(result)

            # Claim the run with the smallest time difference
            if candidates:
                candidates.sort(key=lambda x: x[1])
                best_run_id = candidates[0][0]
                GitHubProvider._claimed_runs.add(best_run_id)
                return best_run_id

        return None

    def _calculate_duration(self, data: Mapping[str, object]) -> float:
        """Calculate workflow run duration from timestamps.

        Args:
            data: Workflow run data from GitHub API

        Returns:
            Duration in seconds, or 0.0 if timestamps unavailable

        """
        from datetime import datetime

        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if not isinstance(created_at, str) or not isinstance(updated_at, str):
            return 0.0

        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            duration = (updated - created).total_seconds()
            return max(0.0, duration)  # Ensure non-negative
        except (ValueError, AttributeError):
            return 0.0

    def _map_conclusion(
        self, conclusion: str
    ) -> Literal["success", "failure", "timeout", "error"]:
        """Map GitHub conclusion to test status."""
        mapping: dict[str, Literal["success", "failure", "timeout", "error"]] = {
            "success": "success",
            "failure": "failure",
            "cancelled": "error",
            "timed_out": "timeout",
            "action_required": "error",
            "neutral": "success",
            "skipped": "error",
            "stale": "error",
        }
        return mapping.get(conclusion, "error")
