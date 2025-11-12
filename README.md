# Scanner Registry Test Action

[![boostsecurity](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action)](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action/details)

Automated testing system for validating scanner updates across multiple CI/CD platforms (GitHub Actions, GitLab CI, Azure DevOps, Bitbucket Pipelines).

## Quick Start

**📚 For detailed setup instructions, see [CONFIGURATION.md](./CONFIGURATION.md)**

This guide covers:
- ✅ Source repository setup (GitHub workflow configuration)
- ✅ GitLab test runner setup (token creation, .gitlab-ci.yml)
- ✅ GitHub test runner setup (PAT creation, workflow_dispatch)
- ✅ Scanner repository structure (tests.yaml format)
- ✅ Troubleshooting common issues

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

The action uses a JSON configuration string for provider-specific settings. Each provider requires different authentication tokens and configuration parameters stored as repository secrets.

### Provider Configuration Schemas

#### GitHub Actions
```json
{
  "token": "your-github-token",
  "owner": "repository-owner",
  "repo": "repository-name",
  "workflow_id": "workflow.yml"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | Yes | GitHub personal access token or `GITHUB_TOKEN` with `actions: write, contents: read` |
| `owner` | string | Yes | Repository owner (organization or user) |
| `repo` | string | Yes | Repository name |
| `workflow_id` | string | Yes | Workflow file name or ID to dispatch |

#### GitLab CI
```json
{
  "token": "your-gitlab-token",
  "project_id": "12345",
  "ref": "main"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | Yes | GitLab Project Access Token with Maintainer role and `api` scope |
| `project_id` | string | Yes | GitLab project ID (numeric) or full path (e.g., "group/subgroup/project") |
| `ref` | string | No | Branch to run tests on (default: "main") |

**⚠️ Important**: Must use **Project Access Token** with **Maintainer role** to run pipelines on protected branches. See [CONFIGURATION.md](./CONFIGURATION.md#gitlab-test-runner-setup) for detailed token setup.

#### Azure DevOps
```json
{
  "token": "your-azure-pat",
  "organization": "your-org",
  "project": "your-project",
  "pipeline_id": 123
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | Yes | Azure Personal Access Token with `Code (R&W), Build (R&E)` permissions |
| `organization` | string | Yes | Azure DevOps organization name |
| `project` | string | Yes | Azure DevOps project name |
| `pipeline_id` | integer | Yes | Pipeline/Build definition ID |

#### Bitbucket Pipelines
```json
{
  "username": "your-username",
  "app_password": "your-app-password",
  "workspace": "your-workspace",
  "repo_slug": "repository-slug"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Bitbucket username |
| `app_password` | string | Yes | Bitbucket App Password with `repository:write, pipeline:write` permissions |
| `workspace` | string | Yes | Bitbucket workspace slug |
| `repo_slug` | string | Yes | Repository slug for the runner |

## Usage

Add this action to your scanner-registry workflow. The action supports testing on multiple CI/CD providers by specifying the provider type and configuration as JSON.

### GitHub Actions Example

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
          provider: github
          provider-config: |
            {
              "token": "${{ secrets.GITHUB_TOKEN }}",
              "owner": "${{ github.repository_owner }}",
              "repo": "scanner-test-runner",
              "workflow_id": "test-scanner.yml"
            }
```

### GitLab CI Example

```yaml
- uses: boostsecurityio/registry-test-action@v1
  with:
    provider: gitlab
    provider-config: |
      {
        "token": "${{ secrets.GITLAB_TOKEN }}",
        "project_id": "your-group/test-runner",
        "ref": "main"
      }
```

### Azure DevOps Example

```yaml
- uses: boostsecurityio/registry-test-action@v1
  with:
    provider: azure
    provider-config: |
      {
        "token": "${{ secrets.AZURE_PAT }}",
        "organization": "${{ secrets.AZURE_ORG }}",
        "project": "${{ secrets.AZURE_PROJECT }}",
        "pipeline_id": ${{ secrets.AZURE_PIPELINE_ID }}
      }
```

### Bitbucket Pipelines Example

```yaml
- uses: boostsecurityio/registry-test-action@v1
  with:
    provider: bitbucket
    provider-config: |
      {
        "username": "${{ secrets.BITBUCKET_USERNAME }}",
        "app_password": "${{ secrets.BITBUCKET_APP_PASSWORD }}",
        "workspace": "${{ secrets.BITBUCKET_WORKSPACE }}",
        "repo_slug": "${{ secrets.BITBUCKET_REPO_SLUG }}"
      }
```

### Optional Parameters

All examples above can include these optional parameters:

```yaml
- uses: boostsecurityio/registry-test-action@v1
  with:
    provider: github
    provider-config: '{ ... }'
    registry-path: '.'           # Path to scanner registry (default: '.')
    base-ref: 'origin/main'      # Base git reference (default: 'origin/main')
    head-ref: 'HEAD'             # Head git reference (default: 'HEAD')
```

**Note**: In GitHub Actions, the `base-ref` should use the `origin/` prefix (e.g., `origin/main`) since the checkout action creates a detached HEAD with only remote refs available.

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
│       ├── cli.py                     # CLI entry point
│       ├── orchestrator.py            # Test orchestration
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
- **Module tests**: End-to-end tests of the action using [act](https://nektosact.com/) (requires Docker and act to be installed)

```bash
# Run all tests
make test

# Run specific test file
poetry run pytest tests/unit/test_scanner_detector.py

# Update snapshots
make snapshot.update
```

### Module Test Requirements

The end-to-end module tests require:
- [act](https://nektosact.com/) - Run GitHub Actions locally
- Docker - Required by act to run action containers

Install act:
```bash
# macOS
brew install act

# Linux
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Windows
choco install act-cli
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
