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
        if not content.startswith("---"):
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    return data, ""
            except Exception:
                pass
            return {}, content
        
        try:
            # We use a more robust split that handles both \n and \r\n
            parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
            if len(parts) >= 3:
                front_yaml = parts[1].strip()
                body = parts[2].strip()
                data = yaml.safe_load(front_yaml)
                if isinstance(data, dict):
                    return data, body
        except Exception as e:
            import logging
            logging.getLogger("ledgermind.loader").error(f"YAML Parse Error: {e}")
        
        return {}, content

    @staticmethod
    def stringify(data: Dict[str, Any], body: str = "") -> str:
        """
        Serializes metadata and body into a single Markdown string with frontmatter.
        Uses literal block style for multiline strings.
        """
        # Custom representer for multiline strings
        def str_presenter(dumper, data):
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)

        class SafeFoldedDumper(yaml.SafeDumper):
            pass
        
        SafeFoldedDumper.add_representer(str, str_presenter)
            
        yaml_str = yaml.dump(data, Dumper=SafeFoldedDumper, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000).strip()
        return f"---\n{yaml_str}\n---\n\n{body}"
