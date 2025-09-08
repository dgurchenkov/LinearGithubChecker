"""
Linear API access module for Linear-GitHub issue matching scripts.
Provides a unified interface for accessing Linear's GraphQL API.
"""

import requests
from typing import List, Dict, Optional, Tuple


class LinearAPI:
    """Unified Linear API access class"""
    
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

    def get_moco_team_id(self) -> str:
        """Get the team ID for MojoCompiler team (legacy method for compatibility)"""
        team = self.get_team_by_identifier("MOCO")
        if team:
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
                    key
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
                        key
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
                            key
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