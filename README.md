```markdown
## 📡 API Routes

### 🔐 POST `/login`
**Authentication:** Not required  
**Request:**
```json
{
  "username": "abdulfayiz",
  "password": "123456"
}
```
**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ1c2VybmFtZSI6IkFiZHVsZmF5aXoiLCJleHAiOjE3NTk2Nzc4OTV9.olrtIYz5f6b00-7ewIJum2AXY1K137IosbmH8nmsMaE",
  "token_type": "bearer",
  "user_role": "admin"
}
```

### 👤 GET `/users` 
**Authentication:** Required (Bearer Token)  
**Headers:**
```
Authorization: Bearer <your_token>
```
**Response:**
```json
[
  {
    "id": 1,
    "password": "hashedpassword",
    "username": "Abdulfayiz",
    "role": "admin",
    "company_id": 1
  }
]
```

---


### 🔐 POST `/create_job/vacancies/create`
**Authentication:** Not required  
**Request:**
```json
{
  "id": 2,
  "company_id": 1,
  "job_name": "Frontend Developer",
  "job_description": "Develop responsive web interfaces using React and Tailwind CSS.",
  "tag": "React",
  "start_date": "2025-10-10",
  "end_date": "2025-11-10"
}


```
**Response:**
 content-length: 203 
 content-type: application/json 
 date: Tue,07 Oct 2025 06:40:53 GMT 
 server: uvicorn 
```
