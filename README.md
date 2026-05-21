# HR Assistant API

FastAPI backend  for TalentFlow-style HR automation: user authentication, company vacancies, resume uploads, candidate dashboards, admin operations, test assignment, HTTP-driven live assessment, and adaptive question difficulty.

Production base URL used by the existing API notes:

```text
https://api.talentflow.uz
```

Local development usually runs on:

```text
http://127.0.0.1:8000
```

Interactive API docs are available at `/docs` and `/redoc` when the app is running.

## What This Backend Does

This service is the backend API layer for an HR assistant platform. It stores companies, users, vacancies, candidates, questions, practices, assignments, test sessions, and answers. It also has two AI-adjacent pieces: an adaptive test difficulty recalculation loop inside the live testing HTTP endpoints, and a prototype Google Gemini resume-review script.

The main application is created in `main.py`. Routers are mounted from `routers/`, database models live in `database/models.py`, authentication helpers live in `auth/jwt_handler.py`, and request/response schemas live in `schemas/user_schema.py`.

## Repository Map

| Path | Purpose |
| --- | --- |
| `main.py` | Creates the FastAPI app, mounts routers, configures CORS, and exposes `/health/ping` plus `/users`. |
| `auth/jwt_handler.py` | Creates and verifies JWT access tokens. |
| `database/database.py` | Builds the SQLAlchemy engine, session factory, base model, and DB dependency. |
| `database/models.py` | SQLAlchemy models for companies, users, vacancies, candidates, questions, practices, assignments, test sessions, and answers. |
| `database/enums.py` | Role enum: `USER`, `ADMIN`, `SUPERADMIN`. |
| `routers/login.py` | Login, registration, password hashing, and cookie/header JWT auth helpers. |
| `routers/main_page.py` | Vacancy create/list endpoints and PDF resume upload/extraction. |
| `routers/candidate_dashboard.py` | Candidate pipeline summary and recent applications. |
| `routers/admin_panel.py` | Admin dashboard, users, companies, vacancies, candidates, questions, practices, assignments, and test sessions. |
| `routers/questions.py` | Live testing HTTP session lifecycle (start/next/answer/finish/result) plus assignment/result REST endpoints. |
| `routers/tester_main.py` | Candidate test-session lists: active, completed, all. |
| `routers/email.py` | Email verification via Gmail SMTP and legacy seed/schema helper code. |
| `routers/user_profile.py` | Current user's profile and test activity. |
| `routers/user_resumes.py` | Placeholder router; it is not currently mounted in `main.py`. |
| `schemas/ai_resume_reviewer.py` | Prototype Gemini resume-review prompt/script; not mounted as an API route. |
| `utils/ai_logic.py` | Sigmoid-based adaptive difficulty calculation for questions. |
| `utils/mailer.py` | Environment-driven SMTP helper used by admin account and assessment invitations. |
| `db.py` | Destructive sample-data seeding script; drops and recreates tables. |
| `alembic/` and `alembic.ini` | Alembic migration setup. Current migration history appears older than the current models. |
| `passenger_wsgi.py` | Passenger/cPanel-style WSGI bridge using `a2wsgi`. |
| `100_questions_import.csv` | Sample/importable question data. |
| `test.db` and `test.sqbpro` | Legacy SQLite test database and DB Browser project file. Not the source of truth for the current PostgreSQL models. |
| `cv.html`, `resume.html`, PDFs | Static/sample resume and candidate profile artifacts. |

## Architecture

```text
Client app
  |
  | HTTP: REST endpoints with cookie or Bearer JWT
  v
FastAPI app in main.py
  |
  +-- Authentication router
  +-- User/profile/email routers
  +-- Vacancy and resume-upload router
  +-- Candidate dashboard router
  +-- Admin router
  +-- Testing session lifecycle router
  |
  v
SQLAlchemy session dependency
  |
  v
PostgreSQL database
```

The core request pattern is:

1. The client logs in through `/auth/login`.
2. The API creates a JWT signed with the app secret.
3. The token is returned in the JSON response and also set as an `access_token` cookie.
4. Protected HTTP endpoints read the token from either the cookie or `Authorization: Bearer <token>`. The testing flow is entirely HTTP — no WebSocket is required.

## Configuration And Secrets

Important: the current repository contains real-looking credentials hardcoded in source files. Treat every committed secret as compromised, rotate it in the provider dashboard, and move runtime configuration into environment variables before production use.

This README intentionally does not repeat secret values. The table below documents what each key/config value does, why it exists, and where the current code uses it.

Only one true third-party API key appears in the current code: the Google Gemini key. The database URL, JWT secret, and Gmail app password are not "API keys" in the narrow sense, but they are equally sensitive credentials and should be handled with the same care. There is no OpenAI API key in the checked-in code.

| Recommended env name | Current code name/location | What it does | Why the app needs it |
| --- | --- | --- | --- |
| `DATABASE_URL` | `DATABASE_URL` in `database/database.py`; another URL appears in `alembic.ini`; imported in `routers/email.py` | SQLAlchemy connection string for the application database. It tells SQLAlchemy which DB server to connect to, which database to use, and which credentials authenticate the connection. | Every persistent feature depends on it: users, companies, vacancies, candidates, questions, assignments, sessions, answers, and difficulty history. Without this value, the API cannot read or write platform state. |
| `JWT_SECRET_KEY` | `SECRET_KEY` in `auth/jwt_handler.py`; imported by `routers/login.py` | Symmetric signing secret for JWT access tokens using HS256. The same secret signs tokens at login and verifies them on protected requests. | Prevents users from forging or modifying tokens. If this changes, all existing tokens become invalid, which is useful after a breach but disruptive during normal operation. |
| `JWT_ALGORITHM` | `ALGORITHM` in `auth/jwt_handler.py` | JWT signing algorithm. The code currently uses `HS256`. | Defines how token signatures are produced and verified. Keep this consistent across token creation and validation. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `ACCESS_TOKEN_EXPIRE_MINUTES` in `auth/jwt_handler.py` | Controls the JWT `exp` claim. The current code sets token lifetime to 60 minutes. | Limits how long a stolen token remains useful. Shorter lifetimes improve security; longer lifetimes reduce login friction. |
| `SMTP_SERVER` | `SMTP_SERVER` in `routers/email.py`; env-read by `utils/mailer.py` | SMTP hostname used to send verification emails and admin invitations. Current default points at Gmail SMTP. | The email verification route and admin invitation routes need a mail server to deliver one-time codes, account credentials, and assessment links. |
| `SMTP_PORT` | `PORT` in `routers/email.py`; env-read by `utils/mailer.py` | SMTP SSL port. Current default is `465`. | Required to establish the encrypted SMTP connection. |
| `SMTP_LOGIN` | `LOGIN` in `routers/email.py`; env-read by `utils/mailer.py` | Sender mailbox username for SMTP authentication. | Identifies the mailbox sending verification codes and admin invitations. |
| `SMTP_APP_PASSWORD` | `PASSWORD` in `routers/email.py`; env-read by `utils/mailer.py` | Gmail app password used by the SMTP client. This is not a normal Google password; it is a scoped credential generated from a Google account with 2FA. | Gmail will not allow this app to send mail unless SMTP login succeeds. Rotate this value if it has ever been committed. |
| `SENDER_EMAIL` | `SENDER_EMAIL` in `routers/email.py`; env-read by `utils/mailer.py` | Email address shown in the `From` header. Current email-verification code sets it to the SMTP login. | Users need a recognizable sender for verification messages and assessment invitations, and SMTP providers often require the sender to match the authenticated account. |
| `GOOGLE_GEMINI_API_KEY` | Hardcoded `genai.configure(api_key=...)` in `schemas/ai_resume_reviewer.py` and `test.py` | Authenticates requests to Google Generative AI / Gemini. The prototype uses `gemini-2.5-flash`. | Used by the resume-review prototype to turn a job description and resume text into structured JSON: match score, advantages, disadvantages, education, experience, and skills. This logic is not currently wired into the FastAPI upload endpoint. |
| `CORS_ALLOWED_ORIGINS` | Hardcoded list in `main.py` | Browser security allow-list for frontend origins. Current values include localhost and deployed Vercel frontends. | Allows the frontend to call this API from a different origin and send credentials such as cookies. Missing origins cause browser CORS failures even when the API is healthy. |

Example `.env` shape for a production-ready version of this app:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB_NAME
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_LOGIN=sender@example.com
SMTP_APP_PASSWORD=replace-with-gmail-app-password
SENDER_EMAIL=sender@example.com

GOOGLE_GEMINI_API_KEY=replace-with-google-ai-studio-key
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://your-frontend.example
```

The new admin invitation helper reads SMTP settings from environment variables. The older database, JWT, Gemini, and email-verification code still uses hardcoded constants, so those should be moved to `os.getenv(...)` or a settings object before deployment.

## Local Setup

```bash
git clone https://github.com/asaprockky/hrassistant.git
cd hrassistant

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

Notes:

- `google-generativeai` is used by the Gemini prototype but is not currently listed in `requirements.txt`.
- `a2wsgi` is used by `passenger_wsgi.py` but is not currently listed in `requirements.txt`.
- The current models use PostgreSQL-specific types such as `UUID` and `ARRAY`. Use PostgreSQL for the real app. `test.db` is a legacy SQLite artifact and does not match the current model set.

## Database

The SQLAlchemy models define these main entities:

| Model | Table | Meaning |
| --- | --- | --- |
| `Company` | `companies` | Employer/company owning users and vacancies. |
| `User` | `users` | Platform user with role, hashed password, profile fields, optional company, and optional group. |
| `Created_Vacancy` | `created_vacancies` | Job opening created by a company. |
| `Candidate` | `candidates` | Candidate application/resume record linked to a user and vacancy. |
| `Question` | `user_questions` | Test question with JSON options, correct option UUID, category, points, and adaptive difficulty. |
| `QuestionHistory` | `question_history` | Audit trail for difficulty changes. |
| `Practice` | `practice` | Assessment definition: title, question IDs, tags, deadline, duration, validity. |
| `PracticeAssignment` | `practice_assignments` | Join table assigning practices to users and marking completion. |
| `TestSession` | `test_session` | One user's attempt at one practice. |
| `UserAnswer` | `user_answers` | Answer submitted during a test session, including correctness, points, and time spent. |

### Migrations And Seeding

Alembic is configured, but the checked-in migration does not fully match the current models. For example, the migration still references older practice fields while the current model uses `duration_minutes`, `description`, `created_at`, and `practice_assignments`.

`db.py` is a destructive seed script:

```bash
python db.py
```

It calls `Base.metadata.drop_all(bind=engine)` and recreates tables, so run it only against a disposable local database.

`alembic.py` autogenerates a revision and immediately upgrades:

```bash
python alembic.py
```

Use that carefully. In a production workflow, prefer explicit Alembic commands, review generated migrations, and never run schema-changing scripts against production without a backup.

## Authentication

### Login

`POST /auth/login`

This endpoint expects OAuth2 form data, not JSON.

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=1234"
```

Response shape:

```json
{
  "access_token": "jwt-token",
  "user": {
    "name": "Admin",
    "surname": "User",
    "username": "admin",
    "userRole": "ADMIN",
    "age": 21,
    "email": "admin@example.com"
  }
}
```

The endpoint also sets an HTTP-only `access_token` cookie. For local development the cookie uses `secure=False`; on HTTPS production deployments this should be `secure=True`.

### Register

`POST /auth/register`

```json
{
  "username": "candidate1",
  "password": "strong-password",
  "role": "USER",
  "name": "Candidate",
  "surname": "One",
  "age": 24,
  "email": "candidate@example.com"
}
```

Passwords are hashed with bcrypt through Passlib. The helper truncates password bytes to 72 bytes because bcrypt ignores input beyond that limit.

### Using Protected Routes

Protected HTTP endpoints accept either:

```http
Authorization: Bearer <access_token>
```

or the `access_token` cookie set by login.

Roles:

- `USER` can use candidate/user routes.
- `ADMIN` and `SUPERADMIN` can use admin routes in `routers/admin_panel.py`.

## HTTP Testing Protocol

The live assessment flow used to run over a single WebSocket. It is now a set
of normal HTTP endpoints under `/testing/...` so clients that can't use
WebSockets (mobile webviews, restrictive corporate networks, hosted previews,
etc.) can still take a test. All endpoints require a normal JWT in the
`access_token` cookie or `Authorization: Bearer <token>` header.

### State Machine

```text
  +------------------+
  | (not started)    |
  +--------+---------+
           | POST /practices/{id}/sessions      -> creates TestSession
           v
  +------------------+
  | in_progress      |
  +--------+---------+
           | GET  /sessions/{id}/next-question  -> next unanswered question
           | POST /sessions/{id}/answers        -> score one question
           |                                    -> auto-finishes when last
           | POST /sessions/{id}/finish         -> manual finalize (idempotent)
           v
  +------------------+
  | finished         |
  +------------------+
           | GET  /sessions/{id}                -> progress snapshot
           | GET  /sessions/{id}/result         -> full per-question result
           | GET  /sessions/{id}/answers        -> answer list w/ correctness
```

Re-entry is blocked: each (user, practice) pair can have at most one
`TestSession`. `POST /practices/{id}/sessions` returns `409 Conflict` with the
existing session id so the client can resume or view results without guessing.

Duration is enforced server-side. If the user lets the timer expire,
`/next-question` and `/answers` auto-finish the session — the frontend no
longer has to call `finish` on a timer.

### Pre-Test

#### `GET /testing/practices/{practice_id}`

Metadata for the candidate test page. Does not include the questions
themselves so the question bank isn't leaked before the user actually starts.

```json
{
  "practice_id": "practice-uuid",
  "title": "Backend Engineer Screening",
  "description": "30 minutes, multiple choice.",
  "duration_minutes": 30,
  "deadline": "2026-01-30T18:00:00",
  "question_count": 10,
  "tags": ["backend", "sql"]
}
```

#### `GET /testing/practices/{practice_id}/eligibility`

Tells the frontend which CTA to show — `Start`, `Resume`, `View result`, etc.
— without having to POST and parse a 4xx.

```json
{
  "status": "eligible",
  "can_start": true,
  "can_resume": false,
  "session_id": null,
  "reason": null
}
```

`status` is one of `eligible`, `in_progress`, `finished`, `duration_exceeded`,
`assignment_completed`, `deadline_passed`, `not_invited`, `not_found`. When
`status` is `in_progress`, the frontend should use the returned `session_id`
to resume.

#### `GET /testing/practices/{practice_id}/session`

Shortcut: returns the user's session for the given practice (if any), or
`null`. Useful right before showing the test page so the client knows
immediately whether to render the start screen, the in-progress screen, or
the result screen.

### Session Lifecycle

#### `POST /testing/practices/{practice_id}/sessions`

Starts a session. Checks invitation, assignment completion, re-entry, and
deadline — same rules as the old `start_test` WS action.

Success response (`201 Created`):

```json
{
  "event": "test_started",
  "session_id": "session-uuid",
  "practice_id": "practice-uuid",
  "started_at": "2026-01-15T11:00:00",
  "duration_minutes": 30,
  "ends_at": "2026-01-15T11:30:00",
  "total_questions": 10,
  "quantity": 10,
  "duration": 30
}
```

`quantity` and `duration` are kept alongside the new field names so any
frontend that already reads the legacy WS payload keeps working.

Failure modes:

- `403 Not invited` — no `PracticeAssignment` for this user.
- `409 Already completed` — assignment is already marked completed.
- `409 Re-entry not allowed` — a session already exists; the response body
  carries the existing `session_id` so the frontend can resume / view.
- `409 Deadline has passed`.
- `404 Practice not found` (or `is_valid=False`).

#### `GET /testing/sessions/{session_id}`

Progress snapshot. Cheap to poll for the in-progress timer / progress bar.

```json
{
  "session_id": "session-uuid",
  "practice_id": "practice-uuid",
  "is_finished": false,
  "answered_count": 3,
  "correct_count": 2,
  "total_questions": 10,
  "overall_points": 20.0,
  "started_at": "2026-01-15T11:00:00",
  "ends_at": "2026-01-15T11:30:00",
  "seconds_remaining": 1234
}
```

#### `GET /testing/sessions/{session_id}/next-question`

Returns the next unanswered question, in `Practice.question_ids` order. If
there are no remaining questions, or the duration has expired, the session
is auto-finalized and the response is the `test_finished` payload.

Question payload:

```json
{
  "event": "question_data",
  "session_id": "session-uuid",
  "id": "question-uuid",
  "text": "Which SQL clause filters rows?",
  "options": [
    { "id": "option-uuid-1", "text": "ORDER BY" },
    { "id": "option-uuid-2", "text": "WHERE" }
  ],
  "category": "SQL",
  "points": 5.0,
  "progress": {
    "answered_count": 3,
    "total_questions": 10,
    "remaining_count": 7
  }
}
```

The correct answer is intentionally not included.

Auto-finish payload (when nothing is left to answer):

```json
{
  "event": "test_finished",
  "session_id": "session-uuid",
  "final_score": 82.5,
  "reason": "all_answered"
}
```

`reason` is one of `all_answered`, `duration_exceeded`.

#### `POST /testing/sessions/{session_id}/answers`

Submit a single answer.

Request:

```json
{
  "question_id": "question-uuid",
  "user_answer": "selected-option-uuid",
  "time_spent": 18.4
}
```

Response when the session is still in progress:

```json
{
  "event": "answer_result",
  "is_correct": true,
  "correct_answer": "correct-option-uuid",
  "points_awarded": 12.5,
  "new_difficulty": 0.61,
  "answered_count": 4,
  "total_questions": 10,
  "is_finished": false,
  "final_score": null
}
```

Response when this answer is the last one (session auto-finalizes):

```json
{
  "event": "answer_result",
  "is_correct": false,
  "correct_answer": "correct-option-uuid",
  "points_awarded": 0.0,
  "new_difficulty": 0.72,
  "answered_count": 10,
  "total_questions": 10,
  "is_finished": true,
  "final_score": 67.5
}
```

The scoring formula is unchanged:

```text
points_awarded = (question.points / sum(all practice question points)) * 100
```

The adaptive difficulty formula lives in `utils/ai_logic.py`:

```text
z = (0.8 * failure_rate) + (0.2 * min(avg_time / 60, 1)) - 0.5
difficulty = sigmoid(z)
```

Failure modes:

- `400` — question isn't part of this practice.
- `404` — session not found / not owned / question not found.
- `409 Session already finished`.
- `409 Duration expired` — session is also auto-finalized.
- `409 Question already answered` — duplicate submission for the same
  `(session_id, question_id)`.

#### `POST /testing/sessions/{session_id}/finish`

Manually finalize a session. Idempotent — calling on an already finished
session just returns the final state.

```json
{
  "event": "test_finished",
  "session_id": "session-uuid",
  "final_score": 82.5,
  "is_finished": true,
  "answered_count": 10,
  "total_questions": 10,
  "message": "Assignment completed and locked."
}
```

#### `GET /testing/sessions/{session_id}/answers`

List every answer in the session with the question text and the correct
option id — useful for a review screen.

```json
{
  "items": [
    {
      "id": "answer-uuid",
      "question_id": "question-uuid",
      "question_text": "Which SQL clause filters rows?",
      "user_answer": "option-uuid-1",
      "is_correct": false,
      "correct_answer_id": "option-uuid-2",
      "points_awarded": 0.0,
      "time_spent": 18.4
    }
  ],
  "total": 1
}
```

#### `GET /testing/sessions/{session_id}/result`

A progress snapshot plus the full answers list in one call — convenient for
the post-test result page.

### Client Example

```js
const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

// 1. Start a session (or recover the existing one)
let sessionId;
const start = await fetch(`/testing/practices/${practiceId}/sessions`, { method: "POST", headers });
if (start.status === 201) {
  sessionId = (await start.json()).session_id;
} else if (start.status === 409) {
  // Re-entry blocked — the existing session id is in the error body.
  const body = await start.json();
  sessionId = body.detail.session_id;
}

// 2. Loop: fetch next question, submit answer, repeat.
while (true) {
  const q = await fetch(`/testing/sessions/${sessionId}/next-question`, { headers }).then(r => r.json());
  if (q.event === "test_finished") {
    console.log("Final score:", q.final_score);
    break;
  }

  const optionId = chooseOption(q.options);
  const res = await fetch(`/testing/sessions/${sessionId}/answers`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question_id: q.id, user_answer: optionId, time_spent: 12.0 }),
  }).then(r => r.json());

  if (res.is_finished) {
    console.log("Final score:", res.final_score);
    break;
  }
}
```

### Rules To Build The Frontend Around

- Bearer JWT or `access_token` cookie on every call.
- `POST /sessions` is single-shot per `(user, practice)`; on `409`, read
  `detail.session_id` from the response body and resume.
- Sessions auto-finalize when there are no questions left or the timer
  expires; the frontend doesn't have to call `finish` on a timer.
- Calling `finish` more than once is safe.
- The correct answer is never sent in `next-question`. It is only returned
  after the answer is submitted (or via the `/answers` / `/result` endpoints
  which are available regardless of finish state).
- **No-resume policy.** Leaving the test (closing the tab,
  switching windows, calling `/sessions/{id}/abandon`, or reaching the
  strike threshold) finalizes the session immediately and the user
  cannot continue it. Admins can re-assign a new attempt via the
  existing assignment flow.
- `POST /testing/sessions/{id}/abandon` is intended as a beacon target
  for the frontend (fires on `pagehide` / `visibilitychange` /
  fullscreen-exit). It is idempotent and returns the final score.
- A browser refresh during an *unfinished* session no longer "resumes"
  the session — eligibility now returns `already_attempted` once a
  session has been opened, and the in-progress session is auto-finished
  on the spot.

### Anti-Cheat & Adaptive Difficulty

The testing flow has two cheat-resistance layers and a per-student
adaptive difficulty layer. Schema for all three lives in
`db/anticheat_schema.sql` — **run that script on the database before
deploying this code**, otherwise the new endpoints 500. The migration
uses sidecar tables (`user_skills`, `test_session_meta`,
`session_events`) so existing endpoints keep working before the script
is run.

**1. Per-session question shuffle (server-side, no client opt-out).**
`POST /testing/practices/{id}/sessions` snapshots and shuffles
`Practice.question_ids` into `TestSessionMeta.question_order`. Every
subsequent `/next-question` walks that shuffled list. Refreshing the
tab gets you back where you were — no replay of the easier questions,
no memorizing a static question order across attempts.

**2. Per-student adaptive difficulty.** Each user has a running
`UserSkill.skill_estimate` in `[0, 1]`, defaulting to `0.5`.
`/next-question` picks the unanswered question whose `difficulty_level`
is *closest* to the user's skill. `/answers` updates the skill with a
logistic-Elo step:

```text
expected = sigmoid((skill - difficulty) * 4)
skill   := clamp(skill + 0.12 * (actual - expected), 0, 1)
```

`/next-question` and `/answers` both return `skill_estimate` so the
frontend can show a "your level" indicator if it wants.

**3. Anti-cheat event ingestion.** The test page reports violation
events to `POST /testing/sessions/{id}/events`:

```json
POST /testing/sessions/{session_id}/events
{
  "event_type": "tab_blur",       // free-form, max 64 chars
  "severity":   "warn",            // "info" | "warn" | "critical"
  "payload":    { "tab_hidden_ms": 4200 }
}
```

Strike policy (configurable via `STRIKE_LIMIT` in
`routers/questions.py`, default `2`):

- `severity=info` — logged, no strike. Use for low-signal events
  (brief `tab_blur`, `right_click`).
- `severity=warn` / `critical` — counts as a strike. **First strike**
  returns `{warning: true, strikes: 1, message: "...one more violation
  will auto-submit..."}`. **Second strike** returns
  `{finished: true, reason: "cheating_detected", final_score: ...}`
  and the session is auto-finalized + the assignment marked completed.

Suspicious-timing is detected server-side: any `/answers` call with
`time_spent < 0.5s` automatically logs a `suspicious_timing` event
with `severity="warn"` (no client cooperation required), so the same
strike policy applies.

Session start also captures the client IP (honouring
`X-Forwarded-For`), User-Agent, and an optional
`device_fingerprint` in the `POST /sessions` body so admins can later
correlate multi-account / shared-session attempts:

```json
POST /testing/practices/{practice_id}/sessions
{ "device_fingerprint": "fp_a1b2c3..." }   // body is optional
```

Read endpoints:

- `GET /testing/sessions/{id}/events` — owner sees own event log +
  current strike count + auto-finish reason.
- `GET /admin/test-sessions/{id}/events` — admin sees the same plus
  the connection fingerprint (`ip_address`, `user_agent`,
  `device_fingerprint`).

What this does *not* fix — these need proctoring or a lockdown
browser, not server-side checks: a second device next to the user
looking up answers, a person in the room helping, audio cheating
(earbuds / voice assistant), screen-sharing to a friend, remote
desktop, OCR on a phone camera, photographing the screen to solve
later.

## REST API

### Health

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health/ping` | No | Returns `{"message": "pong"}` for uptime checks. |

### Authentication

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/login` | No | Accepts OAuth2 form username/password, returns JWT, sets cookie. |
| `POST` | `/auth/register` | No | Creates a user and returns a JWT. |

### Users

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/users` | No in current code | Lists all users. Consider protecting this before production. |
| `GET` | `/users/me` | User | Returns current user's profile fields. |
| `GET` | `/users/me/activity` | User | Returns current user's test-session activity. |

### Email Verification

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/users/me/email/verification-code` | User | Generates a 5-digit code, stores it in memory for 5 minutes, sends it through SMTP. |
| `POST` | `/users/me/email/verification` | User | Verifies the code and updates the user's email. |

The verification store is in memory, so codes disappear on server restart and do not work across multiple API instances unless replaced with Redis/database storage.

### Vacancies And Resume Uploads

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/vacancies` | User | Lists vacancies for the current user's company. |
| `POST` | `/vacancies` | User | Creates a vacancy for the current user's company. |
| `POST` | `/vacancies/resume-uploads` | No in current code | Uploads a PDF, saves it with a UUID filename, extracts text with PyPDF2, returns a 500-character preview. |

Resume upload currently extracts text only. It does not create a `Candidate` row and does not call the Gemini reviewer.

### Candidate Dashboard

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/candidate/dashboard/pipeline` | User | Returns total jobs applied, completed tests, and average test score. |
| `GET` | `/candidate/dashboard/applications/recent?page=1&size=10` | User | Returns paginated recent applications with company, role, status, score, and applied date. |

### Candidate Portal

The candidate portal powers the student-facing single-page app (TalentFlow Student). All routes are mounted under `/candidate/portal` and require a `USER` JWT.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/candidate/portal/me` | Current user + profile completeness for the header card. |
| `GET` | `/candidate/portal/dashboard` | Dashboard snapshot: greeting, stats, active assessments, recent activity, certificates preview, resume insights. |
| `GET` | `/candidate/portal/assessments` | Full list of assigned/active/completed assessments. |
| `GET` | `/candidate/portal/assessments/{practice_id}` | Detail page for one assessment (questions count, last attempt, eligibility). |
| `GET` | `/candidate/portal/reports/{session_id}` | Result page for a finished session (score, per-question breakdown, integrity summary). |
| `GET` | `/candidate/portal/analytics` | Full analytics payload (overview + categories + timeline) for the analytics page. |
| `GET` | `/candidate/portal/analytics/overview` | Lightweight analytics overview for cards. |
| `GET` | `/candidate/portal/analytics/categories` | Per-category mastery rows. |
| `GET` | `/candidate/portal/analytics/timeline` | Time-series of average score for charts. |
| `GET` | `/candidate/portal/notifications` | Notification feed (unread count + items). |
| `GET` | `/candidate/portal/profile/share` | Public shareable profile slug + payload. |
| `GET` | `/candidate/portal/ai-profile` | AI-generated headline + career roadmap. |
| `PATCH` | `/candidate/portal/ai-profile` | Update profile fields (headline, location, university, etc.). |
| `GET` | `/candidate/portal/certificates` | List certificates (`status_filter=all|earned|pending`). |
| `GET` | `/candidate/portal/certificates/{certificate_key}` | One certificate's full payload. |
| `GET` | `/candidate/portal/certificates/{certificate_key}/share` | Public share URL for a certificate. |
| `GET` | `/candidate/portal/certificates/{certificate_key}/download` | Stream a PDF render of a certificate. |
| `POST` | `/candidate/portal/certificates` | Attach an external certificate. |
| `DELETE` | `/candidate/portal/certificates/{certificate_id}` | Remove an external certificate. |
| `GET` | `/candidate/portal/resume-reviews/latest` | Latest AI resume review. |
| `POST` | `/candidate/portal/resume-reviews` | Upload a new PDF for review. |
| `GET` | `/candidate/portal/leaderboard?scope=group\|global` | Ranks students by average score. Other students are anonymized; the current user is named, with a `you_rank` field. |
| `GET` | `/candidate/portal/achievements` | Six derived badges (first session, 5 sessions, perfect score, 5x 80%+, 3-day streak, 3 certificates) plus a streak summary. |
| `GET` | `/candidate/portal/practice/categories` | Available practice categories (derived from assigned practices, falls back to all categories). |
| `GET` | `/candidate/portal/practice/next-question?category=&difficulty=easy\|medium\|hard&exclude_ids=` | Untimed practice question with seeded option shuffle and `correct_answer` for client-side grading. |

### Testing

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/testing/practices/{practice_id}` | User | Practice metadata for the candidate test page (no questions leaked). |
| `GET` | `/testing/practices/{practice_id}/eligibility` | User | Whether the user can start / must resume / has already finished. |
| `GET` | `/testing/practices/{practice_id}/session` | User | The user's session for this practice (active or finished) or `null`. |
| `POST` | `/testing/practices/{practice_id}/sessions` | User | Create a new `TestSession` (re-entry blocked, 409 returns existing id). |
| `GET` | `/testing/sessions/{session_id}` | User | Progress snapshot — score, answered count, time remaining. |
| `GET` | `/testing/sessions/{session_id}/next-question` | User | Next unanswered question, or auto-finish payload. |
| `POST` | `/testing/sessions/{session_id}/answers` | User | Submit one answer; scores, recalculates difficulty, may auto-finish. |
| `GET` | `/testing/sessions/{session_id}/answers` | User | List every answer in the session with correctness info. |
| `POST` | `/testing/sessions/{session_id}/finish` | User | Idempotent manual finalize. |
| `GET` | `/testing/sessions/{session_id}/result` | User | Progress snapshot + full per-question result. |
| `POST` | `/testing/sessions/{session_id}/events` | User | Report a cheating-vector violation; consumes strike, may auto-finish. |
| `GET` | `/testing/sessions/{session_id}/events` | User | Own anti-cheat event log + current strike count. |
| `GET` | `/testing/practices/{practice_id}/result` | User | Latest score and finish state for a practice by id (legacy shortcut). |
| `GET` | `/testing/assignments/{filter_option}` | User | Lists available assignments. `filter_option` can be `latest`, `all`, or a numeric limit. |
| `GET` | `/testing/sessions/active?page=1&size=10` | User | Paginated active test sessions. |
| `GET` | `/testing/sessions/completed?page=1&size=10` | User | Paginated completed test sessions. |
| `GET` | `/testing/sessions/all?page=1&size=10` | User | Paginated active and completed test sessions. |

### Admin

In this product, an admin is not just a "site moderator." An admin is the operational owner for hiring or university assessment workflows. They create vacancies, build question banks, assemble assessments, create or search student/candidate users, assign tests only to invited users, send login credentials and invitations, and track student progress from their own panel.

All admin routes require a user whose role is `ADMIN` or `SUPERADMIN`. Normal admins are scoped to their own `company_id` where the model supports it. `SUPERADMIN` can operate across companies. Normal admins can create `USER` accounts only; only `SUPERADMIN` should create other admins.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/admin/dashboard/summary` | Counts users, candidates, vacancies, practices, questions, active/completed sessions, and average score. |
| `GET` | `/admin/dashboard/students` | Personal admin panel stats for students: assigned tests, pending assignments, active sessions, completed sessions, average score, and last activity. Supports `group_name`, `search`, `offset`, and `limit`. |
| `GET` | `/admin/users` | Lists users with optional `role`, `search`, `company_id`, `group_name`, `offset`, and `limit`. |
| `GET` | `/admin/users/search` | Search endpoint for appointing tests to existing users. Searches username, name, surname, email, and group. |
| `POST` | `/admin/users` | Creates one user/student. Can generate a password, optionally assign a practice, and optionally email login/test invitation. |
| `POST` | `/admin/users/bulk` | Bulk creates or reuses students by email, assigns an optional practice, and sends invitations for massive university-style testing. |
| `GET` | `/admin/users/{user_id}` | Reads one user. |
| `GET` | `/admin/companies` | Lists companies with search and pagination. |
| `GET` | `/admin/companies/{company_id}` | Reads one company. |
| `GET` | `/admin/companies/{company_id}/users` | Lists users in a company. |
| `GET` | `/admin/companies/{company_id}/vacancies` | Lists vacancies for a company. |
| `GET` | `/admin/vacancies` | Lists vacancies with optional filters. |
| `POST` | `/admin/vacancies` | Creates a vacancy for the admin's company or a selected company for superadmins. |
| `GET` | `/admin/vacancies/{vacancy_id}` | Reads one vacancy. |
| `PATCH` | `/admin/vacancies/{vacancy_id}` | Updates vacancy fields, including active/closed state. |
| `GET` | `/admin/vacancies/{vacancy_id}/candidates` | Lists candidates for a vacancy. |
| `GET` | `/admin/candidates` | Lists candidates with optional status, vacancy, and search filters. |
| `PATCH` | `/admin/candidates/{candidate_id}/status` | Updates candidate pipeline status. |
| `GET` | `/admin/questions` | Lists question summaries. |
| `POST` | `/admin/questions` | Creates one question with generated or supplied option UUIDs and a correct answer. |
| `POST` | `/admin/questions/bulk` | Creates multiple questions in one request. |
| `GET` | `/admin/questions/{question_id}` | Reads full question details including options and correct answer. |
| `PATCH` | `/admin/questions/{question_id}` | Updates question text, options, correct answer, category, points, or difficulty. |
| `PATCH` | `/admin/questions/{question_id}/difficulty` | Manually updates difficulty and writes `QuestionHistory`. |
| `GET` | `/admin/questions/{question_id}/history` | Lists difficulty history for a question. |
| `GET` | `/admin/practices` | Lists practices. |
| `POST` | `/admin/practices` | Creates an assessment/practice after validating that all referenced questions exist. |
| `GET` | `/admin/practices/{practice_id}` | Reads one practice. |
| `GET` | `/admin/practices/{practice_id}/questions` | Lists questions inside a practice. |
| `PATCH` | `/admin/practices/{practice_id}` | Updates practice fields. |
| `GET` | `/admin/practices/{practice_id}/assignments` | Lists assignments for a practice. |
| `PATCH` | `/admin/practices/{practice_id}/assignments` | Adds/removes assignments by user IDs and/or group names. Can send invitations to newly added users. |
| `POST` | `/admin/practices/{practice_id}/invitations` | Sends or resends invitations to already assigned users by IDs, groups, or all pending assignees. |
| `GET` | `/admin/test-sessions` | Lists test sessions with filters. |
| `GET` | `/admin/test-sessions/{session_id}` | Reads one test session. |
| `GET` | `/admin/test-sessions/{session_id}/answers` | Lists submitted answers in a session. |
| `GET` | `/admin/test-sessions/{session_id}/events` | Anti-cheat event log + IP/UA/device fingerprint captured at session start. |

#### Creating A Question

Use `correct_option_index` when the client does not want to generate option IDs itself:

```json
{
  "text": "Which SQL clause filters rows?",
  "category": "SQL",
  "points": 5,
  "difficulty_level": 0.4,
  "options": [
    { "text": "ORDER BY" },
    { "text": "WHERE" },
    { "text": "GROUP BY" }
  ],
  "correct_option_index": 1
}
```

The backend stores options as JSON objects with UUIDs and stores `correct_answer` as the UUID of the correct option. That keeps websocket answer checking deterministic.

#### Bulk Student Invitation

`POST /admin/users/bulk` supports the university use case: create many student accounts, assign them to an assessment, and email credentials in one operation.

```json
{
  "practice_id": "practice-uuid",
  "send_invitation": true,
  "frontend_test_base_url": "https://ai-talent-flow.vercel.app/test",
  "group_name": "CS-2026-A",
  "users": [
    {
      "name": "Ali",
      "surname": "Karimov",
      "age": 19,
      "email": "ali@example.edu"
    },
    {
      "name": "Malika",
      "surname": "Rasulova",
      "age": 20,
      "email": "malika@example.edu"
    }
  ]
}
```

The response returns generated usernames and passwords once, plus invitation delivery status. If SMTP is not configured, users and assignments are still created, and the response reports the email failure.

#### Assignment Security

Tests are invitation-only. The candidate assignment list only returns practices where a `practice_assignments` row exists for the current user. `POST /testing/practices/{id}/sessions` returns `403` if the user has no `PracticeAssignment` for the practice. The result endpoint also returns `403` for non-invited users.

## AI Services (Resume Review + Interview)

The candidate portal calls out to OpenAI for two features. The transport
lives in `utils/ai.py` (raw HTTP, no SDK dependency). Both features
**degrade gracefully**: if `OPENAI_API_KEY` is unset they fall back to
heuristic behavior so the endpoints still respond.

**Environment variables (all read at request time, so a hot-reload
isn't needed):**

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | (unset) | Required to enable AI. When empty: resume review returns the heuristic review, AI interview returns 503. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for an Azure / proxy / self-hosted deployment. |
| `OPENAI_INTERVIEW_MODEL` | `gpt-4o-mini` | Model used for the interview chat. |
| `OPENAI_RESUME_MODEL` | `gpt-4o-mini` | Model used for resume review. |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Per-request HTTP timeout. |

The key is **only ever read on the backend**. The frontend never sees
it.

### AI Interview (`/candidate/portal/ai-interview/*`)

Conversation-style mock interview. The interviewer is a GPT system
prompt scoped to the student-supplied role; the grader is a separate
prompt that produces a strict JSON evaluation with strengths,
improvements, summary, score `0..100`, and a per-skill breakdown.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Reports `configured` and `model`. |
| GET | `/sessions` | Lists the user's interview sessions. |
| POST | `/sessions` | Starts a new interview. Body: `{ "role": str, "context": str? }`. Returns the session with the interviewer's opening question already inserted. |
| GET | `/sessions/{id}` | Returns the session including the full transcript. |
| POST | `/sessions/{id}/messages` | Sends the candidate's reply and returns the interviewer's next message. |
| POST | `/sessions/{id}/finish` | Asks the grader to evaluate the transcript and finalizes the session with `final_score` + `final_feedback`. |

The schema is in `database/models.py` (`AIInterviewSession`,
`AIInterviewMessage`) and the migration is
`alembic/versions/20260522_add_ai_interview_tables.py`.

### AI Resume Review

`POST /candidate/portal/resume-reviews` now routes through
`utils/ai.py`:

1. Extract text from the uploaded PDF (`pypdf`).
2. If `OPENAI_API_KEY` is set, send the text to the resume reviewer
   prompt and parse strict JSON back.
3. If the call fails or the key is missing, fall back to the original
   heuristic reviewer.

`/resume-reviews/latest` returns the most recent review.

## Resume AI Prototype (Gemini, legacy)

`schemas/ai_resume_reviewer.py` and `test.py` use Google Generative AI:

```python
genai.GenerativeModel("gemini-2.5-flash").generate_content(...)
```

The intended prompt asks Gemini to compare a job description and resume text and return strict JSON:

- `overall_match_score`
- `advantages`
- `disadvantages`
- `education`
- `experience`
- `skills_summary`
- `skills_match`

At the moment this is a standalone prototype. The API route `/vacancies/resume-uploads` extracts PDF text but does not pass that text into the Gemini reviewer or persist AI results on `Candidate`.

## Deployment Notes

### CORS

`main.py` currently allows:

- `http://localhost:3000`
- `http://localhost:5173`
- `https://hr-assistant-j2u1.vercel.app`
- `https://ai-talent-flow.vercel.app`

Add the production frontend domain before shipping a new client. If cookies are used across domains, keep `allow_credentials=True` and configure cookie security correctly.

### Cookies

Login currently sets:

```python
httponly=True
secure=False
samesite="lax"
```

For HTTPS production, use `secure=True`. If frontend and API are on different sites and cookies must be sent cross-site, review `SameSite=None; Secure` requirements.

### Passenger / cPanel

`passenger_wsgi.py` wraps the FastAPI ASGI app with `a2wsgi.ASGIMiddleware`. If this deployment path is used, install `a2wsgi` and update the hardcoded virtualenv path to match the server.

## Current Implementation Notes

These are not README theory; they come from the checked-in code:

- Real-looking credentials are committed in `database/database.py`, `alembic.ini`, `routers/email.py`, `auth/jwt_handler.py`, `schemas/ai_resume_reviewer.py`, and `test.py`. Rotate them before any public or production use.
- `/users` in `main.py` lists all users without authentication.
- `/vacancies/resume-uploads` writes uploaded PDFs into the project root and checks file type after saving. Validate before saving and use a dedicated upload directory.
- `routers/email.py` contains legacy schema and seed helpers referencing `user_profile`, `userid`, `is_verified`, and `StartedTest`, which do not match the current models.
- Importing `routers/email.py` runs `Base.metadata.create_all(bind=engine)`. Schema creation during router import can surprise deployments; migrations are safer.
- `alembic/versions/81a408e504ad_apply_latest_schema_changes.py` does not match the current `Practice` model.
- `test.db` contains an older SQLite schema with `started_test` and `user_profile`; it should not be treated as the current schema.
- `requirements.txt` is missing packages used by optional/prototype files: `google-generativeai` and `a2wsgi`.
- `schemas/ai_resume_reviewer.py` currently calls `generate_response(...)` with an argument even though its function definition accepts no arguments.
- Practices and questions still do not have `created_by` or `company_id` ownership columns. Admin scoping is enforced where the current schema supports it, but assessment ownership should be added in the next schema migration.
- `__pycache__` files and sample personal artifacts are committed. Consider removing generated files and sensitive samples from version control.

## Production Hardening Checklist

- Move every secret into environment variables.
- Rotate all committed database, SMTP, Gemini, and JWT credentials.
- Add `.env` to `.gitignore`.
- Protect `/users` and resume upload endpoints.
- Make cookies secure in production.
- Replace in-memory email verification codes with Redis or a database table.
- Add ownership columns for practices and questions so admin-created assessments are fully scoped.
- Align Alembic migrations with the current models.
- Remove generated `__pycache__`, local DB files, and private sample documents from the repository.
- Add integration tests for login, protected routes, admin role checks, assignment creation, websocket scoring, and test completion.

## Minimal Smoke Test

Run the app:

```bash
uvicorn main:app --reload
```

Check health:

```bash
curl http://127.0.0.1:8000/health/ping
```

Expected:

```json
{
  "message": "pong"
}
```

Login:

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=1234"
```

Use the returned `access_token` for protected endpoints:

```bash
curl "http://127.0.0.1:8000/users/me" \
  -H "Authorization: Bearer <access_token>"
```

For testing the assessment flow, create or seed a practice, assign it to the user, log in, then run through the HTTP session lifecycle:

```bash
# 1. Create a session
curl -X POST "http://127.0.0.1:8000/testing/practices/<practice_uuid>/sessions" \
  -H "Authorization: Bearer <access_token>"

# 2. Fetch the next question
curl "http://127.0.0.1:8000/testing/sessions/<session_uuid>/next-question" \
  -H "Authorization: Bearer <access_token>"

# 3. Submit an answer
curl -X POST "http://127.0.0.1:8000/testing/sessions/<session_uuid>/answers" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question_id":"<question_uuid>","user_answer":"<option_uuid>","time_spent":12.0}'
```

See the **HTTP Testing Protocol** section above for the full state machine.
