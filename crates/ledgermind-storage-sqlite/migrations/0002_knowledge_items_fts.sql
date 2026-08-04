CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_items_fts USING fts5(
    knowledge_id UNINDEXED,
    memory_space_id UNINDEXED,
    title,
    target,
    statement,
    tokenize = 'unicode61'
);
