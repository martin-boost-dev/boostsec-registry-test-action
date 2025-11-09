"""Tests for test definition models."""

import pytest
from pydantic import ValidationError

from boostsec.registry_test_action.models.test_definition import (
    Test,
    TestDefinition,
    TestSource,
)


def test_test_source_valid() -> None:
    """TestSource accepts valid URL and ref."""
    source = TestSource(url="https://github.com/org/repo.git", ref="main")
    assert source.url == "https://github.com/org/repo.git"
    assert source.ref == "main"


def test_test_source_missing_fields() -> None:
    """TestSource requires both url and ref."""
    with pytest.raises(ValidationError) as exc_info:
        TestSource(url="https://github.com/org/repo.git")  # type: ignore[call-arg]
    assert "ref" in str(exc_info.value)


def test_test_with_defaults() -> None:
    """Test uses default values for optional fields."""
    test = Test(
        name="smoke test",
        type="source-code",
        source=TestSource(url="https://github.com/org/repo.git", ref="main"),
    )
    assert test.name == "smoke test"
    assert test.type == "source-code"
    assert test.scan_paths == []
    assert test.scan_configs is None
    assert test.timeout == "5m"


def test_test_with_all_fields() -> None:
    """Test accepts all optional fields."""
    test = Test(
        name="comprehensive test",
        type="docker-image",
        source=TestSource(url="https://github.com/org/repo.git", ref="v1.0"),
        scan_paths=["/path1", "/path2"],
        scan_configs=[{"default": True}, {"rules": ["rule1"]}],
        timeout="10m",
    )
    assert test.name == "comprehensive test"
    assert test.type == "docker-image"
    assert test.scan_paths == ["/path1", "/path2"]
    assert test.scan_configs == [{"default": True}, {"rules": ["rule1"]}]
    assert test.timeout == "10m"


def test_test_invalid_type() -> None:
    """Test rejects invalid test type."""
    with pytest.raises(ValidationError) as exc_info:
        Test(
            name="invalid test",
            type="invalid-type",  # type: ignore[arg-type]
            source=TestSource(url="https://github.com/org/repo.git", ref="main"),
        )
    assert "type" in str(exc_info.value)


def test_test_definition_empty() -> None:
    """TestDefinition allows empty test list."""
    definition = TestDefinition(version="1.0")
    assert definition.version == "1.0"
    assert definition.tests == []


def test_test_definition_with_tests() -> None:
    """TestDefinition accepts multiple tests."""
    tests = [
        Test(
            name="test1",
            type="source-code",
            source=TestSource(url="https://github.com/org/repo.git", ref="main"),
        ),
        Test(
            name="test2",
            type="docker-image",
            source=TestSource(url="https://github.com/org/repo2.git", ref="v1.0"),
        ),
    ]
    definition = TestDefinition(version="1.0", tests=tests)
    assert definition.version == "1.0"
    assert len(definition.tests) == 2
    assert definition.tests[0].name == "test1"
    assert definition.tests[1].name == "test2"


def test_test_definition_missing_version() -> None:
    """TestDefinition requires version."""
    with pytest.raises(ValidationError) as exc_info:
        TestDefinition()  # type: ignore[call-arg]
    assert "version" in str(exc_info.value)
