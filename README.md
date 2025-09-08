# Linear-GitHub Issue Matching Tools

A collection of Python utilities for analyzing and comparing Linear issues with their mirrored GitHub issues. These tools help identify status mismatches and track synchronization between Linear and GitHub issue tracking systems.

## Overview

This toolkit provides two main scripts:
- **`query_one_issue.py`** - Analyze a single Linear issue and its GitHub links
- **`query_all_issues.py`** - Bulk analysis of all issues in a Linear team

Both scripts support multiple teams and can identify when Linear and GitHub issue statuses are out of sync.

## Features

- ✅ **Multi-team support** - Works with any Linear team (MOCO, MOTO, MSTDL, etc.)
- ✅ **Flexible team selection** - Use team acronyms or full team names
- ✅ **GitHub CLI integration** - Uses `gh` CLI for reliable GitHub API access
- ✅ **Status mismatch detection** - Identifies issues where Linear/GitHub statuses don't align
- ✅ **Markdown export** - Generate professional reports with clickable links
- ✅ **Parallel processing** - Fast bulk analysis with concurrent GitHub API requests
- ✅ **Smart filtering** - Focus on mismatches by hiding expected status combinations

## Prerequisites

### Required
- Python 3.7+
- [GitHub CLI (`gh`)](https://cli.github.com/) - installed and authenticated
- Linear API token in the environment file (`.env`)

### Installation

1. **Install GitHub CLI**:
   ```bash
   # macOS
   brew install gh

   # Other platforms: https://cli.github.com/
   ```

2. **Authenticate with GitHub**:
   ```bash
   gh auth login
   ```

3. **Create `.env` file**:
   ```bash
   # Copy the template and add your tokens
   cp .env.example .env
   ```

   Edit `.env` with your tokens:
   ```
   LINEAR_API_TOKEN=lin_api_your_token_here
   GITHUB_TOKEN=ghp_your_github_token_here
   ```

## Getting API Tokens

### Linear API Token
1. Go to [Linear Settings > API](https://linear.app/settings/api)
2. Create a new personal API token
3. Copy the token to your `.env` file

### GitHub Token (Optional)
The GitHub token is only needed if you plan to use the REST API version (not recommended). The GitHub CLI handles authentication automatically.

1. Go to [GitHub Settings > Tokens](https://github.com/settings/tokens)
2. Generate a classic token with `repo` permissions
3. Add to `.env` file

## Usage

### Single Issue Analysis

Analyze a specific Linear issue and show all its GitHub links with detailed context:

```bash
# Basic usage
python query_one_issue.py MOCO-1233

# Works with any team
python query_one_issue.py MOTO-456
python query_one_issue.py MSTDL-789
```

**Output includes**:
- Linear issue details (ID, title, status)
- All GitHub links found in the issue
- Source context (where each link was found)
- GitHub issue status and details
- Detailed matching information

### Bulk Team Analysis

Analyze all issues in a Linear team to find status mismatches:

```bash
# Analyze MojoCompiler team (default)
python query_all_issues.py

# Analyze specific team by acronym
python query_all_issues.py --team-name MOTO
python query_all_issues.py --team-name MSTDL

# Use full team names
python query_all_issues.py --team-name "Mojo Tooling"
python query_all_issues.py --team-name "Mojo Standard Library"

# Show all status combinations (including matches)
python query_all_issues.py --show-all

# Limit for testing/debugging
python query_all_issues.py --stop-after 50

# Export to markdown
python query_all_issues.py --markdown report.md
python query_all_issues.py --team-name MOTO --markdown moto_report.md
```

## Command Line Options

### `query_one_issue.py`

```
python query_one_issue.py ISSUE_IDENTIFIER

Arguments:
  ISSUE_IDENTIFIER    Linear issue identifier (e.g., MOCO-1233, MOTO-456)
```

### `query_all_issues.py`

```
python query_all_issues.py [OPTIONS]

Options:
  --team-name TEAM     Team identifier or name (default: MOCO)
                      Examples: MOCO, MOTO, MSTDL, "Mojo Tooling"

  --show-all          Show all status combinations including matches
                      By default, hides "expected" status pairs to focus on mismatches

  --stop-after N      Stop after processing N Linear issues (useful for testing)

  --markdown FILE     Save results to markdown file with clickable links

  --help             Show detailed help message
```

## Team Support

The tools support all Linear teams. Common teams include:

To see all available teams:
```bash
python query_all_issues.py --team-name INVALID_TEAM
```

## Output Formats

### Console Table

Default output shows issues in a formatted table:

```
+---------------+------------+------------+------------+------------------------------------------+
| Linear ID     | Status     | GH Status  | GH Number  | Linear Title                             |
+---------------+------------+------------+------------+------------------------------------------+
| MOCO-2295     | Backlog    | open       | 5164       | [BUG] Bad / misleading error from par... |
| MOTO-1314     | Triage     | open       | 5229       | [BUG][LSP] remote PC usecase: vscode ... |
+---------------+------------+------------+------------+------------------------------------------+
```

### Markdown Export

Generate professional reports with clickable links:

```bash
python query_all_issues.py --markdown report.md
```

Creates a markdown file with:
- Summary statistics
- Clickable Linear issue links
- Clickable GitHub issue links
- Formatted table for easy sharing

## Status Mismatch Detection

The tool automatically filters out "expected" status combinations to highlight potential issues:

### Expected Combinations (Hidden by Default)
- `done` + `closed` - Completed work
- `backlog` + `open` - Future work
- `canceled` + `closed` - Cancelled work
- `in review` + `open` - Under review
- `todo` + `open` - Planned work
- `in progress` + `open` - Active work

### Potential Mismatches (Always Shown)
- `done` + `open` - Completed in Linear but still open in GitHub
- `backlog` + `closed` - Future work but closed in GitHub
- Any other unexpected combinations

Use `--show-all` to see everything including expected combinations.

## Architecture

The toolkit is organized into modular components:

```
├── query_one_issue.py      # Single issue analysis script
├── query_all_issues.py     # Bulk team analysis script
├── linear_access.py        # Linear API client (shared)
├── github_access.py        # GitHub API clients (REST + CLI)
├── env_config.py           # Environment configuration (shared)
└── README.md              # This documentation
```

### Key Features
- **Single-sourced modules** - No code duplication between scripts
- **GitHub CLI integration** - Avoids authentication issues with private repos
- **Lazy warnings** - Only shows GitHub token warnings if REST API is used
- **Parallel processing** - Concurrent GitHub API requests for performance

## Troubleshooting

### Common Issues

**"Team not found" error**:
```bash
# Check available teams
python query_all_issues.py --team-name INVALID
```

**GitHub authentication issues**:
```bash
# Check GitHub CLI authentication
gh auth status

# Re-authenticate if needed
gh auth login
```

**Linear API errors**:
- Verify your LINEAR_API_TOKEN in `.env`
- Check token permissions at https://linear.app/settings/api

**Rate limiting**:
- The tool uses GitHub CLI which has higher rate limits
- Parallel processing is automatically throttled
- Linear API calls include appropriate delays

### Performance Tips

- Use `--stop-after` for quick testing
- The tool processes issues in batches of 200
- GitHub API calls are parallelized (5-10 concurrent requests)
- Results are cached during script execution

## Development

### Adding New Features

1. **Linear API changes** - Edit `linear_access.py`
2. **GitHub API changes** - Edit `github_access.py`
3. **Environment handling** - Edit `env_config.py`
4. **New analysis logic** - Add to individual scripts

### Testing

```bash
# Test single issue
python query_one_issue.py MOCO-99

# Test bulk analysis (limited)
python query_all_issues.py --stop-after 10 --show-all

# Test different teams
python query_all_issues.py --team-name MOTO --stop-after 5
```

## Contributing

When making changes:
1. Keep shared modules (linear_access.py, github_access.py, env_config.py) in sync
2. Test both scripts after changes
3. Update documentation for new features
4. Follow existing code style and patterns

## License

Internal tool for Linear-GitHub issue analysis and synchronization tracking.