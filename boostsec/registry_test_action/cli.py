"""CLI entry point for registry test action."""

import asyncio
import json
import logging
import os
import sys
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

# Configure logging - force reconfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
    force=True,  # Force reconfiguration even if already set up
)
logger = logging.getLogger(__name__)

app = typer.Typer()


@app.command()
def main(  # noqa: C901
    registry_path: Path = typer.Option(..., help="Path to scanner registry repository"),  # noqa: B008
    base_ref: str = typer.Option(..., help="Base git reference (e.g., main)"),
    head_ref: str = typer.Option(..., help="Head git reference (e.g., PR branch)"),
    provider: str = typer.Option(
        ..., help="Provider type (github, gitlab, azure, bitbucket)"
    ),
    provider_config: str = typer.Option(
        ..., help="JSON configuration for the provider"
    ),
) -> None:
    """Run scanner tests on a CI/CD provider."""
    logger.info("=" * 80)
    logger.info("Scanner Registry Test Action - Starting")
    logger.info("=" * 80)
    logger.info(f"Registry path: {registry_path}")
    logger.info(f"Base ref: {base_ref}")
    logger.info(f"Head ref: {head_ref}")
    logger.info(f"Provider: {provider}")
    logger.info(f"Working directory: {Path.cwd()}")

    registry_ref = head_ref

    try:
        logger.info("Creating provider...")
        pipeline_provider = _create_provider(provider, provider_config)
        logger.info(f"Provider created: {type(pipeline_provider).__name__}")
    except ValueError as e:
        logger.error(f"Failed to create provider: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    orchestrator = TestOrchestrator(pipeline_provider)

    try:
        logger.info("Starting test orchestration...")
        results = asyncio.run(
            orchestrator.run_tests(registry_path, base_ref, head_ref, registry_ref)
        )
        logger.info(f"Test orchestration completed with {len(results)} results")
    except Exception as e:
        logger.exception("Test execution failed")
        typer.echo(f"Error running tests: {e}", err=True)
        raise typer.Exit(code=1)

    if not results:
        typer.echo("No tests to run")
        return

    # Log results summary
    logger.info("=" * 80)
    logger.info("Test Results Summary:")
    logger.info("=" * 80)
    for result in results:
        if result.status == "success":
            msg = (
                f"✓ {result.scanner}/{result.test_name}: {result.status} "
                f"({result.duration:.2f}s)"
            )
            logger.info(msg)
        else:
            logger.error(f"✗ {result.scanner}/{result.test_name}: {result.status}")
            if result.message:  # pragma: no cover
                logger.error(f"  Message: {result.message}")
            if result.run_url:  # pragma: no cover
                logger.error(f"  Run URL: {result.run_url}")

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
        fail_count = sum(
            1 for r in results if r.status in {"failure", "error", "timeout"}
        )
        logger.error(f"Tests failed: {fail_count}/{len(results)}")
        raise typer.Exit(code=1)


def _create_provider(provider_type: str, config_json: str) -> PipelineProvider:
    """Create provider based on type and JSON configuration."""
    provider_type = provider_type.lower()

    try:
        config_dict = json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in provider-config: {e}")

    if provider_type == "github":
        config = GitHubConfig(**config_dict)
        if "GITHUB_API_URL" in os.environ:
            config.base_url = os.environ["GITHUB_API_URL"]
        return GitHubProvider(config)
    elif provider_type == "gitlab":
        return GitLabProvider(GitLabConfig(**config_dict))
    elif provider_type == "azure":
        return AzureDevOpsProvider(AzureDevOpsConfig(**config_dict))
    elif provider_type == "bitbucket":
        return BitbucketProvider(BitbucketConfig(**config_dict))
    else:
        raise ValueError(
            f"Unknown provider type: {provider_type}. "
            "Must be one of: github, gitlab, azure, bitbucket"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
