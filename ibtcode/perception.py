def detect_intent(user_message: str) -> dict:
    msg = user_message.lower()

    # PASSWORD RESET
    if any(word in msg for word in ["reset", "forgot", "password", "login"]):
        return {"intent": "PASSWORD_RESET", "confidence": 0.9}

    # ESCALATE
    elif any(word in msg for word in ["agent", "human", "help"]):
        return {"intent": "ESCALATE", "confidence": 0.95}

    # ACCOUNT HACKED
    elif any(word in msg for word in ["hack", "hacked", "fraud", "unauthorized"]):
        return {"intent": "ACCOUNT_HACKED", "confidence": 0.95}

    # PATIENT QUERIES
    elif any(word in msg for word in ["patients", "patient", "registered", "city", "gender"]):
        return {"intent": "PATIENT_QUERY", "confidence": 0.9}

    # DOCTOR QUERIES
    elif any(word in msg for word in ["doctors", "doctor", "specialization", "department"]):
        return {"intent": "DOCTOR_QUERY", "confidence": 0.9}

    # APPOINTMENT QUERIES
    elif any(word in msg for word in ["appointments", "appointment", "schedule", "booking", "visit"]):
        return {"intent": "APPOINTMENT_QUERY", "confidence": 0.9}

    # FINANCIAL QUERIES
    elif any(word in msg for word in ["revenue", "invoice", "spending", "cost", "paid", "total", "amount"]):
        return {"intent": "FINANCIAL_QUERY", "confidence": 0.85}

    # SENSITIVE QUERIES
    elif any(word in msg for word in ["phone", "email", "address", "private", "personal", "dob", "birth"]):
        return {"intent": "SENSITIVE_QUERY", "confidence": 0.95}

    # AGGREGATION QUERIES
    elif any(word in msg for word in ["count", "average", "sum", "top", "max", "min", "highest"]):
        return {"intent": "AGGREGATION_QUERY", "confidence": 0.85}

    # TIME QUERIES
    elif any(word in msg for word in ["month", "year", "date", "quarter", "trend", "weekly", "daily"]):
        return {"intent": "TIME_QUERY", "confidence": 0.85}

    # UNKNOWN
    else:
        return {"intent": "UNKNOWN", "confidence": 0.5}