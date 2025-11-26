# PR Stack Plan

This document tracks the plan for splitting the proof-of-concept into reviewable pull requests.

## Workflow

- Work sequentially, one PR at a time
- Reference current `main` code while building each PR fresh
- Iterate on each PR until quality standards are met
- Each PR builds on the merged foundation of previous PRs

## PR Stack (in order)

### PR 1: Implement scanner detection with git integration
- [ ] `scanner_detector.py` with tests
- [ ] README: Add overview and scanner detection section

### PR 2: Add test definition loader with YAML parsing
- [ ] `test_loader.py` with tests
- [ ] `models/test_definition.py`
- [ ] README: Document `tests.yaml` format

### PR 3: Add abstract provider base class with wait logic
- [ ] `providers/base.py` with tests
- [ ] `models/test_result.py`
- [ ] README: Document provider architecture

### PR 4: Implement GitHub Actions provider
- [ ] `providers/github.py` with tests
- [ ] `models/provider_config.py` with `GitHubConfig`
- [ ] README: Add GitHub configuration section

### PR 5: Implement GitLab CI provider
- [ ] `providers/gitlab.py` with tests
- [ ] Add `GitLabConfig` to provider_config.py
- [ ] README: Add GitLab configuration section

### PR 6: Implement Azure DevOps Pipelines provider
- [ ] `providers/azure.py` with tests
- [ ] Add `AzureConfig` to provider_config.py
- [ ] README: Add Azure configuration section

### PR 7: Implement Bitbucket Pipelines provider
- [ ] `providers/bitbucket.py` with tests
- [ ] Add `BitbucketConfig` to provider_config.py
- [ ] README: Add Bitbucket configuration section

### PR 8: Implement test orchestrator
- [ ] `orchestrator.py` with tests
- [ ] README: Document orchestration flow

### PR 9: Add CLI entry point and GitHub Action definition
- [ ] `cli.py`, `__main__.py`, `action.yaml`
- [ ] End-to-end module tests with act and WireMock
- [ ] README: Add usage examples and action inputs/outputs

## Progress

- Current PR: Not started
- Last completed: None
