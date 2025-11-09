# Scanner Registry Test Action

[![boostsecurity](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action)](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action/details)

Automated testing system for validating scanner updates across multiple CI/CD platforms (GitHub Actions, GitLab CI, Azure DevOps, Bitbucket Pipelines).

## Overview

This action runs when a scanner is modified in the scanner-registry repository. It:

1. **Detects Modified Scanners**: Identifies which scanners have changed in a pull request
2. **Reads Test Definitions**: Loads test specifications from `tests.yaml` files
3. **Dispatches Tests**: Triggers test execution on remote CI/CD providers in parallel
4. **Monitors Progress**: Polls for test completion using provider-specific APIs
5. **Reports Results**: Updates pull request status with pass/fail results

## Architecture

```
scanner-registry PR
    ↓
Detect Changed Scanners
    ↓
Read tests.yaml for each scanner
    ↓
Dispatch Tests in Parallel
    ├─→ GitHub Actions (native)
    ├─→ GitLab CI (API dispatch)
    ├─→ Azure DevOps (API dispatch)
    └─→ Bitbucket Pipelines (API dispatch)
    ↓
Poll for Completion
    ↓
Report PR Status
```

## Test Definition Format

Tests are defined in `tests.yaml` files alongside scanner `module.yaml` files:

```yaml
# scanners/boostsecurityio/trivy-fs/tests.yaml
version: 1.0
tests:
  - name: "Smoke test - source code"
    type: "source-code"
    source:
      url: "https://github.com/OWASP/NodeGoat.git"
      ref: "main"
    scan_paths:
      - "."

  - name: "Smoke test - docker image"
    type: "docker-image"
    source:
      url: "https://github.com/vulnerables/web-dvwa.git"
      ref: "v1.9"
    scan_paths:
      - "."
    timeout: 300s
```

## Provider-Specific Implementation

Each CI/CD provider has a dedicated implementation:

- **GitHub Actions**: Uses native workflow dispatch and polling
- **GitLab CI**: Triggers pipeline via API, polls for status
- **Azure DevOps**: Triggers build via API, monitors completion
- **Bitbucket Pipelines**: Triggers pipeline via API, checks status

All providers use `aiohttp` for async HTTP operations.

## Configuration

The action expects repository secrets for authentication:

| Provider | Secret Name | Type | Permissions |
|----------|-------------|------|-------------|
| GitHub | `GITHUB_TOKEN` | Auto-generated | `actions: write, contents: read` |
| GitLab | `GITLAB_TOKEN` | Personal Access Token | `api, write_repository` |
| Azure | `AZURE_PAT` | Personal Access Token | `Code (R&W), Build (R&E)` |
| Bitbucket | `BITBUCKET_APP_PASSWORD` | App Password | `repository:write, pipeline:write` |

Additionally, each provider requires repository configuration:

| Provider | Config Secret | Description |
|----------|---------------|-------------|
| GitLab | `GITLAB_PROJECT_ID` | Project ID for the runner repository |
| Azure | `AZURE_ORG` | Azure DevOps organization |
| Azure | `AZURE_PROJECT` | Azure DevOps project name |
| Azure | `AZURE_PIPELINE_ID` | Pipeline/Build definition ID |
| Bitbucket | `BITBUCKET_WORKSPACE` | Bitbucket workspace slug |
| Bitbucket | `BITBUCKET_REPO_SLUG` | Repository slug for the runner |

## Usage

Add this action to your scanner-registry workflow:

```yaml
name: Test Scanner Updates

on:
  pull_request:
    paths:
      - 'scanners/**'

jobs:
  test-scanners:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history to detect changes

      - uses: boostsecurityio/registry-test-action@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          gitlab-token: ${{ secrets.GITLAB_TOKEN }}
          gitlab-project-id: ${{ secrets.GITLAB_PROJECT_ID }}
          azure-pat: ${{ secrets.AZURE_PAT }}
          azure-org: ${{ secrets.AZURE_ORG }}
          azure-project: ${{ secrets.AZURE_PROJECT }}
          azure-pipeline-id: ${{ secrets.AZURE_PIPELINE_ID }}
          bitbucket-username: ${{ secrets.BITBUCKET_USERNAME }}
          bitbucket-app-password: ${{ secrets.BITBUCKET_APP_PASSWORD }}
          bitbucket-workspace: ${{ secrets.BITBUCKET_WORKSPACE }}
          bitbucket-repo-slug: ${{ secrets.BITBUCKET_REPO_SLUG }}
```

## Development

### Prerequisites

- Python 3.12+
- Poetry
- Make

### Setup

```bash
# Install dependencies
make install

# Activate virtual environment
source .venv/bin/activate

# Install pre-commit hooks (optional)
pre-commit install
```

### Development Workflow

```bash
# Format and lint code before committing
make format lint

# Run tests with coverage
make test

# Update dependencies
make update

# Add new dependency
poetry add <package>

# Add dev dependency
poetry add <package> --group dev
```

### Project Structure

```
boostsec-registry-test-action/
├── boostsec/
│   └── registry_test_action/
│       ├── __init__.py
│       ├── main.py                    # Entry point (Typer CLI)
│       ├── scanner_detector.py        # Detect changed scanners
│       ├── test_loader.py             # Load tests.yaml files
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py                # Abstract provider interface
│       │   ├── github.py              # GitHub Actions provider
│       │   ├── gitlab.py              # GitLab CI provider
│       │   ├── azure.py               # Azure DevOps provider
│       │   └── bitbucket.py           # Bitbucket Pipelines provider
│       └── models/
│           ├── __init__.py
│           ├── test_definition.py     # Test definition models
│           └── provider_config.py     # Provider configuration models
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
├── README.md
├── AGENT.md                           # Implementation details
└── CLAUDE.md                          # Symlink to AGENT.md
```

## Testing

The project maintains 100% code coverage with:

- **Unit tests**: Test individual components with mocks
- **Integration tests**: Test provider API interactions (with test credentials)

```bash
# Run all tests
make test

# Run specific test file
poetry run pytest tests/unit/test_scanner_detector.py

# Update snapshots
make snapshot.update
```

## Security

- Only clones from allowlisted public repositories
- Never executes arbitrary code from test targets
- All API calls use TLS/HTTPS
- Tokens stored as repository secrets
- Timeout enforcement on all operations

## Limitations

- Polling interval: 30 seconds (may add latency)
- Maximum test timeout: 10 minutes per test
- Bitbucket: Limited parallel execution (provider constraint)

## Contributing

1. Create a feature branch
2. Make changes with tests
3. Run `make format lint test`
4. Submit pull request
5. Ensure all CI checks pass

## License

Copyright © 2024 Boost Security
