import os
import yaml
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

def migrate_keywords(repo_path):
    for root, _, filenames in os.walk(repo_path):
        if ".git" in root or ".tx_backup" in root: continue
        for f in filenames:
            if f.endswith(".md"):
                file_path = os.path.join(root, f)
                with open(file_path, 'r', encoding='utf-8') as stream:
                    content = stream.read()
                
                try:
                    data, body = MemoryLoader.parse(content)
                    if not data: continue
                    
                    if "context" not in data:
                        data["context"] = {}
                    
                    if "keywords" not in data["context"]:
                        # Extract simple keywords from title and rationale
                        title = data["context"].get("title", "")
                        rationale = data["context"].get("rationale", "")
                        target = data["context"].get("target", "")
                        
                        import re
                        all_text = f"{title} {target} {rationale}".lower()
                        words = re.findall(r'[a-zа-я0-9]{3,}', all_text)
                        stop_words = {"for", "the", "and", "with", "from", "this", "that", "was", "were", "been", "has", "had", 
                                      "для", "или", "это", "был", "была", "было", "были", "его", "ее", "их"}
                        keywords = sorted(list(set(w for w in words if w not in stop_words)))[:10]
                        
                        data["context"]["keywords"] = keywords
                        
                        new_content = MemoryLoader.stringify(data, body)
                        with open(file_path, 'w', encoding='utf-8') as stream:
                            stream.write(new_content)
                        print(f"Migrated {f} with keywords: {keywords}")
                except Exception as e:
                    print(f"Failed to migrate {f}: {e}")

if __name__ == "__main__":
    migrate_keywords("ledgermind/semantic")
