"""
Ibtcode Integration for NL2SQL Clinic
Intent detection + Safety layer for SQL queries
"""

import os
import sys

# Add ibtcode to path
sys.path.insert(0, os.path.dirname(__file__))

from ibtcode.perception import detect_intent
from ibtcode.validation import validate_perception
from ibtcode.context import Context
from ibtcode.router import Router

# Global instances
ibt_context = Context()
ibt_router = Router()

# Define NL2SQL specific intents
NL2SQL_INTENTS = {
    "PATIENT_QUERY": ["patients", "patient", "registered", "city", "gender"],
    "DOCTOR_QUERY": ["doctors", "doctor", "specialization"],
    "APPOINTMENT_QUERY": ["appointments", "appointment", "schedule"],
    "FINANCIAL_QUERY": ["revenue", "invoice", "spending", "cost", "paid"],
    "SENSITIVE_QUERY": ["personal", "phone", "email", "address", "private"],
    "AGGREGATION_QUERY": ["count", "total", "average", "sum", "top", "max", "min"],
    "TIME_QUERY": ["month", "year", "date", "quarter", "trend"],
    "UNKNOWN": []
}

def classify_nl2sql_intent(question: str) -> dict:
    """
    Classify question into NL2SQL specific intent
    Returns: {"intent": str, "confidence": float, "needs_confirmation": bool}
    """
    question_lower = question.lower()
    
    # Check for sensitive data first
    for keyword in NL2SQL_INTENTS["SENSITIVE_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "SENSITIVE_QUERY",
                "confidence": 0.95,
                "needs_confirmation": True
            }
    
    # Check financial queries
    for keyword in NL2SQL_INTENTS["FINANCIAL_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "FINANCIAL_QUERY",
                "confidence": 0.9,
                "needs_confirmation": False
            }
    
    # Check patient queries
    for keyword in NL2SQL_INTENTS["PATIENT_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "PATIENT_QUERY",
                "confidence": 0.9,
                "needs_confirmation": False
            }
    
    # Check doctor queries
    for keyword in NL2SQL_INTENTS["DOCTOR_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "DOCTOR_QUERY",
                "confidence": 0.9,
                "needs_confirmation": False
            }
    
    # Check appointment queries
    for keyword in NL2SQL_INTENTS["APPOINTMENT_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "APPOINTMENT_QUERY",
                "confidence": 0.9,
                "needs_confirmation": False
            }
    
    # Check aggregation queries
    for keyword in NL2SQL_INTENTS["AGGREGATION_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "AGGREGATION_QUERY",
                "confidence": 0.85,
                "needs_confirmation": False
            }
    
    # Check time-based queries
    for keyword in NL2SQL_INTENTS["TIME_QUERY"]:
        if keyword in question_lower:
            return {
                "intent": "TIME_QUERY",
                "confidence": 0.85,
                "needs_confirmation": False
            }
    
    return {
        "intent": "UNKNOWN",
        "confidence": 0.5,
        "needs_confirmation": False
    }


def validate_sql_with_ibtcode(sql: str) -> dict:
    """
    Use Ibtcode safety rules to validate SQL
    """
    sql_upper = sql.upper()
    
    # Block dangerous operations
    dangerous_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return {
                "valid": False,
                "reason": f"Dangerous operation detected: {keyword}",
                "risk": "HIGH"
            }
    
    # Check for sensitive data access
    sensitive_columns = ["phone", "email", "address", "date_of_birth"]
    sql_lower = sql.lower()
    
    for col in sensitive_columns:
        if col in sql_lower:
            return {
                "valid": True,
                "reason": f"Sensitive column accessed: {col}",
                "risk": "MEDIUM",
                "needs_confirmation": True
            }
    
    return {
        "valid": True,
        "reason": "SQL is safe",
        "risk": "LOW",
        "needs_confirmation": False
    }


def get_route_based_on_intent(intent: str) -> str:
    """
    Decide which handler to use based on intent
    """
    routing_map = {
        "SENSITIVE_QUERY": "fallback",      # Use fallback with confirmation
        "FINANCIAL_QUERY": "agent",         # Use Vanna agent
        "PATIENT_QUERY": "fallback",        # Use direct SQL (faster)
        "DOCTOR_QUERY": "fallback",         # Use direct SQL (faster)
        "APPOINTMENT_QUERY": "agent",       # Use Vanna agent
        "AGGREGATION_QUERY": "fallback",    # Use direct SQL
        "TIME_QUERY": "agent",              # Use Vanna agent
        "UNKNOWN": "agent"                  # Try agent first
    }
    
    return routing_map.get(intent, "agent")


# For testing
if __name__ == "__main__":
    test_questions = [
        "Show me top 5 patients by spending",
        "What is total revenue?",
        "List all doctors",
        "Show me patient phone numbers",  # sensitive
        "DROP TABLE patients",            # dangerous
    ]
    
    for q in test_questions:
        intent = classify_nl2sql_intent(q)
        print(f"Q: {q}")
        print(f"  Intent: {intent}")
        print()