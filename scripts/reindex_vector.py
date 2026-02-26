from ledgermind.core.api.memory import Memory

def reindex_vector_store():
    m = Memory(storage_path="ledgermind")
    print("Clearing vector store...")
    m.vector._vectors = None
    m.vector._doc_ids = []
    m.vector._dirty = True
    m.vector.save()
    
    print("Re-indexing all semantic memories...")
    all_decisions = m.semantic.meta.list_all()
    print(f"Found {len(all_decisions)} decisions in metadata store.")
    docs = []
    for meta in all_decisions:
        # Combine content with rationale as in process_event
        content = meta.get('content', '')
        # rationale is already included in 'content' column of semantic_meta during sync
        docs.append({
            "id": meta['fid'],
            "content": content
        })
    
    m.vector.add_documents(docs)
    m.vector.save()
    print(f"Successfully re-indexed {len(docs)} documents.")
    m.close()

if __name__ == "__main__":
    reindex_vector_store()
