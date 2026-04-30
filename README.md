# HR Assistant Routes

Base URL: `https://api.talentflow.uz`

## 1. Health

| Method | URL |
| --- | --- |
| GET | `/health/ping` |

## 2. Authentication

| Method | URL |
| --- | --- |
| POST | `/auth/login` |
| POST | `/auth/register` |

## 3. Users

| Method | URL |
| --- | --- |
| GET | `/users` |
| GET | `/users/me` |
| GET | `/users/me/activity` |
| POST | `/users/me/email/verification-code` |
| POST | `/users/me/email/verification` |

## 4. Vacancies

| Method | URL |
| --- | --- |
| GET | `/vacancies` |
| POST | `/vacancies` |
| POST | `/vacancies/resume-uploads` |

## 5. Candidate Dashboard

| Method | URL |
| --- | --- |
| GET | `/candidate/dashboard/pipeline` |
| GET | `/candidate/dashboard/applications/recent` |

## 6. Admin

| Method | URL |
| --- | --- |
| GET | `/admin/questions` |
| POST | `/admin/practices` |
| PATCH | `/admin/practices/{practice_id}/assignments` |

## 7. Testing

| Method | URL |
| --- | --- |
| WS | `/testing/practices/{practice_id}/ws` |
| GET | `/testing/practices/{practice_id}/result` |
| GET | `/testing/assignments/{filter_option}` |
| GET | `/testing/sessions/active` |
| GET | `/testing/sessions/completed` |
