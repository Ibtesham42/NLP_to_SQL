#!/usr/bin/env python3
"""
NL2SQL Clinic — FastAPI Application with Ibtcode Decision Engine

BUGS FIXED vs previous version:
  1. NL2SQL_INTENTS router was sending PATIENT_QUERY, DOCTOR_QUERY, and
     AGGREGATION_QUERY directly to fallback — meaning "How many patients",
     "List doctors", "Top 5 patients" NEVER reached Groq. Fixed: all
     intents now route to the LLM. Fallback is last-resort only.

  2. SENSITIVE_QUERY (phone/email keywords) blocked the request BEFORE
     Groq could generate SQL, and returned a confirmation gate with no data.
     Fixed: Groq generates the SQL first, then if the SQL itself touches a
     sensitive column we gate on confirmation. This lets Groq handle the
     query correctly while still protecting PII at the SQL level.

  3. "(Fallback mode)" message was being shown even for normal Groq results
     because the route always went to _fallback_sql_generation.

HOW IT WORKS NOW:
  1. Request → rate limit + input validation
  2. Ibtcode intent classification (for audit/logging only, NOT for routing)
  3. Cache check
  4. Groq LLM generates SQL  ← ALL questions go here first
  5. Ibtcode SQL safety check → if sensitive columns, gate on confirmation
  6. Execute SQL → return JSON

Start:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import re
import sqlite3
import time
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from datetime import datetime

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

# Ibtcode imports
from ibtcode.perception import detect_intent
from ibtcode.validation import validate_perception
from ibtcode.context import Context
from ibtcode.router import Router
from ibtcode.audit import AuditLogger


# ── Ibtcode instances ──────────────────────────────────────────────────────────

ibt_context = Context()
ibt_router  = Router()
ibt_audit   = AuditLogger("nl2sql_audit.json")

# Global pending confirmation slot
pending_confirmation: Optional[Dict] = None

# ── Intent Classification ──────────────────────────────────────────────────────
# FIX: intent is now used ONLY for audit labelling.
# It no longer controls whether the LLM is called or not.
# Every question goes to Groq regardless of intent bucket.

NL2SQL_INTENTS = {
    "PATIENT_QUERY":     ["patients", "patient", "registered", "city", "gender"],
    "DOCTOR_QUERY":      ["doctors", "doctor", "specialization", "department"],
    "APPOINTMENT_QUERY": ["appointments", "appointment", "schedule", "booking", "visit"],
    "FINANCIAL_QUERY":   ["revenue", "invoice", "spending", "cost", "paid", "total", "amount"],
    "SENSITIVE_QUERY":   ["phone", "email", "address", "private", "personal", "dob", "birth"],
    "AGGREGATION_QUERY": ["count", "average", "sum", "top", "max", "min", "highest"],
    "TIME_QUERY":        ["month", "year", "date", "quarter", "trend", "weekly", "daily"],
}

# Columns that warrant a confirmation gate AFTER SQL is generated
SENSITIVE_COLUMNS = {"phone", "email", "address", "date_of_birth", "dob"}


def classify_intent(question: str) -> Dict[str, Any]:
    """
    Classify the question for audit purposes only.
    Does NOT affect routing — all questions go to the LLM.
    """
    q = question.lower()
    try:
        perception = detect_intent(q)
    except Exception:
        perception = {}

    for intent, keywords in NL2SQL_INTENTS.items():
        if any(kw in q for kw in keywords):
            return {
                "intent": intent,
                "confidence": 0.9,
                "original_intent": perception.get("intent", "UNKNOWN"),
            }

    return {
        "intent": "GENERAL_QUERY",
        "confidence": 0.7,
        "original_intent": perception.get("intent", "UNKNOWN"),
    }


def sql_risk_check(sql: str) -> Dict[str, Any]:
    """
    Check generated SQL for dangerous operations and sensitive column access.
    Returns: {"valid": bool, "risk": str, "reason": str, "needs_confirmation": bool}
    """
    if not sql:
        return {"valid": False, "risk": "HIGH", "reason": "Empty SQL", "needs_confirmation": False}

    sql_upper = sql.upper()
    dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "EXEC"]
    for kw in dangerous:
        if re.search(rf"\b{kw}\b", sql_upper):
            return {
                "valid": False,
                "risk": "HIGH",
                "reason": f"Dangerous operation: {kw}",
                "needs_confirmation": False,
            }

    sql_lower = sql.lower()
    for col in SENSITIVE_COLUMNS:
        if col in sql_lower:
            return {
                "valid": True,
                "risk": "MEDIUM",
                "reason": f"Sensitive column accessed: {col}",
                "needs_confirmation": True,
                "sensitive_column": col,
            }

    return {"valid": True, "risk": "LOW", "reason": "SQL is safe", "needs_confirmation": False}


# ── Audit Logger ───────────────────────────────────────────────────────────────

def log_audit(action: str, intent: str, state: str, risk: str, details: Dict = None):
    try:
        entry = {
            "action": action,
            "intent": intent,
            "state": state,
            "risk": risk,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }
        try:
            with open("nl2sql_audit.json", "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

        logs.append(entry)
        if len(logs) > 1000:
            logs = logs[-1000:]

        with open("nl2sql_audit.json", "w") as f:
            json.dump(logs, f, indent=2)

        logger.info(f"[AUDIT] {action} | {intent} | {risk}")
    except Exception as e:
        logger.error(f"[AUDIT] Write failed: {e}")


# ── App Lifecycle ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NL2SQL Clinic API with Ibtcode...")
    get_agent()
    logger.info("Agent (GroqDirectClient) ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="NL2SQL Clinic API with Ibtcode",
    description="Natural Language to SQL — Groq LLM + Ibtcode decision engine",
    version="4.1.0",
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


class ConfirmRequest(BaseModel):
    confirm: bool = Field(..., description="Confirm or cancel the pending sensitive query")


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
    intent:     str | None = None
    risk:       str | None = None


class HealthResponse(BaseModel):
    status:             str
    database:           str
    agent_memory_items: int
    cache_size:         int
    pending_confirm:    bool
    version:            str = "4.1.0"


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


def _execute_sql(sql: str) -> tuple[Optional[List[str]], Optional[List[list]], int]:
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


# ── Fallback SQL (last resort only) ───────────────────────────────────────────

async def _fallback_sql_generation(question: str) -> Dict[str, Any]:
    """
    Rule-based SQL — only called when Groq is genuinely unavailable.
    NOT a routing destination for normal questions.
    """
    logger.warning("[FALLBACK] Groq unavailable — using rule-based SQL.")
    q = question.lower()

    # Patient queries
    if re.search(r"how many patients|total patients|patient count", q):
        sql = "SELECT COUNT(*) AS total_patients FROM patients"
    elif re.search(r"registration.*trend|patient.*month|registered.*month", q):
        sql = "SELECT strftime('%Y-%m', registered_date) AS month, COUNT(*) AS registrations FROM patients GROUP BY month ORDER BY month"
    elif re.search(r"which city|city.*most patients", q):
        sql = "SELECT city, COUNT(*) AS patient_count FROM patients GROUP BY city ORDER BY patient_count DESC LIMIT 1"
    elif re.search(r"male.*female|gender.*patients", q):
        sql = "SELECT gender, COUNT(*) AS count FROM patients GROUP BY gender"
    elif re.search(r"visited more than|visit(ed)? (\d+|three|3) times", q):
        sql = ("SELECT p.first_name || ' ' || p.last_name AS patient, COUNT(a.id) AS visit_count "
               "FROM appointments a JOIN patients p ON p.id = a.patient_id "
               "GROUP BY p.id HAVING visit_count > 3 ORDER BY visit_count DESC")
    elif re.search(r"(list|show|all) ?(all )?patients", q):
        sql = "SELECT first_name, last_name, city, email FROM patients LIMIT 20"

    # Doctor queries
    elif re.search(r"(list|show|all) ?(all )?doctors", q):
        sql = "SELECT name, specialization, department FROM doctors ORDER BY specialization"
    elif re.search(r"doctor.*most appointments|busiest doctor", q):
        sql = ("SELECT d.name, COUNT(a.id) AS appointment_count FROM doctors d "
               "JOIN appointments a ON a.doctor_id = d.id GROUP BY d.id ORDER BY appointment_count DESC LIMIT 1")
    elif re.search(r"revenue.*doctor|doctor.*revenue", q):
        sql = ("SELECT d.name, SUM(i.total_amount) AS total_revenue FROM invoices i "
               "JOIN appointments a ON a.patient_id = i.patient_id "
               "JOIN doctors d ON d.id = a.doctor_id GROUP BY d.name ORDER BY total_revenue DESC")
    elif re.search(r"avg.*duration|duration.*doctor", q):
        sql = ("SELECT d.name, ROUND(AVG(t.duration_minutes), 1) AS avg_duration_minutes "
               "FROM treatments t JOIN appointments a ON a.id = t.appointment_id "
               "JOIN doctors d ON d.id = a.doctor_id GROUP BY d.name ORDER BY avg_duration_minutes DESC")

    # Appointment queries
    elif re.search(r"how many appointments|total appointments", q):
        sql = "SELECT COUNT(*) AS total_appointments FROM appointments"
    elif re.search(r"cancelled.*last quarter|last quarter.*cancel", q):
        sql = ("SELECT COUNT(*) AS cancelled_count FROM appointments "
               "WHERE status = 'Cancelled' AND appointment_date >= date('now', '-3 months')")
    elif re.search(r"no.?show", q):
        sql = ("SELECT ROUND(100.0 * SUM(CASE WHEN status = 'No-Show' THEN 1 ELSE 0 END) / COUNT(*), 2) "
               "AS no_show_percentage FROM appointments")
    elif re.search(r"busiest day|day of the week", q):
        sql = ("SELECT CASE strftime('%w', appointment_date) WHEN '0' THEN 'Sunday' "
               "WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' "
               "WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' WHEN '6' THEN 'Saturday' END AS day_of_week, "
               "COUNT(*) AS appointment_count FROM appointments "
               "GROUP BY strftime('%w', appointment_date) ORDER BY appointment_count DESC")
    elif re.search(r"monthly.*appointment|appointment.*6 months", q):
        sql = ("SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS appointments "
               "FROM appointments WHERE appointment_date >= date('now', '-6 months') "
               "GROUP BY month ORDER BY month")
    elif re.search(r"last month.*appointments|appointments.*last month", q):
        sql = ("SELECT a.id, p.first_name || ' ' || p.last_name AS patient, d.name AS doctor, "
               "a.appointment_date, a.status FROM appointments a "
               "JOIN patients p ON p.id = a.patient_id JOIN doctors d ON d.id = a.doctor_id "
               "WHERE strftime('%Y-%m', a.appointment_date) = strftime('%Y-%m', date('now', '-1 month')) "
               "ORDER BY a.appointment_date")

    # Financial queries
    elif re.search(r"revenue.*month|monthly revenue|revenue trend", q):
        sql = ("SELECT strftime('%Y-%m', invoice_date) AS month, "
               "SUM(total_amount) AS revenue, SUM(paid_amount) AS collected "
               "FROM invoices GROUP BY month ORDER BY month")
    elif re.search(r"revenue.*department|department.*revenue|compare.*revenue", q):
        sql = ("SELECT d.department, SUM(i.total_amount) AS total_revenue FROM invoices i "
               "JOIN appointments a ON a.patient_id = i.patient_id "
               "JOIN doctors d ON d.id = a.doctor_id GROUP BY d.department ORDER BY total_revenue DESC")
    elif re.search(r"total revenue|overall revenue", q):
        sql = ("SELECT SUM(total_amount) AS total_revenue, SUM(paid_amount) AS total_collected, "
               "SUM(total_amount - paid_amount) AS outstanding FROM invoices")
    elif re.search(r"unpaid|overdue|pending.*invoice", q):
        sql = ("SELECT p.first_name || ' ' || p.last_name AS patient, i.invoice_date, "
               "i.total_amount, i.paid_amount, i.total_amount - i.paid_amount AS balance, i.status "
               "FROM invoices i JOIN patients p ON p.id = i.patient_id "
               "WHERE i.status IN ('Pending', 'Overdue') ORDER BY i.status, i.total_amount DESC")
    elif re.search(r"top.*patients.*spend|patients.*spend|highest.*spend", q):
        limit_match = re.search(r"\b(\d+)\b", q)
        limit = int(limit_match.group(1)) if limit_match else 5
        sql = (f"SELECT p.first_name || ' ' || p.last_name AS patient, p.city, "
               f"SUM(i.total_amount) AS total_spending FROM invoices i "
               f"JOIN patients p ON p.id = i.patient_id "
               f"GROUP BY p.id ORDER BY total_spending DESC LIMIT {limit}")
    elif re.search(r"avg.*treatment.*cost|cost.*specialization", q):
        sql = ("SELECT d.specialization, ROUND(AVG(t.cost), 2) AS avg_cost, COUNT(t.id) AS treatment_count "
               "FROM treatments t JOIN appointments a ON a.id = t.appointment_id "
               "JOIN doctors d ON d.id = a.doctor_id GROUP BY d.specialization ORDER BY avg_cost DESC")
    else:
        logger.warning(f"[FALLBACK] No rule matched: {question!r}")
        return {
            "message": "Groq is currently unavailable and no matching rule was found. Please try again.",
            "sql_query": None, "columns": None, "rows": None,
            "row_count": None, "chart": None, "chart_type": None,
        }

    columns, rows, row_count = _execute_sql(sql)
    if rows:
        return {
            "message": f"Found {row_count} result(s). (Groq unavailable — fallback mode)",
            "sql_query": sql.strip(), "columns": columns,
            "rows": rows, "row_count": row_count,
            "chart": None, "chart_type": None,
        }
    return {
        "message": "Query ran but returned no data.",
        "sql_query": sql.strip(), "columns": None,
        "rows": None, "row_count": 0,
        "chart": None, "chart_type": None,
    }


# ── Main LLM Runner ────────────────────────────────────────────────────────────

async def _run_llm(question: str) -> Dict[str, Any]:
    """
    FIX: ALL questions come here. No keyword gate before this.
    Groq generates the SQL. Fallback only on genuine Groq failure.
    """
    try:
        client = get_agent()
        sql    = client.generate_sql(question)

        validation = validate_sql(sql)
        if not validation.valid:
            raise ValueError(f"SQL safety check failed: {validation.error}")

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
        return await _fallback_sql_generation(question)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["System"])
async def root():
    return {
        "name":    "NL2SQL Clinic API with Ibtcode",
        "version": "4.1.0",
        "status":  "running",
        "features": {
            "llm_sql_generation":             True,
            "intent_classification":          True,
            "sensitive_query_confirmation":   True,
            "audit_logging":                  True,
            "fallback_sql":                   True,
            "query_caching":                  True,
            "rate_limiting":                  True,
        },
        "endpoints": {
            "health":  "GET /health",
            "chat":    "POST /chat",
            "confirm": "POST /confirm",
            "cache":   "DELETE /cache",
            "logs":    "GET /logs",
            "docs":    "GET /docs",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    global pending_confirmation
    try:
        client       = get_agent()
        memory_count = len(client.agent_memory) if hasattr(client, "agent_memory") else 0
        return HealthResponse(
            status="ok",
            database=_check_db(),
            agent_memory_items=memory_count,
            cache_size=query_cache.size(),
            pending_confirm=pending_confirmation is not None,
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="degraded",
            database=_check_db(),
            agent_memory_items=0,
            cache_size=query_cache.size(),
            pending_confirm=pending_confirmation is not None,
        )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(body: ChatRequest, request: Request):
    global pending_confirmation

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

        # ── Intent classification (audit only, does NOT affect routing) ─────
        intent_info = classify_intent(body.question)
        logger.info(f"[INTENT] {intent_info['intent']} (confidence={intent_info['confidence']})")

        try:
            ibt_context.update(body.question, intent_info["intent"], "processing")
        except Exception:
            pass

        log_audit(
            action="INTENT_DETECTED",
            intent=intent_info["intent"],
            state="processing",
            risk="LOW",
            details={"question": body.question, "confidence": intent_info["confidence"]},
        )

        # ── Cache check ─────────────────────────────────────────────────────
        cached = query_cache.get(body.question)
        if cached is not None:
            logger.info("[CHAT] cache hit")
            cached["cached"]     = True
            cached["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            cached["intent"]     = intent_info["intent"]
            cached["risk"]       = "LOW"
            return ChatResponse(question=body.question, **cached)

        # ── LLM call — ALL questions go here ────────────────────────────────
        # FIX: No keyword routing. Groq handles every question.
        # 🔐 Ibtcode VALIDATION (ADD THIS BLOCK)

        perception = {
            "intent": intent_info["intent"],
            "confidence": intent_info["confidence"],
            "raw_input": body.question
        }

        validation = validate_perception(perception)

        if validation["status"] == "REJECT":
            log_audit(
                action="INPUT_BLOCKED",
                intent="BLOCKED",
                state="rejected",
                risk="HIGH",
                details={"reason": validation["reason"], "question": body.question}
            )

            return ChatResponse(
                question=body.question,
                message=validation["message"],
                sql_query=None,
                columns=None,
                rows=None,
                row_count=None,
                cached=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                intent="BLOCKED",
                risk="HIGH"
                    )
        result = await _run_llm(body.question)

        # ── Ibtcode SQL risk check AFTER Groq generates the SQL ─────────────
        # FIX: We check the *generated SQL* for sensitive columns, not the
        # *question text*. This is the correct place to gate on PII access.
        if result.get("sql_query"):
            risk = sql_risk_check(result["sql_query"])
            logger.info(f"[IBTCODE] Risk: {risk['risk']} — {risk['reason']}")

            if not risk["valid"]:
                log_audit(
                    action="SQL_REJECTED",
                    intent=intent_info["intent"],
                    state="rejected",
                    risk="HIGH",
                    details={"reason": risk["reason"], "sql": result["sql_query"]},
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"SQL safety check failed: {risk['reason']}",
                )

            # Sensitive column access → ask for confirmation
            if risk["needs_confirmation"]:
                pending_confirmation = {
                    "question":  body.question,
                    "intent":    intent_info["intent"],
                    "sql":       result["sql_query"],
                    "result":    result,
                    "timestamp": time.time(),
                }
                log_audit(
                    action="CONFIRMATION_REQUIRED",
                    intent=intent_info["intent"],
                    state="pending",
                    risk="MEDIUM",
                    details={"question": body.question, "reason": risk["reason"]},
                )
                # Return a proper ChatResponse with needs_confirmation hint in message
                return ChatResponse(
                    question=body.question,
                    message=f"This query accesses sensitive data ({risk['reason']}). "
                            f"POST /confirm with {{\"confirm\": true}} to proceed.",
                    sql_query=None,
                    cached=False,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    intent=intent_info["intent"],
                    risk="MEDIUM",
                )

        # ── Cache and return ─────────────────────────────────────────────────
        latency = int((time.perf_counter() - t0) * 1000)

        if result.get("sql_query") and result.get("rows") is not None:
            query_cache.set(body.question, result)

        log_audit(
            action="QUERY_SUCCESS",
            intent=intent_info["intent"],
            state="completed",
            risk="LOW",
            details={"row_count": result.get("row_count"), "latency_ms": latency},
        )

        logger.info(
            f"[CHAT] OK latency={latency}ms "
            f"rows={result.get('row_count')} "
            f"intent={intent_info['intent']}"
        )

        return ChatResponse(
            question=body.question,
            cached=False,
            latency_ms=latency,
            intent=intent_info["intent"],
            risk="LOW",
            **result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAT] Unexpected error: {e}", exc_info=True)
        log_audit(
            action="ERROR",
            intent="UNKNOWN",
            state="error",
            risk="HIGH",
            details={"error": str(e), "question": body.question},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)[:200]}",
        )


@app.post("/confirm", tags=["Chat"])
async def confirm_action(confirm_data: ConfirmRequest):
    """Execute or cancel a pending sensitive query."""
    global pending_confirmation

    if not pending_confirmation:
        return {"status": "error", "message": "No pending action to confirm"}

    intent = pending_confirmation.get("intent", "UNKNOWN")

    if not confirm_data.confirm:
        log_audit(
            action="CONFIRMATION_CANCELLED",
            intent=intent,
            state="cancelled",
            risk="LOW",
            details={"question": pending_confirmation.get("question")},
        )
        pending_confirmation = None
        return {"status": "cancelled", "message": "Action cancelled."}

    # User confirmed — execute the cached result
    result   = pending_confirmation.get("result")
    question = pending_confirmation.get("question", "")

    log_audit(
        action="CONFIRMATION_GRANTED",
        intent=intent,
        state="confirmed",
        risk="MEDIUM",
        details={"question": question},
    )

    pending_confirmation = None

    if result:
        return {"status": "executed", "result": result}

    # Edge case: result wasn't cached in pending — re-run
    result = await _run_llm(question)
    return {"status": "executed", "result": result}


@app.delete("/cache", tags=["System"])
async def clear_cache():
    query_cache.clear()
    logger.info("Cache cleared.")
    return {"message": "Cache cleared.", "status": "success"}


@app.get("/logs", tags=["System"])
async def get_logs(limit: int = 50):
    try:
        with open("nl2sql_audit.json", "r") as f:
            logs = json.load(f)
        return {"logs": logs[-limit:]}
    except Exception:
        return {"logs": []}


@app.delete("/logs", tags=["System"])
async def clear_logs():
    try:
        with open("nl2sql_audit.json", "w") as f:
            json.dump([], f)
        return {"message": "Logs cleared.", "status": "success"}
    except Exception:
        return {"message": "Failed to clear logs.", "status": "error"}


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