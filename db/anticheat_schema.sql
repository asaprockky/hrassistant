-- ============================================================
-- Anti-cheat + per-student adaptive difficulty schema
-- ============================================================
-- Required by the changes in routers/questions.py +
-- routers/admin_panel.py shipped in this PR. Run this BEFORE deploying
-- the new code, otherwise the new endpoints (POST /sessions/{id}/events,
-- GET /admin/test-sessions/{id}/events, the adaptive next-question
-- selection) will 500 with "relation does not exist".
--
-- Every statement is idempotent (IF NOT EXISTS / IF EXISTS), so it's
-- safe to run multiple times.
--
-- Recommended invocation:
--   1. psql:           \i db/anticheat_schema.sql
--   2. Supabase editor: paste in the SQL editor and run as one script
--      (Supabase already wraps the editor in a transaction).
--
-- The schema deliberately uses *sidecar* tables instead of ALTERing
-- `users` or `test_session` directly so that the running API never
-- references columns the database doesn't have yet — i.e. you can run
-- the migration whenever, before or after the deploy, without breaking
-- existing endpoints. The sidecar relationships are lazy in
-- SQLAlchemy, so only the anti-cheat code paths touch them.

BEGIN;

-- ------------------------------------------------------------
-- 1) Per-user running skill estimate (0..1) driving adaptive
--    question selection in GET /testing/sessions/{id}/next-question.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_skills (
    user_id        uuid PRIMARY KEY
                       REFERENCES users (id) ON DELETE CASCADE,
    skill_estimate double precision NOT NULL DEFAULT 0.5,
    updated_at     timestamp        NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 2) Per-session anti-cheat sidecar: the shuffled+locked question
--    order (so a refresh returns the same order), the connection
--    fingerprint captured at session start, the strike counter
--    consumed by POST /testing/sessions/{id}/events, and the
--    auto-finish reason if the strike limit was hit.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_session_meta (
    session_id            uuid PRIMARY KEY
                              REFERENCES test_session (session_id) ON DELETE CASCADE,
    question_order        uuid[],
    ip_address            varchar(45),
    user_agent            text,
    device_fingerprint    varchar(128),
    strikes               integer NOT NULL DEFAULT 0,
    auto_finished_reason  varchar(64)
);

-- ------------------------------------------------------------
-- 3) Anti-cheat event log (tab_blur, paste_attempt, copy_attempt,
--    devtools_open, fullscreen_exit, right_click, suspicious_timing,
--    ...) ingested via POST /testing/sessions/{id}/events. Read via
--    GET /testing/sessions/{id}/events (owner) and
--    GET /admin/test-sessions/{id}/events (admin).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_events (
    id          uuid    PRIMARY KEY,
    session_id  uuid    NOT NULL
                        REFERENCES test_session (session_id) ON DELETE CASCADE,
    event_type  varchar(64) NOT NULL,
    severity    varchar(16) NOT NULL DEFAULT 'info',
    payload     json,
    created_at  timestamp   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_session_events_session_id
    ON session_events (session_id);
CREATE INDEX IF NOT EXISTS ix_session_events_event_type
    ON session_events (event_type);
CREATE INDEX IF NOT EXISTS ix_session_events_severity
    ON session_events (severity);

COMMIT;

-- ------------------------------------------------------------
-- Refresh planner stats so the new tables/indexes are picked up
-- immediately. ANALYZE must run outside the transaction above.
-- ------------------------------------------------------------
ANALYZE user_skills;
ANALYZE test_session_meta;
ANALYZE session_events;

-- ------------------------------------------------------------
-- Rollback (uncomment to remove everything this script added).
-- ------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS session_events;
-- DROP TABLE IF EXISTS test_session_meta;
-- DROP TABLE IF EXISTS user_skills;
-- COMMIT;
