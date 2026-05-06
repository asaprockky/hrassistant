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
| GET | `/admin/dashboard/summary` |
| GET | `/admin/users` |
| GET | `/admin/users/{user_id}` |
| GET | `/admin/companies` |
| GET | `/admin/companies/{company_id}` |
| GET | `/admin/companies/{company_id}/users` |
| GET | `/admin/companies/{company_id}/vacancies` |
| GET | `/admin/vacancies` |
| GET | `/admin/vacancies/{vacancy_id}` |
| GET | `/admin/vacancies/{vacancy_id}/candidates` |
| GET | `/admin/candidates` |
| PATCH | `/admin/candidates/{candidate_id}/status` |
| GET | `/admin/questions` |
| GET | `/admin/questions/{question_id}` |
| PATCH | `/admin/questions/{question_id}/difficulty` |
| GET | `/admin/questions/{question_id}/history` |
| GET | `/admin/practices` |
| POST | `/admin/practices` |
| GET | `/admin/practices/{practice_id}` |
| GET | `/admin/practices/{practice_id}/questions` |
| PATCH | `/admin/practices/{practice_id}` |
| GET | `/admin/practices/{practice_id}/assignments` |
| PATCH | `/admin/practices/{practice_id}/assignments` |
| GET | `/admin/test-sessions` |
| GET | `/admin/test-sessions/{session_id}` |
| GET | `/admin/test-sessions/{session_id}/answers` |

## 7. Testing

| Method | URL |
| --- | --- |
| WS | `/testing/practices/{practice_id}/ws` |
| GET | `/testing/practices/{practice_id}/result` |
| GET | `/testing/assignments/{filter_option}` |
| GET | `/testing/sessions/active` |
| GET | `/testing/sessions/completed` |
