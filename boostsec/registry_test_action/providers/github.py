"""GitHub Actions provider implementation."""

import asyncio
import json
import time
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import GitHubConfig
from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class GitHubProvider(PipelineProvider):
    """GitHub Actions pipeline provider."""

    def __init__(self, config: GitHubConfig) -> None:
        """Initialize GitHub provider with configuration."""
        self.config = config
        self.base_url = config.base_url

    async def dispatch_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Dispatch workflow with matrix and return run ID."""
        dispatch_time = time.time()

        matrix_entries = test_definition.to_matrix_entries()
        matrix_json = json.dumps([entry.model_dump() for entry in matrix_entries])

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
                "registry_ref": registry_ref,
                "registry_repo": registry_repo,
                "matrix_tests": matrix_json,
            }

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

        run_id = await self._find_workflow_run(dispatch_time, scanner_id)
        return run_id

    async def poll_status(self, run_id: str) -> tuple[bool, list[TestResult]]:
        """Check if workflow run is complete and get aggregated result."""
        async with aiohttp.ClientSession() as session:
            run_url = (
                f"{self.base_url}/repos/{self.config.owner}/{self.config.repo}/"
                f"actions/runs/{run_id}"
            )
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/vnd.github+json",
            }

            async with session.get(run_url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get workflow run: {response.status} {text}"
                    )
                run_data: Mapping[str, object] = await response.json()

        status_str = run_data.get("status")
        html_url = str(run_data.get("html_url", ""))

        is_complete = status_str == "completed"

        if not is_complete:
            return (False, [])

        # Calculate overall duration from workflow run timestamps
        duration = self._calculate_run_duration(run_data)

        # Map workflow conclusion to test status
        conclusion = str(run_data.get("conclusion", ""))
        test_status = self._map_conclusion(conclusion)

        # Get workflow name for test identification
        workflow_name = str(run_data.get("name", ""))

        # Return single aggregated result for the entire workflow run
        result = TestResult(
            provider="github",
            scanner="",
            test_name=workflow_name,
            status=test_status,
            duration=duration,
            run_url=html_url,
        )

        return (True, [result])

    def _calculate_run_duration(self, run_data: Mapping[str, object]) -> float:
        """Calculate workflow run duration from timestamps."""
        from datetime import datetime

        created_at = run_data.get("created_at")
        updated_at = run_data.get("updated_at")

        if not isinstance(created_at, str) or not isinstance(updated_at, str):
            return 0.0

        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            duration = (updated - created).total_seconds()
            return max(0.0, duration)
        except (ValueError, AttributeError):
            return 0.0

    async def _find_workflow_run(self, dispatch_time: float, scanner_id: str) -> str:
        """Find the workflow run that was just dispatched."""
        for attempt in range(10):
            runs = await self._fetch_recent_runs()
            run_id = self._find_matching_run(runs, dispatch_time, scanner_id)

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

    def _is_matching_run(self, run: object, scanner_id: str) -> bool:
        """Check if run matches scanner_id in display_title."""
        if not isinstance(run, dict):
            return False

        if run.get("status") == "completed":
            return False

        display_title = run.get("display_title")
        if not isinstance(display_title, str):
            return False

        if scanner_id not in display_title:
            return False

        return True

    def _find_matching_run(
        self, runs: list[object], dispatch_time: float, scanner_id: str
    ) -> str | None:
        """Find a run that matches the dispatch time and scanner_id."""
        from datetime import datetime

        for run in runs:
            if not self._is_matching_run(run, scanner_id):
                continue

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
