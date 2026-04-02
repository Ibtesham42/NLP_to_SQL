# NL2SQL Clinic — AI-Powered Natural Language to SQL

> **Assignment:** AI/ML Developer Intern — Round 1  
> **LLM Provider:** Groq (`llama-3.3-70b-versatile`)  
> **Framework:** Vanna 2.0 + FastAPI + SQLite

---

## Overview

This system lets users ask questions about a clinic management database in plain English and
receive SQL results, data tables, and Plotly charts — without writing a single line of SQL.

```
User Question (English)
        │
        ▼
   FastAPI Backend  (main.py)
        │   ├── Input Validation     (validators.py)
        │   ├── Rate Limiting        (rate_limiter.py)
        │   └── Query Cache          (cache.py)
        ▼
   Vanna 2.0 Agent  (vanna_setup.py)
        │   ├── LLM: Groq llama-3.3-70b-versatile
        │   ├── Memory: DemoAgentMemory (20 seeds)
        │   └── Tools: RunSqlTool + VisualizeDataTool
        ▼
   SQL Validator    (validators.py)
        ▼
   SQLite Database  (clinic.db)
        ▼
   Structured JSON Response
   { message, sql_query, columns, rows, row_count, chart }
```

---

## Project Structure

```
nl2sql_clinic/
├── setup_database.py   # Step 1+2 — Create schema + insert 200p/15d/500a dummy data
├── vanna_setup.py      # Vanna 2.0 Agent factory (Groq LLM + SQLite)
├── seed_memory.py      # Pre-seed 20 Q→SQL pairs into DemoAgentMemory
├── main.py             # FastAPI application (chat + health endpoints)
├── validators.py       # SQL safety validator + question input validator
├── cache.py            # In-memory TTL query cache
├── rate_limiter.py     # Sliding-window rate limiter
├── logger_config.py    # Structured logging
├── requirements.txt    # All dependencies
├── .env.example        # Environment variable template
├── .gitignore
├── README.md           # This file
├── RESULTS.md          # 20-question test results
└── logs/               # Log files (auto-created)
```

---

## Quick Start

### 1. Clone & Enter Directory

```bash
git clone <your-repo-url>
cd nl2sql_clinic
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
# Get a free key at https://console.groq.com
```

Your `.env` should look like:
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
DB_PATH=./clinic.db
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
```

### 5. Create the Database

```bash
python setup_database.py
```

Expected output:
```
Database created: /path/to/clinic.db
  Patients     : 200
  Doctors      : 15
  Appointments : 500
  Treatments   : ~350
  Invoices     : 300
```

### 6. Seed Agent Memory

```bash
python seed_memory.py
```

This pre-loads 20 high-quality Q→SQL pairs so the agent starts smart.

### 7. Start the API Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the one-liner from the assignment spec:

```bash
pip install -r requirements.txt && python setup_database.py \
  && python seed_memory.py && uvicorn main:app --port 8000
```

---

## API Documentation

### `POST /chat`

Ask a natural language question.

**Request:**
```json
{
  "question": "Show me the top 5 patients by total spending"
}
```

**Response:**
```json
{
  "question":   "Show me the top 5 patients by total spending",
  "message":    "Here are the top 5 patients by total spending...",
  "sql_query":  "SELECT p.first_name || ' ' || p.last_name AS patient, ...",
  "columns":    ["patient", "city", "total_spending"],
  "rows":       [["Arjun Sharma", "Mumbai", 9800.00]],
  "row_count":  5,
  "chart":      { "data": [...], "layout": {...} },
  "chart_type": "bar",
  "cached":     false,
  "latency_ms": 1243
}
```

**Curl example:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many patients do we have?"}'
```

---

### `GET /health`

System status check.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 20,
  "cache_size": 3,
  "version": "1.0.0"
}
```

---

### `DELETE /cache`

Clear the query cache.

```bash
curl -X DELETE http://localhost:8000/cache
```

---

## Interactive Docs

FastAPI auto-generates interactive docs:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:**      http://localhost:8000/redoc

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Groq `llama-3.3-70b-versatile` | Free, fast (~500 tokens/sec), excellent at SQL generation |
| Vanna 2.0 Agent (not 0.x) | Assignment requirement; cleaner tool-based architecture |
| `DemoAgentMemory` | In-memory, no ChromaDB needed, perfect for assignment scope |
| SQL allow-list validation | Rejects anything that isn't a SELECT; prevents injection |
| In-memory TTL cache | Avoids redundant LLM calls for repeated questions |
| Sliding-window rate limiter | 30 req/min per IP to prevent abuse |
| Schema injected as system prompt | Gives LLM full context without RAG overhead |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Groq API key |
| `DB_PATH` | `./clinic.db` | SQLite database path |
| `APP_HOST` | `0.0.0.0` | Server bind host |
| `APP_PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CACHE_TTL_SECONDS` | `300` | Cache entry lifetime |
| `RATE_LIMIT_PER_MINUTE` | `30` | Max requests per IP per minute |

---

## Security Notes

- **No API keys are hardcoded** — all via `.env`
- **SQL validation** rejects INSERT/UPDATE/DELETE/DROP/ALTER and dangerous patterns
- **Rate limiting** prevents abuse
- **Input validation** rejects empty, too-short, or too-long questions

---

## Troubleshooting

**`GROQ_API_KEY not set`**  
→ Copy `.env.example` to `.env` and add your key from https://console.groq.com

**`ModuleNotFoundError: vanna`**  
→ Make sure you activated the venv: `source venv/bin/activate`

**`clinic.db not found`**  
→ Run `python setup_database.py` first

**Agent returns no SQL**  
→ Check logs in `logs/` — the LLM may have rate-limited or returned a non-SQL response
