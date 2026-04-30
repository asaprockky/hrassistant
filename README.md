# HR Assistant API

Base URL: `/api/v1`

## Health

| Method | URL | Description |
| --- | --- | --- |
| GET | `/health/ping` | Check API availability. |

## Authentication

| Method | URL | Description |
| --- | --- | --- |
| POST | `/auth/login` | Sign in and receive an access token. |
| POST | `/auth/register` | Create a user account. |

## Users

| Method | URL | Description |
| --- | --- | --- |
| GET | `/users` | List users. |
| GET | `/users/me` | Get the authenticated user's profile. |
| GET | `/users/me/activity` | Get the authenticated user's test activity. |
| POST | `/users/me/email/verification-code` | Send an email verification code. |
| POST | `/users/me/email/verification` | Confirm the email verification code. |

## Vacancies

| Method | URL | Description |
| --- | --- | --- |
| GET | `/vacancies` | List vacancies for the authenticated user's company. |
| POST | `/vacancies` | Create a vacancy for the authenticated user's company. |
| POST | `/vacancies/resume-uploads` | Upload and process a resume PDF. |

## Candidate Dashboard

| Method | URL | Description |
| --- | --- | --- |
| GET | `/candidate/dashboard/pipeline` | Get candidate pipeline statistics. |
| GET | `/candidate/dashboard/applications/recent` | Get paginated recent applications. |

## Admin

| Method | URL | Description |
| --- | --- | --- |
| GET | `/admin/questions` | Filter questions by category. |
| POST | `/admin/practices` | Create a practice assessment. |
| PATCH | `/admin/practices/{practice_id}/assignments` | Add or remove users from a practice. |

## Testing

| Method | URL | Description |
| --- | --- | --- |
| WS | `/testing/practices/{practice_id}/ws` | Live testing WebSocket. |
| GET | `/testing/practices/{practice_id}/result` | Get the authenticated user's result for a practice. |
| GET | `/testing/assignments/{filter_option}` | Get assigned practices by filter (`latest`, `all`, or a numeric limit). |
| GET | `/testing/sessions/active` | List active test sessions. |
| GET | `/testing/sessions/completed` | List completed test sessions. |
