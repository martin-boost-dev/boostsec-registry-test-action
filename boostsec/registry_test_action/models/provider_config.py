"""Configuration models for CI/CD pipeline providers."""

from pydantic import BaseModel, Field


class GitHubConfig(BaseModel):
    """Configuration for GitHub Actions provider."""

    token: str = Field(..., description="GitHub personal access token or GITHUB_TOKEN")
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    workflow_id: str = Field(..., description="Workflow file name or ID")
    ref: str = Field(
        default="main",
        description="Git reference to run workflow on in test runner repo",
    )
    base_url: str = Field(
        default="https://api.github.com", description="GitHub API base URL"
    )


class GitLabConfig(BaseModel):
    """Configuration for GitLab CI provider."""

    token: str = Field(..., description="GitLab personal access token")
    project_id: str = Field(..., description="GitLab project ID")
    ref: str = Field(default="main", description="Git reference to run pipeline on")


class AzureDevOpsConfig(BaseModel):
    """Configuration for Azure DevOps provider."""

    token: str = Field(..., description="Azure DevOps personal access token")
    organization: str = Field(..., description="Azure DevOps organization")
    project: str = Field(..., description="Azure DevOps project name")
    pipeline_id: int = Field(..., description="Pipeline/Build definition ID")


class BitbucketConfig(BaseModel):
    """Configuration for Bitbucket Pipelines provider."""

    username: str = Field(..., description="Bitbucket username")
    app_password: str = Field(..., description="Bitbucket app password")
    workspace: str = Field(..., description="Bitbucket workspace slug")
    repo_slug: str = Field(..., description="Repository slug")
