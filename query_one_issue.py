#!/usr/bin/env python3
"""
Script to query a single Linear issue and show its GitHub links.
"""

import re
import json
import sys
import time
import argparse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
from github_access import GitHubAPI
from env_config import load_env_file, check_tokens_tuple
from linear_access import LinearAPI

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

def extract_all_github_links_detailed(issue_data: dict) -> List[Tuple[str, int, str, str, str]]:
    """Extract all GitHub repository and issue numbers from Linear issue data with detailed source info
    Returns: List of (repo, issue_number, source_type, source_detail, matched_text) tuples
    """
    github_patterns = [
        r"github\.com/([^/]+/[^/]+)/issues/(\d+)",
        r"github\.com/([^/]+/[^/]+)/pull/(\d+)",
    ]

    found_links = []
    seen_links = set()  # Track (repo, number) pairs to avoid duplicates

    # Check attachments
    attachments = issue_data.get("attachments", {}).get("nodes", [])
    for i, attachment in enumerate(attachments):
        url = attachment.get("url", "")
        title = attachment.get("title", "")

        # Check attachment URL
        for pattern in github_patterns:
            match = re.search(pattern, url)
            if match and len(match.groups()) == 2:
                repo, number = match.groups()
                link_key = (repo, int(number))
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    found_links.append((
                        repo,
                        int(number),
                        "attachment_url",
                        f"Attachment #{i+1}: '{title}'" if title else f"Attachment #{i+1}",
                        match.group(0)
                    ))

        # Check attachment title
        for pattern in github_patterns:
            match = re.search(pattern, title)
            if match and len(match.groups()) == 2:
                repo, number = match.groups()
                link_key = (repo, int(number))
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    found_links.append((
                        repo,
                        int(number),
                        "attachment_title",
                        f"Attachment #{i+1} title: '{title}'",
                        match.group(0)
                    ))

    # Check issue title
    issue_title = issue_data.get("title", "") or ""
    for pattern in github_patterns:
        match = re.search(pattern, issue_title)
        if match and len(match.groups()) == 2:
            repo, number = match.groups()
            link_key = (repo, int(number))
            if link_key not in seen_links:
                seen_links.add(link_key)
                found_links.append((
                    repo,
                    int(number),
                    "issue_title",
                    f"Linear issue title: '{issue_title}'",
                    match.group(0)
                ))

    # Check description/body
    description = issue_data.get("description", "") or ""
    for pattern in github_patterns:
        for match in re.finditer(pattern, description):
            if len(match.groups()) == 2:
                repo, number = match.groups()
                link_key = (repo, int(number))
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    # Extract some context around the match
                    start = max(0, match.start() - 30)
                    end = min(len(description), match.end() + 30)
                    context = description[start:end].replace('\n', ' ').strip()
                    if start > 0:
                        context = "..." + context
                    if end < len(description):
                        context = context + "..."

                    found_links.append((
                        repo,
                        int(number),
                        "description",
                        f"In description: '{context}'",
                        match.group(0)
                    ))

    return found_links


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Query a single Linear issue and show its GitHub links")
    parser.add_argument("issue_identifier", help="Linear issue identifier (e.g., MOCO-1233)")
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
        # Get the Linear issue by identifier
        issue_data = linear.get_issue_by_identifier(args.issue_identifier)

        if not issue_data:
            print(f"Error: Issue {args.issue_identifier} not found")
            return 1

        # Extract GitHub links with detailed source information
        github_links = extract_all_github_links_detailed(issue_data)

        # Print Linear issue information
        print(f"Linear Issue ID: {issue_data['id']}")
        print(f"Linear Issue Title: {issue_data['title']}")
        print(f"Linear Issue Status: {issue_data['state']['name']}")
        print()

        if github_links:
            print(f"Found {len(github_links)} GitHub link(s):")
            print("=" * 80)

            for i, (repo, issue_number, source_type, source_detail, matched_text) in enumerate(github_links, 1):
                print(f"\n{i}. GitHub Link: {repo}#{issue_number}")
                print(f"   URL: https://github.com/{repo}/issues/{issue_number}")
                print(f"   Found in: {source_type.replace('_', ' ').title()}")
                print(f"   Context: {source_detail}")
                print(f"   Matched text: '{matched_text}'")

                # Get GitHub issue details
                github_details, status = github.get_issue_details(repo, issue_number)
                if github_details and status == 'success':
                    print(f"   GitHub Status: {github_details['state']}")
                    print(f"   GitHub Title: {github_details['title']}")
                    print(f"   GitHub Number: {github_details['number']}")
                elif status == 'not_found':
                    print(f"   GitHub Status: ❌ Not found")
                elif status == 'rate_limited':
                    print(f"   GitHub Status: ⏳ Rate limited")
                else:
                    print(f"   GitHub Status: ❌ Error accessing issue")

                if i < len(github_links):
                    print("-" * 40)
        else:
            print("No GitHub links found in this Linear issue.")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())