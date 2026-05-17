-- Performance indexes for HR Assistant
--
-- Run this once against your Postgres database (Supabase or self-hosted).
-- Every statement uses IF NOT EXISTS, so it is safe to re-run.
--
-- We use `CONCURRENTLY` so the indexes are built without locking writes on
-- the target tables. Because of that, this script MUST NOT be executed
-- inside a transaction block. In `psql`:
--
--     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/performance_indexes.sql
--
-- If you run it from Supabase's SQL editor, paste these statements one at a
-- time (the editor wraps everything in a transaction, which breaks
-- CONCURRENTLY). For an initial run you can also drop the keyword if you
-- accept a brief lock.
--
-- The indexes below cover every column we filter, join or order by in the
-- application code: foreign keys, status flags, and time/score sort keys.

-- ============================================================
-- users
-- ============================================================
-- Foreign key -> companies. Without this every "admin scoped to my company"
-- query falls back to a sequential scan of users.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_company_id
    ON users (company_id);

-- Used by the bulk-create flow to find existing rows by email.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email
    ON users (email);

-- Helps the admin /students sort (surname, name).
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_surname_name
    ON users (surname, name);

-- Optional partial index for "list me only the regular users" queries that
-- power the student dashboard. Postgres can use this without scanning admin
-- rows at all.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_role_user
    ON users (id)
    WHERE role = 'USER';


-- ============================================================
-- created_vacancies
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_created_vacancies_company_id
    ON created_vacancies (company_id);

-- Partial index for the "active vacancies" lookups used on the dashboard.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_created_vacancies_active
    ON created_vacancies (company_id)
    WHERE is_available = TRUE;

-- For ordering by recency in /vacancies.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_created_vacancies_start_date
    ON created_vacancies (start_date DESC);


-- ============================================================
-- candidates
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_candidates_user_id
    ON candidates (user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_candidates_vacancy_id
    ON candidates (vacancy_id);

-- Used in /candidate/dashboard/applications/recent (filter user_id + order
-- by created_at desc).
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_candidates_user_created_at
    ON candidates (user_id, created_at DESC);


-- ============================================================
-- practice
-- ============================================================
-- /testing/assignments/* filters by is_valid + deadline.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_practice_valid_deadline
    ON practice (deadline)
    WHERE is_valid = TRUE;


-- ============================================================
-- practice_assignments
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_practice_assignments_user_id
    ON practice_assignments (user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_practice_assignments_practice_id
    ON practice_assignments (practice_id);

-- Composite for the "is this user assigned to this practice?" lookup that
-- runs in the WebSocket start_test path and the invitation flow.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_practice_assignments_practice_user
    ON practice_assignments (practice_id, user_id);

-- Speeds up the "open assignments" filter on the dashboard.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_practice_assignments_user_open
    ON practice_assignments (user_id)
    WHERE is_completed = FALSE;


-- ============================================================
-- test_session
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_test_session_user_id
    ON test_session (user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_test_session_practice_id
    ON test_session (practice_id);

-- Powers the /testing/sessions/{active,completed,all} pages — filter by
-- user, then order by started_time desc.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_test_session_user_started
    ON test_session (user_id, started_time DESC);

-- Powers the admin dashboard summary counts (active vs completed) and the
-- per-user aggregates in /admin/dashboard/students.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_test_session_user_finished
    ON test_session (user_id, is_finished);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_test_session_finished
    ON test_session (is_finished);


-- ============================================================
-- user_answers
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_answers_session_id
    ON user_answers (session_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_answers_question_id
    ON user_answers (question_id);

-- For the "did this session already answer this question?" check in the
-- testing WebSocket.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_answers_session_question
    ON user_answers (session_id, question_id);


-- ============================================================
-- question_history
-- ============================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_question_history_question_id
    ON question_history (question_id);


-- ============================================================
-- After running everything above, refresh planner statistics so Postgres
-- knows the new indexes exist.
-- ============================================================
ANALYZE users;
ANALYZE created_vacancies;
ANALYZE candidates;
ANALYZE practice;
ANALYZE practice_assignments;
ANALYZE test_session;
ANALYZE user_answers;
ANALYZE question_history;
