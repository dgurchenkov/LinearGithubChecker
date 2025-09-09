# Linear-GitHub Issue Matching Tools

Python utilities for identifying status mismatches between Linear issues and their mirrored GitHub issues. This is a narrowly focused project I created for my work needs, where we use both Linear and GitHub issue tracking systems that sometimes fall out of sync.

**Note**: This project is unlikely to be useful to anyone else unless they use the same combination of issue trackers (Linear + GitHub) with similar mirroring setup.

## Overview

Two scripts for analyzing Linear-GitHub issue synchronization:
- `query_one_issue.py` - Check a single Linear issue and its GitHub links
- `query_all_issues.py` - Bulk analysis of all issues in a Linear team

## Prerequisites

- Python 3.7+
- [GitHub CLI (`gh`)](https://cli.github.com/) - installed and authenticated
- Linear API token

### Setup

1. Install GitHub CLI:
   ```bash
   # macOS
   brew install gh
   
   # Other platforms: https://cli.github.com/
   ```

2. Authenticate with GitHub:
   ```bash
   gh auth login
   ```

3. Create `.env` file with your Linear API token:
   ```
   LINEAR_API_TOKEN=lin_api_your_token_here
   ```

## Getting API Tokens

### Linear API Token
1. Go to [Linear Settings > API](https://linear.app/settings/api)
2. Create a personal API token
3. Add to `.env` file

### GitHub Token (Optional)
The GitHub CLI handles authentication automatically. A GitHub token is only needed if using the REST API version (not recommended).

## Usage

### Single Issue Analysis

```bash
python query_one_issue.py MOCO-1233
python query_one_issue.py MOTO-456
```

Shows Linear issue details, GitHub links found, and their current status.

### Bulk Team Analysis

```bash
# Default team (MOCO)
python query_all_issues.py

# Specific team
python query_all_issues.py --team-name MOTO
python query_all_issues.py --team-name "Mojo Tooling"

# Show all combinations (including matches)
python query_all_issues.py --show-all

# Limit for testing
python query_all_issues.py --stop-after 50

# Export to markdown
python query_all_issues.py --markdown report.md
```

## Command Line Options

### `query_one_issue.py`

```
python query_one_issue.py ISSUE_IDENTIFIER
```

### `query_all_issues.py`

```
Options:
  --team-name TEAM     Team identifier or name (default: MOCO)
  --show-all          Show all status combinations including matches
  --stop-after N      Stop after processing N Linear issues
  --markdown FILE     Save results to markdown file
```

## Team Support

To see all available teams:
```bash
python query_all_issues.py --team-name INVALID_TEAM
```

## Output

Console table showing Linear ID, status, GitHub status, GitHub number, and titles:

```
+---------------+------------+------------+------------+------------------------------------------+
| Linear ID     | Status     | GH Status  | GH Number  | Linear Title                             |
+---------------+------------+------------+------------+------------------------------------------+
| MOCO-2295     | Backlog    | open       | 5164       | [BUG] Bad / misleading error from par... |
+---------------+------------+------------+------------+------------------------------------------+
```

## Status Filtering

By default, hides "expected" status combinations to focus on mismatches:
- `done` + `closed`
- `backlog` + `open`
- `canceled` + `closed`
- `in review` + `open`
- `todo` + `open`
- `in progress` + `open`

Use `--show-all` to see everything.

## Architecture

```
├── query_one_issue.py      # Single issue analysis
├── query_all_issues.py     # Bulk team analysis
├── linear_access.py        # Linear API client
├── github_access.py        # GitHub API clients (REST + CLI)
├── env_config.py           # Environment configuration
└── README.md              # This file
```

## Troubleshooting

**Team not found**:
```bash
python query_all_issues.py --team-name INVALID
```

**GitHub authentication**:
```bash
gh auth status
gh auth login
```

**Linear API errors**:
- Check LINEAR_API_TOKEN in `.env`
- Verify token at https://linear.app/settings/api