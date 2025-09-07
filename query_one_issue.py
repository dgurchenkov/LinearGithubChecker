#!/usr/bin/env python3
"""
Script to query a single Linear issue and show its GitHub links.
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

class GitHubAPI:
    def __init__(self, token: str = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_interval = 1.0  # Minimum seconds between requests
    
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
    
    def get_issue_details(self, repo: str, issue_number: int) -> Optional[dict]:
        """Get details of a GitHub issue including title and state"""
        self._rate_limit()
        
        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 404:
                return None
            elif response.status_code == 403:
                return {"state": "rate_limited", "title": "Rate limited"}
            response.raise_for_status()
            data = response.json()
            return {
                "id": data.get("id"),
                "number": data.get("number"),
                "title": data.get("title"),
                "state": data.get("state"),
                "html_url": data.get("html_url")
            }
        except requests.RequestException as e:
            print(f"Error fetching {repo}#{issue_number}: {e}")
            return None

def extract_all_github_links(issue_data: dict) -> List[Tuple[str, int, str]]:
    """Extract all GitHub repository and issue numbers from Linear issue data"""
    github_patterns = [
        r"github\.com/([^/]+/[^/]+)/issues/(\d+)",
        r"github\.com/([^/]+/[^/]+)/pull/(\d+)",
    ]
    
    found_links = []
    
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
                    found_links.append((repo, int(number), url))
        
        # Check title for issue numbers
        for pattern in github_patterns:
            match = re.search(pattern, title)
            if match:
                if len(match.groups()) == 2:
                    repo, number = match.groups()
                    found_links.append((repo, int(number), f"title: {title}"))
    
    # Check description
    description = issue_data.get("description", "") or ""
    for pattern in github_patterns:
        for match in re.finditer(pattern, description):
            if len(match.groups()) == 2:
                repo, number = match.groups()
                found_links.append((repo, int(number), f"description: {match.group(0)}"))
    
    return found_links

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
    parser = argparse.ArgumentParser(description="Query a single Linear issue and show its GitHub links")
    parser.add_argument("issue_identifier", help="Linear issue identifier (e.g., MOCO-1233)")
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
        # Get the Linear issue by identifier
        issue_data = linear.get_issue_by_identifier(args.issue_identifier)
        
        if not issue_data:
            print(f"Error: Issue {args.issue_identifier} not found")
            return 1
        
        # Extract GitHub links
        github_links = extract_all_github_links(issue_data)
        
        # Print Linear issue information
        print(f"Linear Issue ID: {issue_data['id']}")
        print(f"Linear Issue Title: {issue_data['title']}")
        print(f"Linear Issue Status: {issue_data['state']['name']}")
        
        if github_links:
            print("Linked GitHub Issues:")
            for repo, issue_number, source in github_links:
                github_details = github.get_issue_details(repo, issue_number)
                if github_details:
                    print(f"  - ID: {github_details['id']}")
                    print(f"    Title: {github_details['title']}")
                    print(f"    Status: {github_details['state']}")
                    print(f"    URL: {github_details['html_url']}")
                else:
                    print(f"  - {repo}#{issue_number} (not found or inaccessible)")
                print()
        else:
            print("No GitHub issues linked")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())