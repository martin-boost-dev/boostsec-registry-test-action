"""Tests for test result models."""

import pytest
from pydantic import ValidationError

from boostsec.registry_test_action.models.test_result import TestResult


def test_test_result_minimal() -> None:
    """TestResult accepts minimal required fields."""
    result = TestResult(
        provider="github",
        scanner="boostsecurityio/trivy-fs",
        test_name="smoke test",
        status="success",
        duration=42.5,
    )
    assert result.provider == "github"
    assert result.scanner == "boostsecurityio/trivy-fs"
    assert result.test_name == "smoke test"
    assert result.status == "success"
    assert result.duration == 42.5
    assert result.message is None
    assert result.run_url is None


def test_test_result_with_optional_fields() -> None:
    """TestResult accepts optional message and run_url."""
    result = TestResult(
        provider="gitlab",
        scanner="boostsecurityio/semgrep",
        test_name="config test",
        status="failure",
        duration=120.0,
        message="Test failed: scanner exited with code 1",
        run_url="https://gitlab.com/org/project/-/pipelines/123",
    )
    assert result.message == "Test failed: scanner exited with code 1"
    assert result.run_url == "https://gitlab.com/org/project/-/pipelines/123"


def test_test_result_all_statuses() -> None:
    """TestResult accepts all valid status values."""
    for status in ["success", "failure", "timeout", "error"]:
        result = TestResult(
            provider="test",
            scanner="test/scanner",
            test_name="test",
            status=status,  # type: ignore[arg-type]
            duration=1.0,
        )
        assert result.status == status


def test_test_result_invalid_status() -> None:
    """TestResult rejects invalid status."""
    with pytest.raises(ValidationError) as exc_info:
        TestResult(
            provider="test",
            scanner="test/scanner",
            test_name="test",
            status="invalid",  # type: ignore[arg-type]
            duration=1.0,
        )
    assert "status" in str(exc_info.value)


def test_test_result_missing_required_fields() -> None:
    """TestResult requires all mandatory fields."""
    with pytest.raises(ValidationError) as exc_info:
        TestResult(provider="github", scanner="scanner")  # type: ignore[call-arg]
    errors = str(exc_info.value)
    assert "test_name" in errors
    assert "status" in errors
    assert "duration" in errors
