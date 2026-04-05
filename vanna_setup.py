"""
NL2SQL Clinic — LLM Setup (Groq Direct)

ROOT CAUSE OF VANNA AGENT FAILURE:
  Vanna 2.0's Agent sends tool/function schemas to Groq in a format that
  llama-3.3-70b-versatile rejects → "Failed to call a function" on EVERY
  request regardless of prompt wording.  This is a Vanna 2.0 ↔ Groq
  incompatibility, not a prompt problem.

FIX:
  Bypass the Vanna Agent entirely.  Call Groq directly via the OpenAI
  client (Groq exposes an OpenAI-compatible /v1/chat/completions endpoint).
  We ask the model to return ONLY a SQL query — no tools, no streaming
  quirks, no schema mismatch.  The response is deterministic plain text
  that we validate and execute ourselves.

  get_agent() now returns a lightweight GroqDirectClient wrapper so
  main.py needs zero changes to its import / call surface.
"""

import os
import logging
import re
from functools import lru_cache
from dotenv import load_dotenv
from openai import OpenAI          # Groq's OpenAI-compatible SDK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH   = "./clinic.db"
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"
DEFAULT_MODEL     = "llama-3.3-70b-versatile"

# ── System Prompt ──────────────────────────────────────────────────────────────
# Plain-text SQL generation — NO tool-calling, NO JSON wrapper.
# The model returns a bare SELECT statement and nothing else.

SYSTEM_PROMPT = """You are an expert SQLite query generator for a clinic management database.

Your ONLY job: convert the user's question into a single valid SQLite SELECT query.


FLIPPED INTERACTION (INTERNAL — DO NOT SHOW)

Before generating SQL, internally analyze:

- What exactly is the user asking?
- Which tables are required?
- What joins are needed?
- Is aggregation required (COUNT, SUM, AVG)?
- Are filters required (date, status, city, etc.)?
- Is ranking required (ORDER BY, LIMIT)?

Use this internally to improve accuracy.
DO NOT show reasoning.


INTERNAL QUERY REFINEMENT (HIDDEN)

- Rewrite the user question into precise SQL intent
- Identify:
  • Entities (patients, doctors, appointments, invoices, etc.)
  • Metrics (count, revenue, average, etc.)
  • Constraints (date filters, status, grouping)

DO NOT show this.


SELF-VALIDATION LOOP (CRITICAL — INTERNAL)
Before returning SQL, check:

- Does query fully answer the question?
- Are all tables and columns valid?
- Are joins correct and complete?
- Is aggregation correct with proper GROUP BY?
- Is ORDER BY / LIMIT used when needed?

If ANY issue → fix internally before output.

DO NOT show this process.


OUTPUT RULES — CRITICAL
- Output the SQL query and absolutely nothing else.
- No explanation, no markdown, no code fences, no commentary.
- No ```sql blocks. Raw SQL only.
- The query MUST start with SELECT or WITH.


DATABASE SCHEMA
TABLE patients (
  id INTEGER PRIMARY KEY,
  first_name TEXT, last_name TEXT, email TEXT, phone TEXT,
  date_of_birth DATE, gender TEXT, city TEXT, registered_date DATE
)

TABLE doctors (
  id INTEGER PRIMARY KEY,
  name TEXT, specialization TEXT, department TEXT, phone TEXT
)

TABLE appointments (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER,
  doctor_id  INTEGER,
  appointment_date DATETIME,
  status TEXT,
  notes TEXT
)

TABLE treatments (
  id INTEGER PRIMARY KEY,
  appointment_id INTEGER,
  treatment_name TEXT, cost REAL, duration_minutes INTEGER
)

TABLE invoices (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER,
  invoice_date DATE,
  total_amount REAL, paid_amount REAL,
  status TEXT
)

SQL RULES
- Only SELECT queries. Never INSERT/UPDATE/DELETE/DROP/ALTER.
- Use aliases:
  patients → p
  doctors → d
  appointments → a
  treatments → t
  invoices → i

- Use:
  COUNT() → totals
  SUM() → revenue
  AVG() → averages

- Always use GROUP BY when aggregation is present
- Use ORDER BY + LIMIT for top-N queries

- Date grouping:
  strftime('%Y-%m', column)

- Date filtering:
  date('now', '-N months') or date('now', '-N days')

- Never query sqlite_master or system tables
- Never use columns not defined in schema


EXAMPLES

Q: How many patients do we have?
A: SELECT COUNT(*) AS total_patients FROM patients

Q: Top 5 patients by spending
A: SELECT p.first_name, p.last_name, SUM(i.total_amount) AS total_spent
FROM patients p
JOIN invoices i ON p.id = i.patient_id
GROUP BY p.id
ORDER BY total_spent DESC
LIMIT 5

Q: Show revenue by doctor
A: SELECT d.name, d.specialization, SUM(i.total_amount) AS total_revenue
FROM invoices i
JOIN appointments a ON a.patient_id = i.patient_id
JOIN doctors d ON d.id = a.doctor_id
GROUP BY d.id
ORDER BY total_revenue DESC

Q: List all doctors
A: SELECT name, specialization, department FROM doctors ORDER BY specialization

Q: Monthly appointment count for the past 6 months
A: SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS appointments
FROM appointments
WHERE appointment_date >= date('now', '-6 months')
GROUP BY month ORDER BY month

Q: What percentage of appointments are no-shows?
A: SELECT ROUND(100.0 * SUM(CASE WHEN status = 'No-Show' THEN 1 ELSE 0 END) / COUNT(*), 2) AS no_show_percentage
FROM appointments


FINAL INSTRUCTION

Think carefully, validate internally, and return ONLY the final SQL query.
"""


#  Groq Direct Client 

class GroqDirectClient:
    """
    Lightweight wrapper around the Groq/OpenAI client.
    Replaces the Vanna Agent with a simple chat-completion call.

    Interface kept identical to what main.py expects:
      - client.generate_sql(question) -> str  (raw SQL)
      - client.agent_memory            -> list (for /health endpoint)
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model  = model
        self.agent_memory: list = []   # kept for /health compatibility
        logger.info(f"GroqDirectClient ready (model={model})")

    def generate_sql(self, question: str) -> str:
        """
        Send the question to Groq and return the raw SQL string.
        Raises ValueError if the response does not look like SQL.
        """
        logger.info(f"[GROQ] Sending question: {question[:120]!r}")

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            temperature=0.0,      # deterministic SQL generation
            max_tokens=512,
            stream=False,         # simple blocking call — no streaming headaches
        )

        raw = response.choices[0].message.content or ""
        sql = self._clean_sql(raw)

        logger.info(f"[GROQ] Raw response : {raw[:300]!r}")
        logger.info(f"[GROQ] Cleaned SQL  : {sql[:300]!r}")

        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            raise ValueError(
                f"Groq returned non-SQL: {sql[:200]!r}"
            )

        return sql

    @staticmethod
    def _clean_sql(text: str) -> str:
        """Strip markdown fences, backticks, and whitespace."""
        text = text.strip()
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$",          "", text)
        text = text.replace("`", "")
        return text.strip()


# ── Config Validation ──────────────────────────────────────────────────────────

def validate_config() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your key from https://console.groq.com\n"
            "  3. Restart the server."
        )
    if not api_key.startswith("gsk_"):
        logger.warning("GROQ_API_KEY does not start with 'gsk_' — verify the key.")

    db_path = os.getenv("DB_PATH", DEFAULT_DB_PATH)
    if not os.path.exists(db_path):
        logger.warning(f"Database not found at '{db_path}'. Run setup_database.py first.")

    logger.info("Configuration validated.")


# ── Singleton Factory ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_agent() -> GroqDirectClient:
    """
    Returns the singleton GroqDirectClient.
    Named get_agent() so main.py import does not change.
    """
    logger.info("Initializing GroqDirectClient...")
    validate_config()

    client = GroqDirectClient(
        api_key  = os.getenv("GROQ_API_KEY"),
        model    = os.getenv("LLM_MODEL", DEFAULT_MODEL),
        base_url = GROQ_BASE_URL,
    )
    logger.info("GroqDirectClient initialized successfully.")
    return client


# ── Health / Utility ───────────────────────────────────────────────────────────

def health_check() -> dict:
    try:
        client = get_agent()
        return {"status": "healthy", "agent_ready": client is not None}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def cleanup_agent() -> None:
    get_agent.cache_clear()
    logger.info("Agent cache cleared.")


def validate_environment() -> list[str]:
    issues = []
    if not os.getenv("GROQ_API_KEY"):
        issues.append("GROQ_API_KEY is missing")
    if not os.path.exists(os.getenv("DB_PATH", DEFAULT_DB_PATH)):
        issues.append(f"Database not found at {os.getenv('DB_PATH', DEFAULT_DB_PATH)}")
    return issues


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing GroqDirectClient...")
    issues = validate_environment()
    if issues:
        for i in issues:
            print(f"  - {i}")
    else:
        try:
            client = get_agent()
            sql = client.generate_sql("How many patients do we have?")
            print(f"  SQL: {sql}")
        except Exception as e:
            print(f"  Failed: {e}")