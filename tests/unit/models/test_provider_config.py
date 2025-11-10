"""Tests for provider configuration models."""

import pytest
from pydantic import ValidationError

from boostsec.registry_test_action.models.provider_config import (
    AzureDevOpsConfig,
    BitbucketConfig,
    GitHubConfig,
    GitLabConfig,
)


def test_github_config_valid() -> None:
    """GitHubConfig accepts all required fields."""
    config = GitHubConfig(
        token="ghp_token123",
        owner="boostsecurityio",
        repo="test-repo",
        workflow_id="test.yml",
    )
    assert config.token == "ghp_token123"
    assert config.owner == "boostsecurityio"
    assert config.repo == "test-repo"
    assert config.workflow_id == "test.yml"
    assert config.ref == "main"  # Default value


def test_github_config_custom_ref() -> None:
    """GitHubConfig accepts custom ref."""
    config = GitHubConfig(
        token="ghp_token123",
        owner="boostsecurityio",
        repo="test-repo",
        workflow_id="test.yml",
        ref="develop",
    )
    assert config.ref == "develop"


def test_github_config_missing_fields() -> None:
    """GitHubConfig requires all fields."""
    with pytest.raises(ValidationError) as exc_info:
        GitHubConfig(token="token", owner="owner")  # type: ignore[call-arg]
    assert "repo" in str(exc_info.value)
    assert "workflow_id" in str(exc_info.value)


def test_gitlab_config_with_defaults() -> None:
    """GitLabConfig uses default ref."""
    config = GitLabConfig(token="glpat_token123", project_id="12345")
    assert config.token == "glpat_token123"
    assert config.project_id == "12345"
    assert config.ref == "main"


def test_gitlab_config_custom_ref() -> None:
    """GitLabConfig accepts custom ref."""
    config = GitLabConfig(token="glpat_token123", project_id="12345", ref="develop")
    assert config.ref == "develop"


def test_gitlab_config_missing_required() -> None:
    """GitLabConfig requires token and project_id."""
    with pytest.raises(ValidationError) as exc_info:
        GitLabConfig(token="token")  # type: ignore[call-arg]
    assert "project_id" in str(exc_info.value)


def test_azure_config_valid() -> None:
    """AzureDevOpsConfig accepts all required fields."""
    config = AzureDevOpsConfig(
        token="azure_pat_123",
        organization="boostsecurity",
        project="test-project",
        pipeline_id=42,
    )
    assert config.token == "azure_pat_123"
    assert config.organization == "boostsecurity"
    assert config.project == "test-project"
    assert config.pipeline_id == 42


def test_azure_config_missing_fields() -> None:
    """AzureDevOpsConfig requires all fields."""
    with pytest.raises(ValidationError) as exc_info:
        AzureDevOpsConfig(token="token", organization="org")  # type: ignore[call-arg]
    assert "project" in str(exc_info.value)
    assert "pipeline_id" in str(exc_info.value)


def test_azure_config_invalid_pipeline_id() -> None:
    """AzureDevOpsConfig requires integer pipeline_id."""
    with pytest.raises(ValidationError) as exc_info:
        AzureDevOpsConfig(
            token="token",
            organization="org",
            project="proj",
            pipeline_id="not-an-int",  # type: ignore[arg-type]
        )
    assert "pipeline_id" in str(exc_info.value)


def test_bitbucket_config_valid() -> None:
    """BitbucketConfig accepts all required fields."""
    config = BitbucketConfig(
        username="user123",
        app_password="app_pwd_456",
        workspace="boost-workspace",
        repo_slug="test-repo",
    )
    assert config.username == "user123"
    assert config.app_password == "app_pwd_456"
    assert config.workspace == "boost-workspace"
    assert config.repo_slug == "test-repo"


def test_bitbucket_config_missing_fields() -> None:
    """BitbucketConfig requires all fields."""
    with pytest.raises(ValidationError) as exc_info:
        BitbucketConfig(username="user", app_password="pwd")  # type: ignore[call-arg]
    assert "workspace" in str(exc_info.value)
    assert "repo_slug" in str(exc_info.value)
