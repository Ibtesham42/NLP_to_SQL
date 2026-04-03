"""
Ibtcode Validation Layer - Production Grade
Features: Profanity filtering, SQL injection detection, intent validation, context awareness
"""

import re
import time
from typing import Dict, Any, Optional, List

# =========================
# PROFANITY FILTER
# =========================

PROFANITY_LIST = [
    "fuk", "fuck", "shit", "damn", "hell", "ass", "bitch", 
    "crap", "bloody", "bastard", "dick", "piss", "suck",
    "fck", "fukc", "b8tch", "b1tch", "b!tch", "f@ck", "f#ck",
    "motherfucker", "mf", "wtf", "stfu", "gtfo"
]

PROFANITY_PATTERNS = [
    r"f[u3@][ck]+",
    r"s[h!][i1][t7]+",
    r"b[i1][t7][c][h]",
    r"d[a@4][m][n]",
    r"h[e3][l1][l]",
]

def contains_profanity(text: str) -> bool:
    """Check if text contains profanity"""
    if not text:
        return False
    text_lower = text.lower()
    for word in PROFANITY_LIST:
        if word in text_lower:
            return True
    for pattern in PROFANITY_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def get_profanity_message() -> str:
    return "Your query contains inappropriate language. Please rephrase respectfully."


# =========================
# DANGEROUS KEYWORDS (Input Level)
# =========================

DANGEROUS_KEYWORDS = [
    "drop", "delete", "truncate", "alter", "create", "insert", "update",
    "drop table", "delete from", "truncate table", "alter table", "create table"
]

def contains_dangerous_keyword(text: str) -> tuple:
    """Check if text contains dangerous keywords. Returns (bool, keyword)"""
    if not text:
        return False, None
    text_lower = text.lower()
    for keyword in DANGEROUS_KEYWORDS:
        if keyword in text_lower:
            return True, keyword
    return False, None


# =========================
# SQL INJECTION PATTERNS
# =========================

DANGEROUS_SQL_PATTERNS = [
    r"\bDROP\s+TABLE\b",
    r"\bDROP\b",
    r"\bDELETE\s+FROM\b",
    r"\bDELETE\b",
    r"\bUPDATE\s+.+\s+SET\b",
    r"\bUPDATE\b",
    r"\bINSERT\s+INTO\b",
    r"\bALTER\s+TABLE\b",
    r"\bCREATE\s+TABLE\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"--",
    r"/\*",
    r"xp_",
    r"sp_",
    r"\bUNION\b",
    r"\bOR\s+1=1\b",
    r";\s*DROP",
    r";\s*DELETE",
    r";\s*UPDATE",
]

def contains_dangerous_sql(text: str) -> bool:
    """Check if text contains dangerous SQL patterns"""
    if not text:
        return False
    text_upper = text.upper()
    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, text_upper, re.IGNORECASE):
            return True
    return False


# =========================
# INTENT VALIDATION
# =========================

ALL_INTENTS = [
    "PASSWORD_RESET", "ESCALATE", "ACCOUNT_HACKED",
    "PATIENT_QUERY", "DOCTOR_QUERY", "APPOINTMENT_QUERY",
    "FINANCIAL_QUERY", "SENSITIVE_QUERY", "AGGREGATION_QUERY",
    "TIME_QUERY", "GENERAL_QUERY", "UNKNOWN"
]

INTENT_THRESHOLDS = {
    "PASSWORD_RESET": 0.75,
    "ESCALATE": 0.9,
    "ACCOUNT_HACKED": 0.85,
    "PATIENT_QUERY": 0.7,
    "DOCTOR_QUERY": 0.7,
    "APPOINTMENT_QUERY": 0.7,
    "FINANCIAL_QUERY": 0.7,
    "SENSITIVE_QUERY": 0.8,
    "AGGREGATION_QUERY": 0.7,
    "TIME_QUERY": 0.7,
    "GENERAL_QUERY": 0.6,
}


# =========================
# MAIN VALIDATION FUNCTION
# =========================

def validate_perception(perception: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Production-grade validation layer
    
    Args:
        perception: Dict with "intent", "confidence", "raw_input"
        context: Optional dict with "last_intent", "last_timestamp"
    
    Returns:
        Validation result with status and details
    """
    
    intent = perception.get("intent", "UNKNOWN")
    confidence = perception.get("confidence", 0.0)
    raw_input = perception.get("raw_input", "")
    
    # =========================
    # 1. PROFANITY CHECK (HIGHEST PRIORITY)
    # =========================
    if raw_input and contains_profanity(raw_input):
        return {
            "status": "REJECT",
            "reason": "profanity_detected",
            "message": get_profanity_message(),
            "blocked": True,
            "intent": "BLOCKED"
        }
    
    # =========================
    # 2. DANGEROUS KEYWORD CHECK
    # =========================
    has_dangerous, keyword = contains_dangerous_keyword(raw_input)
    if has_dangerous:
        return {
            "status": "CONFIRM",
            "reason": "dangerous_keyword_detected",
            "message": f"This is a destructive action ('{keyword.upper()}'). Do you want to proceed?",
            "blocked": False,
            "intent": "DESTRUCTIVE_QUERY",
            "keyword": keyword,
            "requires_confirmation": True
        }
    
    # =========================
    # 3. SQL INJECTION CHECK
    # =========================
    if raw_input and contains_dangerous_sql(raw_input):
        return {
            "status": "REJECT",
            "reason": "dangerous_sql_pattern",
            "message": "Your query contains potentially dangerous SQL patterns. This has been blocked.",
            "blocked": True,
            "intent": "BLOCKED"
        }
    
    # =========================
    # 4. UNKNOWN INTENT
    # =========================
    if intent == "UNKNOWN":
        return {
            "status": "CLARIFY",
            "reason": "unknown_intent",
            "message": "I didn't understand your query. Can you please rephrase?",
            "candidates": ["PATIENT_QUERY", "DOCTOR_QUERY", "FINANCIAL_QUERY", "APPOINTMENT_QUERY"]
        }
    
    # =========================
    # 5. EMPTY OR TOO SHORT
    # =========================
    if raw_input and len(raw_input.strip()) < 3:
        return {
            "status": "CLARIFY",
            "reason": "too_short",
            "message": "Your query is too short. Please provide more details.",
            "candidates": ALL_INTENTS
        }
    
    # =========================
    # 6. CONFIDENCE CHECK
    # =========================
    threshold = INTENT_THRESHOLDS.get(intent, 0.7)
    
    if confidence < threshold:
        return {
            "status": "CLARIFY",
            "reason": "low_confidence",
            "message": f"I'm not fully sure about your intent ({int(confidence*100)}% confidence). Can you please rephrase?",
            "intent": intent,
            "confidence": confidence,
            "threshold": threshold,
            "candidates": ["PATIENT_QUERY", "DOCTOR_QUERY", "FINANCIAL_QUERY", "APPOINTMENT_QUERY", "TIME_QUERY"]
        }
    
    # =========================
    # 7. AMBIGUOUS ESCALATION
    # =========================
    if intent == "ESCALATE" and confidence < 0.95:
        return {
            "status": "CLARIFY",
            "reason": "ambiguous_escalation",
            "message": "Do you want to speak with a human agent or need password support?",
            "candidates": ["ESCALATE", "PASSWORD_RESET"]
        }
    
    # =========================
    # 8. CONTEXT-AWARE SAFETY
    # =========================
    if context:
        last_intent = context.get("last_intent")
        
        if last_intent == intent and intent == "ACCOUNT_HACKED":
            return {
                "status": "CLARIFY",
                "reason": "repeat_sensitive_intent",
                "message": "You already reported this. Do you want further action?",
                "candidates": [intent, "CANCEL"]
            }
        
        last_timestamp = context.get("last_timestamp")
        if last_timestamp:
            current_time = time.time()
            if current_time - last_timestamp < 2:
                return {
                    "status": "CLARIFY",
                    "reason": "rate_limit_intent",
                    "message": "Please slow down. Wait a moment before submitting another query.",
                    "candidates": ALL_INTENTS
                }
    
    # =========================
    # 9. SENSITIVE INTENT WARNING
    # =========================
    if intent == "SENSITIVE_QUERY":
        return {
            "status": "WARNING",
            "reason": "sensitive_intent",
            "message": "This query may access sensitive patient data. Please confirm if you want to proceed.",
            "intent": intent,
            "confidence": confidence,
            "requires_confirmation": True
        }
    
    # =========================
    # 10. FINAL ACCEPT
    # =========================
    return {
        "status": "VALID",
        "intent": intent,
        "confidence": confidence,
        "message": f"Intent validated: {intent}"
    }


def sanitize_user_input(user_input: str) -> str:
    """Sanitize user input by removing profanity"""
    if not user_input:
        return user_input
    sanitized = user_input
    for word in PROFANITY_LIST:
        if word in sanitized.lower():
            sanitized = re.sub(re.escape(word), "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


def validate_sql_query(sql: str) -> Dict[str, Any]:
    """
    Validate generated SQL for safety before execution
    """
    if not sql:
        return {"valid": False, "reason": "Empty SQL", "risk": "HIGH"}
    
    sql_upper = sql.upper()
    
    # Block dangerous operations
    dangerous_ops = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "EXEC"]
    for op in dangerous_ops:
        if re.search(rf"\b{op}\b", sql_upper):
            return {
                "valid": False,
                "reason": f"Dangerous SQL operation detected: {op}",
                "risk": "CRITICAL"
            }
    
    # Check for sensitive columns
    sensitive_columns = ["phone", "email", "address", "date_of_birth", "dob"]
    sql_lower = sql.lower()
    
    for col in sensitive_columns:
        if col in sql_lower:
            return {
                "valid": True,
                "reason": f"Sensitive column accessed: {col}",
                "risk": "MEDIUM",
                "needs_confirmation": True,
                "sensitive_column": col
            }
    
    return {
        "valid": True,
        "reason": "SQL is safe",
        "risk": "LOW",
        "needs_confirmation": False
    }


# =========================
# TEST FUNCTION
# =========================

if __name__ == "__main__":
    test_inputs = [
        "fuk u show me patients",
        "How many patients do we have?",
        "DROP TABLE patients",
        "Drop patient Kamla",
        "delete from patients",
        "show me patient phone numbers",
        "a",
        "help me with password"
    ]
    
    print("=" * 70)
    print("Validation Layer Test")
    print("=" * 70)
    
    for test in test_inputs:
        perception = {"intent": "UNKNOWN", "confidence": 0.5, "raw_input": test}
        result = validate_perception(perception)
        print(f"\nInput: {test}")
        print(f"Status: {result['status']}")
        if result.get('blocked'):
            print(f"BLOCKED: {result.get('message', '')[:80]}")
        else:
            print(f"Message: {result.get('message', 'N/A')[:80]}")
    
    print("\n" + "=" * 70)
    print("SQL Validation Test")
    print("=" * 70)
    
    sql_tests = [
        "SELECT * FROM patients",
        "SELECT phone, email FROM patients",
        "DROP TABLE patients",
        "DELETE FROM patients WHERE id=1"
    ]
    
    for sql in sql_tests:
        result = validate_sql_query(sql)
        print(f"\nSQL: {sql}")
        print(f"Valid: {result['valid']}, Risk: {result.get('risk', 'UNKNOWN')}")
        if not result['valid']:
            print(f"Reason: {result['reason']}")