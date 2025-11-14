# Token Configuration Reference

Quick reference for configuring authentication tokens for each CI/CD provider.

## GitLab

### Token Requirements

| Property | Value |
|----------|-------|
| **Token Type** | Project Access Token |
| **Role** | Maintainer (access level 40) |
| **Scope** | `api` |

### Why These Requirements?

- **Reporter role**: ❌ Cannot trigger pipelines (403 Forbidden)
- **Developer role**: ❌ Cannot run pipelines on protected branches (400 Bad Request)
- **Maintainer role**: ✅ Can trigger and poll pipelines on protected branches
- **Trigger tokens**: ❌ Cannot poll pipeline status (authentication errors)
- **Personal Access Tokens**: ⚠️ Work but are user-scoped; Project Access Tokens are preferred

### How to Create

1. Go to project: **Settings → Access Tokens**
2. Click **Add new token**
3. Configure:
   - **Token name**: `Registry Test Runner`
   - **Role**: **Maintainer**
   - **Scopes**: **`api`**
   - **Expiration**: Set per security policy
4. Click **Create project access token**
5. Copy token immediately (shown only once)

### Configuration Format

```json
{
  "token": "glpat-xxxxxxxxxxxxxxxxxxxxx",
  "project_id": "group/subgroup/project",
  "ref": "main"
}
```

**Note**: `project_id` accepts numeric IDs (`"12345"`) or full paths (`"group/project"`). Paths are automatically URL-encoded.

---

## GitHub

### Token Requirements

| Property | Value |
|----------|-------|
| **Token Type** | Personal Access Token (fine-grained) or GitHub App |
| **Repository Access** | Target test runner repository |
| **Permissions** | `actions: read/write` |

### How to Create (Fine-grained PAT)

1. Go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Configure:
   - **Token name**: `Registry Test Runner`
   - **Repository access**: Only select repositories → Choose test runner repo
   - **Repository permissions**:
     - **Actions**: Read and write
     - **Metadata**: Read (automatic)
   - **Expiration**: Set per security policy
4. Click **Generate token**
5. Copy token immediately

### Configuration Format

```json
{
  "token": "github_pat_xxxxxxxxxxxxxxxxxxxxx",
  "owner": "organization-name",
  "repo": "test-runner-repo",
  "workflow_id": "scanner-test.yml",
  "ref": "main"
}
```

---

## Azure DevOps

### Token Requirements

| Property | Value |
|----------|-------|
| **Token Type** | Personal Access Token |
| **Scopes** | `Build: Read & Execute` |

### How to Create

1. Go to **User Settings → Personal Access Tokens**
2. Click **New Token**
3. Configure:
   - **Name**: `Registry Test Runner`
   - **Organization**: Select target organization
   - **Scopes**: Custom defined
     - **Build**: Read & execute
   - **Expiration**: Set per security policy
4. Click **Create**
5. Copy token immediately

### Configuration Format

```json
{
  "token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "organization": "your-org",
  "project": "your-project",
  "pipeline_id": 123
}
```

---

## Bitbucket

### Token Requirements

| Property | Value |
|----------|-------|
| **Token Type** | Repository Access Token |
| **Permissions** | `Pipelines: Read`, `Pipelines: Write` |

### How to Create

1. Go to the test runner repository in Bitbucket
2. Navigate to **Repository Settings → Security → Access tokens**
3. Click **Create Repository Access Token**
4. Configure:
   - **Token name**: `Registry Test Runner`
   - **Permissions**:
     - **Pipelines**: Read
     - **Pipelines**: Write
5. Click **Create**
6. Copy token immediately (shown only once)

**Official guide**: [Create a repository access token](https://support.atlassian.com/bitbucket-cloud/docs/create-a-repository-access-token/)

### Configuration Format

```json
{
  "username": "your-email@example.com",
  "api_token": "xxxxxxxxxxxxxxxxxxxxx",
  "workspace": "your-workspace",
  "repo_slug": "test-runner-repo",
  "branch": "main"
}
```

**Note**: `username` should be the email address associated with your Bitbucket account.

---

## Troubleshooting

### GitLab Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 403 Forbidden | Token has Reporter role | Use Maintainer role |
| 400 "insufficient permission" | Token has Developer role on protected branch | Use Maintainer role or unprotected branch |
| 404 Not Found | Invalid project_id or not URL-encoded | Verify project path; encoding is automatic |
| Authentication error on poll | Using trigger token | Use Project Access Token |

### GitHub Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid or expired token | Generate new token |
| 403 Forbidden | Missing Actions write permission | Update token permissions |
| 404 Not Found | Incorrect owner/repo | Verify repository details |
| Workflow not found | workflow_id doesn't exist or wrong path | Check workflow file path |

### Azure DevOps Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid or expired PAT | Generate new PAT |
| 403 Forbidden | Missing Build execute permission | Update PAT scopes |
| 404 Not Found | Incorrect org/project/pipeline_id | Verify configuration |

### Bitbucket Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid or expired access token | Generate new repository access token |
| 403 Forbidden | Missing pipelines read/write permissions | Update token permissions |
| 404 Not Found | Incorrect workspace/repo_slug | Verify repository details |
| Pipeline not triggered | Custom pipeline selector not found | Verify repository has `test-scanner` custom pipeline |
