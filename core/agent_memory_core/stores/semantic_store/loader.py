import yaml
import re
from typing import Dict, Any, Tuple

class MemoryLoader:
    # Pattern to match YAML frontmatter between --- and ---
    FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*(.*)', re.DOTALL | re.MULTILINE)

    @staticmethod
    def parse(content: str) -> Tuple[Dict[str, Any], str]:
        """
        Separates YAML frontmatter from Markdown body.
        Returns (metadata_dict, body_string).
        """
        match = MemoryLoader.FRONTMATTER_RE.match(content)
        if not match:
            # Try to parse as pure YAML (backward compatibility)
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    return data, ""
            except yaml.YAMLError:
                pass
            return {}, content
        
        front_yaml = match.group(1)
        body = match.group(2).strip()
        
        try:
            data = yaml.safe_load(front_yaml)
            return data if isinstance(data, dict) else {}, body
        except yaml.YAMLError:
            return {}, body

    @staticmethod
    def stringify(data: Dict[str, Any], body: str = "") -> str:
        """
        Serializes metadata and body into a single Markdown string with frontmatter.
        """
        # Ensure timestamp is ISO string for consistency
        if 'timestamp' in data and not isinstance(data['timestamp'], str):
            try:
                data['timestamp'] = data['timestamp'].isoformat()
            except AttributeError:
                pass
                
        yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{body}"
