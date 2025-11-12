"""GitHub Actions provider implementation."""

import asyncio
import json
import time
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import GitHubConfig
from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class GitHubProvider(PipelineProvider):
    """GitHub Actions pipeline provider."""

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

        run_id = await self._find_workflow_run(dispatch_time, scanner_id, test.name)
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
        self, dispatch_time: float, scanner_id: str, test_name: str
    ) -> str:
        """Find the workflow run that was just dispatched.

        Matches runs by time window and scanner_id in display_title.
        """
        for attempt in range(10):
            runs = await self._fetch_recent_runs()
            run_id = self._find_matching_run(runs, dispatch_time, scanner_id, test_name)

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

    def _is_matching_run(self, run: object, scanner_id: str, test_name: str) -> bool:
        """Check if run matches scanner_id and test_name in display_title."""
        if not isinstance(run, dict):
            return False

        if run.get("status") == "completed":
            return False

        display_title = run.get("display_title")
        if not isinstance(display_title, str):
            return False

        if scanner_id not in display_title:
            return False

        if test_name not in display_title:
            return False

        return True

    def _find_matching_run(
        self, runs: list[object], dispatch_time: float, scanner_id: str, test_name: str
    ) -> str | None:
        """Find a run that matches the dispatch time and scanner_id.

        Matches by:
        1. Time window (within 60 seconds of dispatch)
        2. Scanner ID in display_title
        3. Test name in display_title (for additional precision)
        """
        from datetime import datetime

        for run in runs:
            if not self._is_matching_run(run, scanner_id, test_name):
                continue

            # At this point, run is guaranteed to be a dict by _is_matching_run
            # Check time window
            created_at = run.get("created_at")  # type: ignore[attr-defined]
            if not isinstance(created_at, str):
                continue

            created_time = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).timestamp()

            if created_time >= dispatch_time - 60:
                run_id = run.get("id")  # type: ignore[attr-defined]
                if isinstance(run_id, int):
                    return str(run_id)

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
