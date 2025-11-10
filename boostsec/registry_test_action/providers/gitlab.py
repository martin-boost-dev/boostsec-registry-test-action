"""GitLab CI provider implementation."""

import json
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import GitLabConfig
from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class GitLabProvider(PipelineProvider):
    """GitLab CI pipeline provider."""

    def __init__(self, config: GitLabConfig) -> None:
        """Initialize GitLab provider with configuration."""
        self.config = config
        self.base_url = "https://gitlab.com/api/v4"

    async def dispatch_test(
        self, scanner_id: str, test: Test, registry_ref: str
    ) -> str:
        """Dispatch pipeline and return pipeline ID."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/projects/{self.config.project_id}/pipeline"
            headers = {
                "PRIVATE-TOKEN": self.config.token,
                "Content-Type": "application/json",
            }
            variables = [
                {"key": "SCANNER_ID", "value": scanner_id},
                {"key": "TEST_NAME", "value": test.name},
                {"key": "TEST_TYPE", "value": test.type},
                {"key": "SOURCE_URL", "value": test.source.url},
                {"key": "SOURCE_REF", "value": test.source.ref},
                {"key": "REGISTRY_REF", "value": registry_ref},
                {"key": "SCAN_PATHS", "value": json.dumps(test.scan_paths)},
                {"key": "TIMEOUT", "value": test.timeout},
            ]

            if test.scan_configs is not None:
                variables.append(
                    {"key": "SCAN_CONFIGS", "value": json.dumps(test.scan_configs)}
                )

            payload = {
                "ref": self.config.ref,
                "variables": variables,
            }

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 201:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to create pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        pipeline_id = data.get("id")
        if not isinstance(pipeline_id, int):
            raise RuntimeError("Pipeline ID not found in response")

        return str(pipeline_id)

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if pipeline is complete and get result."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/projects/{self.config.project_id}/pipelines/{run_id}"
            )
            headers = {
                "PRIVATE-TOKEN": self.config.token,
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        status_str = data.get("status")
        web_url = str(data.get("web_url", ""))

        is_complete = status_str in {
            "success",
            "failed",
            "canceled",
            "skipped",
            "manual",
        }

        if not is_complete:
            result = TestResult(
                provider="gitlab",
                scanner="unknown",
                test_name="unknown",
                status="error",
                duration=0.0,
                run_url=web_url,
            )
            return (False, result)

        test_status = self._map_status(str(status_str))

        result = TestResult(
            provider="gitlab",
            scanner="unknown",
            test_name="unknown",
            status=test_status,
            duration=0.0,
            run_url=web_url,
        )

        return (True, result)

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
