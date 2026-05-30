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

-- ------------------------------------------------------------
-- T1: tie every PracticeAssignment / TestSession row to the specific job
-- application it belongs to.
--
-- Before this migration, both tables were keyed only on (user_id, practice_id).
-- If a candidate had two confirmed applications that happened to use the same
-- practice, the system collapsed them onto a single row — completing the test
-- for one application wrongly marked the other one completed too, and the
-- "My Applications" surface could only show one of the two tests.
--
-- candidate_id / vacancy_id are nullable so legacy rows survive. New rows
-- always set them, and the backfill block below also fills them for any
-- legacy `(user, practice)` pair that resolves to exactly one application.
-- ------------------------------------------------------------
ALTER TABLE practice_assignments
    ADD COLUMN IF NOT EXISTS candidate_id UUID,
    ADD COLUMN IF NOT EXISTS vacancy_id   UUID;

ALTER TABLE practice_assignments
    DROP CONSTRAINT IF EXISTS practice_assignments_candidate_id_fkey;
ALTER TABLE practice_assignments
    ADD CONSTRAINT practice_assignments_candidate_id_fkey
    FOREIGN KEY (candidate_id) REFERENCES candidates (id) ON DELETE CASCADE;

ALTER TABLE practice_assignments
    DROP CONSTRAINT IF EXISTS practice_assignments_vacancy_id_fkey;
ALTER TABLE practice_assignments
    ADD CONSTRAINT practice_assignments_vacancy_id_fkey
    FOREIGN KEY (vacancy_id) REFERENCES created_vacancies (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_practice_assignments_candidate_id
    ON practice_assignments (candidate_id);
CREATE INDEX IF NOT EXISTS ix_practice_assignments_vacancy_id
    ON practice_assignments (vacancy_id);

ALTER TABLE test_session
    ADD COLUMN IF NOT EXISTS candidate_id  UUID,
    ADD COLUMN IF NOT EXISTS vacancy_id    UUID,
    ADD COLUMN IF NOT EXISTS assignment_id UUID;

ALTER TABLE test_session
    DROP CONSTRAINT IF EXISTS test_session_candidate_id_fkey;
ALTER TABLE test_session
    ADD CONSTRAINT test_session_candidate_id_fkey
    FOREIGN KEY (candidate_id) REFERENCES candidates (id) ON DELETE SET NULL;

ALTER TABLE test_session
    DROP CONSTRAINT IF EXISTS test_session_vacancy_id_fkey;
ALTER TABLE test_session
    ADD CONSTRAINT test_session_vacancy_id_fkey
    FOREIGN KEY (vacancy_id) REFERENCES created_vacancies (id) ON DELETE SET NULL;

ALTER TABLE test_session
    DROP CONSTRAINT IF EXISTS test_session_assignment_id_fkey;
ALTER TABLE test_session
    ADD CONSTRAINT test_session_assignment_id_fkey
    FOREIGN KEY (assignment_id) REFERENCES practice_assignments (assignment_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_test_session_candidate_id
    ON test_session (candidate_id);
CREATE INDEX IF NOT EXISTS ix_test_session_vacancy_id
    ON test_session (vacancy_id);
CREATE INDEX IF NOT EXISTS ix_test_session_assignment_id
    ON test_session (assignment_id);

-- Backfill: for every legacy practice_assignment that maps unambiguously to
-- exactly one candidate row (same user, vacancy linked to the same practice),
-- set candidate_id / vacancy_id. Rows with two or more candidates remain
-- ambiguous and are left NULL; the API falls back to the legacy
-- (user_id, practice_id) lookup for those.
WITH user_practice_candidates AS (
    SELECT c.user_id,
           cv.practice_id,
           c.id  AS candidate_id,
           c.vacancy_id
    FROM candidates c
    JOIN created_vacancies cv ON cv.id = c.vacancy_id
    WHERE cv.practice_id IS NOT NULL
), counted AS (
    SELECT user_id,
           practice_id,
           candidate_id,
           vacancy_id,
           COUNT(*) OVER (PARTITION BY user_id, practice_id) AS dup_count
    FROM user_practice_candidates
)
UPDATE practice_assignments pa
SET    candidate_id = counted.candidate_id,
       vacancy_id   = counted.vacancy_id
FROM   counted
WHERE  pa.user_id     = counted.user_id
  AND  pa.practice_id = counted.practice_id
  AND  pa.candidate_id IS NULL
  AND  counted.dup_count = 1;

-- Backfill test_session from practice_assignments now that they're linked.
UPDATE test_session ts
SET    candidate_id  = pa.candidate_id,
       vacancy_id    = pa.vacancy_id,
       assignment_id = pa.assignment_id
FROM   practice_assignments pa
WHERE  pa.user_id     = ts.user_id
  AND  pa.practice_id = ts.practice_id
  AND  ts.candidate_id IS NULL
  AND  pa.candidate_id IS NOT NULL;

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
