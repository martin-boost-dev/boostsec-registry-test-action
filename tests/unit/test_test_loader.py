"""Tests for test definition loader."""

from pathlib import Path

import pytest

from boostsec.registry_test_action.test_loader import (
    load_all_tests,
    load_test_definition,
)


async def test_load_test_definition_valid(tmp_path: Path) -> None:
    """load_test_definition loads and parses valid YAML."""
    scanner_dir = tmp_path / "scanners" / "boostsecurityio" / "trivy-fs"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text(
        """
version: "1.0"
tests:
  - name: "smoke test"
    type: "source-code"
    source:
      url: "https://github.com/OWASP/NodeGoat.git"
      ref: "main"
    scan_paths:
      - "."
    timeout: "5m"
"""
    )

    definition = await load_test_definition(tmp_path, "boostsecurityio/trivy-fs")

    assert definition.version == "1.0"
    assert len(definition.tests) == 1
    assert definition.tests[0].name == "smoke test"
    assert definition.tests[0].type == "source-code"
    assert definition.tests[0].source.url == "https://github.com/OWASP/NodeGoat.git"
    assert definition.tests[0].source.ref == "main"
    assert definition.tests[0].scan_paths == ["."]
    assert definition.tests[0].timeout == "5m"


async def test_load_test_definition_multiple_tests(tmp_path: Path) -> None:
    """load_test_definition handles multiple tests."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text(
        """
version: "1.0"
tests:
  - name: "test1"
    type: "source-code"
    source:
      url: "https://github.com/org/repo1.git"
      ref: "main"
  - name: "test2"
    type: "docker-image"
    source:
      url: "https://github.com/org/repo2.git"
      ref: "v1.0"
"""
    )

    definition = await load_test_definition(tmp_path, "org/scanner")

    assert len(definition.tests) == 2
    assert definition.tests[0].name == "test1"
    assert definition.tests[1].name == "test2"


async def test_load_test_definition_file_not_found(tmp_path: Path) -> None:
    """load_test_definition raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError, match="Test file not found"):
        await load_test_definition(tmp_path, "boostsecurityio/nonexistent")


async def test_load_test_definition_invalid_yaml(tmp_path: Path) -> None:
    """load_test_definition raises ValueError for invalid YAML."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text("invalid: yaml: content: [")

    with pytest.raises(ValueError, match="Invalid YAML"):
        await load_test_definition(tmp_path, "org/scanner")


async def test_load_test_definition_empty_file(tmp_path: Path) -> None:
    """load_test_definition raises ValueError for empty file."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text("")

    with pytest.raises(ValueError, match="Empty test file"):
        await load_test_definition(tmp_path, "org/scanner")


async def test_load_test_definition_invalid_schema(tmp_path: Path) -> None:
    """load_test_definition raises ValueError for schema validation errors."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text(
        """
version: "1.0"
tests:
  - name: "test"
    type: "invalid-type"
    source:
      url: "https://github.com/org/repo.git"
      ref: "main"
"""
    )

    with pytest.raises(ValueError, match="Invalid test definition schema"):
        await load_test_definition(tmp_path, "org/scanner")


async def test_load_test_definition_missing_required_fields(tmp_path: Path) -> None:
    """load_test_definition raises ValueError for missing required fields."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner"
    scanner_dir.mkdir(parents=True)

    test_yaml = scanner_dir / "tests.yaml"
    test_yaml.write_text(
        """
tests:
  - name: "test"
    type: "source-code"
    source:
      url: "https://github.com/org/repo.git"
      ref: "main"
"""
    )

    with pytest.raises(ValueError, match="Invalid test definition schema"):
        await load_test_definition(tmp_path, "org/scanner")


async def test_load_all_tests_multiple_scanners(tmp_path: Path) -> None:
    """load_all_tests loads definitions for multiple scanners."""
    scanner1_dir = tmp_path / "scanners" / "org" / "scanner1"
    scanner2_dir = tmp_path / "scanners" / "org" / "scanner2"
    scanner1_dir.mkdir(parents=True)
    scanner2_dir.mkdir(parents=True)

    (scanner1_dir / "tests.yaml").write_text(
        """
version: "1.0"
tests:
  - name: "test1"
    type: "source-code"
    source:
      url: "https://github.com/org/repo.git"
      ref: "main"
"""
    )

    (scanner2_dir / "tests.yaml").write_text(
        """
version: "1.0"
tests:
  - name: "test2"
    type: "docker-image"
    source:
      url: "https://github.com/org/repo.git"
      ref: "v1.0"
"""
    )

    results = await load_all_tests(tmp_path, ["org/scanner1", "org/scanner2"])

    assert len(results) == 2
    assert "org/scanner1" in results
    assert "org/scanner2" in results
    assert results["org/scanner1"].tests[0].name == "test1"
    assert results["org/scanner2"].tests[0].name == "test2"


async def test_load_all_tests_skips_missing(tmp_path: Path) -> None:
    """load_all_tests skips scanners with missing test files."""
    scanner_dir = tmp_path / "scanners" / "org" / "scanner1"
    scanner_dir.mkdir(parents=True)

    (scanner_dir / "tests.yaml").write_text(
        """
version: "1.0"
tests:
  - name: "test1"
    type: "source-code"
    source:
      url: "https://github.com/org/repo.git"
      ref: "main"
"""
    )

    results = await load_all_tests(
        tmp_path, ["org/scanner1", "org/scanner2", "org/scanner3"]
    )

    assert len(results) == 1
    assert "org/scanner1" in results
    assert "org/scanner2" not in results
    assert "org/scanner3" not in results


async def test_load_all_tests_skips_invalid(tmp_path: Path) -> None:
    """load_all_tests skips scanners with invalid YAML."""
    scanner1_dir = tmp_path / "scanners" / "org" / "scanner1"
    scanner2_dir = tmp_path / "scanners" / "org" / "scanner2"
    scanner1_dir.mkdir(parents=True)
    scanner2_dir.mkdir(parents=True)

    (scanner1_dir / "tests.yaml").write_text(
        """
version: "1.0"
tests:
  - name: "test1"
    type: "source-code"
    source:
      url: "https://github.com/org/repo.git"
      ref: "main"
"""
    )

    (scanner2_dir / "tests.yaml").write_text("invalid: yaml: [")

    results = await load_all_tests(tmp_path, ["org/scanner1", "org/scanner2"])

    assert len(results) == 1
    assert "org/scanner1" in results
    assert "org/scanner2" not in results


async def test_load_all_tests_empty_list(tmp_path: Path) -> None:
    """load_all_tests returns empty dict for empty scanner list."""
    results = await load_all_tests(tmp_path, [])
    assert results == {}
