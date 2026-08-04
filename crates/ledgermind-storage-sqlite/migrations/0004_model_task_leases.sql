ALTER TABLE model_tasks ADD COLUMN expires_at TEXT;
ALTER TABLE model_tasks ADD COLUMN lease_owner TEXT;
ALTER TABLE model_tasks ADD COLUMN lease_expires_at TEXT;
ALTER TABLE model_tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX ix_model_tasks_lease
    ON model_tasks (memory_space_id, status, lease_expires_at, expires_at);
