ALTER TABLE inference_profiles
    ADD COLUMN extra_body_json TEXT NOT NULL DEFAULT '{}';

