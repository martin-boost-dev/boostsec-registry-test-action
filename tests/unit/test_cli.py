"""Tests for CLI entry point."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from boostsec.registry_test_action.cli import app
from boostsec.registry_test_action.models.test_result import TestResult

runner = CliRunner()


def test_main_success_with_results() -> None:
    """Main outputs results and exits successfully when all tests pass."""
    results = [
        TestResult(
            provider="github",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["total"] == 1
    assert output["passed"] == 1
    assert output["failed"] == 0


def test_main_failure_with_failed_tests() -> None:
    """Main exits with error code when tests fail."""
    results = [
        TestResult(
            provider="github",
            scanner="scanner1",
            test_name="test1",
            status="failure",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["failed"] == 1


def test_main_no_tests_to_run() -> None:
    """Main handles case when no tests need to run."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=[])

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

    assert result.exit_code == 0
    assert "No tests to run" in result.stdout


def test_main_invalid_provider() -> None:
    """Main exits with error for invalid provider."""
    result = runner.invoke(
        app,
        [
            "--registry-path",
            "/test/registry",
            "--base-ref",
            "main",
            "--head-ref",
            "feature",
            "--provider",
            "invalid",
        ],
    )

    assert result.exit_code == 1
    assert "Unknown provider type" in result.output


def test_main_github_custom_api_url() -> None:
    """Main works with custom GitHub API URL."""
    results = [
        TestResult(
            provider="github",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
                "GITHUB_API_URL": "http://localhost:8080",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
        patch(
            "boostsec.registry_test_action.cli.GitHubProvider"
        ) as mock_provider_class,
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

        mock_provider_class.assert_called_once()
        config = mock_provider_class.call_args[0][0]
        assert config.base_url == "http://localhost:8080"

    assert result.exit_code == 0


def test_main_gitlab_provider() -> None:
    """Main works with GitLab provider."""
    results = [
        TestResult(
            provider="gitlab",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "GITLAB_TOKEN": "token",
                "GITLAB_PROJECT_ID": "12345",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "gitlab",
            ],
        )

    assert result.exit_code == 0


def test_main_azure_provider() -> None:
    """Main works with Azure DevOps provider."""
    results = [
        TestResult(
            provider="azure",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "AZURE_DEVOPS_TOKEN": "token",
                "AZURE_DEVOPS_ORGANIZATION": "org",
                "AZURE_DEVOPS_PROJECT": "project",
                "AZURE_DEVOPS_PIPELINE_ID": "123",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "azure",
            ],
        )

    assert result.exit_code == 0


def test_main_bitbucket_provider() -> None:
    """Main works with Bitbucket provider."""
    results = [
        TestResult(
            provider="bitbucket",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        )
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "BITBUCKET_USERNAME": "user",
                "BITBUCKET_APP_PASSWORD": "pass",
                "BITBUCKET_WORKSPACE": "workspace",
                "BITBUCKET_REPO_SLUG": "repo",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "bitbucket",
            ],
        )

    assert result.exit_code == 0


def test_main_orchestrator_exception() -> None:
    """Main exits with error when orchestrator raises exception."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(side_effect=RuntimeError("API Error"))

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

    assert result.exit_code == 1
    assert "Error running tests" in result.output


def test_main_mixed_results() -> None:
    """Main handles mixed test results correctly."""
    results = [
        TestResult(
            provider="github",
            scanner="scanner1",
            test_name="test1",
            status="success",
            duration=10.0,
        ),
        TestResult(
            provider="github",
            scanner="scanner1",
            test_name="test2",
            status="failure",
            duration=15.0,
        ),
        TestResult(
            provider="github",
            scanner="scanner2",
            test_name="test3",
            status="error",
            duration=5.0,
        ),
        TestResult(
            provider="github",
            scanner="scanner2",
            test_name="test4",
            status="timeout",
            duration=120.0,
        ),
    ]

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run_tests = AsyncMock(return_value=results)

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY_OWNER": "owner",
                "GITHUB_REPOSITORY": "owner/repo",
                "WORKFLOW_ID": "workflow.yml",
            },
        ),
        patch(
            "boostsec.registry_test_action.cli.TestOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--registry-path",
                "/test/registry",
                "--base-ref",
                "main",
                "--head-ref",
                "feature",
                "--provider",
                "github",
            ],
        )

    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["total"] == 4
    assert output["passed"] == 1
    assert output["failed"] == 1
    assert output["errors"] == 1
    assert output["timeouts"] == 1
