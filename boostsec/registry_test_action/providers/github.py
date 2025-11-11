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

        run_id = await self._find_workflow_run(dispatch_time)
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

        test_status = self._map_conclusion(str(conclusion_str))

        result = TestResult(
            provider="github",
            scanner="unknown",
            test_name="unknown",
            status=test_status,
            duration=0.0,
            run_url=html_url,
        )

        return (True, result)

    async def _find_workflow_run(self, dispatch_time: float) -> str:
        """Find the workflow run that was just dispatched."""
        for attempt in range(10):
            runs = await self._fetch_recent_runs()
            run_id = self._find_matching_run(runs, dispatch_time)

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

    def _find_matching_run(
        self, runs: list[object], dispatch_time: float
    ) -> str | None:
        """Find a run that matches the dispatch time."""
        from datetime import datetime

        for run in runs:
            if not isinstance(run, dict):
                continue

            if run.get("status") == "completed":
                continue

            created_at = run.get("created_at")
            if not isinstance(created_at, str):
                continue

            created_time = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).timestamp()

            if created_time >= dispatch_time - 60:
                run_id = run.get("id")
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
