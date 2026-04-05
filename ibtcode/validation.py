"""
Ibtcode Validation Layer — Production Grade
Layers (in order):
  1. Profanity Filter
  2. Dangerous Keyword Detection (DROP, DELETE, …)
  3. SQL Injection Pattern Detection
  4. Unknown Intent Handling
  5. Minimum Length Check
  6. Confidence Threshold Check
  7. Sensitive Intent Warning
  8. Context-Aware Rate / Repeat Guard
  9. Final Accept

Also exports:
  - validate_sql_query()   → validates a generated SQL string
  - sanitize_user_input()  → redacts profanity from text
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ── 1. PROFANITY ───────────────────────────────────────────────────────────────

PROFANITY_LIST: List[str] = [
    "fuk", "fuck", "shit", "bitch", "bastard", "dick", "piss",
    "fck", "fukc", "b8tch", "b1tch", "b!tch", "f@ck", "f#ck",
    "motherfucker", "stfu", "gtfo",
]

PROFANITY_PATTERNS: List[str] = [
    r"f[u3@][ck]+",
    r"s[h!][i1][t7]+",
    r"b[i1][t7][c][h]",
]


def contains_profanity(text: str) -> bool:
    if not text:
        return False
    lo = text.lower()
    for word in PROFANITY_LIST:
        # Use word boundary so "hell" doesn't match "hello", "shell", etc.
        if re.search(rf"\b{re.escape(word)}\b", lo):
            return True
    for pat in PROFANITY_PATTERNS:
        if re.search(pat, lo):
            return True
    return False


def sanitize_user_input(text: str) -> str:
    """Replace profane words with [REDACTED]."""
    if not text:
        return text
    out = text
    for word in PROFANITY_LIST:
        out = re.sub(re.escape(word), "[REDACTED]", out, flags=re.IGNORECASE)
    return out


# ── 2. DANGEROUS INPUT-LEVEL KEYWORDS ─────────────────────────────────────────

DANGEROUS_KEYWORDS: List[str] = [
    "drop table", "drop",
    "delete from", "delete",
    "truncate table", "truncate",
    "alter table", "alter",
    "create table", "create",
    "insert into", "insert",
    "update",
    "exec ", "execute ",
    "xp_", "sp_",
    "shutdown",
    "grant ", "revoke ",
]


def contains_dangerous_keyword(text: str) -> Tuple[bool, Optional[str]]:
    lo = text.lower()
    for kw in DANGEROUS_KEYWORDS:
        if kw in lo:
            return True, kw.strip().upper()
    return False, None


# ── 3. SQL INJECTION PATTERNS ─────────────────────────────────────────────────

DANGEROUS_SQL_PATTERNS: List[str] = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b.*\bSET\b",
    r"\bINSERT\b.*\bINTO\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bUNION\b.*\bSELECT\b",
    r"\bOR\b\s+1\s*=\s*1",
    r"--",
    r"/\*",
    r"xp_",
    r"sp_",
    r";\s*(DROP|DELETE|UPDATE|INSERT)",
    r"sqlite_master",
    r"information_schema",
]


def contains_dangerous_sql(text: str) -> bool:
    if not text:
        return False
    up = text.upper()
    for pat in DANGEROUS_SQL_PATTERNS:
        if re.search(pat, up, re.IGNORECASE):
            return True
    return False


# ── INTENT CONFIG ──────────────────────────────────────────────────────────────

ALL_INTENTS: List[str] = [
    "PASSWORD_RESET", "ESCALATE", "ACCOUNT_HACKED",
    "PATIENT_QUERY", "DOCTOR_QUERY", "APPOINTMENT_QUERY",
    "FINANCIAL_QUERY", "SENSITIVE_QUERY", "AGGREGATION_QUERY",
    "TIME_QUERY", "TREATMENT_QUERY", "COMPARISON_QUERY",
    "GENERAL_QUERY", "UNKNOWN",
]

# Minimum confidence required per intent before we ask for clarification
INTENT_THRESHOLDS: Dict[str, float] = {
    "PASSWORD_RESET":     0.75,
    "ESCALATE":           0.90,
    "ACCOUNT_HACKED":     0.85,
    "PATIENT_QUERY":      0.70,
    "DOCTOR_QUERY":       0.70,
    "APPOINTMENT_QUERY":  0.70,
    "FINANCIAL_QUERY":    0.70,
    "SENSITIVE_QUERY":    0.80,
    "AGGREGATION_QUERY":  0.70,
    "TIME_QUERY":         0.70,
    "TREATMENT_QUERY":    0.70,
    "COMPARISON_QUERY":   0.70,
    "GENERAL_QUERY":      0.60,
}

# ── MAIN VALIDATION ────────────────────────────────────────────────────────────

def validate_perception(
    perception: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the full validation pipeline against a perception dict.

    perception format:
        {"intent": str, "confidence": float, "raw_input": str}

    context (optional):
        {"last_intent": str, "last_timestamp": float}

    Return format always contains at minimum:
        {"status": str, ...}

    status values:
        VALID        → pass, proceed with SQL generation
        WARNING      → pass but flag (sensitive intent, needs_confirmation=True)
        CLARIFY      → ask user to rephrase
        CONFIRM      → dangerous keyword — ask user to confirm before proceeding
        REJECT       → hard block (profanity / SQL injection detected)
    """

    intent      = perception.get("intent",     "UNKNOWN")
    confidence  = perception.get("confidence", 0.0)
    raw_input   = perception.get("raw_input",  "")

    # ── Layer 1: PROFANITY ─────────────────────────────────────────────────────
    if raw_input and contains_profanity(raw_input):
        return {
            "status":  "REJECT",
            "reason":  "profanity_detected",
            "message": "Your query contains inappropriate language. Please rephrase respectfully.",
            "blocked": True,
            "intent":  "BLOCKED",
        }

    # ── Layer 2: DANGEROUS INPUT KEYWORDS ─────────────────────────────────────
    has_danger, kw = contains_dangerous_keyword(raw_input)
    if has_danger:
        return {
            "status":                "CONFIRM",
            "reason":                "dangerous_keyword_in_input",
            "message":               f"Your input contains a destructive keyword ('{kw}'). Did you mean to query, not modify data?",
            "blocked":               False,
            "intent":                "DESTRUCTIVE_QUERY",
            "keyword":               kw,
            "requires_confirmation": True,
        }

    # ── Layer 3: SQL INJECTION PATTERNS ───────────────────────────────────────
    if raw_input and contains_dangerous_sql(raw_input):
        return {
            "status":  "REJECT",
            "reason":  "sql_injection_pattern",
            "message": "Potentially dangerous SQL pattern detected in your query. This has been blocked.",
            "blocked": True,
            "intent":  "BLOCKED",
        }

    # ── Layer 4: UNKNOWN INTENT ────────────────────────────────────────────────
    if intent == "UNKNOWN":
        return {
            "status":     "CLARIFY",
            "reason":     "unknown_intent",
            "message":    "I couldn't understand your query. Could you rephrase it?",
            "candidates": ["PATIENT_QUERY", "DOCTOR_QUERY", "FINANCIAL_QUERY", "APPOINTMENT_QUERY"],
        }

    # ── Layer 5: TOO SHORT ─────────────────────────────────────────────────────
    if raw_input and len(raw_input.strip()) < 3:
        return {
            "status":     "CLARIFY",
            "reason":     "too_short",
            "message":    "Your query is too short. Please provide more details.",
            "candidates": ALL_INTENTS,
        }

    # ── Layer 6: CONFIDENCE CHECK ──────────────────────────────────────────────
    threshold = INTENT_THRESHOLDS.get(intent, 0.70)
    if confidence < threshold:
        return {
            "status":     "CLARIFY",
            "reason":     "low_confidence",
            "message":    f"I'm not fully sure what you mean ({int(confidence * 100)}% confidence). Can you rephrase?",
            "intent":     intent,
            "confidence": confidence,
            "threshold":  threshold,
            "candidates": ["PATIENT_QUERY", "DOCTOR_QUERY", "FINANCIAL_QUERY",
                           "APPOINTMENT_QUERY", "TIME_QUERY"],
        }

    # ── Layer 7: CONTEXT GUARDS ────────────────────────────────────────────────
    if context:
        last_intent = context.get("last_intent")
        last_ts     = context.get("last_timestamp", 0)

        # Rapid-fire repeat guard (< 1.5 s)
        if last_ts and (time.time() - last_ts) < 1.5:
            return {
                "status":     "CLARIFY",
                "reason":     "rate_limit_intent",
                "message":    "Please slow down. Wait a moment before submitting another query.",
                "candidates": ALL_INTENTS,
            }

        # Repeat ACCOUNT_HACKED guard
        if last_intent == intent == "ACCOUNT_HACKED":
            return {
                "status":     "CLARIFY",
                "reason":     "repeat_sensitive_intent",
                "message":    "You already reported this. Do you need further action?",
                "candidates": [intent, "CANCEL"],
            }

    # ── Layer 8: SENSITIVE INTENT WARNING ─────────────────────────────────────
    if intent == "SENSITIVE_QUERY":
        return {
            "status":                "WARNING",
            "reason":                "sensitive_intent",
            "message":               "This query may access sensitive patient data (phone, email, DOB). Confirm to proceed.",
            "intent":                intent,
            "confidence":            confidence,
            "requires_confirmation": True,
        }

    # ── Layer 9: FINAL ACCEPT ──────────────────────────────────────────────────
    return {
        "status":     "VALID",
        "intent":     intent,
        "confidence": confidence,
        "message":    f"Intent validated: {intent}",
    }


# ── SQL QUERY VALIDATOR (post-LLM) ────────────────────────────────────────────

# Columns that trigger a MEDIUM-risk confirmation gate
_SENSITIVE_COLS = {"phone", "email", "address", "date_of_birth", "dob"}

# Operations that are flatly blocked
_BLOCKED_OPS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
}


def validate_sql_query(sql: str) -> Dict[str, Any]:
    """
    Validate a SQL string that was generated by the LLM.

    Risk levels:
        CRITICAL  → dangerous DML/DDL detected — do NOT execute
        HIGH      → blocked pattern detected    — do NOT execute
        MEDIUM    → sensitive column access     — ask for confirmation
        LOW       → safe SELECT                 — execute freely

    Returns:
        {
            "valid":               bool,
            "risk":                str,          # CRITICAL / HIGH / MEDIUM / LOW
            "reason":              str,
            "needs_confirmation":  bool,
            "sensitive_column":    str | None,
        }
    """
    if not sql or not sql.strip():
        return {
            "valid": False, "risk": "HIGH",
            "reason": "Empty SQL query.",
            "needs_confirmation": False, "sensitive_column": None,
        }

    sql_upper = sql.strip().upper()
    sql_lower = sql.strip().lower()

    # Must be a SELECT (or CTE starting with WITH … SELECT)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return {
            "valid": False, "risk": "CRITICAL",
            "reason": "Only SELECT statements are permitted.",
            "needs_confirmation": False, "sensitive_column": None,
        }

    # Block dangerous DML/DDL keywords
    for op in _BLOCKED_OPS:
        if re.search(rf"\b{op}\b", sql_upper):
            return {
                "valid": False, "risk": "CRITICAL",
                "reason": f"Dangerous SQL operation detected: {op}",
                "needs_confirmation": False, "sensitive_column": None,
            }

    # Block injection patterns
    if contains_dangerous_sql(sql):
        return {
            "valid": False, "risk": "HIGH",
            "reason": "SQL injection pattern detected.",
            "needs_confirmation": False, "sensitive_column": None,
        }

    # Sensitive column check → MEDIUM risk, ask user
    for col in _SENSITIVE_COLS:
        # match as a column name token (not inside a string literal ideally)
        if re.search(rf"\b{col}\b", sql_lower):
            return {
                "valid": True, "risk": "MEDIUM",
                "reason": f"Sensitive column accessed: {col}",
                "needs_confirmation": True, "sensitive_column": col,
            }

    return {
        "valid": True, "risk": "LOW",
        "reason": "SQL is safe.",
        "needs_confirmation": False, "sensitive_column": None,
    }