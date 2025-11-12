"""GitLab CI provider implementation."""

import json
from collections.abc import Mapping
from typing import Literal
from urllib.parse import quote

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
        # Store test context for each pipeline to populate TestResult correctly
        self._pipeline_context: dict[str, tuple[str, str]] = {}
        # URL-encode project_id to support both numeric IDs and paths
        self._encoded_project_id = quote(str(config.project_id), safe="")

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Dispatch pipeline using trigger token and return pipeline ID."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/projects/{self._encoded_project_id}/trigger/pipeline"
            )

            # Use FormData for trigger tokens
            data = aiohttp.FormData()
            data.add_field("token", self.config.token)
            data.add_field("ref", self.config.ref)

            # Add variables as form fields
            variables = [
                ("SCANNER_ID", scanner_id),
                ("TEST_NAME", test.name),
                ("TEST_TYPE", test.type),
                ("SOURCE_URL", test.source.url),
                ("SOURCE_REF", test.source.ref),
                ("REGISTRY_REF", registry_ref),
                ("REGISTRY_REPO", registry_repo),
                ("SCAN_PATHS", json.dumps(test.scan_paths)),
                ("TIMEOUT", test.timeout),
            ]

            if test.scan_configs is not None:
                variables.append(("SCAN_CONFIGS", json.dumps(test.scan_configs)))

            for key, value in variables:
                data.add_field(f"variables[{key}]", value)

            async with session.post(url, data=data) as response:
                if response.status != 201:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to create pipeline: {response.status} {text}"
                    )

                response_data: Mapping[str, object] = await response.json()

        pipeline_id = response_data.get("id")
        if not isinstance(pipeline_id, int):
            raise RuntimeError("Pipeline ID not found in response")

        pipeline_id_str = str(pipeline_id)

        # Store test context for later use in poll_status
        self._pipeline_context[pipeline_id_str] = (scanner_id, test.name)

        return pipeline_id_str

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if pipeline is complete and get result."""
        # Retrieve stored test context
        scanner, test_name = self._pipeline_context.get(run_id, ("unknown", "unknown"))

        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/projects/{self._encoded_project_id}/"
                f"pipelines/{run_id}"
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
                scanner=scanner,
                test_name=test_name,
                status="error",
                duration=0.0,
                run_url=web_url,
            )
            return (False, result)

        test_status = self._map_status(str(status_str))

        result = TestResult(
            provider="gitlab",
            scanner=scanner,
            test_name=test_name,
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
