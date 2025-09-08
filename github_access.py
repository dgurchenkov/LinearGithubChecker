"""
GitHub API access classes for Linear-GitHub issue matching.
Contains both REST API and CLI-based implementations.
"""

import json
import os
import time
import subprocess
import re
from typing import Optional, Tuple
import requests


class GitHubAPIRest:
    """GitHub API access using REST API calls (original version, kept for history)"""
    
    def __init__(self, token: str = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        # Track if we've shown the token warning
        self._token_warning_shown = False

        # Note: Rate limiting is now handled by ThreadPoolExecutor max_workers
    
    def _show_token_warning_once(self):
        """Show GitHub token warning only once, on first API use"""
        if not self.token and not self._token_warning_shown:
            print("Warning: GITHUB_TOKEN not set. You'll have lower rate limits.")
            print("Add it to your .env file or get your token from: https://github.com/settings/tokens")
            print("Add to .env file: GITHUB_TOKEN=your_github_token_here")
            self._token_warning_shown = True

    def get_issue_details(self, repo: str, issue_number: int, max_retries: int = 2) -> tuple[Optional[dict], str]:
        """Get details of a GitHub issue including title and state with retry logic
        Returns: (issue_details, status) where status is 'success', 'not_found', 'rate_limited', or 'error'
        """
        # Show token warning on first use
        self._show_token_warning_once()
        
        for attempt in range(max_retries):
            url = f"{self.base_url}/repos/{repo}/issues/{issue_number}"
            try:
                response = requests.get(url, headers=self.headers)
                if response.status_code == 404:
                    return None, 'not_found'
                elif response.status_code == 403:
                    # Rate limited - wait and retry
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5  # 5, 10 seconds
                        time.sleep(wait_time)
                        continue
                    else:
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
                    time.sleep(2)
                    continue
                else:
                    return None, 'error'

        return None, 'error'


class GitHubAPI:
    """GitHub API access using GitHub CLI tool (gh command) - current version"""
    
    def __init__(self, token: str = None):
        # Token parameter kept for compatibility, but gh CLI uses its own auth
        self.token = token

    def get_issue_details(self, repo: str, issue_number: int, max_retries: int = 2) -> tuple[Optional[dict], str]:
        """Get details of a GitHub issue using GitHub CLI
        Returns: (issue_details, status) where status is 'success', 'not_found', 'rate_limited', or 'error'
        """
        for attempt in range(max_retries):
            try:
                # Use GitHub CLI to get issue details in JSON format
                cmd = ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", 
                       "number,title,state,url,id"]
                
                # Pass environment but remove GITHUB_TOKEN as it interferes with gh CLI's own auth
                env = os.environ.copy()
                # Remove GITHUB_TOKEN if present - gh CLI uses its own auth mechanism
                env.pop('GITHUB_TOKEN', None)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
                
                if result.returncode == 0:
                    # Success - parse JSON response
                    try:
                        data = json.loads(result.stdout)
                        # Convert GitHub CLI state format to match REST API
                        state = data.get("state", "").lower()  # OPEN -> open, CLOSED -> closed
                        
                        return {
                            "id": data.get("id"),
                            "number": data.get("number"),
                            "title": data.get("title"),
                            "state": state,
                            "html_url": data.get("url")
                        }, 'success'
                    except json.JSONDecodeError:
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return None, 'error'
                
                elif "not found" in result.stderr.lower() or "could not resolve" in result.stderr.lower():
                    return None, 'not_found'
                
                elif "rate limit" in result.stderr.lower() or result.returncode == 22:
                    # GitHub CLI rate limiting
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # 10, 20 seconds
                        time.sleep(wait_time)
                        continue
                    else:
                        return None, 'rate_limited'
                
                else:
                    # Other error
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        return None, 'error'
                        
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None, 'error'
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None, 'error'

        return None, 'error'


def extract_first_attachment_github_link(issue_data: dict) -> Optional[Tuple[str, int, str]]:
    """Extract only the first GitHub issue from attachments (for mirrored issues)
    Returns: (repo, issue_number, source) tuple or None if no GitHub link found
    """
    github_patterns = [
        r"github\.com/([^/]+/[^/]+)/issues/(\d+)",
    ]

    # Only check attachments, and only return the first GitHub link found
    attachments = issue_data.get("attachments", {}).get("nodes", [])
    
    for attachment in attachments:
        url = attachment.get("url", "")
        
        for pattern in github_patterns:
            match = re.search(pattern, url)
            if match and len(match.groups()) == 2:
                repo, number = match.groups()
                # Return immediately after finding the first GitHub issue in attachments
                return (repo, int(number), url)
    
    # No GitHub link found in attachments
    return None