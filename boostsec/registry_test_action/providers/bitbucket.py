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
        # Store test context and URLs for each pipeline to populate TestResult correctly
        self._pipeline_context: dict[str, tuple[str, str, str]] = {}
        # Bitbucket uses Basic auth with username:api_token
        auth_string = f"{config.username}:{config.api_token}"
        auth_bytes = auth_string.encode("utf-8")
        self._auth_header = f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"

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
            headers = {
                "Authorization": self._auth_header,
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
                    "type": "pipeline_ref_target",
                    "selector": {
                        "type": "custom",
                        "pattern": "test-scanner",
                    },
                    "ref_name": self.config.branch,
                    "ref_type": "branch",
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

        pipeline_id = pipeline_uuid.strip("{}")

        # Construct pipeline URL
        # Pattern: https://bitbucket.org/{workspace}/{repo_slug}/pipelines/results/{run_id}
        # The run_id in the URL is a sequential number from build_number
        build_number = data.get("build_number")
        if isinstance(build_number, int):
            run_url = (
                f"https://bitbucket.org/{self.config.workspace}/"
                f"{self.config.repo_slug}/pipelines/results/{build_number}"
            )
        else:
            run_url = ""

        # Store test context and URL for later use in poll_status
        self._pipeline_context[pipeline_id] = (scanner_id, test.name, run_url)

        return pipeline_id

    async def poll_status(self, run_id: str) -> tuple[bool, TestResult]:
        """Check if pipeline is complete and get result."""
        # Retrieve stored test context and URL
        scanner, test_name, run_url = self._pipeline_context.get(
            run_id, ("unknown", "unknown", "")
        )

        data = await self._fetch_pipeline_status(run_id)

        state_info = data.get("state")

        if not isinstance(state_info, dict):
            result = TestResult(
                provider="bitbucket",
                scanner=scanner,
                test_name=test_name,
                status="error",
                duration=0.0,
                run_url=run_url,
            )
            return (False, result)

        state_name = state_info.get("name")

        # Check for terminal states
        terminal_states = {"COMPLETED", "STOPPED", "ERROR", "FAILED"}
        is_complete = state_name in terminal_states

        if not is_complete:
            # Still running (PENDING, IN_PROGRESS)
            result = TestResult(
                provider="bitbucket",
                scanner=scanner,
                test_name=test_name,
                status="error",
                duration=0.0,
                run_url=run_url,
            )
            return (False, result)

        # Pipeline completed, check the result
        result_info = state_info.get("result", {})
        if isinstance(result_info, dict):
            result_name = result_info.get("name", "")
        else:
            result_name = ""

        test_status = self._map_result(str(result_name))

        result = TestResult(
            provider="bitbucket",
            scanner=scanner,
            test_name=test_name,
            status=test_status,
            duration=0.0,
            run_url=run_url,
        )

        return (True, result)

    async def _fetch_pipeline_status(self, run_id: str) -> Mapping[str, object]:
        """Fetch pipeline status from Bitbucket API."""
        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/repositories/{self.config.workspace}/"
                f"{self.config.repo_slug}/pipelines/{{{run_id}}}"
            )
            headers = {
                "Authorization": self._auth_header,
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(
                        f"Failed to get pipeline: {response.status} {text}"
                    )

                data: Mapping[str, object] = await response.json()

        return data

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
