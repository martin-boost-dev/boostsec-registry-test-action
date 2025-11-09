"""Models for test execution results."""

from typing import Literal

from pydantic import BaseModel, Field


class TestResult(BaseModel):
    """Result of a single test execution."""

    provider: str = Field(..., description="CI/CD provider name")
    scanner: str = Field(..., description="Scanner identifier")
    test_name: str = Field(..., description="Test name")
    status: Literal["success", "failure", "timeout", "error"] = Field(
        ..., description="Test execution status"
    )
    duration: float = Field(..., description="Execution time in seconds")
    message: str | None = Field(
        default=None, description="Error message or status details"
    )
    run_url: str | None = Field(default=None, description="Link to CI run")
