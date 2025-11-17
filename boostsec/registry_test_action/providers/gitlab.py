"""GitLab CI provider implementation."""

import json
from collections.abc import Mapping
from typing import Literal
from urllib.parse import quote

import aiohttp

from boostsec.registry_test_action.models.provider_config import GitLabConfig
from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class GitLabProvider(PipelineProvider):
    """GitLab CI pipeline provider."""

    def __init__(self, config: GitLabConfig) -> None:
        """Initialize GitLab provider with configuration."""
        self.config = config
        self.base_url = "https://gitlab.com/api/v4"
        self._encoded_project_id = quote(str(config.project_id), safe="")

    async def dispatch_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Dispatch pipeline with matrix and return pipeline ID."""
        matrix_entries = test_definition.to_matrix_entries()
        matrix_json = json.dumps([entry.model_dump() for entry in matrix_entries])

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/projects/{self._encoded_project_id}/pipeline"
            headers = {
                "PRIVATE-TOKEN": self.config.token,
                "Content-Type": "application/json",
            }

            variables = [
                ("SCANNER_ID", scanner_id),
                ("REGISTRY_REF", registry_ref),
                ("REGISTRY_REPO", registry_repo),
                ("MATRIX_TESTS", matrix_json),
            ]

            payload = {
                "ref": self.config.ref,
                "variables": [{"key": key, "value": value} for key, value in variables],
            }

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 201:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to create pipeline: {response.status} {text}"
                    )

                response_data: Mapping[str, object] = await response.json()

        pipeline_id = response_data.get("id")
        if not isinstance(pipeline_id, int):
            raise RuntimeError("Pipeline ID not found in response")

        return str(pipeline_id)

    async def poll_status(self, run_id: str) -> tuple[bool, list[TestResult]]:
        """Check if all pipeline jobs are complete and get results."""
        async with aiohttp.ClientSession() as session:
            pipeline_url = (
                f"{self.base_url}/projects/{self._encoded_project_id}/"
                f"pipelines/{run_id}"
            )
            jobs_url = (
                f"{self.base_url}/projects/{self._encoded_project_id}/"
                f"pipelines/{run_id}/jobs"
            )
            headers = {
                "PRIVATE-TOKEN": self.config.token,
            }

            async with session.get(pipeline_url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline: {response.status} {text}"
                    )
                pipeline_data: Mapping[str, object] = await response.json()

            async with session.get(jobs_url, headers=headers) as response:
                if response.status != 200:  # pragma: no cover
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline jobs: {response.status} {text}"
                    )
                jobs_data: list[object] = await response.json()

        status_str = pipeline_data.get("status")
        web_url = str(pipeline_data.get("web_url", ""))

        is_complete = status_str in {
            "success",
            "failed",
            "canceled",
            "skipped",
            "manual",
        }

        if not is_complete:
            return (False, [])

        results: list[TestResult] = []
        for job in jobs_data:
            if not isinstance(job, dict):  # pragma: no cover
                continue

            job_name = str(job.get("name", ""))
            if not job_name.startswith("run-test-"):  # pragma: no cover
                continue

            job_status = str(job.get("status", ""))
            test_status = self._map_status(job_status)
            test_name = self._extract_test_name_from_job(job_name)

            duration = self._calculate_job_duration(job)

            result = TestResult(
                provider="gitlab",
                scanner="",
                test_name=test_name,
                status=test_status,
                duration=duration,
                run_url=web_url,
            )
            results.append(result)

        return (True, results)

    def _extract_test_name_from_job(self, job_name: str) -> str:
        """Extract test name from job name."""
        parts = job_name.replace("run-test-", "").split("-")
        return "-".join(parts) if parts else "unknown"

    def _calculate_job_duration(self, job: Mapping[str, object]) -> float:
        """Calculate job duration from timestamps."""
        from datetime import datetime

        started_at = job.get("started_at")
        finished_at = job.get("finished_at")

        if not isinstance(started_at, str) or not isinstance(finished_at, str):  # pragma: no cover
            return 0.0

        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            duration = (finished - started).total_seconds()
            return max(0.0, duration)
        except (ValueError, AttributeError):  # pragma: no cover
            return 0.0

    def _map_status(
        self, status: str
    ) -> Literal["success", "failure", "timeout", "error"]:
        """Map GitLab status to test status."""
        mapping: dict[str, Literal["success", "failure", "timeout", "error"]] = {
            "success": "success",
            "failed": "failure",
            "canceled": "error",
            "skipped": "error",
            "manual": "error",
        }
        return mapping.get(status, "error")
