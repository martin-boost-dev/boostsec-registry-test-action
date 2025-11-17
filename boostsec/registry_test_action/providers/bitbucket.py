"""Bitbucket Pipelines provider implementation."""

import base64
import json
from collections.abc import Mapping
from typing import Literal

import aiohttp

from boostsec.registry_test_action.models.provider_config import BitbucketConfig
from boostsec.registry_test_action.models.test_definition import TestDefinition
from boostsec.registry_test_action.models.test_result import TestResult
from boostsec.registry_test_action.providers.base import PipelineProvider


class BitbucketProvider(PipelineProvider):
    """Bitbucket Pipelines provider."""

    def __init__(self, config: BitbucketConfig) -> None:
        """Initialize Bitbucket provider with configuration."""
        self.config = config
        self.base_url = "https://api.bitbucket.org/2.0"
        auth_string = f"{config.username}:{config.api_token}"
        auth_bytes = auth_string.encode("utf-8")
        self._auth_header = f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"
        self._run_urls: dict[str, str] = {}

    async def dispatch_scanner_tests(
        self,
        scanner_id: str,
        test_definition: TestDefinition,
        registry_ref: str,
        registry_repo: str,
    ) -> str:
        """Trigger pipeline with matrix and return pipeline UUID."""
        matrix_entries = test_definition.to_matrix_entries()
        matrix_json = json.dumps([entry.model_dump() for entry in matrix_entries])

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
                {"key": "REGISTRY_REF", "value": registry_ref},
                {"key": "REGISTRY_REPO", "value": registry_repo},
                {"key": "MATRIX_TESTS", "value": matrix_json},
            ]

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

        build_number = data.get("build_number")
        if isinstance(build_number, int):
            run_url = (
                f"https://bitbucket.org/{self.config.workspace}/"
                f"{self.config.repo_slug}/pipelines/results/{build_number}"
            )
            self._run_urls[pipeline_id] = run_url

        return pipeline_id

    async def poll_status(self, run_id: str) -> tuple[bool, list[TestResult]]:
        """Check if all pipeline steps are complete and get results."""
        data = await self._fetch_pipeline_status(run_id)

        state_info = data.get("state")
        if not isinstance(state_info, dict):
            return (False, [])

        state_name = state_info.get("name")

        terminal_states = {"COMPLETED", "STOPPED", "ERROR", "FAILED"}
        is_complete = state_name in terminal_states

        if not is_complete:
            return (False, [])

        run_url = self._run_urls.get(run_id, "")

        # Check the result
        result_info = state_info.get("result", {})
        if isinstance(result_info, dict):
            result_name = result_info.get("name", "")
        else:
            result_name = ""

        test_status = self._map_result(str(result_name))

        # For Bitbucket, we have parallel slots, so we need to check each one
        # The pipeline will fail if any slot fails
        # We'll create results for each matrix entry
        # Since Bitbucket doesn't provide detailed job-level results via API
        # We create a single result representing the overall pipeline status
        result = TestResult(
            provider="bitbucket",
            scanner="",
            test_name="matrix-tests",
            status=test_status,
            duration=0.0,
            run_url=run_url,
        )

        return (True, [result])

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
