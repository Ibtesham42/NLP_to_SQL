"""
SQL safety validator + question input validator.
"""

import re
from dataclasses import dataclass


# ── SQL Validation ────────────────────────────────────────────────────────────

FORBIDDEN_STATEMENTS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "MERGE", "EXEC", "EXECUTE",
}

DANGEROUS_PATTERNS = [
    r"\bEXEC\b",
    r"\bxp_",
    r"\bsp_",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bSHUTDOWN\b",
    r"sqlite_master",
    r"sqlite_sequence",
    r"information_schema",
    r"sys\.",
    r"--",          # SQL comment injection
    r"/\*",        # Block comment
]


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None


def validate_sql(sql: str) -> ValidationResult:
    """
    Returns ValidationResult.
    Rejects anything that isn't a safe SELECT statement.
    """
    if not sql or not sql.strip():
        return ValidationResult(valid=False, error="Empty SQL query.")

    normalised = sql.strip().upper()

    # Must start with SELECT
    if not normalised.startswith("SELECT"):
        return ValidationResult(
            valid=False,
            error="Only SELECT statements are permitted.",
        )

    # No forbidden DML/DDL
    for word in FORBIDDEN_STATEMENTS:
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, normalised):
            return ValidationResult(
                valid=False,
                error=f"Forbidden SQL operation detected: {word}",
            )

    # No dangerous patterns
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, sql, re.IGNORECASE):
            return ValidationResult(
                valid=False,
                error=f"Dangerous SQL pattern detected.",
            )

    return ValidationResult(valid=True)


# ── Question Validation ───────────────────────────────────────────────────────

MAX_QUESTION_LENGTH = 500
MIN_QUESTION_LENGTH = 3


def validate_question(question: str) -> ValidationResult:
    if not question or not question.strip():
        return ValidationResult(valid=False, error="Question cannot be empty.")

    q = question.strip()

    if len(q) < MIN_QUESTION_LENGTH:
        return ValidationResult(
            valid=False,
            error=f"Question too short (min {MIN_QUESTION_LENGTH} characters).",
        )

    if len(q) > MAX_QUESTION_LENGTH:
        return ValidationResult(
            valid=False,
            error=f"Question too long (max {MAX_QUESTION_LENGTH} characters).",
        )

    # Reject pure whitespace / special-character spam
    if not re.search(r"[a-zA-Z]", q):
        return ValidationResult(
            valid=False,
            error="Question must contain at least some text.",
        )

    return ValidationResult(valid=True)
