#!/usr/bin/env python3
"""
NL2SQL Clinic — FastAPI Application with Ibtcode Decision Engine

FIXED:
1. DELETE/DROP detection BEFORE LLM call (no unnecessary LLM calls)
2. Proper confirmation flow for destructive operations
3. Clean audit logging for all operations
4. SQL validation with proper risk assessment
5. Name extraction and cleaning for DELETE operations

Start: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import re
import sqlite3
import time
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
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
from vanna_setup import get_agent

from ibtcode.perception import detect_intent
from ibtcode.validation import validate_perception
from ibtcode.context import Context
from ibtcode.router import Router
from ibtcode.audit import AuditLogger


# ============================================================
# NAME CLEANING AND EXTRACTION FUNCTIONS
# ============================================================

def extract_name_from_question(text: str) -> str:
    """Extract patient name from delete query"""
    text = text.lower()
    
    # Remove keywords
    for word in ["delete", "patient", "name", "remove", "erase"]:
        text = text.replace(word, "")
    
    # Remove extra spaces
    text = " ".join(text.split())
    return text.strip()


def clean_name(name: str) -> str:
    """Remove profanity and clean name"""
    bad_words = ["fuck", "idiot", "shit", "damn", "hell", "ass", "bitch", "crap", "bloody", "bastard"]
    name_lower = name.lower()
    
    for word in bad_words:
        name_lower = name_lower.replace(word, "")
    
    # Clean multiple spaces
    name_lower = " ".join(name_lower.split())
    return name_lower.strip()


# ============================================================
# IBTCODE INSTANCES
# ============================================================

ibt_context = Context()
ibt_router = Router()
ibt_audit = AuditLogger("nl2sql_audit.json")
pending_confirmation: Optional[Dict] = None


# ============================================================
# INTENT CLASSIFICATION
# ============================================================

NL2SQL_INTENTS = {
    "PATIENT_QUERY": ["patients", "patient", "registered", "city", "gender"],
    "DOCTOR_QUERY": ["doctors", "doctor", "specialization", "department"],
    "APPOINTMENT_QUERY": ["appointments", "appointment", "schedule", "booking", "visit"],
    "FINANCIAL_QUERY": ["revenue", "invoice", "spending", "cost", "paid", "total", "amount"],
    "SENSITIVE_QUERY": ["phone", "email", "address", "private", "personal", "dob", "birth"],
    "AGGREGATION_QUERY": ["count", "average", "sum", "top", "max", "min", "highest"],
    "TIME_QUERY": ["month", "year", "date", "quarter", "trend", "weekly", "daily"],
}

SENSITIVE_COLUMNS = {"phone", "email", "address", "date_of_birth", "dob"}


def classify_intent(question: str) -> Dict[str, Any]:
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
    if not sql:
        return {"valid": False, "risk": "HIGH", "reason": "Empty SQL", "needs_confirmation": False}

    sql_upper = sql.upper()
    dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]
    
    for kw in dangerous:
        if re.search(rf"\b{kw}\b", sql_upper):
            return {
                "valid": True,
                "risk": "CRITICAL",
                "reason": f"Dangerous operation: {kw}",
                "needs_confirmation": True,
                "operation": kw
            }

    sql_lower = sql.lower()
    for col in SENSITIVE_COLUMNS:
        if col in sql_lower:
            return {
                "valid": True,
                "risk": "MEDIUM",
                "reason": f"Sensitive column: {col}",
                "needs_confirmation": True,
            }

    return {"valid": True, "risk": "LOW", "reason": "SQL is safe", "needs_confirmation": False}


def extract_patient_name_for_delete(question: str) -> Optional[str]:
    q = question.lower()
    patterns = [
        r"delete\s+patient\s+name\s+([A-Za-z\s]+)",
        r"remove\s+patient\s+([A-Za-z\s]+)",
        r"delete\s+([A-Za-z\s]+)\s+patient",
        r"erase\s+patient\s+([A-Za-z\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name:
                return clean_name(name)
    return None


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
        except:
            logs = []
        logs.append(entry)
        if len(logs) > 1000:
            logs = logs[-1000:]
        with open("nl2sql_audit.json", "w") as f:
            json.dump(logs, f, indent=2)
        logger.info(f"[AUDIT] {action} | {intent} | {risk}")
    except Exception as e:
        logger.error(f"[AUDIT] Failed: {e}")


# ============================================================
# APP LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NL2SQL Clinic API...")
    get_agent()
    logger.info("Agent ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="NL2SQL Clinic API",
    description="Natural Language to SQL with Ibtcode",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


class ConfirmRequest(BaseModel):
    confirm: bool


class ChatResponse(BaseModel):
    question: str
    message: str
    sql_query: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int | None = None
    cached: bool = False
    latency_ms: int = 0
    intent: str | None = None
    risk: str | None = None
    needs_confirmation: bool = False


class HealthResponse(BaseModel):
    status: str
    database: str
    agent_memory_items: int
    cache_size: int
    pending_confirm: bool
    version: str = "5.0.0"


# ============================================================
# DATABASE HELPERS
# ============================================================

def _db_path() -> str:
    return os.getenv("DB_PATH", "./clinic.db")


def _check_db() -> str:
    try:
        conn = sqlite3.connect(_db_path())
        conn.execute("SELECT 1")
        conn.close()
        return "connected"
    except:
        return "error"


def _execute_sql(sql: str) -> Tuple[Optional[List[str]], Optional[List[list]], int, int]:
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        
        sql_upper = sql.strip().upper()
        
        if sql_upper.startswith("SELECT"):
            rows = cursor.fetchall()
            if rows:
                columns = [d[0] for d in cursor.description]
                data = [list(row) for row in rows]
                conn.close()
                return columns, data, len(rows), 0
            conn.close()
            return None, None, 0, 0
        else:
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return None, None, 0, affected
            
    except Exception as e:
        logger.error(f"SQL error: {e}")
        return None, None, 0, 0


def _execute_delete_patient_by_name(patient_name: str) -> int:
    """
    Delete patient by full name using exact match with case-insensitive comparison
    """
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()
        
        sql = """
            DELETE FROM patients 
            WHERE LOWER(first_name || ' ' || last_name) = LOWER(?)
        """
        cursor.execute(sql, (patient_name,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        logger.info(f"DELETE executed for name: '{patient_name}', affected rows: {affected}")
        return affected
    except Exception as e:
        logger.error(f"Delete error for name '{patient_name}': {e}")
        return 0


def _execute_delete_patient_by_like(patient_name: str) -> int:
    """
    Delete patient by partial name match (fallback method)
    """
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()
        
        search_pattern = f"%{patient_name}%"
        sql = """
            DELETE FROM patients 
            WHERE LOWER(first_name || ' ' || last_name) LIKE LOWER(?)
        """
        cursor.execute(sql, (search_pattern,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        logger.info(f"LIKE DELETE executed for pattern: '{patient_name}', affected rows: {affected}")
        return affected
    except Exception as e:
        logger.error(f"LIKE Delete error for pattern '{patient_name}': {e}")
        return 0


# ============================================================
# FALLBACK SQL
# ============================================================

async def _fallback_sql_generation(question: str) -> Dict[str, Any]:
    logger.warning("[FALLBACK] Using rule-based SQL")
    q = question.lower()

    if re.search(r"how many patients|total patients", q):
        sql = "SELECT COUNT(*) AS total_patients FROM patients"
    elif re.search(r"top.*patients.*spend", q):
        sql = "SELECT p.first_name, p.last_name, SUM(i.total_amount) as total FROM patients p JOIN invoices i ON p.id = i.patient_id GROUP BY p.id ORDER BY total DESC LIMIT 5"
    elif re.search(r"total revenue", q):
        sql = "SELECT SUM(total_amount) AS total_revenue FROM invoices"
    elif re.search(r"list.*doctors", q):
        sql = "SELECT name, specialization FROM doctors"
    else:
        return {"message": "Could not understand", "sql_query": None, "columns": None, "rows": None, "row_count": 0}

    columns, rows, row_count, _ = _execute_sql(sql)
    return {"message": f"Found {row_count} result(s)", "sql_query": sql, "columns": columns, "rows": rows, "row_count": row_count}


# ============================================================
# MAIN LLM RUNNER
# ============================================================

async def _run_llm(question: str) -> Dict[str, Any]:
    try:
        client = get_agent()
        sql = client.generate_sql(question)
        validation = validate_sql(sql)
        if not validation.valid:
            raise ValueError(f"SQL invalid: {validation.error}")

        logger.info(f"[LLM] SQL: {sql[:200]}")
        columns, rows, row_count, affected = _execute_sql(sql)

        if columns and rows:
            return {"message": f"Found {row_count} result(s)", "sql_query": sql, "columns": columns, "rows": rows, "row_count": row_count}
        elif affected > 0:
            return {"message": f"{affected} row(s) affected", "sql_query": sql, "columns": None, "rows": None, "row_count": 0}
        else:
            return {"message": "No data found", "sql_query": sql, "columns": None, "rows": None, "row_count": 0}

    except Exception as e:
        logger.error(f"[LLM ERROR] {e}")
        return await _fallback_sql_generation(question)


# ============================================================
# ROUTES
# ============================================================

@app.get("/", tags=["System"])
async def root():
    return {
        "name": "NL2SQL Clinic",
        "version": "5.0.0",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "chat": "POST /chat",
            "confirm": "POST /confirm",
            "cache": "DELETE /cache",
            "logs": "GET /logs",
            "docs": "GET /docs",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    global pending_confirmation
    try:
        client = get_agent()
        memory_count = len(client.agent_memory) if hasattr(client, "agent_memory") else 0
        return HealthResponse(
            status="ok",
            database=_check_db(),
            agent_memory_items=memory_count,
            cache_size=query_cache.size(),
            pending_confirm=pending_confirmation is not None,
        )
    except:
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

    t0 = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    try:
        if not rate_limiter.is_allowed(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        qv = validate_question(body.question)
        if not qv.valid:
            raise HTTPException(status_code=422, detail=qv.error)

        logger.info(f"[CHAT] {client_ip}: {body.question}")

        q = body.question.lower()

        # ============================================================
        # DESTRUCTIVE OPERATION DETECTION - BEFORE LLM CALL
        # ============================================================

        if "drop" in q:
            log_audit(
                action="DROP_BLOCKED",
                intent="BLOCKED",
                state="rejected",
                risk="CRITICAL",
                details={"question": body.question}
            )
            return ChatResponse(
                question=body.question,
                message="DROP operation is not allowed. This system only permits SELECT and DELETE with confirmation.",
                sql_query=None,
                columns=None,
                rows=None,
                row_count=None,
                cached=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                intent="BLOCKED",
                risk="CRITICAL",
                needs_confirmation=False
            )

        delete_keywords = ["delete", "remove", "erase"]
        if any(k in q.split() for k in delete_keywords):
            raw_name = extract_patient_name_for_delete(body.question)
            
            if not raw_name:
                return ChatResponse(
                    question=body.question,
                    message="Please specify patient name to delete. Example: 'delete patient name Anjali Chopra'",
                    sql_query=None,
                    columns=None,
                    rows=None,
                    row_count=None,
                    cached=False,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    intent="DESTRUCTIVE_QUERY",
                    risk="HIGH",
                    needs_confirmation=False
                )
            
            cleaned_name = clean_name(raw_name)
            extracted_name = extract_name_from_question(raw_name)
            final_name = cleaned_name if cleaned_name else extracted_name
            
            if not final_name:
                final_name = raw_name
            
            pending_confirmation = {
                "question": body.question,
                "operation": "DELETE",
                "patient_name": final_name,
                "raw_name": raw_name,
                "timestamp": time.time()
            }
            
            log_audit(
                action="DELETE_CONFIRMATION_REQUIRED",
                intent="DESTRUCTIVE_QUERY",
                state="pending",
                risk="HIGH",
                details={"question": body.question, "patient_name": final_name, "raw_input": raw_name}
            )
            
            return ChatResponse(
                question=body.question,
                message=f"WARNING: You are about to DELETE patient '{final_name}'. This action cannot be undone. Send POST /confirm with {{\"confirm\": true}} to execute.",
                sql_query=f"DELETE FROM patients WHERE LOWER(first_name || ' ' || last_name) = LOWER('{final_name}')",
                columns=None,
                rows=None,
                row_count=None,
                cached=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                intent="DESTRUCTIVE_QUERY",
                risk="HIGH",
                needs_confirmation=True
            )

        if "update" in q or "modify" in q or "change" in q:
            pending_confirmation = {
                "question": body.question,
                "operation": "UPDATE",
                "timestamp": time.time()
            }
            log_audit(
                action="UPDATE_CONFIRMATION_REQUIRED",
                intent="DESTRUCTIVE_QUERY",
                state="pending",
                risk="HIGH",
                details={"question": body.question}
            )
            return ChatResponse(
                question=body.question,
                message="WARNING: UPDATE operation detected. This will modify data. Send POST /confirm with {\"confirm\": true} to execute.",
                sql_query=None,
                columns=None,
                rows=None,
                row_count=None,
                cached=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                intent="DESTRUCTIVE_QUERY",
                risk="HIGH",
                needs_confirmation=True
            )

        # ============================================================
        # SAFE QUERIES - PROCEED WITH LLM
        # ============================================================

        intent_info = classify_intent(body.question)
        logger.info(f"[INTENT] {intent_info['intent']}")

        log_audit(
            action="INTENT_DETECTED",
            intent=intent_info["intent"],
            state="processing",
            risk="LOW",
            details={"question": body.question},
        )

        cached = query_cache.get(body.question)
        if cached is not None:
            logger.info("[CHAT] cache hit")
            cached["cached"] = True
            cached["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return ChatResponse(question=body.question, **cached)

        result = await _run_llm(body.question)

        if result.get("sql_query"):
            risk = sql_risk_check(result["sql_query"])
            
            if risk.get("needs_confirmation") and risk.get("risk") == "CRITICAL":
                pending_confirmation = {
                    "question": body.question,
                    "operation": risk.get("operation"),
                    "sql": result["sql_query"],
                    "result": result,
                    "timestamp": time.time()
                }
                log_audit(
                    action="DANGEROUS_SQL_CONFIRMATION_REQUIRED",
                    intent=intent_info["intent"],
                    state="pending",
                    risk=risk["risk"],
                    details={"question": body.question, "sql": result["sql_query"]}
                )
                return ChatResponse(
                    question=body.question,
                    message=f"WARNING: Generated SQL contains {risk.get('operation', 'DANGEROUS')} operation. Confirm to execute.",
                    sql_query=result["sql_query"],
                    cached=False,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    intent=intent_info["intent"],
                    risk=risk["risk"],
                    needs_confirmation=True
                )

            if risk.get("needs_confirmation") and risk.get("risk") == "MEDIUM":
                pending_confirmation = {
                    "question": body.question,
                    "operation": "SENSITIVE",
                    "sql": result["sql_query"],
                    "result": result,
                    "timestamp": time.time()
                }
                log_audit(
                    action="SENSITIVE_DATA_CONFIRMATION_REQUIRED",
                    intent=intent_info["intent"],
                    state="pending",
                    risk=risk["risk"],
                    details={"question": body.question, "reason": risk["reason"]}
                )
                return ChatResponse(
                    question=body.question,
                    message=f"This query accesses sensitive data: {risk['reason']}. Confirm to proceed.",
                    sql_query=result["sql_query"],
                    cached=False,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    intent=intent_info["intent"],
                    risk=risk["risk"],
                    needs_confirmation=True
                )

        latency = int((time.perf_counter() - t0) * 1000)

        if result.get("sql_query") and result.get("rows") is not None:
            query_cache.set(body.question, result)

        log_audit(
            action="QUERY_SUCCESS",
            intent=intent_info["intent"],
            state="completed",
            risk="LOW",
            details={"row_count": result.get("row_count")}
        )

        return ChatResponse(
            question=body.question,
            cached=False,
            latency_ms=latency,
            intent=intent_info["intent"],
            risk="LOW",
            needs_confirmation=False,
            **result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAT] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/confirm", tags=["Chat"])
async def confirm_action(confirm_data: ConfirmRequest):
    global pending_confirmation

    if not pending_confirmation:
        return {"status": "error", "message": "No pending action to confirm"}

    if not confirm_data.confirm:
        log_audit(
            action="CONFIRMATION_CANCELLED",
            intent=pending_confirmation.get("intent", "UNKNOWN"),
            state="cancelled",
            risk="MEDIUM",
            details={"question": pending_confirmation.get("question")}
        )
        pending_confirmation = None
        return {"status": "cancelled", "message": "Operation cancelled"}

    operation = pending_confirmation.get("operation")
    
    if operation == "DELETE":
        patient_name = pending_confirmation.get("patient_name")
        raw_name = pending_confirmation.get("raw_name", "")
        
        if not patient_name:
            if raw_name:
                patient_name = clean_name(raw_name)
                patient_name = extract_name_from_question(patient_name)
            else:
                pending_confirmation = None
                return {"status": "error", "message": "No patient name found"}
        
        if patient_name:
            affected = _execute_delete_patient_by_name(patient_name)
            
            if affected == 0:
                affected = _execute_delete_patient_by_like(patient_name)
            
            log_audit(
                action="DELETE_EXECUTED",
                intent="DESTRUCTIVE_QUERY",
                state="executed",
                risk="HIGH",
                details={"patient_name": patient_name, "affected_rows": affected, "raw_input": raw_name}
            )
            pending_confirmation = None
            return {
                "status": "executed",
                "message": f"Deleted {affected} patient(s) with name '{patient_name}'",
                "affected_rows": affected,
                "patient_name": patient_name
            }
    
    sql = pending_confirmation.get("sql")
    if sql:
        _, _, _, affected = _execute_sql(sql)
        log_audit(
            action="SQL_EXECUTED",
            intent=pending_confirmation.get("intent", "UNKNOWN"),
            state="executed",
            risk="HIGH",
            details={"sql": sql, "affected_rows": affected}
        )
        pending_confirmation = None
        return {
            "status": "executed",
            "message": f"Operation executed. {affected} row(s) affected.",
            "affected_rows": affected
        }
    
    pending_confirmation = None
    return {"status": "error", "message": "No valid operation found"}


@app.delete("/cache", tags=["System"])
async def clear_cache():
    query_cache.clear()
    return {"message": "Cache cleared", "status": "success"}


@app.get("/logs", tags=["System"])
async def get_logs(limit: int = 50):
    try:
        with open("nl2sql_audit.json", "r") as f:
            logs = json.load(f)
        return {"logs": logs[-limit:]}
    except:
        return {"logs": []}


@app.delete("/logs", tags=["System"])
async def clear_logs():
    try:
        with open("nl2sql_audit.json", "w") as f:
            json.dump([], f)
        return {"message": "Logs cleared", "status": "success"}
    except:
        return {"message": "Failed", "status": "error"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )