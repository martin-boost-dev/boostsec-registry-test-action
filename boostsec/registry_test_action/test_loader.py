"""Load and parse test definitions from YAML files."""

from pathlib import Path

import yaml

from boostsec.registry_test_action.models.test_definition import TestDefinition


async def load_test_definition(registry_path: Path, scanner_id: str) -> TestDefinition:
    """Load test definition for a scanner.

    Args:
        registry_path: Path to the scanner registry repository
        scanner_id: Scanner identifier (e.g., "boostsecurityio/trivy-fs")

    Returns:
        Parsed test definition

    Raises:
        FileNotFoundError: If tests.yaml doesn't exist
        ValueError: If YAML is invalid or doesn't match schema

    """
    test_file = registry_path / "scanners" / scanner_id / "tests.yaml"

    if not test_file.exists():
        raise FileNotFoundError(f"Test file not found: {test_file}")

    try:
        with test_file.open() as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {test_file}: {e}") from e

    if data is None:
        raise ValueError(f"Empty test file: {test_file}")

    try:
        return TestDefinition.model_validate(data)
    except Exception as e:
        raise ValueError(f"Invalid test definition schema in {test_file}: {e}") from e


async def load_all_tests(
    registry_path: Path, scanner_ids: list[str]
) -> dict[str, TestDefinition]:
    """Load test definitions for multiple scanners.

    Args:
        registry_path: Path to the scanner registry repository
        scanner_ids: List of scanner identifiers

    Returns:
        Dictionary mapping scanner IDs to their test definitions
        Scanners with missing or invalid tests are excluded

    """
    results: dict[str, TestDefinition] = {}

    for scanner_id in scanner_ids:
        try:
            definition = await load_test_definition(registry_path, scanner_id)
            results[scanner_id] = definition
        except (FileNotFoundError, ValueError):
            # Skip scanners with missing or invalid test definitions
            continue

    return results
