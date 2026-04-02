#!/usr/bin/env python3
"""
NL2SQL Clinic — FastAPI Application

HOW IT WORKS NOW:
  1. Request comes in via POST /chat
  2. Rate limit + input validation
  3. Cache check
  4. GroqDirectClient.generate_sql(question) → SQL string from Groq LLM
  5. SQL safety validation
  6. Execute SQL against clinic.db
  7. Return structured JSON response

  If Groq fails for any reason, the rule-based fallback kicks in.

Start:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

load_dotenv()

from cache import query_cache
from logger_config import logger
from rate_limiter import rate_limiter
from validators import validate_question, validate_sql
from vanna_setup import get_agent   # returns GroqDirectClient


# ── App Lifecycle ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NL2SQL Clinic API...")
    get_agent()          # warm up — creates the singleton
    logger.info("Agent ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="NL2SQL Clinic API",
    description="Natural Language to SQL for the Clinic Management System",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, max_length=500,
        example="Show me the top 5 patients by total spending",
    )

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


class ChartData(BaseModel):
    data: list[Any]
    layout: dict[str, Any]


class ChatResponse(BaseModel):
    question:   str
    message:    str
    sql_query:  str | None = None
    columns:    list[str] | None = None
    rows:       list[list[Any]] | None = None
    row_count:  int | None = None
    chart:      ChartData | None = None
    chart_type: str | None = None
    cached:     bool = False
    latency_ms: int = 0


class HealthResponse(BaseModel):
    status:             str
    database:           str
    agent_memory_items: int
    cache_size:         int
    version:            str = "3.0.0"


# ── Database Helpers ───────────────────────────────────────────────────────────

def _db_path() -> str:
    return os.getenv("DB_PATH", "./clinic.db")


def _check_db() -> str:
    try:
        conn = sqlite3.connect(_db_path())
        conn.execute("SELECT 1")
        conn.close()
        return "connected"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return "error"


def _execute_sql(
    sql: str,
) -> tuple[Optional[List[str]], Optional[List[list]], int]:
    """Execute a SELECT query and return (columns, rows, row_count)."""
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows:
            columns = [d[0] for d in cursor.description]
            data = [list(row) for row in rows]
            conn.close()
            return columns, data, len(rows)
        conn.close()
        return None, None, 0
    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return None, None, 0


# ── Fallback SQL Generation ────────────────────────────────────────────────────
# Only called when Groq itself fails (network error, rate limit, etc.)

async def _fallback_sql_generation(question: str) -> Dict[str, Any]:
    """Rule-based SQL — last resort when Groq is unavailable."""
    logger.warning("[FALLBACK] Groq unavailable — using rule-based SQL generation.")

    q = question.lower()

    # ── Patient queries ───────────────────────────────────────────────────────
    if re.search(r"how many patients|total patients|patient count", q):
        sql = "SELECT COUNT(*) AS total_patients FROM patients"

    elif re.search(r"(list|show|all|get) ?(all )?patients", q) and "city" not in q:
        sql = "SELECT first_name, last_name, city, email FROM patients LIMIT 20"

    elif re.search(r"patients? ?(from|in) ?\w+", q):
        match = re.search(r"(?:from|in) ([A-Za-z]+)", question)
        city = match.group(1) if match else "Mumbai"
        sql = f"SELECT first_name, last_name, email, phone FROM patients WHERE city = '{city}'"

    elif re.search(r"which city|city.*most patients|patients.*by city", q):
        sql = (
            "SELECT city, COUNT(*) AS patient_count FROM patients "
            "GROUP BY city ORDER BY patient_count DESC LIMIT 1"
        )

    elif re.search(r"male.*female|gender.*patients|patients.*gender", q):
        sql = "SELECT gender, COUNT(*) AS count FROM patients GROUP BY gender"

    elif re.search(r"registration.*trend|patient.*month|registered.*month", q):
        sql = (
            "SELECT strftime('%Y-%m', registered_date) AS month, "
            "COUNT(*) AS registrations "
            "FROM patients GROUP BY month ORDER BY month"
        )

    elif re.search(r"visited more than|visit(ed)? (\d+|three|3) times", q):
        sql = (
            "SELECT p.first_name || ' ' || p.last_name AS patient, p.city, "
            "COUNT(a.id) AS visit_count "
            "FROM appointments a JOIN patients p ON p.id = a.patient_id "
            "GROUP BY p.id HAVING visit_count > 3 ORDER BY visit_count DESC"
        )

    # ── Doctor queries ────────────────────────────────────────────────────────
    elif re.search(r"(list|show|all|get) ?(all )?doctors", q):
        sql = "SELECT name, specialization, department FROM doctors ORDER BY specialization"

    elif re.search(r"doctor.*most appointments|busiest doctor", q):
        sql = (
            "SELECT d.name, d.specialization, COUNT(a.id) AS appointment_count "
            "FROM doctors d JOIN appointments a ON a.doctor_id = d.id "
            "GROUP BY d.id ORDER BY appointment_count DESC LIMIT 1"
        )

    elif re.search(r"revenue.*doctor|doctor.*revenue", q):
        sql = (
            "SELECT d.name, SUM(i.total_amount) AS total_revenue "
            "FROM invoices i "
            "JOIN appointments a ON a.patient_id = i.patient_id "
            "JOIN doctors d ON d.id = a.doctor_id "
            "GROUP BY d.name ORDER BY total_revenue DESC"
        )

    elif re.search(r"avg.*duration|duration.*doctor|appointment.*duration", q):
        sql = (
            "SELECT d.name, ROUND(AVG(t.duration_minutes), 1) AS avg_duration_minutes "
            "FROM treatments t "
            "JOIN appointments a ON a.id = t.appointment_id "
            "JOIN doctors d ON d.id = a.doctor_id "
            "GROUP BY d.name ORDER BY avg_duration_minutes DESC"
        )

    # ── Appointment queries ───────────────────────────────────────────────────
    elif re.search(r"how many appointments|total appointments|appointment count", q):
        sql = "SELECT COUNT(*) AS total_appointments FROM appointments"

    elif re.search(r"last month.*appointments|appointments.*last month", q):
        sql = (
            "SELECT a.id, p.first_name || ' ' || p.last_name AS patient, "
            "d.name AS doctor, a.appointment_date, a.status "
            "FROM appointments a "
            "JOIN patients p ON p.id = a.patient_id "
            "JOIN doctors d ON d.id = a.doctor_id "
            "WHERE strftime('%Y-%m', a.appointment_date) = "
            "strftime('%Y-%m', date('now', '-1 month')) "
            "ORDER BY a.appointment_date"
        )

    elif re.search(r"cancelled.*last quarter|last quarter.*cancel", q):
        sql = (
            "SELECT COUNT(*) AS cancelled_count FROM appointments "
            "WHERE status = 'Cancelled' "
            "AND appointment_date >= date('now', '-3 months')"
        )

    elif re.search(r"monthly.*appointment|appointment.*6 months|past.*months.*appointment", q):
        sql = (
            "SELECT strftime('%Y-%m', appointment_date) AS month, "
            "COUNT(*) AS appointments "
            "FROM appointments "
            "WHERE appointment_date >= date('now', '-6 months') "
            "GROUP BY month ORDER BY month"
        )

    elif re.search(r"no.?show", q):
        sql = (
            "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'No-Show' THEN 1 ELSE 0 END) "
            "/ COUNT(*), 2) AS no_show_percentage FROM appointments"
        )

    elif re.search(r"busiest day|day of the week|appointment.*day", q):
        sql = (
            "SELECT CASE strftime('%w', appointment_date) "
            "WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' "
            "WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' "
            "WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' "
            "WHEN '6' THEN 'Saturday' END AS day_of_week, "
            "COUNT(*) AS appointment_count "
            "FROM appointments GROUP BY strftime('%w', appointment_date) "
            "ORDER BY appointment_count DESC"
        )

    # ── Financial queries ─────────────────────────────────────────────────────
    elif re.search(r"total revenue|overall revenue|what.*revenue", q) and "doctor" not in q and "month" not in q:
        sql = (
            "SELECT SUM(total_amount) AS total_revenue, "
            "SUM(paid_amount) AS total_collected, "
            "SUM(total_amount - paid_amount) AS outstanding "
            "FROM invoices"
        )

    elif re.search(r"revenue.*month|monthly revenue|revenue trend", q):
        sql = (
            "SELECT strftime('%Y-%m', invoice_date) AS month, "
            "SUM(total_amount) AS revenue, SUM(paid_amount) AS collected "
            "FROM invoices GROUP BY month ORDER BY month"
        )

    elif re.search(r"revenue.*department|department.*revenue|compare.*revenue", q):
        sql = (
            "SELECT d.department, SUM(i.total_amount) AS total_revenue "
            "FROM invoices i "
            "JOIN appointments a ON a.patient_id = i.patient_id "
            "JOIN doctors d ON d.id = a.doctor_id "
            "GROUP BY d.department ORDER BY total_revenue DESC"
        )

    elif re.search(r"unpaid|overdue|pending.*invoice", q):
        sql = (
            "SELECT p.first_name || ' ' || p.last_name AS patient, "
            "i.invoice_date, i.total_amount, i.paid_amount, "
            "i.total_amount - i.paid_amount AS balance, i.status "
            "FROM invoices i JOIN patients p ON p.id = i.patient_id "
            "WHERE i.status IN ('Pending', 'Overdue') "
            "ORDER BY i.status, i.total_amount DESC"
        )

    elif re.search(r"top.*patients.*spend|patients.*top.*spend|highest.*spend", q):
        limit_match = re.search(r"\b(\d+)\b", q)
        limit = int(limit_match.group(1)) if limit_match else 5
        sql = (
            f"SELECT p.first_name || ' ' || p.last_name AS patient, p.city, "
            f"SUM(i.total_amount) AS total_spending "
            f"FROM invoices i JOIN patients p ON p.id = i.patient_id "
            f"GROUP BY p.id ORDER BY total_spending DESC LIMIT {limit}"
        )

    elif re.search(r"avg.*treatment.*cost|treatment.*cost.*specialization|cost.*specialization", q):
        sql = (
            "SELECT d.specialization, ROUND(AVG(t.cost), 2) AS avg_cost, "
            "COUNT(t.id) AS treatment_count "
            "FROM treatments t "
            "JOIN appointments a ON a.id = t.appointment_id "
            "JOIN doctors d ON d.id = a.doctor_id "
            "GROUP BY d.specialization ORDER BY avg_cost DESC"
        )

    else:
        logger.warning(f"[FALLBACK] No rule matched for: {question!r}")
        return {
            "message": (
                "Could not understand that query. Try: "
                "'How many patients do we have?' or 'Show top 5 patients by spending'."
            ),
            "sql_query": None,
            "columns": None,
            "rows": None,
            "row_count": None,
            "chart": None,
            "chart_type": None,
        }

    columns, rows, row_count = _execute_sql(sql)
    if rows:
        return {
            "message": f"Found {row_count} result(s). (fallback mode — Groq unavailable)",
            "sql_query": sql.strip(),
            "columns": columns,
            "rows": rows,
            "row_count": row_count,
            "chart": None,
            "chart_type": None,
        }
    return {
        "message": "Query ran but returned no data.",
        "sql_query": sql.strip(),
        "columns": None,
        "rows": None,
        "row_count": 0,
        "chart": None,
        "chart_type": None,
    }


# ── Main LLM Runner ────────────────────────────────────────────────────────────

async def _run_llm(question: str) -> Dict[str, Any]:
    """
    Call Groq directly via GroqDirectClient.generate_sql().
    Falls back to rule-based generation only on genuine errors.
    """
    try:
        client = get_agent()
        sql    = client.generate_sql(question)   # blocking but fast (~200-600ms)

        # Safety validation
        validation = validate_sql(sql)
        if not validation.valid:
            raise ValueError(f"SQL failed safety validation: {validation.error}")

        logger.info(f"[LLM] SQL: {sql[:300]}")

        columns, rows, row_count = _execute_sql(sql)

        if rows:
            return {
                "message":    f"Found {row_count} result(s).",
                "sql_query":  sql,
                "columns":    columns,
                "rows":       rows,
                "row_count":  row_count,
                "chart":      None,
                "chart_type": None,
            }

        return {
            "message":    "Query executed — no data returned.",
            "sql_query":  sql,
            "columns":    None,
            "rows":       None,
            "row_count":  0,
            "chart":      None,
            "chart_type": None,
        }

    except Exception as e:
        logger.error(f"[LLM ERROR] {type(e).__name__}: {e}")
        logger.info("[LLM] Falling back to rule-based SQL generation.")
        return await _fallback_sql_generation(question)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["System"])
async def root():
    return {
        "name":    "NL2SQL Clinic API",
        "version": "3.0.0",
        "status":  "running",
        "endpoints": {
            "health": "GET /health",
            "chat":   "POST /chat",
            "cache":  "DELETE /cache",
            "docs":   "GET /docs",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    try:
        client       = get_agent()
        memory_count = len(client.agent_memory)
        return HealthResponse(
            status="ok",
            database=_check_db(),
            agent_memory_items=memory_count,
            cache_size=query_cache.size(),
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="degraded",
            database=_check_db(),
            agent_memory_items=0,
            cache_size=query_cache.size(),
        )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(body: ChatRequest, request: Request):
    t0        = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    try:
        # ── Rate limit ──────────────────────────────────────────────────────
        if not rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {rate_limiter._max} requests/minute.",
            )

        # ── Input validation ────────────────────────────────────────────────
        qv = validate_question(body.question)
        if not qv.valid:
            raise HTTPException(status_code=422, detail=qv.error)

        logger.info(f"[CHAT] ip={client_ip} question={body.question!r}")

        # ── Cache check ─────────────────────────────────────────────────────
        cached = query_cache.get(body.question)
        if cached is not None:
            logger.info("[CHAT] cache hit")
            cached["cached"]     = True
            cached["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return ChatResponse(question=body.question, **cached)

        # ── LLM call ────────────────────────────────────────────────────────
        result  = await _run_llm(body.question)
        latency = int((time.perf_counter() - t0) * 1000)

        # Cache successful results only
        if result.get("sql_query") and result.get("rows") is not None:
            query_cache.set(body.question, result)

        logger.info(
            f"[CHAT] OK latency={latency}ms "
            f"rows={result.get('row_count')} "
            f"sql_len={len(result.get('sql_query') or '')}"
        )

        return ChatResponse(
            question=body.question,
            cached=False,
            latency_ms=latency,
            **result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAT] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)[:200]}",
        )


@app.delete("/cache", tags=["System"])
async def clear_cache():
    query_cache.clear()
    logger.info("Cache cleared.")
    return {"message": "Cache cleared.", "status": "success"}


# ── Dev entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )