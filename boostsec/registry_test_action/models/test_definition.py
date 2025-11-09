"""Models for test definitions loaded from tests.yaml files."""

from typing import Literal

from pydantic import BaseModel, Field


class TestSource(BaseModel):
    """Source repository configuration for a test."""

    url: str = Field(..., description="Git repository URL (HTTPS only)")
    ref: str = Field(..., description="Git reference (branch, tag, or commit SHA)")


class Test(BaseModel):
    """Individual test specification."""

    name: str = Field(..., description="Human-readable test name")
    type: Literal["source-code", "docker-image"] = Field(
        ..., description="Type of test to execute"
    )
    source: TestSource = Field(..., description="Source repository details")
    scan_paths: list[str] = Field(
        default_factory=list, description="Paths to scan within the repository"
    )
    scan_configs: list[dict[str, object]] | None = Field(
        default=None, description="Optional scan configurations"
    )
    timeout: str = Field(default="5m", description="Test timeout (e.g., '300s', '5m')")


class TestDefinition(BaseModel):
    """Complete test definition loaded from tests.yaml."""

    version: str = Field(..., description="Test definition schema version")
    tests: list[Test] = Field(default_factory=list, description="List of tests")
