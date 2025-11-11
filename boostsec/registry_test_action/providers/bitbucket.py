"""Bitbucket Pipelines provider implementation."""

import base64
import json
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import BitbucketConfig
from boostsec.registry_test_action.models.test_definition import Test
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class BitbucketProvider(PipelineProvider):
    """Bitbucket Pipelines provider."""

    def __init__(self, config: BitbucketConfig) -> None:
        """Initialize Bitbucket provider with configuration."""
        self.config = config
        self.base_url = "https://api.bitbucket.org/2.0"

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Trigger pipeline and return pipeline UUID."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repositories/{self.config.workspace}/"
                f"{self.config.repo_slug}/pipelines/"
            )
            auth_str = f"{self.config.username}:{self.config.app_password}"
            auth_bytes = auth_str.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json",
            }
            variables = [
                {"key": "SCANNER_ID", "value": scanner_id},
                {"key": "TEST_NAME", "value": test.name},
                {"key": "TEST_TYPE", "value": test.type},
                {"key": "SOURCE_URL", "value": test.source.url},
                {"key": "SOURCE_REF", "value": test.source.ref},
                {"key": "REGISTRY_REF", "value": registry_ref},
                {"key": "REGISTRY_REPO", "value": registry_repo},
                {"key": "SCAN_PATHS", "value": json.dumps(test.scan_paths)},
                {"key": "TIMEOUT", "value": test.timeout},
            ]

            if test.scan_configs is not None:
                variables.append(
                    {"key": "SCAN_CONFIGS", "value": json.dumps(test.scan_configs)}
                )

            payload = {
                "target": {
                    "ref_type": "branch",
                    "type": "pipeline_ref_target",
                    "ref_name": "main",
                },
                "variables": variables,
            }

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 201:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to trigger pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        pipeline_uuid = data.get("uuid")
        if not isinstance(pipeline_uuid, str):
            raise RuntimeError("Pipeline UUID not found in response")

        return pipeline_uuid.strip("{}")

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if pipeline is complete and get result."""
        data = await self._fetch_pipeline_status(run_id)

        state_info = data.get("state")
        web_url = self._extract_web_url(data)

        if not isinstance(state_info, dict):
            result = TestResult(
                provider="bitbucket",
                scanner="unknown",
                test_name="unknown",
                status="error",
                duration=0.0,
                run_url=web_url,
            )
            return (False, result)

        state_name = state_info.get("name")
        is_complete = state_name == "COMPLETED"

        if not is_complete:
            result = TestResult(
                provider="bitbucket",
                scanner="unknown",
                test_name="unknown",
                status="error",
                duration=0.0,
                run_url=web_url,
            )
            return (False, result)

        result_info = state_info.get("result", {})
        if isinstance(result_info, dict):
            result_name = result_info.get("name", "")
        else:
            result_name = ""

        test_status = self._map_result(str(result_name))

        result = TestResult(
            provider="bitbucket",
            scanner="unknown",
            test_name="unknown",
            status=test_status,
            duration=0.0,
            run_url=web_url,
        )

        return (True, result)

    async def _fetch_pipeline_status(self, run_id: str) -> Mapping[str, object]:
        """Fetch pipeline status from Bitbucket API."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repositories/{self.config.workspace}/"
                f"{self.config.repo_slug}/pipelines/{{{run_id}}}"
            )
            auth_str = f"{self.config.username}:{self.config.app_password}"
            auth_bytes = auth_str.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_b64}",
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        return data

    def _extract_web_url(self, data: Mapping[str, object]) -> str:
        """Extract web URL from pipeline data."""
        web_url = ""
        if isinstance(data.get("links"), dict):
            links = data["links"]
            if isinstance(links, dict) and isinstance(links.get("html"), dict):
                html = links["html"]
                if isinstance(html, dict):
                    web_url = str(html.get("href", ""))
        return web_url

    def _map_result(
        self, result: str
    ) -> Literal["success", "failure", "timeout", "error"]:
        """Map Bitbucket result to test status."""
        mapping: dict[str, Literal["success", "failure", "timeout", "error"]] = {
            "SUCCESSFUL": "success",
            "FAILED": "failure",
            "ERROR": "error",
            "STOPPED": "error",
        }
        return mapping.get(result, "error")
