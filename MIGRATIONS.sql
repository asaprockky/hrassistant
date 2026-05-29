-- ============================================================
-- TalentFlow backend migrations
--
-- Run this MANUALLY against the database. The application code in this PR is
-- written to match this schema, but Alembic is intentionally NOT executed
-- against the live DB (per task constraints).
--
-- Safe to run more than once: every statement uses IF [NOT] EXISTS guards.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- A4: link a vacancy to the practice/assessment used when HR confirms an
-- applicant. Nullable so existing vacancies keep working.
-- ------------------------------------------------------------
ALTER TABLE created_vacancies
    ADD COLUMN IF NOT EXISTS practice_id UUID;

ALTER TABLE created_vacancies
    DROP CONSTRAINT IF EXISTS created_vacancies_practice_id_fkey;

ALTER TABLE created_vacancies
    ADD CONSTRAINT created_vacancies_practice_id_fkey
    FOREIGN KEY (practice_id) REFERENCES practice (practice_id) ON DELETE SET NULL;

-- ------------------------------------------------------------
-- U2: force a password change on first login for admin-created / invited /
-- reset accounts.
-- ------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false;

-- ------------------------------------------------------------
-- U5: real, persisted in-app notifications (status changes, etc.). Previously
-- notifications were only derived; this stores actual rows with their own
-- read state.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id                   UUID PRIMARY KEY,
    user_id              UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type                 VARCHAR(40) NOT NULL DEFAULT 'status_change',
    title                VARCHAR(150) NOT NULL,
    body                 TEXT,
    related_candidate_id UUID,
    related_vacancy_id   UUID,
    created_at           TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    read_at              TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id
    ON notifications (user_id);

CREATE INDEX IF NOT EXISTS ix_notifications_user_created
    ON notifications (user_id, created_at);

COMMIT;

-- ============================================================
-- OPTIONAL / DISABLED — do NOT run unless product confirms question-level
-- tag filtering is wanted (A1 PM note). Questions filter by `category` today;
-- tags live on practices, not questions.
-- ============================================================
-- ALTER TABLE user_questions
--     ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
-- CREATE INDEX IF NOT EXISTS ix_user_questions_tags
--     ON user_questions USING GIN (tags);
