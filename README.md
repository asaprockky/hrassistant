# HR Assistant API

FastAPI backend for TalentFlow-style HR automation: user authentication, company vacancies, resume uploads, candidate dashboards, admin operations, test assignment, live assessment over WebSocket, and adaptive question difficulty.

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

This service is the backend API layer for an HR assistant platform. It stores companies, users, vacancies, candidates, questions, practices, assignments, test sessions, and answers. It also has two AI-adjacent pieces: an adaptive test difficulty recalculation loop inside the live testing websocket, and a prototype Google Gemini resume-review script.

The main application is created in `main.py`. Routers are mounted from `routers/`, database models live in `database/models.py`, authentication helpers live in `auth/jwt_handler.py`, and request/response schemas live in `schemas/user_schema.py`.

## Repository Map

| Path | Purpose |
| --- | --- |
| `main.py` | Creates the FastAPI app, mounts routers, configures CORS, and exposes `/health/ping` plus `/users`. |
| `auth/jwt_handler.py` | Creates and verifies JWT access tokens. |
| `database/database.py` | Builds the SQLAlchemy engine, session factory, base model, and DB dependency. |
| `database/models.py` | SQLAlchemy models for companies, users, vacancies, candidates, questions, practices, assignments, test sessions, and answers. |
| `database/enums.py` | Role enum: `USER`, `ADMIN`, `SUPERADMIN`. |
| `routers/login.py` | Login, registration, password hashing, cookie/header auth, websocket-token auth helpers. |
| `routers/main_page.py` | Vacancy create/list endpoints and PDF resume upload/extraction. |
| `routers/candidate_dashboard.py` | Candidate pipeline summary and recent applications. |
| `routers/admin_panel.py` | Admin dashboard, users, companies, vacancies, candidates, questions, practices, assignments, and test sessions. |
| `routers/questions.py` | Live testing WebSocket plus assignment/result REST endpoints. |
| `routers/tester_main.py` | Candidate test-session lists: active, completed, all. |
| `routers/email.py` | Email verification via Gmail SMTP and legacy seed/schema helper code. |
| `routers/user_profile.py` | Current user's profile and test activity. |
| `routers/user_resumes.py` | Placeholder router; it is not currently mounted in `main.py`. |
| `schemas/ai_resume_reviewer.py` | Prototype Gemini resume-review prompt/script; not mounted as an API route. |
| `utils/ai_logic.py` | Sigmoid-based adaptive difficulty calculation for questions. |
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
  | WS: /testing/practices/{practice_id}/ws?token=<jwt>
  v
FastAPI app in main.py
  |
  +-- Authentication router
  +-- User/profile/email routers
  +-- Vacancy and resume-upload router
  +-- Candidate dashboard router
  +-- Admin router
  +-- Testing websocket/session routers
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
4. Protected HTTP endpoints read the token from either the cookie or `Authorization: Bearer <token>`.
5. The WebSocket endpoint reads the same token from the `token` query parameter because browser websocket constructors cannot reliably set custom authorization headers.

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
| `SMTP_SERVER` | `SMTP_SERVER` in `routers/email.py` | SMTP hostname used to send verification emails. Current code points at Gmail SMTP. | The email verification route needs a mail server to deliver one-time codes. |
| `SMTP_PORT` | `PORT` in `routers/email.py` | SMTP SSL port. Current code uses `465`. | Required to establish the encrypted SMTP connection. |
| `SMTP_LOGIN` | `LOGIN` in `routers/email.py` | Sender mailbox username for SMTP authentication. | Identifies the Gmail account sending verification codes. |
| `SMTP_APP_PASSWORD` | `PASSWORD` in `routers/email.py` | Gmail app password used by the SMTP client. This is not a normal Google password; it is a scoped credential generated from a Google account with 2FA. | Gmail will not allow this app to send mail unless SMTP login succeeds. Rotate this value if it has ever been committed. |
| `SENDER_EMAIL` | `SENDER_EMAIL` in `routers/email.py` | Email address shown in the `From` header. Current code sets it to the SMTP login. | Users need a recognizable sender for verification messages, and SMTP providers often require the sender to match the authenticated account. |
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

Current code does not load this `.env` automatically. To make the configuration above active, update the hardcoded constants to read from `os.getenv(...)` or a settings object before deployment.

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

## WebSocket Testing Protocol

The live assessment flow is built in `routers/questions.py`.

Endpoint:

```text
ws://127.0.0.1:8000/testing/practices/{practice_id}/ws?token=<access_token>
```

Production should use TLS:

```text
wss://api.talentflow.uz/testing/practices/{practice_id}/ws?token=<access_token>
```

### Why The Token Is In The Query String

Browser WebSocket APIs do not let frontend code reliably set arbitrary headers such as `Authorization`. Because of that, the backend reads `token` from the websocket URL query parameter:

```python
token: str = Query(...)
```

The dependency decodes the JWT, loads the user from the database, and rejects the connection with websocket close code `1008` when the token is missing, expired, invalid, or points to a missing user.

Because query strings can appear in logs, production should use `wss://`, avoid logging full websocket URLs, and keep token lifetimes short.

### Lifecycle

1. Client opens the websocket with a valid JWT query token.
2. Backend authenticates the token and accepts the connection.
3. Client sends `start_test`.
4. Backend checks assignment, completion state, existing sessions, practice validity, and deadline.
5. Backend creates a `TestSession` and returns `test_started`.
6. Client repeatedly sends `get_question`.
7. Backend returns the next unanswered question in the order stored in `Practice.question_ids`.
8. Client sends `submit_answer` with the selected option UUID and time spent.
9. Backend stores `UserAnswer`, awards weighted points, updates `TestSession.overall_points`, recalculates question difficulty, and returns `answer_result`.
10. When no questions remain, or the client sends `finish_test`, backend marks the session and assignment complete, sends `test_finished`, and closes the connection.

### Client Example

```js
const token = "<access_token>";
const practiceId = "<practice_uuid>";
const ws = new WebSocket(
  `ws://127.0.0.1:8000/testing/practices/${practiceId}/ws?token=${encodeURIComponent(token)}`
);

ws.onopen = () => {
  ws.send(JSON.stringify({ action: "start_test" }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.event === "test_started") {
    ws.send(JSON.stringify({ action: "get_question" }));
  }

  if (message.event === "question_data") {
    console.log("Render this question:", message);
  }

  if (message.event === "answer_result") {
    ws.send(JSON.stringify({ action: "get_question" }));
  }

  if (message.event === "test_finished") {
    console.log("Final score:", message.final_score);
  }
};
```

### `start_test`

Client sends:

```json
{
  "action": "start_test"
}
```

Backend checks:

- the user has a `PracticeAssignment` for the requested practice;
- the assignment is not already completed;
- the user has not already created a `TestSession` for that practice;
- the practice exists and `is_valid` is true;
- the deadline has not passed.

Success response:

```json
{
  "event": "test_started",
  "session_id": "uuid",
  "quantity": 10,
  "duration": 30
}
```

Possible errors:

```json
{ "error": "Test already completed or not assigned." }
{ "error": "Re-entry is not allowed." }
{ "error": "Practice not found." }
{ "error": "Practice deadline has passed." }
```

### `get_question`

Client sends:

```json
{
  "action": "get_question"
}
```

Success response:

```json
{
  "event": "question_data",
  "id": "question_uuid",
  "text": "Which SQL clause is used to filter records?",
  "options": [
    { "id": "option_uuid_1", "text": "ORDER BY" },
    { "id": "option_uuid_2", "text": "WHERE" }
  ],
  "category": "SQL",
  "points": 5.0
}
```

The correct answer is intentionally not sent in `question_data`.

### `submit_answer`

Client sends:

```json
{
  "action": "submit_answer",
  "question_id": "question_uuid",
  "user_answer": "selected_option_uuid",
  "time_spent": 18.4
}
```

Success response when more questions remain:

```json
{
  "event": "answer_result",
  "is_correct": true,
  "correct_answer": "correct_option_uuid",
  "points_awarded": 12.5,
  "new_difficulty": 0.61
}
```

The scoring formula is:

```text
points_awarded = (question.points / sum(all practice question points)) * 100
```

The adaptive difficulty formula lives in `utils/ai_logic.py`. It combines failure rate and average time spent:

```text
z = (0.8 * failure_rate) + (0.2 * min(avg_time / 60, 1)) - 0.5
difficulty = sigmoid(z)
```

That means the app treats incorrect answers as the strongest signal and time pressure as a secondary signal. Difficulty stays in the `0..1` range.

### `finish_test`

Client sends:

```json
{
  "action": "finish_test"
}
```

Backend response:

```json
{
  "event": "test_finished",
  "final_score": 82.5,
  "message": "Assignment completed and locked."
}
```

After this message, the backend closes the websocket.

### WebSocket Rules To Build The Frontend Around

- All messages are JSON.
- The client must send `start_test` before requesting or submitting questions.
- `session_id` is stored server-side per websocket connection; the client does not need to send it back.
- Re-entry is blocked: one user cannot start a second session for the same practice.
- Completed assignments are locked.
- The server closes the websocket after final completion.
- A browser refresh during the test can leave an unfinished session that blocks re-entry because the current implementation creates the session at start.

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

### Testing

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `WS` | `/testing/practices/{practice_id}/ws?token=<jwt>` | User via query token | Live assessment loop. |
| `GET` | `/testing/practices/{practice_id}/result` | User | Returns the current user's score and finish state for a practice. |
| `GET` | `/testing/assignments/{filter_option}` | User | Lists available assignments. `filter_option` can be `latest`, `all`, or a numeric limit. |
| `GET` | `/testing/sessions/active?page=1&size=10` | User | Paginated active test sessions. |
| `GET` | `/testing/sessions/completed?page=1&size=10` | User | Paginated completed test sessions. |
| `GET` | `/testing/sessions/all?page=1&size=10` | User | Paginated active and completed test sessions. |

### Admin

All admin routes require a user whose role is `ADMIN` or `SUPERADMIN`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/admin/dashboard/summary` | Counts users, candidates, vacancies, practices, questions, active/completed sessions, and average score. |
| `GET` | `/admin/users` | Lists users with optional `role`, `search`, `company_id`, `offset`, and `limit`. |
| `GET` | `/admin/users/{user_id}` | Reads one user. |
| `GET` | `/admin/companies` | Lists companies with search and pagination. |
| `GET` | `/admin/companies/{company_id}` | Reads one company. |
| `GET` | `/admin/companies/{company_id}/users` | Lists users in a company. |
| `GET` | `/admin/companies/{company_id}/vacancies` | Lists vacancies for a company. |
| `GET` | `/admin/vacancies` | Lists vacancies with optional filters. |
| `GET` | `/admin/vacancies/{vacancy_id}` | Reads one vacancy. |
| `GET` | `/admin/vacancies/{vacancy_id}/candidates` | Lists candidates for a vacancy. |
| `GET` | `/admin/candidates` | Lists candidates with optional status, vacancy, and search filters. |
| `PATCH` | `/admin/candidates/{candidate_id}/status` | Updates candidate pipeline status. |
| `GET` | `/admin/questions` | Lists question summaries. |
| `GET` | `/admin/questions/{question_id}` | Reads full question details including options and correct answer. |
| `PATCH` | `/admin/questions/{question_id}/difficulty` | Manually updates difficulty and writes `QuestionHistory`. |
| `GET` | `/admin/questions/{question_id}/history` | Lists difficulty history for a question. |
| `GET` | `/admin/practices` | Lists practices. |
| `POST` | `/admin/practices` | Intended to create a practice. Current implementation has issues listed below. |
| `GET` | `/admin/practices/{practice_id}` | Reads one practice. |
| `GET` | `/admin/practices/{practice_id}/questions` | Lists questions inside a practice. |
| `PATCH` | `/admin/practices/{practice_id}` | Updates practice fields. |
| `GET` | `/admin/practices/{practice_id}/assignments` | Lists assignments for a practice. |
| `PATCH` | `/admin/practices/{practice_id}/assignments` | Adds/removes assignments by user IDs and/or group names. |
| `GET` | `/admin/test-sessions` | Lists test sessions with filters. |
| `GET` | `/admin/test-sessions/{session_id}` | Reads one test session. |
| `GET` | `/admin/test-sessions/{session_id}/answers` | Lists submitted answers in a session. |

## Resume AI Prototype

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
- `routers/admin_panel.py` `POST /admin/practices` creates a `Practice`, then references undefined names `data` and `generate_unique_username`, and returns candidate-user fields instead of practice fields. This endpoint needs repair before use.
- `routers/email.py` contains legacy schema and seed helpers referencing `user_profile`, `userid`, `is_verified`, and `StartedTest`, which do not match the current models.
- Importing `routers/email.py` runs `Base.metadata.create_all(bind=engine)`. Schema creation during router import can surprise deployments; migrations are safer.
- `alembic/versions/81a408e504ad_apply_latest_schema_changes.py` does not match the current `Practice` model.
- `test.db` contains an older SQLite schema with `started_test` and `user_profile`; it should not be treated as the current schema.
- `requirements.txt` is missing packages used by optional/prototype files: `google-generativeai` and `a2wsgi`.
- `schemas/ai_resume_reviewer.py` currently calls `generate_response(...)` with an argument even though its function definition accepts no arguments.
- `__pycache__` files and sample personal artifacts are committed. Consider removing generated files and sensitive samples from version control.

## Production Hardening Checklist

- Move every secret into environment variables.
- Rotate all committed database, SMTP, Gemini, and JWT credentials.
- Add `.env` to `.gitignore`.
- Protect `/users` and resume upload endpoints.
- Make cookies secure in production.
- Replace in-memory email verification codes with Redis or a database table.
- Repair `POST /admin/practices`.
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

For websocket testing, create or seed a practice, assign it to the user, log in, then connect to:

```text
ws://127.0.0.1:8000/testing/practices/{practice_id}/ws?token=<access_token>
```
