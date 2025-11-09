"""Detect modified scanners in a git repository."""

import asyncio
from collections.abc import Sequence
from pathlib import Path


async def detect_changed_scanners(
    registry_path: Path, base_ref: str, head_ref: str
) -> list[str]:
    """Detect scanners modified between base_ref and head_ref.

    Args:
        registry_path: Path to the scanner registry repository
        base_ref: Base git reference (e.g., "origin/main")
        head_ref: Head git reference (e.g., "HEAD")

    Returns:
        List of scanner identifiers (e.g., ["boostsecurityio/trivy-fs"])

    """
    changed_files = await _get_changed_files(registry_path, base_ref, head_ref)
    scanner_paths = _extract_scanner_paths(changed_files)
    scanners_with_tests = []

    for scanner_path in scanner_paths:
        if await has_test_definition(registry_path, scanner_path):
            scanners_with_tests.append(scanner_path)

    return scanners_with_tests


async def has_test_definition(registry_path: Path, scanner_id: str) -> bool:
    """Check if scanner has a tests.yaml file.

    Args:
        registry_path: Path to the scanner registry repository
        scanner_id: Scanner identifier (e.g., "boostsecurityio/trivy-fs")

    Returns:
        True if tests.yaml exists, False otherwise

    """
    test_file = registry_path / "scanners" / scanner_id / "tests.yaml"
    return test_file.exists()


async def _get_changed_files(
    registry_path: Path, base_ref: str, head_ref: str
) -> list[str]:
    """Get list of changed files between two git refs.

    Args:
        registry_path: Path to the git repository
        base_ref: Base git reference
        head_ref: Head git reference

    Returns:
        List of changed file paths relative to repository root

    """
    process = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "--name-only",
        base_ref,
        head_ref,
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        raise RuntimeError(f"Git command failed: {error_msg}")

    files = stdout.decode().strip().split("\n")
    return [f for f in files if f]


def _extract_scanner_paths(changed_files: Sequence[str]) -> list[str]:
    """Extract unique scanner identifiers from changed file paths.

    Args:
        changed_files: List of file paths (e.g., ["scanners/org/scanner/module.yaml"])

    Returns:
        List of unique scanner identifiers (e.g., ["org/scanner"])

    """
    scanner_paths = set()

    for file_path in changed_files:
        if not file_path.startswith("scanners/"):
            continue

        parts = Path(file_path).parts
        if len(parts) < 4:
            continue

        scanner_id = f"{parts[1]}/{parts[2]}"
        scanner_paths.add(scanner_id)

    return sorted(scanner_paths)
