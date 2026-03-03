import os
from typing import List, Dict, Any, Set, Optional
from ledgermind.core.stores.interfaces import MetadataStore

class KnowledgeGraphGenerator:
    """Generates a Mermaid diagram representing the knowledge evolution graph."""

    def __init__(self, repo_path: str, meta_store: MetadataStore, episodic_store: Optional[Any] = None):
        self.repo_path = repo_path
        self.meta = meta_store
        self.episodic = episodic_store

    def generate_mermaid(self, target_filter: Optional[str] = None) -> str:
        """
        Builds a Mermaid graph using the metadata index.
        """
        # Fetch all metadata from DB
        all_meta = self.meta.list_all()
        
        if target_filter:
            all_meta = [m for m in all_meta if m.get('target') == target_filter]
        
        mermaid_lines = ["graph TD"]
        # Styling
        mermaid_lines.append("  classDef active fill:#9f9,stroke:#333,stroke-width:2px;")
        mermaid_lines.append("  classDef superseded fill:#eee,stroke:#999,stroke-dasharray: 5 5;")
        mermaid_lines.append("  classDef proposal fill:#fff,stroke:#00f,stroke-dasharray: 5 5;")

        if not all_meta:
            return "\n".join(mermaid_lines)

        for m in all_meta:
            fid = m['fid']
            target = m.get('target', 'unknown')
            status = m.get('status', 'unknown')
            kind = m.get('kind', 'decision')
            
            # Evidence count for label
            evidence_label = ""
            if self.episodic:
                count, _ = self.episodic.count_links_for_semantic(fid)
                if count > 0:
                    evidence_label = f"<br/>[{count} evidence]"

            # Sanitize for Mermaid
            node_id = fid.replace('.', '_').replace('-', '_').replace('/', '_')
            display_text = f"{target}<br/>({status}){evidence_label}"
            
            # Add node with style
            style_class = status if status in ["active", "superseded"] else "proposal" if kind == "proposal" else ""
            node_def = f'  {node_id}["{display_text}"]'
            if style_class:
                node_def += f'::: {style_class}'
            mermaid_lines.append(node_def)

            # Add links (supersedes)
            # Metadata store currently doesn't store 'supersedes' list, but it stores 'superseded_by'
            successor = m.get("superseded_by")
            if successor:
                succ_id = successor.replace('.', '_').replace('-', '_').replace('/', '_')
                mermaid_lines.append(f"  {node_id} -->|superseded by| {succ_id}")

        return "\n".join(mermaid_lines)
