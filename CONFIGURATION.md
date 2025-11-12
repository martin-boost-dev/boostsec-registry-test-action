# Configuration Guide

This guide explains how to configure both the **source repository** (scanner registry) and **target test runners** (GitLab/GitHub) to use the Scanner Registry Test Action.

## Table of Contents

- [Source Repository Setup](#source-repository-setup)
- [GitLab Test Runner Setup](#gitlab-test-runner-setup)
- [GitHub Test Runner Setup](#github-test-runner-setup)
- [Scanner Repository Structure](#scanner-repository-structure)

---

## Source Repository Setup

### 1. GitHub Action Workflow

Create `.github/workflows/test-scanners.yml` in your scanner registry repository:

```yaml
name: Test Scanners

on:
  pull_request:
    branches: [main]

jobs:
  test-scanners:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout registry
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for git diff

      - name: Run scanner tests on GitLab
        uses: martin-boost-dev/boostsec-registry-test-action@df82403a273b294747554d33ed9b4253302be72c
        with:
          registry-path: ${{ github.workspace }}
          base-ref: origin/${{ github.base_ref }}
          head-ref: HEAD
          provider: gitlab
          provider-config: |
            {
              "token": "${{ secrets.GITLAB_TOKEN }}",
              "project_id": "boostsecurityio/martin/boostsec-registry-test-runner",
              "ref": "main"
            }
```

### 2. Required Secrets

Add these secrets in your repository settings (Settings → Secrets and variables → Actions):

**For GitLab:**
- `GITLAB_TOKEN`: GitLab Project Access Token (see [GitLab Test Runner Setup](#gitlab-test-runner-setup))

**For GitHub:**
- `GITHUB_TOKEN`: GitHub Personal Access Token or use the built-in `${{ secrets.GITHUB_TOKEN }}` with appropriate permissions

### 3. Multiple Providers

You can test on multiple providers in parallel:

```yaml
jobs:
  test-gitlab:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: martin-boost-dev/boostsec-registry-test-action@df82403a273b294747554d33ed9b4253302be72c
        with:
          registry-path: ${{ github.workspace }}
          base-ref: origin/${{ github.base_ref }}
          head-ref: HEAD
          provider: gitlab
          provider-config: |
            {
              "token": "${{ secrets.GITLAB_TOKEN }}",
              "project_id": "your-group/test-runner",
              "ref": "main"
            }

  test-github:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: martin-boost-dev/boostsec-registry-test-action@df82403a273b294747554d33ed9b4253302be72c
        with:
          registry-path: ${{ github.workspace }}
          base-ref: origin/${{ github.base_ref }}
          head-ref: HEAD
          provider: github
          provider-config: |
            {
              "token": "${{ secrets.GH_TEST_TOKEN }}",
              "owner": "your-org",
              "repo": "test-runner",
              "workflow_id": "scanner-test.yml",
              "ref": "main"
            }
```

---

## GitLab Test Runner Setup

### 1. Create Project Access Token

1. Go to your test runner project in GitLab
2. Navigate to **Settings → Access Tokens**
3. Click **Add new token**
4. Configure the token:
   - **Token name**: `Registry Test Runner` (or any descriptive name)
   - **Role**: **Maintainer** (required to run pipelines on protected branches)
   - **Scopes**: **`api`** (full API access - needed for both triggering and polling)
   - **Expiration date**: Set according to your security policy

5. Click **Create project access token**
6. **Copy the token immediately** (you won't be able to see it again)
7. Add it as `GITLAB_TOKEN` secret in your source repository

### 2. Token Requirements

✅ **Required Configuration:**
- **Token Type**: Project Access Token (NOT Personal Access Token or Trigger Token)
- **Minimum Role**: Maintainer (access level 40)
- **Required Scope**: `api`

❌ **Why other tokens don't work:**
- **Reporter role**: Cannot trigger pipelines on protected branches (403 Forbidden)
- **Developer role**: Cannot trigger pipelines on protected branches (400 Bad Request)
- **Trigger tokens**: Cannot poll pipeline status (authentication errors)

### 3. Create `.gitlab-ci.yml`

Create a `.gitlab-ci.yml` file in your GitLab test runner repository:

```yaml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "api"

stages:
  - test

test-scanner:
  stage: test
  image: ubuntu:22.04
  variables:
    # These are provided by the action via API
    SCANNER_ID: ""
    TEST_NAME: ""
    TEST_TYPE: ""
    SOURCE_URL: ""
    SOURCE_REF: ""
    REGISTRY_REF: ""
    REGISTRY_REPO: ""
    SCAN_PATHS: ""
    TIMEOUT: ""
    SCAN_CONFIGS: ""  # Optional
  script:
    - echo "Testing scanner $SCANNER_ID"
    - echo "Test name: $TEST_NAME"
    - echo "Test type: $TEST_TYPE"
    - echo "Source: $SOURCE_URL @ $SOURCE_REF"
    - echo "Registry: $REGISTRY_REPO @ $REGISTRY_REF"
    - echo "Scan paths: $SCAN_PATHS"

    # Install dependencies
    - apt-get update && apt-get install -y git curl

    # Clone test source repository
    - git clone --depth 1 --branch "$SOURCE_REF" "$SOURCE_URL" /test-source

    # Clone scanner registry
    - git clone "$REGISTRY_REPO" /scanner-registry
    - cd /scanner-registry
    - git checkout "$REGISTRY_REF"

    # Run the scanner test
    # TODO: Implement your scanner test logic here
    # This should:
    # 1. Load the scanner from /scanner-registry/scanners/$SCANNER_ID
    # 2. Run it against /test-source with the specified scan paths
    # 3. Validate the output
    # 4. Exit with appropriate status code

  timeout: 10m
  retry:
    max: 1
```

### 4. Branch Protection

If your test runner's `main` branch is protected:

- ✅ **With Maintainer token**: Pipelines can run on protected branches
- ❌ **With Developer token**: Cannot run pipelines on protected branches

**Alternative**: Use an unprotected branch like `test-runner` by setting `"ref": "test-runner"` in the provider config.

### 5. Project ID Format

The `project_id` can be either:
- **Numeric ID**: `"12345"` (found in project settings)
- **Full path**: `"group/subgroup/project"` (automatically URL-encoded)

Both formats work - the action handles URL encoding automatically.

---

## GitHub Test Runner Setup

### 1. Create Personal Access Token or GitHub App

**Option A: Personal Access Token (simpler)**

1. Go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Configure:
   - **Token name**: `Registry Test Runner`
   - **Repository access**: Only select repositories → Choose your test runner repo
   - **Permissions**:
     - **Actions**: Read and write (to trigger workflows)
     - **Contents**: Read (to access repository)
     - **Metadata**: Read (automatic)

**Option B: GitHub App (more secure)**

Follow GitHub's guide for creating a GitHub App with workflow permissions.

### 2. Create Workflow File

Create `.github/workflows/scanner-test.yml` in your GitHub test runner repository:

```yaml
name: Scanner Test

on:
  workflow_dispatch:
    inputs:
      scanner_id:
        required: true
        type: string
      test_name:
        required: true
        type: string
      test_type:
        required: true
        type: string
      source_url:
        required: true
        type: string
      source_ref:
        required: true
        type: string
      registry_ref:
        required: true
        type: string
      registry_repo:
        required: true
        type: string
      scan_paths:
        required: true
        type: string
      timeout:
        required: true
        type: string
      scan_configs:
        required: false
        type: string

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Display test info
        run: |
          echo "Testing scanner: ${{ inputs.scanner_id }}"
          echo "Test name: ${{ inputs.test_name }}"
          echo "Test type: ${{ inputs.test_type }}"
          echo "Source: ${{ inputs.source_url }} @ ${{ inputs.source_ref }}"
          echo "Registry: ${{ inputs.registry_repo }} @ ${{ inputs.registry_ref }}"
          echo "Scan paths: ${{ inputs.scan_paths }}"

      - name: Clone test source
        uses: actions/checkout@v4
        with:
          repository: ${{ inputs.source_url }}
          ref: ${{ inputs.source_ref }}
          path: test-source

      - name: Clone scanner registry
        uses: actions/checkout@v4
        with:
          repository: ${{ inputs.registry_repo }}
          ref: ${{ inputs.registry_ref }}
          path: scanner-registry

      - name: Run scanner test
        run: |
          # TODO: Implement your scanner test logic here
          # This should:
          # 1. Load the scanner from scanner-registry/scanners/${{ inputs.scanner_id }}
          # 2. Run it against test-source with the specified scan paths
          # 3. Validate the output
          # 4. Exit with appropriate status code
          echo "Running test..."
```

### 3. Workflow Identification

The action identifies the dispatched workflow by:
1. **Time window**: Within 60 seconds of dispatch
2. **Display title**: Must contain both `scanner_id` and `test_name`

The workflow run will automatically show: `[scanner-id] test-name` as the display title.

---

## Scanner Repository Structure

### Required Files

Each scanner that should be tested must have a `tests.yaml` file:

```
scanners/
├── boostsecurityio/
│   ├── trivy-fs/
│   │   ├── module.yaml
│   │   └── tests.yaml        ← Required for testing
│   └── semgrep/
│       ├── module.yaml
│       └── tests.yaml
```

### tests.yaml Format

```yaml
version: "1.0"
tests:
  - name: smoke-test
    type: source-code
    source:
      url: https://github.com/OWASP/NodeGoat.git
      ref: main
    scan_paths:
      - "."
    timeout: 5m

  - name: specific-vuln
    type: source-code
    source:
      url: https://github.com/example/vulnerable-app.git
      ref: v1.0.0
    scan_paths:
      - "src/"
      - "lib/"
    scan_configs:
      - severity: high
        rules: ["rule-001", "rule-002"]
    timeout: 10m
```

### Test Definition Fields

- **name** (required): Test identifier
- **type** (required): `source-code` or `docker-image`
- **source** (required):
  - **url**: Git repository URL (must be HTTPS)
  - **ref**: Branch, tag, or commit SHA
- **scan_paths** (required): List of paths to scan (relative to repository root)
- **timeout** (optional): Maximum test duration (default: `5m`)
- **scan_configs** (optional): Scanner-specific configuration

---

## Troubleshooting

### GitLab Issues

**403 Forbidden when creating pipeline:**
- Token has insufficient permissions
- Solution: Use Maintainer role token

**400 Bad Request: "You do not have sufficient permission to run a pipeline on 'main'":**
- Branch is protected and token doesn't have Maintainer role
- Solution: Use Maintainer token or unprotected branch

**404 Not Found:**
- Project ID is incorrect or not URL-encoded
- Solution: Verify project path and ensure it's URL-encoded (handled automatically)

### GitHub Issues

**Could not find dispatched workflow run:**
- Workflow file doesn't exist at specified path
- Workflow doesn't have `workflow_dispatch` trigger
- Display title doesn't match scanner_id + test_name

**Permission denied:**
- Token lacks Actions: Read and write permission
- Solution: Update token permissions

### General Issues

**No tests detected:**
- Scanner directory missing `tests.yaml`
- File format is invalid YAML
- Check logs for parsing errors

**Tests timeout:**
- Increase timeout in `tests.yaml`
- Check test runner has sufficient resources
- Verify network access to source repositories

---

## Security Best Practices

1. **Use Project Access Tokens** (GitLab) or Fine-grained PATs (GitHub) instead of personal tokens
2. **Set token expiration** according to your security policy
3. **Rotate tokens regularly**
4. **Use minimum required permissions**:
   - GitLab: Maintainer role, `api` scope
   - GitHub: Actions read/write, Contents read
5. **Never commit tokens** to version control
6. **Use GitHub Secrets** to store tokens securely
7. **Audit token usage** regularly through provider logs

---

## Example Configurations

### Complete GitLab Setup

```yaml
# Source repo: .github/workflows/test-scanners.yml
name: Test Scanners
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: martin-boost-dev/boostsec-registry-test-action@df82403a273b294747554d33ed9b4253302be72c
        with:
          registry-path: ${{ github.workspace }}
          base-ref: origin/${{ github.base_ref }}
          head-ref: HEAD
          provider: gitlab
          provider-config: |
            {
              "token": "${{ secrets.GITLAB_TOKEN }}",
              "project_id": "boostsecurityio/martin/test-runner",
              "ref": "main"
            }
```

```yaml
# GitLab test runner: .gitlab-ci.yml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "api"

stages:
  - test

test-scanner:
  stage: test
  image: ubuntu:22.04
  script:
    - echo "Testing $SCANNER_ID - $TEST_NAME"
    - apt-get update && apt-get install -y git
    - git clone --depth 1 --branch "$SOURCE_REF" "$SOURCE_URL" /test-source
    - git clone "$REGISTRY_REPO" /registry
    - cd /registry && git checkout "$REGISTRY_REF"
    # Run your scanner test logic here
  timeout: 10m
```

```yaml
# Scanner repo: scanners/boostsecurityio/trivy-fs/tests.yaml
version: "1.0"
tests:
  - name: smoke-test
    type: source-code
    source:
      url: https://github.com/OWASP/NodeGoat.git
      ref: main
    scan_paths: ["."]
    timeout: 5m
```

### Complete GitHub Setup

```yaml
# Source repo: .github/workflows/test-scanners.yml
name: Test Scanners
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: martin-boost-dev/boostsec-registry-test-action@df82403a273b294747554d33ed9b4253302be72c
        with:
          registry-path: ${{ github.workspace }}
          base-ref: origin/${{ github.base_ref }}
          head-ref: HEAD
          provider: github
          provider-config: |
            {
              "token": "${{ secrets.GH_TEST_TOKEN }}",
              "owner": "boostsecurityio",
              "repo": "scanner-test-runner",
              "workflow_id": "scanner-test.yml",
              "ref": "main"
            }
```

```yaml
# GitHub test runner: .github/workflows/scanner-test.yml
name: Scanner Test
on:
  workflow_dispatch:
    inputs:
      scanner_id:
        required: true
        type: string
      test_name:
        required: true
        type: string
      test_type:
        required: true
        type: string
      source_url:
        required: true
        type: string
      source_ref:
        required: true
        type: string
      registry_ref:
        required: true
        type: string
      registry_repo:
        required: true
        type: string
      scan_paths:
        required: true
        type: string
      timeout:
        required: true
        type: string
      scan_configs:
        required: false
        type: string

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: ${{ inputs.source_url }}
          ref: ${{ inputs.source_ref }}
          path: test-source
      - uses: actions/checkout@v4
        with:
          repository: ${{ inputs.registry_repo }}
          ref: ${{ inputs.registry_ref }}
          path: scanner-registry
      - name: Run test
        run: |
          echo "Testing ${{ inputs.scanner_id }}"
          # Your test logic here
```

---

## Support

For issues or questions:
- Open an issue at: https://github.com/boostsecurityio/boostsec-registry-test-action/issues
- Review logs in GitHub Actions for detailed error messages
