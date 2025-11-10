"""Detect modified scanners in a git repository."""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


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
    logger.info(
        "Detecting changed scanners",
        extra={
            "registry_path": str(registry_path),
            "base_ref": base_ref,
            "head_ref": head_ref,
        },
    )

    # Log git status for debugging
    await _log_git_status(registry_path, base_ref, head_ref)

    changed_files = await _get_changed_files(registry_path, base_ref, head_ref)
    logger.info(f"Found {len(changed_files)} changed files")

    scanner_paths = _extract_scanner_paths(changed_files)
    logger.info(f"Extracted {len(scanner_paths)} scanner paths: {scanner_paths}")

    scanners_with_tests = []
    for scanner_path in scanner_paths:
        if await has_test_definition(registry_path, scanner_path):
            logger.info(f"Scanner {scanner_path} has tests.yaml")
            scanners_with_tests.append(scanner_path)
        else:
            logger.info(f"Scanner {scanner_path} has no tests.yaml, skipping")

    logger.info(f"Found {len(scanners_with_tests)} scanners with tests")
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


async def _log_git_status(  # pragma: no cover
    registry_path: Path, base_ref: str, head_ref: str
) -> None:
    """Log git repository status for debugging."""
    # Log current branch
    process = await asyncio.create_subprocess_exec(
        "git",
        "branch",
        "--show-current",
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    current_branch = stdout.decode().strip() or "(detached HEAD)"
    logger.info(f"Current git branch: {current_branch}")

    # Log available refs
    process = await asyncio.create_subprocess_exec(
        "git",
        "show-ref",
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if stdout:
        refs = stdout.decode().strip().split("\n")[:10]  # First 10 refs
        logger.info(f"Available git refs (first 10): {refs}")

    # Check if base_ref exists
    process = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--verify",
        base_ref,
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode == 0:
        logger.info(f"Base ref '{base_ref}' exists: {stdout.decode().strip()}")
    else:
        logger.warning(f"Base ref '{base_ref}' not found: {stderr.decode().strip()}")


async def _resolve_ref(registry_path: Path, ref: str) -> str:
    """Resolve a git reference, trying origin/ prefix if needed.

    In CI environments like GitHub Actions, refs often exist as origin/main
    instead of main. This function tries both.

    Args:
        registry_path: Path to the git repository
        ref: Git reference to resolve

    Returns:
        Resolved git reference

    Raises:
        RuntimeError: If the reference cannot be resolved

    """
    # Try the ref as-is first
    process = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--verify",
        ref,
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        resolved = stdout.decode().strip()
        logger.info(f"Resolved ref '{ref}' to {resolved}")
        return ref

    # If that failed and ref doesn't already have origin/, try with origin/ prefix
    if not ref.startswith("origin/") and not ref.startswith("refs/"):
        origin_ref = f"origin/{ref}"
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--verify",
            origin_ref,
            cwd=registry_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            resolved = stdout.decode().strip()
            logger.info(f"Resolved ref '{ref}' as '{origin_ref}' to {resolved}")
            return origin_ref

    # Both attempts failed
    error_msg = stderr.decode().strip()
    raise RuntimeError(
        f"Cannot resolve git ref '{ref}'. Tried '{ref}' and 'origin/{ref}'. "
        f"Error: {error_msg}"
    )


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
    # Resolve refs (they might need origin/ prefix in CI)
    resolved_base = await _resolve_ref(registry_path, base_ref)
    resolved_head = await _resolve_ref(registry_path, head_ref)

    logger.info(f"Running: git diff --name-only {resolved_base} {resolved_head}")

    process = await asyncio.create_subprocess_exec(
        "git",
        "diff",
        "--name-only",
        resolved_base,
        resolved_head,
        cwd=registry_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        logger.error(f"Git diff command failed with exit code {process.returncode}")
        logger.error(f"Git stderr: {error_msg}")
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
