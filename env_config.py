"""
Environment configuration handling for Linear-GitHub issue matching scripts.
Loads environment variables from .env file without polluting os.environ.
"""

import os
from typing import Optional, NamedTuple


class ApiTokens(NamedTuple):
    """Named tuple for API tokens."""
    linear_token: Optional[str]
    github_token: Optional[str]


def load_env_file(env_path: Optional[str] = None) -> ApiTokens:
    """Load environment variables from .env file and return as named tuple.
    
    Args:
        env_path: Optional path to .env file. If not provided, looks for .env in script directory.
        
    Returns:
        ApiTokens named tuple with linear_token and github_token fields
    """
    if env_path is None:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    linear_token = None
    github_token = None
    
    if os.path.exists(env_path):
        print(f"Loading environment variables from {env_path}")
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    
                    if key == 'LINEAR_API_TOKEN':
                        linear_token = value
                    elif key == 'GITHUB_TOKEN':
                        github_token = value
        
        print("Environment variables loaded successfully")
    else:
        print(f"Warning: .env file not found at {env_path}")
        print("You can create a .env file with your API tokens:")
        print("LINEAR_API_TOKEN=your_linear_token_here")
        print("GITHUB_TOKEN=your_github_token_here")
    
    return ApiTokens(linear_token=linear_token, github_token=github_token)


def check_tokens_tuple(tokens: ApiTokens) -> bool:
    """Check if required tokens are present and provide helpful messages.
    
    Args:
        tokens: ApiTokens named tuple
        
    Returns:
        True if all required tokens are present, False otherwise
    """
    return check_tokens(tokens.linear_token, tokens.github_token)


def check_tokens(linear_token: Optional[str], github_token: Optional[str]) -> bool:
    """Check if required tokens are present and provide helpful messages.
    
    Args:
        linear_token: Linear API token
        github_token: GitHub token (not checked here - warning is lazy)
        
    Returns:
        True if all required tokens are present, False otherwise
    """
    if not linear_token:
        print("Error: LINEAR_API_TOKEN is required")
        print("Add it to your .env file or get your token from: https://linear.app/settings/api")
        print("Example .env file:")
        print("LINEAR_API_TOKEN=your_linear_token_here")
        return False
    
    # GitHub token warning removed - will be shown lazily only if REST API is used
    
    return True