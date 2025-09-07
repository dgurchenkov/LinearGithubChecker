#!/usr/bin/env python3
"""
Script to query all Linear issues in the MOCO team and show their GitHub links in a table format.
"""

import os
import re
import json
import sys
import time
import argparse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import requests
from urllib.parse import urlparse

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

    def get_moco_team_id(self) -> str:
        """Get the team ID for MojoCompiler team"""
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                }
            }
        }
        """
        result = self.query(query)
        for team in result["data"]["teams"]["nodes"]:
            if team["name"] == "MojoCompiler":
                return team["id"]
        raise ValueError("MojoCompiler team not found")

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

class GitHubAPI:
    def __init__(self, token: str = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"token {token}"

        # Rate limiting
        self.last_request_time = 0
        self.min_interval = 0.01  # Minimum seconds between requests

    def _rate_limit(self):
        """Simple rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval:
            time.sleep(self.min_interval - time_since_last)
        self.last_request_time = time.time()

    def get_issue_state(self, repo: str, issue_number: int) -> Optional[str]:
        """Get the state of a GitHub issue"""
        self._rate_limit()

        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 404:
                print(f"Issue {repo}#{issue_number} not found")
                return None
            elif response.status_code == 403:
                print(f"Rate limited or access denied for {repo}#{issue_number}")
                return "rate_limited"  # Special marker to skip this issue
            response.raise_for_status()
            return response.json().get("state")
        except requests.RequestException as e:
            print(f"Error fetching {repo}#{issue_number}: {e}")
            return None

    def get_issue_details(self, repo: str, issue_number: int, max_retries: int = 3) -> tuple[Optional[dict], str]:
        """Get details of a GitHub issue including title and state with retry logic
        Returns: (issue_details, status) where status is 'success', 'not_found', 'rate_limited', or 'error'
        """
        for attempt in range(max_retries):
            self._rate_limit()

            url = f"{self.base_url}/repos/{repo}/issues/{issue_number}"
            try:
                response = requests.get(url, headers=self.headers)
                if response.status_code == 404:
                    return None, 'not_found'
                elif response.status_code == 403:
                    # Rate limited - wait longer and retry
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 30  # 30, 60, 90 seconds
                        print(f"Rate limited for {repo}#{issue_number}. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"Failed to fetch {repo}#{issue_number} after {max_retries} attempts due to rate limiting")
                        return None, 'rate_limited'
                response.raise_for_status()
                data = response.json()
                return {
                    "id": data.get("id"),
                    "number": data.get("number"),
                    "title": data.get("title"),
                    "state": data.get("state"),
                    "html_url": data.get("html_url")
                }, 'success'
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"Error fetching {repo}#{issue_number} (attempt {attempt + 1}): {e}. Retrying...")
                    time.sleep(5)
                    continue
                else:
                    print(f"Error fetching {repo}#{issue_number} after {max_retries} attempts: {e}")
                    return None, 'error'

        return None, 'error'

def extract_all_github_links(issue_data: dict) -> List[Tuple[str, int, str]]:
    """Extract all GitHub repository and issue numbers from Linear issue data
    Returns unique GitHub links only (deduplicated by repo and issue number)
    """
    github_patterns = [
        r"github\.com/([^/]+/[^/]+)/issues/(\d+)",
        r"github\.com/([^/]+/[^/]+)/pull/(\d+)",
    ]

    found_links = []
    seen_links = set()  # Track (repo, number) pairs to avoid duplicates

    # Check attachments
    attachments = issue_data.get("attachments", {}).get("nodes", [])
    for attachment in attachments:
        url = attachment.get("url", "")
        title = attachment.get("title", "")

        for pattern in github_patterns:
            match = re.search(pattern, url)
            if match:
                if len(match.groups()) == 2:
                    repo, number = match.groups()
                    link_key = (repo, int(number))
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        found_links.append((repo, int(number), url))

        # Check title for issue numbers
        for pattern in github_patterns:
            match = re.search(pattern, title)
            if match:
                if len(match.groups()) == 2:
                    repo, number = match.groups()
                    link_key = (repo, int(number))
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        found_links.append((repo, int(number), f"title: {title}"))

    # Check description
    description = issue_data.get("description", "") or ""
    for pattern in github_patterns:
        for match in re.finditer(pattern, description):
            if len(match.groups()) == 2:
                repo, number = match.groups()
                link_key = (repo, int(number))
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    found_links.append((repo, int(number), f"description: {match.group(0)}"))

    return found_links

def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max_length characters, adding ellipsis if truncated"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def print_table_header():
    """Print the table header with proper formatting"""
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+")
    print(f"| {'Linear ID':<13} | {'Status':<10} | {'Linear Title':<40} | {'GH ID':<10} | {'GH Status':<10} | {'GH Title':<40} |")
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+")

def print_table_row(linear_id: str, linear_status: str, linear_title: str,
                   gh_id: str, gh_status: str, gh_title: str):
    """Print a single table row with proper formatting"""
    print(f"| {truncate_text(linear_id, 13):<13} | {truncate_text(linear_status, 10):<10} | {truncate_text(linear_title, 40):<40} | {truncate_text(gh_id, 10):<10} | {truncate_text(gh_status, 10):<10} | {truncate_text(gh_title, 40):<40} |")

def print_table_footer():
    """Print the table footer"""
    print("+" + "-" * 15 + "+" + "-" * 12 + "+" + "-" * 42 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 42 + "+")

def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        print(f"Loading environment variables from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value
        print("Environment variables loaded successfully")
    else:
        print(f"Warning: .env file not found at {env_file}")
        print("You can create a .env file with your API tokens:")
        print("LINEAR_API_TOKEN=your_linear_token_here")
        print("GITHUB_TOKEN=your_github_token_here")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Query all Linear issues in the MOCO team and show their GitHub links")
    args = parser.parse_args()

    # Load environment variables from .env file if it exists
    load_env_file()

    # Get API tokens from environment variables
    linear_token = os.getenv("LINEAR_API_TOKEN")
    github_token = os.getenv("GITHUB_TOKEN")  # Optional but recommended for higher rate limits

    if not linear_token:
        print("Error: LINEAR_API_TOKEN environment variable is required")
        print("Add it to your .env file or get your token from: https://linear.app/settings/api")
        print("Example .env file:")
        print("LINEAR_API_TOKEN=your_linear_token_here")
        return 1

    if not github_token:
        print("Warning: GITHUB_TOKEN not set. You'll have lower rate limits.")
        print("Add it to your .env file or get your token from: https://github.com/settings/tokens")
        print("Add to .env file: GITHUB_TOKEN=your_github_token_here")

    # Initialize APIs
    linear = LinearAPI(linear_token)
    github = GitHubAPI(github_token)

    try:
        # Get MojoCompiler team ID
        print("Getting MojoCompiler team ID...")
        team_id = linear.get_moco_team_id()
        print(f"Found team ID: {team_id}")

        # Collect all team issues
        print("Fetching all MOCO issues (page size: 200)...")
        all_issues = []
        cursor = None

        while True:
            issues, next_cursor = linear.get_all_team_issues(team_id, cursor)
            all_issues.extend(issues)
            print(f"Fetched {len(issues)} issues (total: {len(all_issues)})")

            if not next_cursor:
                break
            cursor = next_cursor
            time.sleep(0.25)  # Be nice to the API

        print(f"Total issues found: {len(all_issues)}")
        print(f"Processing GitHub links for {len(all_issues)} issues...")

        # Phase 1: Process all GitHub links and collect valid entries
        table_rows = []
        issues_with_gh_links = 0
        rate_limit_hits = 0

        for i, issue_data in enumerate(all_issues):
            # Extract GitHub links
            github_links = extract_all_github_links(issue_data)

            linear_id = issue_data['identifier']
            linear_status = issue_data['state']['name']
            linear_title = issue_data['title']

            has_gh_links = bool(github_links)
            if has_gh_links:
                issues_with_gh_links += 1

            if github_links:
                # Process each GitHub link
                for repo, issue_number, source in github_links:
                    github_details, status = github.get_issue_details(repo, issue_number)

                    # Track rate limit hits specifically
                    if status == 'rate_limited':
                        rate_limit_hits += 1

                    # Only add to table if we successfully got GitHub issue details
                    if status == 'success' and github_details and github_details.get('id'):
                        gh_id = str(github_details['id'])
                        gh_status = github_details['state']
                        gh_title = github_details['title']
                        table_rows.append((linear_id, linear_status, linear_title, gh_id, gh_status, gh_title))

            # Print progress every 50 issues
            if (i + 1) % 50 == 0:
                processed_in_batch = 50
                gh_links_in_batch = sum(1 for j in range(i - 49, i + 1) if j >= 0 and extract_all_github_links(all_issues[j]))
                print(f"Processed {processed_in_batch} issues, of those {gh_links_in_batch:2d} had GH links, hit rate limit {rate_limit_hits:2d} times. Total {i + 1:3d}/{len(all_issues)} issues.")
                rate_limit_hits = 0  # Reset counter for next batch

        # Phase 2: Display the table
        print(f"\nFound {len(table_rows)} Linear issues with valid GitHub links")
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