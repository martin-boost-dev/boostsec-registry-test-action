# Scanner Registry Test Action - Implementation Guide

This document provides detailed implementation guidance for building the scanner registry test action.

## Implementation Phases

### Phase 1: Core Models and Data Structures

**Files to create:**
- `boostsec/registry_test_action/models/test_definition.py`
- `boostsec/registry_test_action/models/provider_config.py`
- `boostsec/registry_test_action/models/test_result.py`

**Models needed:**

1. **TestDefinition** (test_definition.py)
   - `version`: str - Test definition version (e.g., "1.0")
   - `tests`: list[Test] - List of test specifications

2. **Test** (test_definition.py)
   - `name`: str - Test name
   - `type`: Literal["source-code", "docker-image"] - Test type
   - `source`: TestSource - Source repository details
   - `scan_paths`: list[str] - Paths to scan
   - `scan_configs`: list[dict] | None - Optional scan configurations
   - `timeout`: str - Timeout (e.g., "300s"), default "5m"

3. **TestSource** (test_definition.py)
   - `url`: str - Git repository URL
   - `ref`: str - Branch/tag reference

4. **ProviderConfig** (provider_config.py)
   - Base configuration for all providers
   - Provider-specific configurations (GitHubConfig, GitLabConfig, etc.)

5. **TestResult** (test_result.py)
   - `provider`: str - Provider name
   - `scanner`: str - Scanner identifier
   - `test_name`: str - Test name
   - `status`: Literal["success", "failure", "timeout", "error"]
   - `duration`: float - Execution time in seconds
   - `message`: str | None - Error/status message
   - `run_url`: str | None - Link to CI run

**Dependencies to add:**
```bash
poetry add pydantic pyyaml
```

**Tests to write:**
- `tests/unit/models/test_test_definition.py` - Test model validation and parsing
- `tests/unit/models/test_provider_config.py` - Test provider configurations

---

### Phase 2: Scanner Detection

**Files to create:**
- `boostsec/registry_test_action/scanner_detector.py`

**Functionality:**
- Detect modified scanners in a PR by comparing HEAD with base branch
- Use git commands to find changed files under `scanners/`
- Extract scanner identifiers (e.g., "boostsecurityio/trivy-fs")
- Filter only scanners that have a `tests.yaml` file

**Key functions:**
```python
async def detect_changed_scanners(
    registry_path: Path,
    base_ref: str,
    head_ref: str
) -> list[str]:
    """Detect scanners modified between base_ref and head_ref."""
    pass

async def has_test_definition(
    registry_path: Path,
    scanner_id: str
) -> bool:
    """Check if scanner has a tests.yaml file."""
    pass
```

**Dependencies:**
- Uses subprocess/asyncio.create_subprocess_exec for git commands
- No new dependencies needed

**Tests to write:**
- `tests/unit/test_scanner_detector.py` - Test scanner detection logic with mocked git output
- Create test fixtures with sample git diff output

---

### Phase 3: Test Definition Loader

**Files to create:**
- `boostsec/registry_test_action/test_loader.py`

**Functionality:**
- Load and parse `tests.yaml` files from scanner directories
- Validate test definitions against the schema
- Handle missing or invalid test files gracefully

**Key functions:**
```python
async def load_test_definition(
    registry_path: Path,
    scanner_id: str
) -> TestDefinition:
    """Load test definition for a scanner."""
    pass

async def load_all_tests(
    registry_path: Path,
    scanner_ids: list[str]
) -> dict[str, TestDefinition]:
    """Load test definitions for multiple scanners."""
    pass
```

**Error handling:**
- File not found → skip scanner (log warning)
- Invalid YAML → raise exception with clear message
- Schema validation error → raise exception with field details

**Tests to write:**
- `tests/unit/test_test_loader.py` - Test loading valid/invalid YAML files
- Create test fixture YAML files

---

### Phase 4: Provider Base Interface

**Files to create:**
- `boostsec/registry_test_action/providers/__init__.py`
- `boostsec/registry_test_action/providers/base.py`

**Abstract interface:**
```python
class PipelineProvider(ABC):
    """Abstract base for CI/CD pipeline providers."""

    @abstractmethod
    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str
    ) -> str:
        """
        Dispatch a test run and return a run identifier.

        Args:
            scanner_id: Scanner identifier (e.g., "boostsecurityio/trivy-fs")
            test: Test definition to execute
            registry_ref: Git ref of the registry (for checking out scanner)

        Returns:
            Run identifier for polling status
        """
        pass

    @abstractmethod
    async def poll_status(
        self,
        run_id: str
    ) -> tuple[bool, TestResult]:
        """
        Check if test run is complete and get result.

        Args:
            run_id: Run identifier from dispatch_test

        Returns:
            Tuple of (is_complete, result)
        """
        pass

    @abstractmethod
    async def wait_for_completion(
        self,
        run_id: str,
        timeout: int = 1800,  # 30 minutes
        poll_interval: int = 30
    ) -> TestResult:
        """
        Wait for test run to complete.

        Args:
            run_id: Run identifier from dispatch_test
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            Final test result

        Raises:
            TimeoutError: If run doesn't complete within timeout
        """
        pass
```

**Dependencies to add:**
```bash
poetry add aiohttp
```

**Tests to write:**
- `tests/unit/providers/test_base.py` - Test base class behavior and helpers

---

### Phase 5: GitHub Provider Implementation

**Files to create:**
- `boostsec/registry_test_action/providers/github.py`

**Implementation details:**
- Use GitHub Actions API for workflow dispatch
- Poll using `GET /repos/{owner}/{repo}/actions/runs/{run_id}`
- Handle workflow finding (match by dispatch time and status)
- Parse conclusion (success, failure, cancelled, etc.)

**Key methods:**
```python
class GitHubProvider(PipelineProvider):
    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: str
    ):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.workflow_id = workflow_id
        self.base_url = "https://api.github.com"

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str
    ) -> str:
        """Dispatch workflow and return run ID."""
        # POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
        # Wait and find the run by matching dispatch time
        pass
```

**API endpoints:**
- Dispatch: `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`
- List runs: `GET /repos/{owner}/{repo}/actions/runs?workflow_id={id}&per_page=5`
- Get run: `GET /repos/{owner}/{repo}/actions/runs/{run_id}`

**Tests to write:**
- `tests/unit/providers/test_github.py` - Test with mocked aiohttp responses
- Mock the API responses for dispatch, list, and get operations

---

### Phase 6: GitLab Provider Implementation

**Files to create:**
- `boostsec/registry_test_action/providers/gitlab.py`

**Implementation details:**
- Use GitLab CI API for pipeline trigger
- Pass scanner_id, test details as pipeline variables
- Poll using `GET /projects/{id}/pipelines/{pipeline_id}`

**Key methods:**
```python
class GitLabProvider(PipelineProvider):
    def __init__(
        self,
        token: str,
        project_id: str,
        ref: str = "main"
    ):
        self.token = token
        self.project_id = project_id
        self.ref = ref
        self.base_url = "https://gitlab.com/api/v4"

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str
    ) -> str:
        """Trigger pipeline and return pipeline ID."""
        # POST /projects/{id}/trigger/pipeline
        # or POST /projects/{id}/pipeline with variables
        pass
```

**API endpoints:**
- Trigger: `POST /projects/{id}/trigger/pipeline`
- Get pipeline: `GET /projects/{id}/pipelines/{pipeline_id}`

**Tests to write:**
- `tests/unit/providers/test_gitlab.py` - Test with mocked aiohttp responses

---

### Phase 7: Azure DevOps Provider Implementation

**Files to create:**
- `boostsec/registry_test_action/providers/azure.py`

**Implementation details:**
- Use Azure DevOps REST API for build queue
- Pass parameters via template parameters or variables
- Poll using `GET /{organization}/{project}/_apis/build/builds/{buildId}`

**Key methods:**
```python
class AzureDevOpsProvider(PipelineProvider):
    def __init__(
        self,
        token: str,
        organization: str,
        project: str,
        pipeline_id: int
    ):
        self.token = token
        self.organization = organization
        self.project = project
        self.pipeline_id = pipeline_id
        self.base_url = f"https://dev.azure.com/{organization}"

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str
    ) -> str:
        """Queue build and return build ID."""
        # POST /{org}/{project}/_apis/build/builds?api-version=7.0
        pass
```

**API endpoints:**
- Queue: `POST /{org}/{project}/_apis/build/builds?api-version=7.0`
- Get build: `GET /{org}/{project}/_apis/build/builds/{buildId}?api-version=7.0`

**Authentication:**
- Use Basic Auth with empty username and PAT as password
- Encode as base64: `base64(":" + token)`

**Tests to write:**
- `tests/unit/providers/test_azure.py` - Test with mocked aiohttp responses

---

### Phase 8: Bitbucket Provider Implementation

**Files to create:**
- `boostsec/registry_test_action/providers/bitbucket.py`

**Implementation details:**
- Use Bitbucket Cloud API for pipeline trigger
- Pass custom pipeline variables
- Poll using `GET /repositories/{workspace}/{repo_slug}/pipelines/{uuid}`

**Key methods:**
```python
class BitbucketProvider(PipelineProvider):
    def __init__(
        self,
        username: str,
        app_password: str,
        workspace: str,
        repo_slug: str
    ):
        self.username = username
        self.app_password = app_password
        self.workspace = workspace
        self.repo_slug = repo_slug
        self.base_url = "https://api.bitbucket.org/2.0"

    async def dispatch_test(
        self,
        scanner_id: str,
        test: Test,
        registry_ref: str
    ) -> str:
        """Trigger pipeline and return pipeline UUID."""
        # POST /repositories/{workspace}/{repo}/pipelines/
        pass
```

**API endpoints:**
- Trigger: `POST /repositories/{workspace}/{repo_slug}/pipelines/`
- Get pipeline: `GET /repositories/{workspace}/{repo_slug}/pipelines/{uuid}`

**Authentication:**
- Use Basic Auth with username and app password

**Tests to write:**
- `tests/unit/providers/test_bitbucket.py` - Test with mocked aiohttp responses

---

### Phase 9: Main Orchestration

**Files to create:**
- `boostsec/registry_test_action/orchestrator.py`

**Functionality:**
- Coordinate the entire test execution flow
- Dispatch tests to all providers in parallel
- Aggregate results from all providers
- Generate final status report

**Key functions:**
```python
class TestOrchestrator:
    def __init__(
        self,
        providers: dict[str, PipelineProvider],
        registry_path: Path
    ):
        self.providers = providers
        self.registry_path = registry_path

    async def run_tests(
        self,
        base_ref: str,
        head_ref: str
    ) -> dict[str, list[TestResult]]:
        """
        Run all tests for changed scanners.

        Returns:
            Dictionary mapping provider names to their test results
        """
        # 1. Detect changed scanners
        # 2. Load test definitions
        # 3. For each provider:
        #    - Dispatch all tests in parallel
        #    - Wait for completion
        # 4. Aggregate and return results
        pass

    async def dispatch_provider_tests(
        self,
        provider_name: str,
        provider: PipelineProvider,
        scanner_tests: dict[str, TestDefinition],
        registry_ref: str
    ) -> list[TestResult]:
        """Dispatch all tests for a single provider."""
        pass
```

**Tests to write:**
- `tests/unit/test_orchestrator.py` - Test orchestration logic with mocked providers
- `tests/integration/test_orchestrator.py` - Integration test with real provider setup

---

### Phase 10: CLI Entry Point

**Files to create:**
- `boostsec/registry_test_action/main.py`

**Functionality:**
- Command-line interface using Typer
- Load configuration from environment variables or CLI args
- Initialize providers based on configuration
- Run orchestrator and report results
- Exit with appropriate status code

**Dependencies to add:**
```bash
poetry add typer "rich"  # rich for pretty output
```

**CLI structure:**
```python
import typer
from typing_extensions import Annotated

app = typer.Typer()

@app.command()
def test(
    registry_path: Annotated[Path, typer.Option(envvar="REGISTRY_PATH")] = Path("."),
    base_ref: Annotated[str, typer.Option(envvar="BASE_REF")] = "origin/main",
    head_ref: Annotated[str, typer.Option(envvar="HEAD_REF")] = "HEAD",

    # GitHub
    github_token: Annotated[str | None, typer.Option(envvar="GITHUB_TOKEN")] = None,
    github_owner: Annotated[str | None, typer.Option(envvar="GITHUB_OWNER")] = None,
    github_repo: Annotated[str | None, typer.Option(envvar="GITHUB_REPO")] = None,
    github_workflow_id: Annotated[str | None, typer.Option(envvar="GITHUB_WORKFLOW_ID")] = None,

    # GitLab
    gitlab_token: Annotated[str | None, typer.Option(envvar="GITLAB_TOKEN")] = None,
    gitlab_project_id: Annotated[str | None, typer.Option(envvar="GITLAB_PROJECT_ID")] = None,

    # Azure DevOps
    azure_pat: Annotated[str | None, typer.Option(envvar="AZURE_PAT")] = None,
    azure_org: Annotated[str | None, typer.Option(envvar="AZURE_ORG")] = None,
    azure_project: Annotated[str | None, typer.Option(envvar="AZURE_PROJECT")] = None,
    azure_pipeline_id: Annotated[int | None, typer.Option(envvar="AZURE_PIPELINE_ID")] = None,

    # Bitbucket
    bitbucket_username: Annotated[str | None, typer.Option(envvar="BITBUCKET_USERNAME")] = None,
    bitbucket_app_password: Annotated[str | None, typer.Option(envvar="BITBUCKET_APP_PASSWORD")] = None,
    bitbucket_workspace: Annotated[str | None, typer.Option(envvar="BITBUCKET_WORKSPACE")] = None,
    bitbucket_repo_slug: Annotated[str | None, typer.Option(envvar="BITBUCKET_REPO_SLUG")] = None,
) -> None:
    """Run scanner tests across all configured CI/CD providers."""
    pass

def main() -> None:
    app()
```

**Output format:**
- Use rich tables to display results
- Show provider status, test counts, duration
- Color-code success/failure

**Tests to write:**
- `tests/unit/test_main.py` - Test CLI argument parsing and provider initialization
- Use Typer's testing utilities

**Poetry script configuration:**
Add to pyproject.toml:
```toml
[tool.poetry.scripts]
registry-test-action = "boostsec.registry_test_action.main:main"
```

---

## Implementation Order Summary

1. **Phase 1**: Models (foundation for all other code)
2. **Phase 2**: Scanner detection (independent utility)
3. **Phase 3**: Test loader (depends on models)
4. **Phase 4**: Provider base (interface definition)
5. **Phase 5**: GitHub provider (simplest, native support)
6. **Phase 6**: GitLab provider
7. **Phase 7**: Azure provider
8. **Phase 8**: Bitbucket provider
9. **Phase 9**: Orchestrator (depends on all providers)
10. **Phase 10**: CLI entry point (final integration)

## Testing Strategy

### Unit Tests
- Mock all external dependencies (aiohttp, subprocess)
- Test each component in isolation
- Use pytest fixtures for common test data
- Aim for 100% coverage

### Integration Tests
- Requires test credentials for each provider
- Can use test/staging projects
- Tests should be skippable if credentials not available
- Use markers: `@pytest.mark.integration`

### Test Data Fixtures
Create realistic test data in `tests/fixtures/`:
- Sample `tests.yaml` files
- Mock API responses for each provider
- Git diff output examples

## Error Handling Strategy

### Expected Errors
- Scanner has no tests.yaml → Skip, log warning
- Provider credentials missing → Skip provider, log error
- API rate limiting → Retry with exponential backoff
- Test timeout → Mark as timeout, continue
- Network errors → Retry 3 times, then fail

### Unexpected Errors
- Invalid test.yaml schema → Fail fast with clear message
- Authentication failure → Fail immediately
- Unknown API response → Log full response, fail

## Logging Strategy

Use structured logging with boostsec-common:
```python
from boostsec.monitoring.logging import get_boostsec_logger

log = get_boostsec_logger()

log.info(
    "Dispatched test",
    provider="github",
    scanner_id="boostsecurityio/trivy-fs",
    test_name="smoke-test",
    run_id=run_id
)
```

## Security Considerations

1. **Token Handling**
   - Never log tokens or credentials
   - Use environment variables for secrets
   - Clear tokens from memory when done

2. **Input Validation**
   - Validate all YAML input against schema
   - Sanitize scanner IDs (no path traversal)
   - Validate URLs (must be HTTPS)

3. **API Security**
   - Use TLS for all API calls (aiohttp default)
   - Verify SSL certificates (don't disable)
   - Set reasonable timeouts on all requests

## Performance Considerations

1. **Parallelization**
   - Use asyncio.gather for provider dispatch
   - Each provider runs independently
   - Tests within a provider can be batched

2. **Resource Limits**
   - Limit concurrent API calls per provider (rate limiting)
   - Set maximum test duration (default 10 minutes)
   - Total execution timeout (default 30 minutes)

3. **Polling Efficiency**
   - Use exponential backoff for polling intervals
   - Start at 10s, increase to 30s max
   - Cancel polling on timeout

## Dependencies Summary

```toml
# Runtime dependencies
python = "^3.12"
aiohttp = "^3.9"
pydantic = "^2.0"
pyyaml = "^6.0"
typer = "^0.9"
rich = "^13.0"
boostsec-common = {git = "...", rev = "main"}

# Dev dependencies (already in template)
pytest = "^7.4.3"
pytest-cov = "^4.1.0"
mypy = "^1.11.0"
ruff = "0.*"
coverage = "^7.3.3"
```

## Commit Strategy

Each phase should have multiple small commits:

1. "Add test definition models and tests"
2. "Add provider config models and tests"
3. "Implement scanner detector and tests"
4. "Add test loader with validation and tests"
5. "Define provider base interface and tests"
6. "Implement GitHub provider and tests"
7. "Implement GitLab provider and tests"
8. "Implement Azure DevOps provider and tests"
9. "Implement Bitbucket provider and tests"
10. "Add test orchestrator and tests"
11. "Add CLI entry point and tests"
12. "Update documentation with examples"

Before each commit:
```bash
make format lint test
```

## Future Enhancements (Out of Scope for MVP)

- Result caching to avoid re-running identical tests
- Parallel test execution within providers
- Metrics dashboard for test results
- Slack/email notifications on failure
- Support for private test repositories
- Performance benchmarking and comparison
- Test result artifacts and logs

## Learnings and Implementation Notes

### Key Decisions Made During Implementation

1. **Repository Format**: Changed from sending full repository URLs to org/repo format
   - GitHub Actions workflows receive cleaner input: "org/repo" instead of "https://github.com/org/repo.git"
   - Parsing logic handles both HTTPS and SSH git URL formats
   - Improves compatibility with various CI/CD provider APIs

2. **Commit SHA Instead of Branch Name**:
   - Always send exact commit SHA instead of branch name (e.g., "abc123" instead of "scanner-setup")
   - Prevents race conditions where PR gets updated between dispatch and checkout
   - Ensures test runner checks out the exact code that was tested
   - Implemented via `git rev-parse HEAD` in CLI

3. **Multi-line JSON Output Fix**:
   - GitHub Actions `$GITHUB_OUTPUT` requires heredoc syntax for multi-line values
   - Changed from `echo "results=$JSON"` to heredoc format with `<<EOF`
   - Prevents "Invalid format" errors from GitHub Actions

4. **Test Duration from API Timestamps**:
   - Extract duration from workflow API response timestamps instead of wall-clock time
   - Use `created_at` and `updated_at` fields from API
   - Provides accurate test execution time without polling overhead
   - Handles missing/invalid timestamps gracefully (returns 0.0)

5. **GitHub Actions Environment Assumptions**:
   - Simplified git status logging - removed confusing warnings about detached HEAD
   - Changed default `base-ref` from "main" to "origin/main" to match GitHub Actions reality
   - Changed `head-ref` from required to optional with default "HEAD"
   - `_resolve_ref()` function automatically handles `origin/` prefix when needed

6. **Logging Cleanup**:
   - Removed redundant "Orchestrator:" prefixes from log messages
   - Logger format already includes module name, so prefixes were duplicative
   - Results in cleaner, more readable logs

### Mistakes to Avoid

1. **Don't use wall-clock time for test duration** - Always extract timing from the CI/CD provider's API response to get accurate execution time without polling overhead.

2. **Don't assume branch refs exist locally** - In GitHub Actions, only remote refs exist (e.g., "origin/main"), so always handle the origin/ prefix.

3. **Don't forget multi-line output handling** - GitHub Actions requires heredoc syntax for multi-line `$GITHUB_OUTPUT` values.

4. **Don't skip commit SHA resolution** - Always use exact commit SHA instead of branch name to prevent race conditions in concurrent environments.

### Testing Strategy

- Maintained 100% code coverage throughout development
- Used `aioresponses` to mock HTTP calls in provider tests
- Added comprehensive edge case testing for duration calculation
- All tests must pass with `make format lint test` before committing

### Action Defaults

The action now works out-of-the-box with sensible defaults:
- `registry-path`: "." (current directory)
- `base-ref`: "origin/main" (works with GitHub Actions checkout)
- `head-ref`: "HEAD" (current commit)
- Users only need to specify `provider` and `provider-config`
