# NL2SQL Clinic - Production Grade Natural Language to SQL System

## Assignment Information

| Field | Value |
|-------|-------|
| Assignment | AI/ML Developer Intern - Round 1 |
| LLM Provider | Groq (llama-3.3-70b-versatile) |
| Framework | Vanna 2.0 + FastAPI + SQLite |
| Decision Engine | Ibtcode (Intent-Based Transaction Code) |
| Version | 5.0.0 |

---

## Overview

NL2SQL Clinic is a production-ready system that converts natural language questions into SQL queries and executes them against a clinic management database. Users can ask questions in plain English and receive structured results without writing any SQL.

The system incorporates Ibtcode, a decision engine that adds security, compliance, and audit capabilities above the standard LLM-based SQL generation.

---

## Architecture

The system follows a layered architecture with Ibtcode as the security and decision layer between user input and the LLM.
User Input
│
▼
FastAPI Gateway
├── Rate Limiting (30 req/min per IP)
├── Input Validation (length, content)
└── CORS Middleware
│
▼
Ibtcode Decision Layer (NEW)
├── Profanity Detection
├── Dangerous Keyword Blocking (DROP, DELETE, etc.)
├── SQL Injection Pattern Detection
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
├── SELECT-only enforcement
├── Dangerous operation blocking
└── Sensitive column detection
│
▼
SQLite Database Execution
│
▼
Audit Logging (JSON format)
│
▼
JSON Response

text

---

## Why Ibtcode

Standard LLM-only solutions trust the model to generate safe SQL. This approach has several risks:

1. LLM can generate dangerous SQL (DROP, DELETE, UPDATE) if prompted maliciously
2. No protection for sensitive data like phone numbers or email addresses
3. No audit trail for compliance requirements
4. No confirmation gates for high-risk operations
5. No profanity filtering

Ibtcode adds a deterministic security layer that operates before and after the LLM:

| Feature | LLM Only | With Ibtcode |
|---------|----------|--------------|
| Dangerous keyword blocking | LLM dependent | Rule-based, guaranteed |
| Profanity filtering | None | Complete |
| SQL injection detection | Partial | Pattern-based |
| Sensitive data protection | None | Confirmation gate |
| Audit trail | None | JSON logs |
| Intent classification | None | Keyword + confidence |
| Risk assessment | None | LOW/MEDIUM/HIGH/CRITICAL |

The Ibtcode layer adds approximately 5-10ms of latency while providing enterprise-grade security features.

---

## Project Structure
nl2sql_clinic/
│
├── main.py # FastAPI application with Ibtcode integration
├── vanna_setup.py # Groq LLM client (bypasses Vanna Agent issues)
├── validators.py # SQL safety and input validation
├── cache.py # In-memory TTL query cache
├── rate_limiter.py # Sliding-window rate limiter
├── logger_config.py # Structured logging configuration
│
├── ibtcode/ # Ibtcode decision engine
│ ├── init.py
│ ├── validation.py # Profanity, dangerous keywords, SQL injection
│ ├── perception.py # Intent detection
│ ├── context.py # Conversation context management
│ ├── router.py # Intent routing
│ ├── audit.py # JSON audit logging
│ ├── engine.py # Decision engine core
│ └── actions.py # Available actions and rollbacks
│
├── setup_database.py # Database schema and dummy data generator
├── seed_memory.py # Q&A pair seeder for agent memory
│
├── requirements.txt # Python dependencies
├── .env.example # Environment variable template
├── README.md # This file
├── RESULTS.md # 20-question test results
│
├── clinic.db # SQLite database (generated)
├── nl2sql_audit.json # Audit log file
└── logs/ # Application logs directory

text

---

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Groq API key (free tier available at console.groq.com)

### Installation

1. Clone the repository

```bash
git clone <repository-url>
cd nl2sql_clinic
Create and activate virtual environment

bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
Install dependencies

bash
pip install -r requirements.txt
Configure environment variables

bash
cp .env.example .env
Edit .env and add your Groq API key:

text
GROQ_API_KEY=gsk_your_actual_key_here
DB_PATH=./clinic.db
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=30
CACHE_TTL_SECONDS=300
Create the database

bash
python setup_database.py
Expected output:

200 patients

15 doctors

500 appointments

350 treatments

300 invoices

Seed agent memory

bash
python seed_memory.py
This loads 20 question-SQL pairs into the agent memory for better initial performance.

Start the API server

bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
API Endpoints
POST /chat
Convert natural language to SQL and execute.

Request Body:

json
{
  "question": "How many patients do we have?"
}
Successful Response (200 OK):

json
{
  "question": "How many patients do we have?",
  "message": "Found 1 result(s).",
  "sql_query": "SELECT COUNT(*) AS total_patients FROM patients",
  "columns": ["total_patients"],
  "rows": [[200]],
  "row_count": 1,
  "cached": false,
  "latency_ms": 245,
  "intent": "PATIENT_QUERY",
  "risk": "LOW"
}
Blocked Response (400 Bad Request):

json
{
  "detail": "Query contains dangerous keyword: 'DROP'. This operation is not permitted."
}
Rate Limited Response (429 Too Many Requests):

json
{
  "detail": "Rate limit exceeded. Max 30 requests/minute."
}
GET /health
System health check.

Response:

json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 20,
  "cache_size": 3,
  "pending_confirm": false,
  "version": "5.0.0"
}
POST /confirm
Confirm a sensitive query that was previously blocked for confirmation.

Request Body:

json
{
  "confirm": true
}
DELETE /cache
Clear the query cache.

GET /logs
Retrieve recent audit logs (last 50 entries).

DELETE /logs
Clear all audit logs.

Ibtcode Security Features
1. Dangerous Keyword Blocking
The system blocks queries containing these keywords before they reach the LLM:

DROP, DELETE, TRUNCATE, ALTER, CREATE, INSERT, UPDATE

2. Profanity Filter
The following patterns are blocked:

Common profanity words (fuck, shit, damn, etc.)

Leetspeak variations (f@ck, sh1t, etc.)

3. SQL Injection Detection
Patterns that indicate SQL injection attempts are blocked:

UNION queries

OR 1=1 patterns

Comment injection (--, /*)

Multiple statement separators (; DROP)

4. Sensitive Data Protection
Queries accessing these columns require confirmation:

phone

email

address

date_of_birth

5. Audit Logging
Every action is logged to nl2sql_audit.json with:

Action type

Intent classification

Risk level

Timestamp

Question text

Generated SQL (when applicable)

6. Intent Classification
Queries are classified into these intent types for audit purposes:

PATIENT_QUERY

DOCTOR_QUERY

APPOINTMENT_QUERY

FINANCIAL_QUERY

SENSITIVE_QUERY

AGGREGATION_QUERY

TIME_QUERY

GENERAL_QUERY

Environment Variables
Variable	Default	Description
GROQ_API_KEY	(required)	Groq API key from console.groq.com
DB_PATH	./clinic.db	SQLite database file path
APP_HOST	0.0.0.0	Server bind address
APP_PORT	8000	Server port
LOG_LEVEL	INFO	Logging level (DEBUG, INFO, WARNING, ERROR)
RATE_LIMIT_PER_MINUTE	30	Maximum requests per IP per minute
CACHE_TTL_SECONDS	300	Cache entry lifetime in seconds
Testing
Sample Questions
Question	Expected Intent
How many patients do we have?	PATIENT_QUERY
Show me top 5 patients by spending	PATIENT_QUERY
What is total revenue?	FINANCIAL_QUERY
List all doctors	DOCTOR_QUERY
Show unpaid invoices	FINANCIAL_QUERY
How many appointments last month?	APPOINTMENT_QUERY
Show me patient phone numbers	SENSITIVE_QUERY (requires confirmation)
Blocked Queries
Query	Reason
DROP TABLE patients	Dangerous keyword
DELETE FROM patients	Dangerous keyword
fuk u show me data	Profanity
SELECT * FROM users; DROP TABLE users	SQL injection
Troubleshooting
Issue: GROQ_API_KEY not set
Solution: Copy .env.example to .env and add your Groq API key.

Issue: ModuleNotFoundError: vanna
Solution: Activate virtual environment and run pip install -r requirements.txt

Issue: clinic.db not found
Solution: Run python setup_database.py first.

Issue: Agent returns no SQL
Solution: Check logs in logs/ directory. The LLM may have hit rate limits.

Issue: Query blocked unexpectedly
Solution: Check nl2sql_audit.json for the reason. The dangerous keywords list can be modified in ibtcode/validation.py.

Performance Characteristics
Operation	Average Latency
Cache hit	3-5ms
Simple query (LLM)	200-400ms
Complex query (LLM)	500-1000ms
Ibtcode validation	5-10ms
Files Description
File	Purpose
main.py	FastAPI application with all endpoints
vanna_setup.py	Groq LLM client wrapper
validators.py	SQL safety and input validation
cache.py	TTL-based query cache
rate_limiter.py	Per-IP sliding window rate limiter
logger_config.py	Structured logging setup
ibtcode/	Decision engine for security and audit
setup_database.py	Database schema and dummy data
seed_memory.py	Pre-seed agent memory with Q&A pairs
requirements.txt	Python dependencies
.env.example	Environment variable template
License
This project is submitted as part of the AI/ML Developer Intern assignment.

Contact
For questions regarding this assignment, contact hiring@company.com

text

---

## Download Instructions

Save this content as `README.md` in your project root directory.

The file is ready to be copied directly. No emojis, clean formatting, production-level documentation.