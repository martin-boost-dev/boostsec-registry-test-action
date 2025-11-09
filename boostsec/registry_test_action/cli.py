"""CLI entry point for registry test action."""

import asyncio
import json
import os
from pathlib import Path

import typer

from boostsec.registry_test_action.models.provider_config import (
    AzureDevOpsConfig,
    BitbucketConfig,
    GitHubConfig,
    GitLabConfig,
)
from boostsec.registry_test_action.orchestrator import TestOrchestrator
from boostsec.registry_test_action.providers.azure import AzureDevOpsProvider
from boostsec.registry_test_action.providers.base import PipelineProvider
from boostsec.registry_test_action.providers.bitbucket import BitbucketProvider
from boostsec.registry_test_action.providers.github import GitHubProvider
from boostsec.registry_test_action.providers.gitlab import GitLabProvider

app = typer.Typer()


@app.command()
def main(
    registry_path: Path = typer.Option(..., help="Path to scanner registry repository"),  # noqa: B008
    base_ref: str = typer.Option(..., help="Base git reference (e.g., main)"),
    head_ref: str = typer.Option(..., help="Head git reference (e.g., PR branch)"),
    provider: str = typer.Option(
        ..., help="Provider type (github, gitlab, azure, bitbucket)"
    ),
) -> None:
    """Run scanner tests on a CI/CD provider."""
    registry_ref = head_ref

    try:
        pipeline_provider = _create_provider(provider)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    orchestrator = TestOrchestrator(pipeline_provider)

    try:
        results = asyncio.run(
            orchestrator.run_tests(registry_path, base_ref, head_ref, registry_ref)
        )
    except Exception as e:  # noqa: BLE001
        typer.echo(f"Error running tests: {e}", err=True)
        raise typer.Exit(code=1)

    if not results:
        typer.echo("No tests to run")
        return

    output = {
        "total": len(results),
        "passed": sum(1 for r in results if r.status == "success"),
        "failed": sum(1 for r in results if r.status == "failure"),
        "errors": sum(1 for r in results if r.status == "error"),
        "timeouts": sum(1 for r in results if r.status == "timeout"),
        "results": [
            {
                "provider": r.provider,
                "scanner": r.scanner,
                "test_name": r.test_name,
                "status": r.status,
                "duration": r.duration,
                "message": r.message,
                "run_url": r.run_url,
            }
            for r in results
        ],
    }

    typer.echo(json.dumps(output, indent=2))

    has_failures = any(r.status in {"failure", "error", "timeout"} for r in results)
    if has_failures:
        raise typer.Exit(code=1)


def _create_provider(provider_type: str) -> PipelineProvider:
    """Create provider based on type and environment variables."""
    provider_type = provider_type.lower()

    if provider_type == "github":
        return GitHubProvider(
            GitHubConfig(
                token=os.environ["GITHUB_TOKEN"],
                owner=os.environ["GITHUB_REPOSITORY_OWNER"],
                repo=os.environ["GITHUB_REPOSITORY"].split("/")[1],
                workflow_id=os.environ["WORKFLOW_ID"],
            )
        )
    elif provider_type == "gitlab":
        return GitLabProvider(
            GitLabConfig(
                token=os.environ["GITLAB_TOKEN"],
                project_id=os.environ["GITLAB_PROJECT_ID"],
                ref=os.environ.get("GITLAB_REF", "main"),
            )
        )
    elif provider_type == "azure":
        return AzureDevOpsProvider(
            AzureDevOpsConfig(
                token=os.environ["AZURE_DEVOPS_TOKEN"],
                organization=os.environ["AZURE_DEVOPS_ORGANIZATION"],
                project=os.environ["AZURE_DEVOPS_PROJECT"],
                pipeline_id=int(os.environ["AZURE_DEVOPS_PIPELINE_ID"]),
            )
        )
    elif provider_type == "bitbucket":
        return BitbucketProvider(
            BitbucketConfig(
                username=os.environ["BITBUCKET_USERNAME"],
                app_password=os.environ["BITBUCKET_APP_PASSWORD"],
                workspace=os.environ["BITBUCKET_WORKSPACE"],
                repo_slug=os.environ["BITBUCKET_REPO_SLUG"],
            )
        )
    else:
        raise ValueError(
            f"Unknown provider type: {provider_type}. "
            "Must be one of: github, gitlab, azure, bitbucket"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
