#!/usr/bin/env python3
"""
Script to query all Linear issues in the MOCO team and show their GitHub links in a table format.
"""

import re
import json
import sys
import time
import argparse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from github_access import GitHubAPI, extract_first_attachment_github_link
from env_config import load_env_file, check_tokens_tuple

@dataclass
class Issue:
    linear_id: str
    linear_identifier: str
    linear_title: str
    linear_status: str
    github_url: Optional[str]
    github_number: Optional[int]
    github_repo: Optional[str]
    github_state: Optional[str]

class LinearAPI:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }

    def query(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query against Linear API"""
        payload = {"query": query, "variables": variables or {}}
        response = requests.post(self.base_url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_all_teams(self) -> List[Dict]:
        """Get all teams with their details"""
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        result = self.query(query)
        return result["data"]["teams"]["nodes"]
    
    def get_team_by_identifier(self, identifier: str) -> Optional[Dict]:
        """Get a team by its key (acronym) or name.
        
        Args:
            identifier: Team key (e.g., 'MOCO', 'MOTO') or name (e.g., 'MojoCompiler')
            
        Returns:
            Team dict with id, name, and key, or None if not found
        """
        # Try to find by key first (case-insensitive)
        identifier_upper = identifier.upper()
        query = """
        query($teamKey: String!) {
            teams(filter: { key: { eq: $teamKey } }) {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        result = self.query(query, {"teamKey": identifier_upper})
        teams = result["data"]["teams"]["nodes"]
        if teams:
            return teams[0]
        
        # If not found by key, try by name (case-sensitive)
        query = """
        query($teamName: String!) {
            teams(filter: { name: { eq: $teamName } }) {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        result = self.query(query, {"teamName": identifier})
        teams = result["data"]["teams"]["nodes"]
        if teams:
            return teams[0]
        
        # If still not found, try case-insensitive name search
        all_teams = self.get_all_teams()
        for team in all_teams:
            if team["name"].lower() == identifier.lower():
                return team
        
        return None

    def get_issue_by_id(self, issue_id: str) -> Optional[dict]:
        """Get a single issue by its Linear ID"""
        query = """
        query GetIssue($issueId: String!) {
            issue(id: $issueId) {
                id
                identifier
                title
                description
                state {
                    name
                }
                team {
                    name
                }
                attachments {
                    nodes {
                        id
                        title
                        url
                        subtitle
                        metadata
                    }
                }
                createdAt
                updatedAt
                assignee {
                    name
                    email
                }
                creator {
                    name
                    email
                }
                labels {
                    nodes {
                        name
                        color
                    }
                }
            }
        }
        """
        variables = {"issueId": issue_id}
        result = self.query(query, variables)
        return result["data"]["issue"] if result["data"]["issue"] else None

    def get_issue_by_identifier(self, identifier: str) -> Optional[dict]:
        """Get a single issue by its identifier (e.g., MOCO-1233)"""
        query = """
        query GetIssues($filter: IssueFilter!) {
            issues(filter: $filter) {
                nodes {
                    id
                    identifier
                    title
                    description
                    state {
                        name
                    }
                    team {
                        name
                    }
                    attachments {
                        nodes {
                            id
                            title
                            url
                            subtitle
                            metadata
                        }
                    }
                    createdAt
                    updatedAt
                    assignee {
                        name
                        email
                    }
                    creator {
                        name
                        email
                    }
                    labels {
                        nodes {
                            name
                            color
                        }
                    }
                }
            }
        }
        """
        variables = {
            "filter": {
                "number": {
                    "eq": int(identifier.split("-")[1])
                },
                "team": {
                    "key": {
                        "eq": identifier.split("-")[0]
                    }
                }
            }
        }
        result = self.query(query, variables)
        issues = result["data"]["issues"]["nodes"]
        return issues[0] if issues else None

    def get_all_team_issues(self, team_id: str, cursor: str = None, page_size: int = 200) -> Tuple[List[dict], Optional[str]]:
        """Get all issues for a team with pagination"""
        query = f"""
        query GetTeamIssues($teamId: String!, $cursor: String) {{
            team(id: $teamId) {{
                issues(first: {page_size}, after: $cursor) {{
                    nodes {{
                        id
                        identifier
                        title
                        description
                        state {{
                            name
                        }}
                        team {{
                            name
                        }}
                        attachments {{
                            nodes {{
                                id
                                title
                                url
                                subtitle
                                metadata
                            }}
                        }}
                        createdAt
                        updatedAt
                        assignee {{
                            name
                            email
                        }}
                        creator {{
                            name
                            email
                        }}
                        labels {{
                            nodes {{
                                name
                                color
                            }}
                        }}
                    }}
                    pageInfo {{
                        hasNextPage
                        endCursor
                    }}
                }}
            }}
        }}
        """
        variables = {"teamId": team_id}
        if cursor:
            variables["cursor"] = cursor

        result = self.query(query, variables)
        team_data = result["data"]["team"]

        if not team_data:
            return [], None

        issues_data = team_data["issues"]
        issues = issues_data["nodes"]
        next_cursor = issues_data["pageInfo"]["endCursor"] if issues_data["pageInfo"]["hasNextPage"] else None

        return issues, next_cursor


def process_github_link(github_api: 'GitHubAPI', linear_id: str, linear_status: str, linear_title: str,
                       repo: str, issue_number: int, source: str) -> tuple[Optional[tuple], str]:
    """Process a single GitHub link and return table row data if successful
    Returns: (table_row_data, status) where status is 'success', 'not_found', 'rate_limited', or 'error'
    """
    github_details, status = github_api.get_issue_details(repo, issue_number)

    if status == 'success' and github_details and github_details.get('number'):
        gh_number = str(github_details['number'])
        gh_status = github_details['state']
        gh_title = github_details['title']
        # Include repo information for markdown links
        table_row = (linear_id, linear_status, linear_title, gh_number, gh_status, gh_title, repo)
        return table_row, status

    return None, status

def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max_length characters, adding ellipsis if truncated"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def print_table_header():
    """Print the table header with proper formatting"""
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 42 + "+")
    print(f"| {'Linear ID':<13} | {'Status':<10} | {'GH Status':<10} | {'GH Number':<10} | {'Linear Title':<40} | {'GH Title':<40} |")
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 42 + "+")

def print_table_row(linear_id: str, linear_status: str, linear_title: str,
                   gh_number: str, gh_status: str, gh_title: str, repo: str = ""):
    """Print a single table row with proper formatting"""
    print(f"| {truncate_text(linear_id, 13):<13} | {truncate_text(linear_status, 10):<10} | {truncate_text(gh_status, 10):<10} | {truncate_text(gh_number, 10):<10} | {truncate_text(linear_title, 40):<40} | {truncate_text(gh_title, 40):<40} |")

def print_table_footer():
    """Print the table footer"""
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 42 + "+")

def create_markdown_table(table_rows) -> str:
    """Create a markdown table from the table rows data"""
    if not table_rows:
        return "No results to display.\n"
    
    # Markdown table header
    markdown = "| Linear Issue | Status | GH Status | GH Issue | Linear Title | GH Title |\n"
    markdown += "|--------------|--------|-----------|----------|--------------|----------|\n"
    
    # Process each row
    for linear_id, linear_status, linear_title, gh_number, gh_status, gh_title, repo in table_rows:
        # Create Linear link
        linear_link = f"[{linear_id}](https://linear.app/modularml/issue/{linear_id})"
        
        # Create GitHub link using the actual repo
        gh_link = f"[#{gh_number}](https://github.com/{repo}/issues/{gh_number})"
        
        # Escape markdown special characters and truncate text
        linear_title_escaped = linear_title.replace("|", "\\|").replace("\n", " ")[:35]
        gh_title_escaped = gh_title.replace("|", "\\|").replace("\n", " ")[:35]
        
        # Add ellipsis if truncated
        if len(linear_title) > 35:
            linear_title_escaped += "..."
        if len(gh_title) > 35:
            gh_title_escaped += "..."
        
        markdown += f"| {linear_link} | {linear_status} | {gh_status} | {gh_link} | {linear_title_escaped} | {gh_title_escaped} |\n"
    
    return markdown


# Define filtered status pairs (Linear status, GitHub status)
# These are considered "matching" or "expected" combinations
FILTERED_STATUS_PAIRS = {
    ("done", "closed"),           # Completed work, properly closed
    ("backlog", "open"),          # Future work, appropriately open
    ("canceled", "closed"),       # Canceled work, properly closed
    ("in review", "open"),        # Under review, still being worked on
    ("todo", "open"),             # Planned work, appropriately still open
    ("in progress", "open"),      # Active work, appropriately still open
    ("duplicate", "closed"),      # Duplicate issues, properly closed
    ("will not fix", "closed"),   # Won't fix issues, properly closed
    ("triage", "open"),           # Issues being triaged, appropriately still open
}

def main():
    # Parse command line arguments
    # Build help text from filtered pairs
    filtered_pairs_text = ", ".join([f"{linear}+{github}" for linear, github in FILTERED_STATUS_PAIRS])
    
    parser = argparse.ArgumentParser(
        description="""
Query all Linear issues in a specified team and analyze their mirrored GitHub issues.
This script helps identify status mismatches between Linear and GitHub issues.

The script extracts the first GitHub issue link from each Linear issue's attachments
(which represents the mirrored GitHub issue) and compares their statuses.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s                              # Show status mismatches in console table
  %(prog)s --show-all                   # Show all issues including matching status pairs
  %(prog)s --stop-after 50              # Process only first 50 Linear issues (debugging)
  %(prog)s --markdown report.md         # Save results to markdown file with clickable links
  %(prog)s --show-all --markdown all.md # Save complete report to markdown

Filtered Status Pairs (hidden by default):
  {filtered_pairs_text}

Environment Variables:
  LINEAR_API_TOKEN    Required. Get from https://linear.app/settings/api
  GITHUB_TOKEN        Optional. Get from https://github.com/settings/tokens
                      (Recommended for higher API rate limits)

Configuration:
  Create a .env file in the script directory with:
    LINEAR_API_TOKEN=your_linear_token_here
    GITHUB_TOKEN=your_github_token_here
""")
    
    parser.add_argument("--stop-after", 
                       type=int, 
                       metavar="N",
                       help="Stop after processing N Linear issues. Useful for debugging or quick testing. "
                            "The script will fetch Linear issues in batches and stop once N issues are collected.")
    
    parser.add_argument("--show-all", 
                       action="store_true", 
                       help=f"Show all status combinations including matching pairs. "
                            f"By default, {len(FILTERED_STATUS_PAIRS)} 'expected' status pairs are hidden "
                            f"to focus on potential mismatches. Use this flag to see everything.")
    
    parser.add_argument("--markdown", 
                       type=str, 
                       metavar="FILENAME", 
                       help="Save output in markdown format to the specified file. "
                            "Creates a professional report with clickable links to Linear issues "
                            "(https://linear.app/modularml/issue/ISSUE-ID) and GitHub issues "
                            "(https://github.com/REPO/issues/NUMBER). Includes summary statistics "
                            "and formatted table.")
    
    parser.add_argument("--team-name",
                       type=str,
                       default="MOCO",
                       help="Team identifier (key/acronym like MOCO, MOTO, MSTDL) or full team name "
                            "(like 'MojoCompiler', 'Mojo Tooling'). Case-insensitive for keys. "
                            "Default: MOCO (MojoCompiler team)")
    
    args = parser.parse_args()

    # Load environment variables from .env file
    tokens = load_env_file()

    # Check if required tokens are present
    if not check_tokens_tuple(tokens):
        return 1

    # Initialize APIs
    linear = LinearAPI(tokens.linear_token)
    github = GitHubAPI(tokens.github_token)

    try:
        # Get team by identifier
        print(f"Looking up team: {args.team_name}...")
        team = linear.get_team_by_identifier(args.team_name)
        
        if not team:
            print(f"Error: Team '{args.team_name}' not found.")
            print("\nAvailable teams:")
            all_teams = linear.get_all_teams()
            for t in sorted(all_teams, key=lambda x: x['key']):
                print(f"  {t['key']:10} - {t['name']}")
            return 1
        
        team_id = team['id']
        team_key = team['key']
        team_name = team['name']
        print(f"Found team: {team_name} (key: {team_key}, id: {team_id})")

        # Collect team issues (with optional limit)
        if args.stop_after:
            print(f"Fetching {team_key} issues (page size: 200, stopping after {args.stop_after})...")
        else:
            print(f"Fetching all {team_key} issues (page size: 200)...")

        all_issues = []
        cursor = None

        while True:
            issues, next_cursor = linear.get_all_team_issues(team_id, cursor)
            all_issues.extend(issues)
            print(f"Fetched {len(issues)} issues (total: {len(all_issues)})")

            # Check if we should stop due to --stop-after limit
            if args.stop_after and len(all_issues) >= args.stop_after:
                all_issues = all_issues[:args.stop_after]  # Trim to exact limit
                print(f"DEBUG MODE: Stopped after fetching {len(all_issues)} issues")
                break

            if not next_cursor:
                break
            cursor = next_cursor
            time.sleep(0.25)  # Be nice to the API

        # Phase 1: Collect GitHub links to process (only first attachment link per Linear issue)
        print(f"Processing {len(all_issues)} Linear issues...")
        print("Extracting mirrored GitHub issues (first attachment link only)...")

        github_tasks = []  # List of (linear_info, github_info) tuples to process
        issues_with_gh_links = 0

        for issue_data in all_issues:
            # Only get the first GitHub link from attachments (mirrored issue)
            github_link = extract_first_attachment_github_link(issue_data)

            if github_link:
                issues_with_gh_links += 1
                linear_id = issue_data['identifier']
                linear_status = issue_data['state']['name']
                linear_title = issue_data['title']

                repo, issue_number, source = github_link
                github_tasks.append((linear_id, linear_status, linear_title, repo, issue_number, source))

        print(f"Found {len(github_tasks)} mirrored GitHub issues from {issues_with_gh_links} Linear issues")
        print("Processing GitHub API requests in parallel...")

        # Phase 2: Process GitHub links in parallel
        table_rows = []
        rate_limit_hits = 0
        processed_count = 0
        error_reports = []  # Collect error reports for problematic links

        # Use ThreadPoolExecutor for parallel processing
        # Limit concurrent requests to avoid overwhelming GitHub API
        max_workers = 10 if tokens.github_token else 5  # More workers with auth token

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(process_github_link, github, linear_id, linear_status, linear_title, repo, issue_number, source):
                (linear_id, linear_status, linear_title, repo, issue_number, source)
                for linear_id, linear_status, linear_title, repo, issue_number, source in github_tasks
            }

            # Process completed requests
            for future in as_completed(future_to_task):
                processed_count += 1
                linear_id, linear_status, linear_title, repo, issue_number, source = future_to_task[future]

                try:
                    table_row, status = future.result()

                    if status == 'success' and table_row:
                        table_rows.append(table_row)
                    elif status == 'rate_limited':
                        rate_limit_hits += 1
                        error_reports.append(f"RATE LIMITED: {linear_id} → {repo}#{issue_number} (after retries)")
                    elif status == 'not_found':
                        error_reports.append(f"NOT FOUND: {linear_id} → {repo}#{issue_number} (GitHub issue does not exist)")
                    elif status == 'error':
                        error_reports.append(f"ERROR: {linear_id} → {repo}#{issue_number} (network/API error)")

                except Exception as e:
                    error_reports.append(f"EXCEPTION: {linear_id} → {repo}#{issue_number} (Python error: {e})")

                # Print progress every 50 completed requests
                if processed_count % 50 == 0:
                    print(f"Processed {processed_count:3d}/{len(github_tasks)} GitHub links, found {len(table_rows):3d} valid, hit rate limit {rate_limit_hits:2d} times.")

        print(f"Completed processing {processed_count} GitHub links")

        # Print error reports if any
        if error_reports:
            print(f"\n⚠️  ERROR REPORT: {len(error_reports)} problematic GitHub links found:")
            print("-" * 80)
            for error in sorted(error_reports):  # Sort for consistent output
                print(error)
            print("-" * 80)

        # Phase 3: Filter and display the table
        # Sort by Linear ID with proper numeric ordering (MOCO-29 before MOCO-289)
        def sort_key(row):
            linear_id = row[0]  # e.g., "MOCO-123"
            if '-' in linear_id:
                prefix, number_str = linear_id.split('-', 1)
                try:
                    number = int(number_str)
                    return (prefix, number)
                except ValueError:
                    # Fallback to string sorting if number parsing fails
                    return (prefix, number_str)
            else:
                # Fallback for IDs without dashes
                return (linear_id, 0)
        
        table_rows.sort(key=sort_key)
        
        # Apply filtering unless --show-all is specified
        if not args.show_all:
            original_count = len(table_rows)
            filtered_rows = []
            for row in table_rows:
                linear_id, linear_status, linear_title, gh_number, gh_status, gh_title, repo = row
                
                # Check if this status pair should be filtered
                status_pair = (linear_status.lower(), gh_status.lower())
                if status_pair in FILTERED_STATUS_PAIRS:
                    continue  # Skip this row as it's a matching/expected status combination
                    
                filtered_rows.append(row)
            
            table_rows = filtered_rows
            filtered_count = original_count - len(table_rows)
            if filtered_count > 0:
                print(f"\nFiltered out {filtered_count} rows ({len(FILTERED_STATUS_PAIRS)} matching status pairs). Use --show-all to see all.")

        # Output results
        if args.markdown:
            # Save to markdown file
            markdown_content = f"# Linear-GitHub Issue Status Report\n\n"
            markdown_content += f"**Generated on:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            markdown_content += f"**Summary:**\n"
            markdown_content += f"- Total Linear issues processed: {len(all_issues)}\n"
            markdown_content += f"- Issues that had mirrored GitHub links: {issues_with_gh_links}\n"
            markdown_content += f"- Issues with valid GitHub links: {len(table_rows)}\n\n"
            
            if not args.show_all:
                markdown_content += f"**Note:** Filtered out {original_count - len(table_rows) if 'original_count' in locals() else 0} matching status pairs. Use --show-all to include all.\n\n"
            
            markdown_content += f"## Results ({len(table_rows)} issues)\n\n"
            markdown_content += create_markdown_table(table_rows)
            
            # Write to file
            with open(args.markdown, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"Results saved to {args.markdown}")
            print(f"Found {len(table_rows)} Linear issues with valid mirrored GitHub issues")
        else:
            # Regular console output
            print(f"\nShowing {len(table_rows)} Linear issues with valid mirrored GitHub issues")
            print_table_header()

            for row in table_rows:
                print_table_row(*row)

            print_table_footer()
        
        print(f"\nTotal Linear issues processed: {len(all_issues)}")
        print(f"Issues that had GitHub links: {issues_with_gh_links}")
        print(f"Issues with valid GitHub links: {len(table_rows)}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())