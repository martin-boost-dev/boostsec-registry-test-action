"""Azure DevOps Pipelines provider implementation."""

import json
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import AzureDevOpsConfig
from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class AzureDevOpsProvider(PipelineProvider):
    """Azure DevOps Pipelines provider."""

    def __init__(self, config: AzureDevOpsConfig) -> None:
        """Initialize Azure DevOps provider with configuration."""
        self.config = config
        self.base_url = "https://dev.azure.com"

    async def dispatch_test(
        self, scanner_id: str, test: Test, registry_ref: str
    ) -> str:
        """Run pipeline and return run ID."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/{self.config.organization}/{self.config.project}/"
                f"_apis/pipelines/{self.config.pipeline_id}/runs?api-version=7.1"
            )
            headers = {
                "Authorization": f"Basic {self.config.token}",
                "Content-Type": "application/json",
            }
            template_params = {
                "SCANNER_ID": scanner_id,
                "TEST_NAME": test.name,
                "TEST_TYPE": test.type,
                "SOURCE_URL": test.source.url,
                "SOURCE_REF": test.source.ref,
                "REGISTRY_REF": registry_ref,
                "SCAN_PATHS": json.dumps(test.scan_paths),
                "TIMEOUT": test.timeout,
            }

            if test.scan_configs is not None:
                template_params["SCAN_CONFIGS"] = json.dumps(test.scan_configs)

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

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if pipeline run is complete and get result."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/{self.config.organization}/{self.config.project}/"
                f"_apis/pipelines/{self.config.pipeline_id}/runs/{run_id}"
                "?api-version=7.1"
            )
            headers = {
                "Authorization": f"Basic {self.config.token}",
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline run: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        state_str = data.get("state")
        result_str = data.get("result")
        web_url = ""
        if isinstance(data.get("_links"), dict):
            links = data["_links"]
            if isinstance(links, dict) and isinstance(links.get("web"), dict):
                web = links["web"]
                if isinstance(web, dict):
                    web_url = str(web.get("href", ""))

        is_complete = state_str in {"completed", "canceling"}

        if not is_complete:
            result = TestResult(
                provider="azure",
                scanner="unknown",
                test_name="unknown",
                status="error",
                duration=0.0,
                run_url=web_url,
            )
            return (False, result)

        test_status = self._map_result(str(result_str))

        result = TestResult(
            provider="azure",
            scanner="unknown",
            test_name="unknown",
            status=test_status,
            duration=0.0,
            run_url=web_url,
        )

        return (True, result)

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
