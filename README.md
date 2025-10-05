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
