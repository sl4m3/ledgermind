CREATE VIRTUAL TABLE core_knowledge_fts USING fts5(
    knowledge_id UNINDEXED,
    memory_space_id UNINDEXED,
    title,
    target,
    statement,
    tokenize='unicode61'
);
