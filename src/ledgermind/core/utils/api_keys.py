"""
Utility functions for API key management.
"""

import os
import re
from typing import Optional, List, Tuple

def find_api_key_in_shell_configs(key_name: str) -> Optional[str]:
    """
    Search for API key in common shell configuration files.
    
    Args:
        key_name: Name of the environment variable (e.g., "GOOGLE_API_KEY")
    
    Returns:
        API key value if found, None otherwise
    """
    # Common shell config files to check
    config_files = [
        os.path.expanduser("~/.bashrc"),
        os.path.expanduser("~/.bash_profile"),
        os.path.expanduser("~/.zshrc"),
        os.path.expanduser("~/.zprofile"),
        os.path.expanduser("~/.profile"),
    ]
    
    # Pattern to match: export KEY_NAME="value" or export KEY_NAME='value'
    pattern = re.compile(rf'export\s+{re.escape(key_name)}\s*=\s*["\']?([^"\'"\s]+)["\']?')
    
    for config_file in config_files:
        if not os.path.exists(config_file):
            continue
        
        try:
            with open(config_file, 'r') as f:
                content = f.read()
                match = pattern.search(content)
                if match:
                    return match.group(1)
        except Exception:
            # Skip files we can't read
            continue
    
    return None


def get_api_key(key_name: str, search_configs: bool = True) -> Tuple[Optional[str], str]:
    """
    Get API key from environment or shell config files.
    
    Args:
        key_name: Name of the environment variable
        search_configs: Whether to search shell config files
    
    Returns:
        Tuple of (api_key, source) where source is one of:
        - "env": Found in environment variables
        - "config": Found in shell config file
        - None: Not found
    """
    # First check environment variables (current session)
    env_key = os.environ.get(key_name)
    if env_key:
        return env_key, "env"
    
    # Then check shell config files
    if search_configs:
        config_key = find_api_key_in_shell_configs(key_name)
        if config_key:
            return config_key, "config"
    
    return None, "none"
