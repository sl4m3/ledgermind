ALTER TABLE round_processing_jobs
ADD COLUMN lease_generation INTEGER NOT NULL DEFAULT 0;
