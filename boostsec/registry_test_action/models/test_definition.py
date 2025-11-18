"""Models for test definitions loaded from tests.yaml files."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TestSource(BaseModel):
    """Source repository configuration for a test."""

    __test__ = False

    url: str = Field(..., description="Git repository URL (HTTPS only)")
    ref: str = Field(..., description="Git reference (branch, tag, or commit SHA)")


class Test(BaseModel):
    """Individual test specification."""

    __test__ = False

    name: str = Field(..., description="Human-readable test name")
    type: Literal["source-code", "container-image"] = Field(
        ..., description="Type of test to execute"
    )
    source: TestSource = Field(..., description="Source repository details")
    scan_paths: list[str] = Field(
        default_factory=list,
        description="Paths to scan within the repository",
    )
    scan_configs: list[dict[str, object]] | None = Field(
        default=None, description="Optional scan configurations"
    )
    timeout: str = Field(default="5m", description="Test timeout (e.g., '300s', '5m')")

    @model_validator(mode="after")
    def default_scan_paths_to_root(self) -> "Test":  # noqa: N804
        """Set scan paths to repository root if empty."""
        if not self.scan_paths:
            self.scan_paths = ["."]
        return self


class MatrixEntry(BaseModel):
    """Single matrix entry representing one (test, scan_path) combination."""

    __test__ = False

    test_name: str = Field(..., description="Test name")
    test_type: Literal["source-code", "container-image"] = Field(
        ..., description="Type of test"
    )
    source_url: str = Field(..., description="Git repository URL")
    source_ref: str = Field(..., description="Git reference")
    scan_path: str = Field(..., description="Single scan path")
    scan_config: dict[str, object] | None = Field(
        default=None, description="Optional scan configuration"
    )
    timeout: str = Field(default="5m", description="Test timeout")


class TestDefinition(BaseModel):
    """Complete test definition loaded from tests.yaml."""

    __test__ = False

    version: str = Field(..., description="Test definition schema version")
    tests: list[Test] = Field(default_factory=list, description="List of tests")

    def to_matrix_entries(self) -> list[MatrixEntry]:
        """Convert all tests into matrix entries (one per test/scan_path combo)."""
        entries: list[MatrixEntry] = []
        for test in self.tests:
            if test.scan_configs:
                for i, scan_config in enumerate(test.scan_configs):
                    scan_path = test.scan_paths[i] if i < len(test.scan_paths) else "."
                    entries.append(
                        MatrixEntry(
                            test_name=test.name,
                            test_type=test.type,
                            source_url=test.source.url,
                            source_ref=test.source.ref,
                            scan_path=scan_path,
                            scan_config=scan_config,
                            timeout=test.timeout,
                        )
                    )
            else:
                for scan_path in test.scan_paths:
                    entries.append(
                        MatrixEntry(
                            test_name=test.name,
                            test_type=test.type,
                            source_url=test.source.url,
                            source_ref=test.source.ref,
                            scan_path=scan_path,
                            scan_config=None,
                            timeout=test.timeout,
                        )
                    )
        return entries
