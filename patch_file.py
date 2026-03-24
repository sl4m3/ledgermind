import re

with open("src/ledgermind/core/api/services/event_processing.py", "r") as f:
    content = f.read()

# Replace the loop with batch call
search_str = """            # 2. Inherit links from predecessors
            if intent and intent.resolution_type == "supersede":
                for old_id in intent.target_decision_ids:
                    old_links = self.episodic.get_linked_event_ids(old_id)
                    self.episodic.link_to_semantic_batch(old_links, new_fid)
                logger.info(f"Inherited grounding from predecessors to {new_fid}")"""

replace_str = """            # 2. Inherit links from predecessors
            if intent and intent.resolution_type == "supersede":
                # ⚡ Bolt: Use get_linked_event_ids_batch to prevent N+1 query problem during evidence inheritance
                batch_links = self.episodic.get_linked_event_ids_batch(intent.target_decision_ids)
                all_old_links = []
                for links in batch_links.values():
                    all_old_links.extend(links)
                if all_old_links:
                    self.episodic.link_to_semantic_batch(all_old_links, new_fid)
                logger.info(f"Inherited grounding from predecessors to {new_fid}")"""

if search_str in content:
    with open("src/ledgermind/core/api/services/event_processing.py", "w") as f:
        f.write(content.replace(search_str, replace_str))
    print("Patched successfully!")
else:
    print("Could not find block to patch")
