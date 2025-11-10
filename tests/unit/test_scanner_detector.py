"""Tests for scanner detector."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from boostsec.registry_test_action.scanner_detector import (
    _extract_scanner_paths,
    _get_changed_files,
    _resolve_ref,
    detect_changed_scanners,
    has_test_definition,
)


async def test_resolve_ref_exists() -> None:
    """_resolve_ref returns ref as-is when it exists."""
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"abc123def456\n", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        resolved = await _resolve_ref(Path("/repo"), "main")

    assert resolved == "main"


async def test_resolve_ref_needs_origin_prefix() -> None:
    """_resolve_ref adds origin/ prefix when ref doesn't exist directly."""
    # First call fails (main doesn't exist)
    mock_process_fail = AsyncMock()
    mock_process_fail.returncode = 128
    mock_process_fail.communicate = AsyncMock(
        return_value=(b"", b"fatal: Needed a single revision\n")
    )

    # Second call succeeds (origin/main exists)
    mock_process_success = AsyncMock()
    mock_process_success.returncode = 0
    mock_process_success.communicate = AsyncMock(return_value=(b"abc123def456\n", b""))

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=[mock_process_fail, mock_process_success],
    ):
        resolved = await _resolve_ref(Path("/repo"), "main")

    assert resolved == "origin/main"


async def test_resolve_ref_not_found() -> None:
    """_resolve_ref raises error when ref cannot be resolved."""
    mock_process = AsyncMock()
    mock_process.returncode = 128
    mock_process.communicate = AsyncMock(
        return_value=(b"", b"fatal: Needed a single revision\n")
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="Cannot resolve git ref 'invalid'"):
            await _resolve_ref(Path("/repo"), "invalid")


async def test_resolve_ref_skips_origin_for_refs() -> None:
    """_resolve_ref doesn't try origin/ prefix for refs/ paths."""
    mock_process = AsyncMock()
    mock_process.returncode = 128
    mock_process.communicate = AsyncMock(
        return_value=(b"", b"fatal: Needed a single revision\n")
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="Cannot resolve git ref"):
            await _resolve_ref(Path("/repo"), "refs/heads/main")


async def test_get_changed_files_success() -> None:
    """_get_changed_files returns list of changed files from git diff."""
    # Mock _resolve_ref calls (base_ref and head_ref)
    mock_resolve_base = AsyncMock()
    mock_resolve_base.returncode = 0
    mock_resolve_base.communicate = AsyncMock(return_value=(b"abc123\n", b""))

    mock_resolve_head = AsyncMock()
    mock_resolve_head.returncode = 0
    mock_resolve_head.communicate = AsyncMock(return_value=(b"def456\n", b""))

    # Mock git diff call
    mock_diff = AsyncMock()
    mock_diff.returncode = 0
    mock_diff.communicate = AsyncMock(
        return_value=(
            b"scanners/org1/scanner1/module.yaml\nscanners/org2/scanner2/tests.yaml\n",
            b"",
        )
    )

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=[mock_resolve_base, mock_resolve_head, mock_diff],
    ):
        files = await _get_changed_files(Path("/repo"), "main", "HEAD")

    assert files == [
        "scanners/org1/scanner1/module.yaml",
        "scanners/org2/scanner2/tests.yaml",
    ]


async def test_get_changed_files_empty() -> None:
    """_get_changed_files returns empty list when no files changed."""
    # Mock _resolve_ref calls
    mock_resolve = AsyncMock()
    mock_resolve.returncode = 0
    mock_resolve.communicate = AsyncMock(return_value=(b"abc123\n", b""))

    # Mock git diff call
    mock_diff = AsyncMock()
    mock_diff.returncode = 0
    mock_diff.communicate = AsyncMock(return_value=(b"", b""))

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=[mock_resolve, mock_resolve, mock_diff],
    ):
        files = await _get_changed_files(Path("/repo"), "main", "HEAD")

    assert files == []


async def test_get_changed_files_error() -> None:
    """_get_changed_files raises RuntimeError when git command fails."""
    # Mock _resolve_ref calls succeed
    mock_resolve = AsyncMock()
    mock_resolve.returncode = 0
    mock_resolve.communicate = AsyncMock(return_value=(b"abc123\n", b""))

    # Mock git diff call fails
    mock_diff = AsyncMock()
    mock_diff.returncode = 128
    mock_diff.communicate = AsyncMock(
        return_value=(b"", b"fatal: bad revision 'invalid-ref'\n")
    )

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=[mock_resolve, mock_resolve, mock_diff],
    ):
        with pytest.raises(RuntimeError, match="Git command failed"):
            await _get_changed_files(Path("/repo"), "invalid-ref", "HEAD")


def test_extract_scanner_paths_single() -> None:
    """_extract_scanner_paths extracts single scanner identifier."""
    files = [
        "scanners/boostsecurityio/trivy-fs/module.yaml",
        "scanners/boostsecurityio/trivy-fs/rules.yaml",
    ]
    scanners = _extract_scanner_paths(files)
    assert scanners == ["boostsecurityio/trivy-fs"]


def test_extract_scanner_paths_multiple() -> None:
    """_extract_scanner_paths extracts multiple unique scanner identifiers."""
    files = [
        "scanners/boostsecurityio/trivy-fs/module.yaml",
        "scanners/boostsecurityio/semgrep/module.yaml",
        "scanners/boostsecurityio/trivy-fs/tests.yaml",
    ]
    scanners = _extract_scanner_paths(files)
    assert scanners == ["boostsecurityio/semgrep", "boostsecurityio/trivy-fs"]


def test_extract_scanner_paths_ignores_non_scanner_files() -> None:
    """_extract_scanner_paths ignores files outside scanners directory."""
    files = [
        ".github/workflows/test.yml",
        "README.md",
        "scanners/boostsecurityio/trivy-fs/module.yaml",
    ]
    scanners = _extract_scanner_paths(files)
    assert scanners == ["boostsecurityio/trivy-fs"]


def test_extract_scanner_paths_ignores_shallow_paths() -> None:
    """_extract_scanner_paths ignores paths that don't reach scanner level."""
    files = [
        "scanners/README.md",
        "scanners/boostsecurityio/README.md",
        "scanners/boostsecurityio/trivy-fs/module.yaml",
    ]
    scanners = _extract_scanner_paths(files)
    assert scanners == ["boostsecurityio/trivy-fs"]


def test_extract_scanner_paths_empty() -> None:
    """_extract_scanner_paths returns empty list for no scanner files."""
    files = [".github/workflows/test.yml", "README.md"]
    scanners = _extract_scanner_paths(files)
    assert scanners == []


async def test_has_test_definition_exists(tmp_path: Path) -> None:
    """has_test_definition returns True when tests.yaml exists."""
    scanner_dir = tmp_path / "scanners" / "boostsecurityio" / "trivy-fs"
    scanner_dir.mkdir(parents=True)
    (scanner_dir / "tests.yaml").write_text("version: 1.0\n")

    result = await has_test_definition(tmp_path, "boostsecurityio/trivy-fs")
    assert result is True


async def test_has_test_definition_missing(tmp_path: Path) -> None:
    """has_test_definition returns False when tests.yaml doesn't exist."""
    scanner_dir = tmp_path / "scanners" / "boostsecurityio" / "trivy-fs"
    scanner_dir.mkdir(parents=True)

    result = await has_test_definition(tmp_path, "boostsecurityio/trivy-fs")
    assert result is False


async def test_detect_changed_scanners_with_tests(tmp_path: Path) -> None:
    """detect_changed_scanners returns only scanners with tests.yaml."""
    scanner1_dir = tmp_path / "scanners" / "boostsecurityio" / "scanner1"
    scanner2_dir = tmp_path / "scanners" / "boostsecurityio" / "scanner2"
    scanner1_dir.mkdir(parents=True)
    scanner2_dir.mkdir(parents=True)
    (scanner1_dir / "tests.yaml").write_text("version: 1.0\n")

    changed_files = [
        "scanners/boostsecurityio/scanner1/module.yaml",
        "scanners/boostsecurityio/scanner2/module.yaml",
    ]

    with (
        patch(
            "boostsec.registry_test_action.scanner_detector._get_changed_files",
            return_value=changed_files,
        ),
        patch(
            "boostsec.registry_test_action.scanner_detector._log_git_status",
            return_value=None,
        ),
    ):
        scanners = await detect_changed_scanners(tmp_path, "main", "HEAD")

    assert scanners == ["boostsecurityio/scanner1"]


async def test_detect_changed_scanners_none_with_tests(tmp_path: Path) -> None:
    """detect_changed_scanners returns empty list when no scanners have tests."""
    scanner_dir = tmp_path / "scanners" / "boostsecurityio" / "scanner1"
    scanner_dir.mkdir(parents=True)

    changed_files = ["scanners/boostsecurityio/scanner1/module.yaml"]

    with (
        patch(
            "boostsec.registry_test_action.scanner_detector._get_changed_files",
            return_value=changed_files,
        ),
        patch(
            "boostsec.registry_test_action.scanner_detector._log_git_status",
            return_value=None,
        ),
    ):
        scanners = await detect_changed_scanners(tmp_path, "main", "HEAD")

    assert scanners == []


async def test_detect_changed_scanners_no_changes(tmp_path: Path) -> None:
    """detect_changed_scanners returns empty list when no files changed."""
    with (
        patch(
            "boostsec.registry_test_action.scanner_detector._get_changed_files",
            return_value=[],
        ),
        patch(
            "boostsec.registry_test_action.scanner_detector._log_git_status",
            return_value=None,
        ),
    ):
        scanners = await detect_changed_scanners(tmp_path, "main", "HEAD")

    assert scanners == []
