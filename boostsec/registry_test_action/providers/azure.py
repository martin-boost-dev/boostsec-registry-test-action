"""Azure DevOps Pipelines provider implementation."""

import base64
import json
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import AzureDevOpsConfig
from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class AzureDevOpsProvider(PipelineProvider):
    """Azure DevOps Pipelines provider."""

    def __init__(self, config: AzureDevOpsConfig) -> None:
        """Initialize Azure DevOps provider with configuration."""
        self.config = config
        self.base_url = "https://dev.azure.com"
        auth_string = f":{config.token}"
        auth_bytes = auth_string.encode("ascii")
        self._auth_header = f"Basic {base64.b64encode(auth_bytes).decode('ascii')}"

    async def dispatch_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Run pipeline with matrix and return run ID."""
        matrix_entries = test_definition.to_matrix_entries()
        matrix_json = json.dumps([entry.model_dump() for entry in matrix_entries])

        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/{self.config.organization}/{self.config.project}/"
                f"_apis/pipelines/{self.config.pipeline_id}/runs?api-version=7.1"
            )
            headers = {
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
            }
            template_params = {
                "SCANNER_ID": scanner_id,
                "REGISTRY_REF": registry_ref,
                "REGISTRY_REPO": registry_repo,
                "MATRIX_TESTS": matrix_json,
            }

            payload = {
                "templateParameters": template_params,
            }

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to run pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        run_id = data.get("id")
        if not isinstance(run_id, int):
            raise RuntimeError("Run ID not found in response")

        return str(run_id)

    async def poll_status(self, run_id: str) -> tuple[bool, list[TestResult]]:
        """Check if pipeline run is complete and get aggregated result."""
        async with aiohttp.ClientSession() as session:
            run_url = (
                f"{self.base_url}/{self.config.organization}/{self.config.project}/"
                f"_apis/pipelines/{self.config.pipeline_id}/runs/{run_id}"
                "?api-version=7.1"
            )
            headers = {
                "Authorization": self._auth_header,
            }

            async with session.get(run_url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline run: {response.status} {text}"
                    )
                run_data: Mapping[str, object] = await response.json()

        state_str = run_data.get("state")
        web_url = ""
        if isinstance(run_data.get("_links"), dict):
            links = run_data["_links"]
            if isinstance(links, dict) and isinstance(links.get("web"), dict):
                web = links["web"]
                if isinstance(web, dict):
                    web_url = str(web.get("href", ""))

        is_complete = state_str in {"completed", "canceling"}

        if not is_complete:
            return (False, [])

        # Get overall pipeline result
        result_str = str(run_data.get("result", ""))
        test_status = self._map_result(result_str)

        # Get pipeline name
        pipeline_name = str(run_data.get("name", ""))

        # Calculate duration from run-level timestamps
        duration = self._calculate_run_duration(run_data)

        # Return single aggregated result for the entire pipeline run
        result = TestResult(
            provider="azure",
            scanner="",
            test_name=pipeline_name,
            status=test_status,
            duration=duration,
            run_url=web_url,
        )

        return (True, [result])

    def _calculate_run_duration(self, run_data: Mapping[str, object]) -> float:
        """Calculate pipeline run duration from timestamps."""
        from datetime import datetime

        created_date = run_data.get("createdDate")
        finished_date = run_data.get("finishedDate")

        if not isinstance(created_date, str) or not isinstance(finished_date, str):
            return 0.0

        try:
            created = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_date.replace("Z", "+00:00"))
            duration = (finished - created).total_seconds()
            return max(0.0, duration)
        except (ValueError, AttributeError):
            return 0.0

    def _map_result(
        self, result: str
    ) -> Literal["success", "failure", "timeout", "error"]:
        """Map Azure DevOps result to test status."""
        mapping: dict[str, Literal["success", "failure", "timeout", "error"]] = {
            "succeeded": "success",
            "failed": "failure",
            "canceled": "error",
            "skipped": "error",
        }
        return mapping.get(result, "error")
