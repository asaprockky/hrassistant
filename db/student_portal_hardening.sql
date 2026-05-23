-- Student portal hardening support:
-- - avatar uploads for candidate profiles
-- - persistent "mark all notifications read" state

ALTER TABLE candidate_profiles
ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255);

CREATE TABLE IF NOT EXISTS candidate_notification_state (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    last_read_at TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
