#!/usr/bin/env python3
"""
Step 1 & 2 — Create SQLite schema and insert realistic dummy data.
Production-ready with validation, logging, error handling, and performance optimization.

Run:  python setup_database.py
Output: clinic.db
"""

import sqlite3
import random
import os
import sys
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "./clinic.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('setup_database.log')
    ]
)
logger = logging.getLogger(__name__)

# ── Constants for reproducibility ─────────────────────────────────────────────
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ── Reference Data ────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Arjun", "Priya", "Rahul", "Sneha", "Vikram", "Anjali", "Karan", "Meera",
    "Suresh", "Divya", "Amit", "Pooja", "Rohit", "Neha", "Sandeep", "Kavya",
    "Manish", "Ritu", "Deepak", "Sunita", "Aditya", "Shruti", "Nitin", "Rekha",
    "Rajesh", "Geeta", "Vivek", "Lalita", "Sanjay", "Usha", "Tarun", "Seema",
    "Gaurav", "Nisha", "Pankaj", "Asha", "Hemant", "Radha", "Saurabh", "Manju",
    "Alok", "Vandana", "Manoj", "Savita", "Yogesh", "Pinki", "Rakesh", "Saroj",
    "Naveen", "Kamla",
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Gupta", "Joshi", "Mishra",
    "Yadav", "Tiwari", "Pandey", "Chaudhary", "Rao", "Nair", "Menon", "Reddy",
    "Iyer", "Shah", "Mehta", "Bose", "Das", "Chatterjee", "Mukherjee", "Sinha",
    "Jain", "Agarwal", "Kapoor", "Chopra", "Malhotra", "Khanna",
]

CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
]

SPECIALIZATIONS = [
    "Dermatology", "Cardiology", "Orthopedics", "General", "Pediatrics",
]

DEPT_MAP = {
    "Dermatology": "Skin & Aesthetics",
    "Cardiology": "Heart & Vascular",
    "Orthopedics": "Bone & Joint",
    "General": "General Medicine",
    "Pediatrics": "Child Health",
}

DOCTOR_NAMES = [
    "Dr. Ananya Krishnan", "Dr. Suresh Patil", "Dr. Kavita Mehra",
    "Dr. Rajiv Sharma", "Dr. Priti Desai", "Dr. Mohan Rao",
    "Dr. Sunita Agarwal", "Dr. Vikram Tiwari", "Dr. Leela Nair",
    "Dr. Arjun Kapoor", "Dr. Shalini Joshi", "Dr. Dinesh Gupta",
    "Dr. Rina Bose", "Dr. Kiran Patel", "Dr. Ajay Verma",
]

TREATMENT_NAMES = {
    "Dermatology": ["Acne Treatment", "Skin Biopsy", "Laser Therapy",
                    "Chemical Peel", "Mole Removal"],
    "Cardiology": ["ECG", "Echocardiogram", "Stress Test",
                   "Cardiac Catheterization", "Pacemaker Check"],
    "Orthopedics": ["X-Ray", "Physiotherapy Session", "Joint Injection",
                    "MRI Scan", "Cast Application"],
    "General": ["Blood Test", "Urine Analysis", "Vaccination",
                "Health Check-up", "BP Monitoring"],
    "Pediatrics": ["Child Vaccination", "Growth Assessment", "Nebulization",
                   "Developmental Screening", "Nutrition Counselling"],
}

STATUS_DIST = ["Scheduled", "Completed", "Cancelled", "No-Show"]
STATUS_WEIGHTS = [0.20, 0.55, 0.15, 0.10]
INVOICE_STATUS = ["Paid", "Pending", "Overdue"]
INVOICE_WEIGHTS = [0.55, 0.25, 0.20]

# ── Data Counts ───────────────────────────────────────────────────────────────
NUM_PATIENTS = 200
NUM_DOCTORS = 15
NUM_APPOINTMENTS = 500
NUM_TREATMENTS = 350
NUM_INVOICES = 300


# ── Helper Functions ──────────────────────────────────────────────────────────
def random_date(start_days_ago: int, end_days_ago: int = 0) -> date:
    """Generate random date between start_days_ago and end_days_ago from today."""
    start = date.today() - timedelta(days=start_days_ago)
    end = date.today() - timedelta(days=end_days_ago)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def random_datetime(start_days_ago: int) -> datetime:
    """Generate random datetime between start_days_ago and today."""
    d = random_date(start_days_ago)
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return datetime(d.year, d.month, d.day, hour, minute)


def maybe(value: any, chance: float = 0.85) -> any:
    """Return value with given probability, else None."""
    return value if random.random() < chance else None


def validate_database(cursor: sqlite3.Cursor) -> Dict[str, int]:
    """Validate database counts and return statistics."""
    tables = ['patients', 'doctors', 'appointments', 'treatments', 'invoices']
    stats = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]
    return stats


@contextmanager
def get_connection(db_path: str):
    """Context manager for database connections."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ── DDL Schema ────────────────────────────────────────────────────────────────
SCHEMA_DDL = """
-- Patients table
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    email           TEXT,
    phone           TEXT,
    date_of_birth   DATE,
    gender          TEXT CHECK (gender IN ('M', 'F')),
    city            TEXT,
    registered_date DATE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Doctors table
CREATE TABLE IF NOT EXISTS doctors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    specialization  TEXT,
    department      TEXT,
    phone           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Appointments table
CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER,
    doctor_id        INTEGER,
    appointment_date DATETIME,
    status           TEXT CHECK (status IN ('Scheduled', 'Completed', 'Cancelled', 'No-Show')),
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
);

-- Treatments table
CREATE TABLE IF NOT EXISTS treatments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id    INTEGER,
    treatment_name    TEXT,
    cost              REAL CHECK (cost >= 0),
    duration_minutes  INTEGER CHECK (duration_minutes > 0),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE
);

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER,
    invoice_date DATE,
    total_amount REAL CHECK (total_amount >= 0),
    paid_amount  REAL CHECK (paid_amount >= 0),
    status       TEXT CHECK (status IN ('Paid', 'Pending', 'Overdue')),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_patients_city ON patients(city);
CREATE INDEX IF NOT EXISTS idx_patients_registered ON patients(registered_date);
CREATE INDEX IF NOT EXISTS idx_doctors_specialization ON doctors(specialization);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_invoices_patient ON invoices(patient_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_treatments_appointment ON treatments(appointment_id);
"""


# ── Data Insertion Functions ─────────────────────────────────────────────────
def create_schema(cursor: sqlite3.Cursor) -> None:
    """Create database schema with all tables and indexes."""
    logger.info("Creating database schema...")
    cursor.executescript(SCHEMA_DDL)
    logger.info("Schema created successfully")


def insert_doctors(cursor: sqlite3.Cursor) -> List[int]:
    """Insert 15 doctors across 5 specializations."""
    logger.info(f"Inserting {NUM_DOCTORS} doctors...")
    doctor_ids = []
    
    # Distribute specializations evenly
    spec_cycle = SPECIALIZATIONS * (NUM_DOCTORS // len(SPECIALIZATIONS) + 1)
    
    for i, name in enumerate(DOCTOR_NAMES[:NUM_DOCTORS]):
        spec = spec_cycle[i % len(SPECIALIZATIONS)]
        dept = DEPT_MAP[spec]
        phone = maybe(f"+91-{random.randint(70000, 99999)}{random.randint(10000, 99999)}", 0.9)
        
        cursor.execute("""
            INSERT INTO doctors (name, specialization, department, phone) 
            VALUES (?, ?, ?, ?)
        """, (name, spec, dept, phone))
        
        doctor_ids.append(cursor.lastrowid)
    
    logger.info(f"Inserted {len(doctor_ids)} doctors")
    return doctor_ids


def insert_patients(cursor: sqlite3.Cursor, count: int = NUM_PATIENTS) -> List[int]:
    """Insert patients with realistic data distribution."""
    logger.info(f"Inserting {count} patients...")
    patient_ids = []
    
    for _ in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        email = maybe(f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@email.com", 0.8)
        phone = maybe(f"+91-{random.randint(70000, 99999)}{random.randint(10000, 99999)}", 0.85)
        dob = random_date(365 * 70, 365 * 5)  # Age between 5 and 70
        gender = random.choice(["M", "F"])
        city = random.choice(CITIES)
        registered_date = random_date(365, 0)  # Registered within last year
        
        cursor.execute("""
            INSERT INTO patients 
            (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (first_name, last_name, email, phone, dob.isoformat(), gender, city, registered_date.isoformat()))
        
        patient_ids.append(cursor.lastrowid)
    
    logger.info(f"Inserted {len(patient_ids)} patients")
    return patient_ids


def insert_appointments(
    cursor: sqlite3.Cursor,
    patient_ids: List[int],
    doctor_ids: List[int],
    count: int = NUM_APPOINTMENTS,
) -> List[Tuple[int, int, str]]:
    """Insert appointments with realistic distribution patterns."""
    logger.info(f"Inserting {count} appointments...")
    
    # 30% of patients are repeat visitors (3-8 visits each)
    repeat_count = int(len(patient_ids) * 0.30)
    repeat_patients = random.sample(patient_ids, min(repeat_count, len(patient_ids)))
    
    # Weight doctors to simulate busy/unbusy
    doc_weights = [random.uniform(0.5, 3.0) for _ in doctor_ids]
    total_weight = sum(doc_weights)
    doc_weights = [w / total_weight for w in doc_weights]
    
    # Build patient pool with repeats
    patient_pool = patient_ids.copy()
    for patient in repeat_patients:
        patient_pool.extend([patient] * random.randint(2, 7))
    random.shuffle(patient_pool)
    
    appointments = []
    
    for i in range(count):
        patient_id = patient_pool[i % len(patient_pool)]
        doctor_id = random.choices(doctor_ids, weights=doc_weights, k=1)[0]
        appointment_date = random_datetime(365)
        status = random.choices(STATUS_DIST, weights=STATUS_WEIGHTS, k=1)[0]
        notes = maybe(random.choice([
            "Follow-up required", "Patient reports improvement",
            "Urgent review needed", "Routine check", "New patient",
            "Post-surgery follow-up", "Medication review"
        ]), 0.6)
        
        cursor.execute("""
            INSERT INTO appointments 
            (patient_id, doctor_id, appointment_date, status, notes) 
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, doctor_id, appointment_date.isoformat(), status, notes))
        
        appointments.append((cursor.lastrowid, doctor_id, status))
    
    logger.info(f"Inserted {len(appointments)} appointments")
    return appointments


def insert_treatments(
    cursor: sqlite3.Cursor,
    appointments: List[Tuple[int, int, str]],
    doctor_ids: List[int],
    count: int = NUM_TREATMENTS,
) -> None:
    """Insert treatments only for completed appointments."""
    logger.info(f"Inserting {count} treatments...")
    
    # Only completed appointments get treatments
    completed_appointments = [a for a in appointments if a[2] == "Completed"]
    
    if len(completed_appointments) > count:
        completed_appointments = random.sample(completed_appointments, count)
    
    # Get doctor specialization mapping
    cursor.execute("SELECT id, specialization FROM doctors")
    doctor_specialization = {row[0]: row[1] for row in cursor.fetchall()}
    
    treatments_inserted = 0
    for appointment_id, doctor_id, _ in completed_appointments:
        specialization = doctor_specialization.get(doctor_id, "General")
        treatment_names = TREATMENT_NAMES.get(specialization, TREATMENT_NAMES["General"])
        treatment_name = random.choice(treatment_names)
        cost = round(random.uniform(50, 5000), 2)
        duration = random.randint(15, 120)
        
        cursor.execute("""
            INSERT INTO treatments 
            (appointment_id, treatment_name, cost, duration_minutes) 
            VALUES (?, ?, ?, ?)
        """, (appointment_id, treatment_name, cost, duration))
        
        treatments_inserted += 1
    
    logger.info(f"Inserted {treatments_inserted} treatments")


def insert_invoices(
    cursor: sqlite3.Cursor,
    patient_ids: List[int],
    count: int = NUM_INVOICES,
) -> None:
    """Insert invoices with realistic payment status distribution."""
    logger.info(f"Inserting {count} invoices...")
    
    # Some patients may have multiple invoices
    patient_pool = random.choices(patient_ids, k=count)
    
    invoices_inserted = 0
    for patient_id in patient_pool:
        total_amount = round(random.uniform(100, 10000), 2)
        status = random.choices(INVOICE_STATUS, weights=INVOICE_WEIGHTS, k=1)[0]
        
        if status == "Paid":
            paid_amount = total_amount
        elif status == "Pending":
            paid_amount = round(random.uniform(0, total_amount * 0.3), 2)
        else:  # Overdue
            paid_amount = round(random.uniform(0, total_amount * 0.5), 2)
        
        invoice_date = random_date(365, 0)
        
        cursor.execute("""
            INSERT INTO invoices 
            (patient_id, invoice_date, total_amount, paid_amount, status) 
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, invoice_date.isoformat(), total_amount, paid_amount, status))
        
        invoices_inserted += 1
    
    logger.info(f"Inserted {invoices_inserted} invoices")


# ── Main Execution ────────────────────────────────────────────────────────────
def print_summary(stats: Dict[str, int], db_path: Path) -> None:
    """Print formatted summary of database creation."""
    print("\n" + "=" * 60)
    print("  DATABASE CREATED SUCCESSFULLY")
    print("=" * 60)
    print(f"  Database Path: {db_path.resolve()}")
    print(f"  Database Size: {db_path.stat().st_size / 1024:.2f} KB")
    print("-" * 60)
    print("  TABLE COUNTS:")
    for table, count in stats.items():
        print(f"    • {table.capitalize():12} : {count:6,}")
    print("-" * 60)
    print(f"  Total Records : {sum(stats.values()):,}")
    print("=" * 60)
    print("\n  ✅ Database is ready for use!")
    print("  ▶ Run: python seed_memory.py")
    print("  ▶ Run: uvicorn main:app --reload")
    print("=" * 60)


def main() -> None:
    """Main execution function with error handling."""
    start_time = datetime.now()
    logger.info("Starting database setup...")
    
    db_path = Path(DB_PATH)
    
    # Remove existing database if it exists
    if db_path.exists():
        logger.info(f"Removing existing database: {db_path}")
        db_path.unlink()
    
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # Create schema
            create_schema(cursor)
            
            # Insert data in correct order (respecting foreign keys)
            doctor_ids = insert_doctors(cursor)
            patient_ids = insert_patients(cursor)
            appointments = insert_appointments(cursor, patient_ids, doctor_ids)
            insert_treatments(cursor, appointments, doctor_ids)
            insert_invoices(cursor, patient_ids)
            
            # Validate and get statistics
            stats = validate_database(cursor)
            
            # Print summary
            print_summary(stats, db_path)
            
            # Log completion
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"Database setup completed in {elapsed:.2f} seconds")
            
            # Verify data integrity
            if stats['patients'] != NUM_PATIENTS:
                logger.warning(f"Expected {NUM_PATIENTS} patients, got {stats['patients']}")
            if stats['doctors'] != NUM_DOCTORS:
                logger.warning(f"Expected {NUM_DOCTORS} doctors, got {stats['doctors']}")
            
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()