# NL2SQL Clinic - Production Grade Natural Language to SQL System

## Assignment Information

| Field           | Value                                   |
| --------------- | --------------------------------------- |
| Assignment      | AI/ML Developer Intern - Round 1        |
| LLM Provider    | Groq (llama-3.3-70b-versatile)          |
| Framework       | FastAPI + SQLite + Vanna 2.0            |
| Decision Engine | Ibtcode (Intent-Based Transaction Code) |
| Version         | 5.0.0                                   |

---

## Overview

NL2SQL Clinic is a production-ready system that converts natural language queries into SQL and executes them on a clinical database.

Users can ask questions in plain English and receive structured results without writing SQL.

The system integrates a **decision layer (Ibtcode)** that ensures:

* Safety
* Validation
* Risk control
* Auditability

---

## Architecture

The system follows a layered architecture with **Ibtcode acting as the security and decision layer** between user input and the LLM.

### Flow Overview

```
User Input
│
▼
FastAPI Gateway
├── Rate Limiting (30 req/min per IP)
├── Input Validation (length, content)
└── CORS Middleware
│
▼
Ibtcode Decision Layer
├── Profanity Detection
├── Dangerous Keyword Handling (DROP, DELETE, etc.)
├── SQL Injection Detection
├── Intent Classification
└── Risk Assessment (LOW, MEDIUM, HIGH, CRITICAL)
│
▼
Cache Layer (TTL-based)
│
▼
LLM Layer (Groq llama-3.3-70b-versatile)
│
▼
SQL Validation Layer
├── SELECT-only enforcement (default)
├── Dangerous operation control
└── Sensitive column detection (phone, email, etc.)
│
▼
SQLite Database Execution
│
▼
Audit Logging (JSON format)
│
▼
JSON Response
```

---

## Why Ibtcode

Traditional LLM-based systems directly trust the model.

### Problems:

* Unsafe SQL generation (DROP, DELETE, UPDATE)
* No sensitive data protection
* No audit trail
* No risk awareness

### Solution (Ibtcode):

| Feature                   | LLM Only | With Ibtcode |
| ------------------------- | -------- | ------------ |
| Dangerous keyword control | ❌        | ✅            |
| Profanity filtering       | ❌        | ✅            |
| SQL injection protection  | ❌        | ✅            |
| Sensitive data protection | ❌        | ✅            |
| Audit logging             | ❌        | ✅            |
| Risk classification       | ❌        | ✅            |

---

## Key Features

### Core

* Natural Language → SQL conversion
* SQLite database execution
* Structured JSON response

### Performance

* Query caching (TTL-based)
* Rate limiting (per IP)
* Optimized LLM usage

### Security

* Input validation
* SQL validation
* Sensitive data protection
* Confirmation system for risky queries

---

## API Endpoints

### POST /chat

```json
{
  "question": "How many patients do we have?"
}
```

Response:

```json
{
  "question": "...",
  "message": "Found 1 result(s).",
  "sql_query": "...",
  "rows": [...],
  "intent": "PATIENT_QUERY",
  "risk": "LOW"
}
```

---

### POST /confirm

```json
{
  "confirm": true
}
```

Used to confirm execution of sensitive queries.

---

### GET /health

Returns system status.

---

### GET /logs

Returns audit logs.

---

## Project Structure

```
nl2sql_clinic/
│
├── main.py
├── vanna_setup.py
├── validators.py
├── cache.py
├── rate_limiter.py
├── logger_config.py
│
├── ibtcode/
│   ├── validation.py
│   ├── perception.py
│   ├── context.py
│   ├── router.py
│   ├── audit.py
│   ├── engine.py
│   └── actions.py
│
├── setup_database.py
├── seed_memory.py
├── requirements.txt
├── .env.example
├── clinic.db
└── README.md
```

---

## Setup Instructions

### 1. Clone Repository

```
git clone <repo-url>
cd nl2sql_clinic
```

---

### 2. Create Virtual Environment

```
python -m venv venv
venv\Scripts\activate
```

---

### 3. Install Dependencies

```
pip install -r requirements.txt
```

---

### 4. Configure Environment

Create `.env` file:

```
GROQ_API_KEY=your_api_key
DB_PATH=./clinic.db
```

---

### 5. Setup Database

```
python setup_database.py
```

---

### 6. Run Server

```
uvicorn main:app --reload
```

Open API docs:

```
http://localhost:8000/docs
```

---

### 7. Run UI (Optional)

```
streamlit run ui_streamlit.py
```

---

## Example Queries

| Query               | Behavior              |
| ------------------- | --------------------- |
| How many patients?  | Count query           |
| List doctors        | Table output          |
| Show revenue        | Aggregation           |
| Show phone numbers  | Confirmation required |
| DROP TABLE patients | Blocked               |

---

## Security Features

* Dangerous keyword detection
* SQL injection detection
* Sensitive data confirmation
* Audit logging
* Rate limiting

---

## Performance

| Operation  | Latency    |
| ---------- | ---------- |
| Cache hit  | 3-5 ms     |
| LLM query  | 200-800 ms |
| Validation | ~5 ms      |

---

## Conclusion

This system demonstrates how to build a **safe, scalable, and production-ready NL2SQL application**.

It goes beyond simple LLM usage by introducing:

* Decision intelligence
* Safety layers
* Controlled execution

---

## One-Line Summary

A **decision-driven NL2SQL system** that combines LLM capabilities with safety, control, and real-world reliability.
