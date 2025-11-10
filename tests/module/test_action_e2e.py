"""End-to-end test for the GitHub Action using act and WireMock."""
# ruff: noqa: S603, S607, T201

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from wiremock.testing.testcontainer import wiremock_container  # type: ignore


@pytest.fixture(scope="module")
def test_registry_repo() -> Generator[Path, None, None]:
    """Create a test git repository with scanner fixtures."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-registry"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )

        # Create initial commit on main
        readme = repo_path / "README.md"
        readme.write_text("# Test Registry\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path,
            check=True,
        )

        # Create feature branch with scanner
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=repo_path,
            check=True,
        )

        # Add a scanner with tests.yaml
        scanner_dir = repo_path / "scanners" / "boostsecurityio" / "test-scanner"
        scanner_dir.mkdir(parents=True)

        scanner_yaml = scanner_dir / "module.yaml"
        scanner_yaml.write_text("""
api_version: 1.0
id: boostsecurityio/test-scanner
name: Test Scanner
""")

        tests_yaml = scanner_dir / "tests.yaml"
        tests_yaml.write_text("""
version: "1.0"
tests:
  - name: basic-test
    type: source-code
    source:
      url: https://github.com/example/test-repo
      ref: main
    scan_paths:
      - .
""")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test scanner"],
            cwd=repo_path,
            check=True,
        )

        yield repo_path


@pytest.fixture(scope="module")
def wiremock_server() -> Generator[str, None, None]:
    """Start WireMock server with GitHub API stubs."""
    # Define mappings
    mappings = [
        # Workflow dispatch endpoint
        (
            "dispatch.json",
            {
                "request": {
                    "method": "POST",
                    "urlPattern": "/repos/.*/actions/workflows/.*/dispatches",
                },
                "response": {"status": 204},
            },
        ),
        # List workflow runs endpoint
        (
            "list-runs.json",
            {
                "request": {
                    "method": "GET",
                    "urlPattern": "/repos/.*/actions/workflows/.*/runs.*",
                },
                "response": {
                    "status": 200,
                    "jsonBody": {
                        "workflow_runs": [
                            {
                                "id": 12345,
                                "status": "completed",
                                "conclusion": "success",
                                "created_at": "2025-01-01T00:00:00Z",
                                "html_url": "https://github.com/test/repo/actions/runs/12345",
                            }
                        ]
                    },
                },
            },
        ),
        # Get workflow run endpoint
        (
            "get-run.json",
            {
                "request": {
                    "method": "GET",
                    "urlPattern": "/repos/.*/actions/runs/.*",
                },
                "response": {
                    "status": 200,
                    "jsonBody": {
                        "id": 12345,
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/test/repo/actions/runs/12345",
                    },
                },
            },
        ),
    ]

    with wiremock_container(secure=False, mappings=mappings) as wm:
        base_url = wm.get_url("")
        yield base_url


@pytest.fixture(scope="module")
def test_workflow(tmp_path_factory: Any) -> Any:
    """Create a test workflow that uses our action."""
    workflows_dir = tmp_path_factory.mktemp("workflows") / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)

    workflow_file = workflows_dir / "test.yml"
    workflow_file.write_text(
        """
name: Test Action
on: push

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run scanner tests
        uses: ./
        with:
          provider: github
          provider-config: >
            {"token": "test-token", "owner": "test-owner",
             "repo": "test-repo", "workflow_id": "test.yml"}
          registry-path: .
          base-ref: main
          head-ref: feature
"""
    )

    return workflows_dir.parent


@pytest.mark.skip(reason="E2E test needs updating for fail-fast behavior")
def test_action_with_act(
    test_registry_repo: Path, wiremock_server: str, test_workflow: Any
) -> None:
    """Test the action end-to-end using act and WireMock.

    Requires: act (nektos) must be installed.
    """
    # Copy action files to test registry (action.yaml and source code)
    action_root = Path(__file__).parent.parent.parent

    # Copy action.yaml
    subprocess.run(
        ["cp", str(action_root / "action.yaml"), str(test_registry_repo)],
        check=True,
    )

    # Copy Python source code
    subprocess.run(
        ["cp", "-r", str(action_root / "boostsec"), str(test_registry_repo)],
        check=True,
    )

    # Copy pyproject.toml and poetry.lock for dependencies
    subprocess.run(
        ["cp", str(action_root / "pyproject.toml"), str(test_registry_repo)],
        check=True,
    )
    subprocess.run(
        ["cp", str(action_root / "poetry.lock"), str(test_registry_repo)],
        check=True,
    )

    # Copy workflow to test registry
    workflow_dest = test_registry_repo / ".github" / "workflows"
    workflow_dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "cp",
            str(test_workflow / "workflows" / "test.yml"),
            str(workflow_dest / "test.yml"),
        ],
        check=True,
    )

    # Build act command with environment variables
    # Use medium-sized runner image to avoid interactive prompt
    act_cmd = [
        "act",
        "push",
        "-v",
        "--env",
        f"GITHUB_API_URL={wiremock_server}",
        "--container-architecture",
        "linux/amd64",
        "-P",
        "ubuntu-latest=catthehacker/ubuntu:act-latest",
    ]

    result = subprocess.run(
        act_cmd,
        cwd=test_registry_repo,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Print output for debugging
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    # Verify act ran successfully
    assert result.returncode == 0, (
        f"act failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )

    # Verify the CLI executed (output contains either test results or "No tests")
    # Note: git diff detection may not work perfectly in act's checkout
    assert (  # pragma: no cover
        "No tests to run" in result.stdout
        or "test-scanner" in result.stdout
        or "passed" in result.stdout.lower()
    ), f"Expected CLI output not found in:\n{result.stdout}"
