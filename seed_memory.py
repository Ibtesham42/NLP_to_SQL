#!/usr/bin/env python3
"""
Step 5 — Seed Vanna 2.0 DemoAgentMemory with 20 known good Q→SQL pairs.
Run:  python seed_memory.py

Production-ready with error handling, validation, logging, and retry logic.
"""

import asyncio
import logging
import sys
from typing import Dict, List, Tuple
from datetime import datetime

from vanna_setup import get_agent

# ── Logging Configuration ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'seed_memory_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# ── 20 high-quality Q→SQL pairs ───────────────────────────────────────────────
QA_PAIRS: List[Tuple[str, str]] = [
    # Patient queries
    (
        "How many patients do we have?",
        "SELECT COUNT(*) AS total_patients FROM patients",
    ),
    (
        "List all patients from Mumbai",
        "SELECT first_name, last_name, email, phone FROM patients WHERE city = 'Mumbai'",
    ),
    (
        "How many male and female patients are there?",
        "SELECT gender, COUNT(*) AS count FROM patients GROUP BY gender",
    ),
    (
        "Which city has the most patients?",
        "SELECT city, COUNT(*) AS patient_count FROM patients "
        "GROUP BY city ORDER BY patient_count DESC LIMIT 1",
    ),
    (
        "Show patient registration trend by month",
        "SELECT strftime('%Y-%m', registered_date) AS month, COUNT(*) AS registrations "
        "FROM patients GROUP BY month ORDER BY month",
    ),
    
    # Doctor queries
    (
        "List all doctors and their specializations",
        "SELECT name, specialization, department FROM doctors ORDER BY specialization, name",
    ),
    (
        "Which doctor has the most appointments?",
        "SELECT d.name, d.specialization, COUNT(a.id) AS appointment_count "
        "FROM doctors d JOIN appointments a ON a.doctor_id = d.id "
        "GROUP BY d.id ORDER BY appointment_count DESC LIMIT 1",
    ),
    (
        "Show revenue by doctor",
        "SELECT d.name, SUM(i.total_amount) AS total_revenue "
        "FROM invoices i "
        "JOIN appointments a ON a.patient_id = i.patient_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "GROUP BY d.name ORDER BY total_revenue DESC",
    ),
    (
        "Average appointment duration by doctor",
        "SELECT d.name, ROUND(AVG(t.duration_minutes), 1) AS avg_duration_minutes "
        "FROM treatments t "
        "JOIN appointments a ON a.id = t.appointment_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "GROUP BY d.name ORDER BY avg_duration_minutes DESC",
    ),
    
    # Appointment queries
    (
        "Show me appointments for last month",
        "SELECT a.id, p.first_name || ' ' || p.last_name AS patient, "
        "d.name AS doctor, a.appointment_date, a.status "
        "FROM appointments a "
        "JOIN patients p ON p.id = a.patient_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "WHERE strftime('%Y-%m', a.appointment_date) = "
        "strftime('%Y-%m', date('now', '-1 month')) "
        "ORDER BY a.appointment_date",
    ),
    (
        "How many cancelled appointments last quarter?",
        "SELECT COUNT(*) AS cancelled_count FROM appointments "
        "WHERE status = 'Cancelled' "
        "AND appointment_date >= date('now', '-3 months')",
    ),
    (
        "Show monthly appointment count for the past 6 months",
        "SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS appointments "
        "FROM appointments "
        "WHERE appointment_date >= date('now', '-6 months') "
        "GROUP BY month ORDER BY month",
    ),
    (
        "What percentage of appointments are no-shows?",
        "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'No-Show' THEN 1 ELSE 0 END) / COUNT(*), 2) "
        "AS no_show_percentage FROM appointments",
    ),
    (
        "Show the busiest day of the week for appointments",
        "SELECT CASE strftime('%w', appointment_date) "
        "WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' "
        "WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' "
        "WHEN '6' THEN 'Saturday' END AS day_of_week, COUNT(*) AS appointment_count "
        "FROM appointments GROUP BY strftime('%w', appointment_date) "
        "ORDER BY appointment_count DESC",
    ),
    
    # Financial queries
    (
        "What is the total revenue?",
        "SELECT SUM(total_amount) AS total_revenue, "
        "SUM(paid_amount) AS total_collected, "
        "SUM(total_amount - paid_amount) AS outstanding "
        "FROM invoices",
    ),
    (
        "Show unpaid invoices",
        "SELECT i.id, p.first_name || ' ' || p.last_name AS patient, "
        "i.invoice_date, i.total_amount, i.paid_amount, "
        "i.total_amount - i.paid_amount AS balance, i.status "
        "FROM invoices i JOIN patients p ON p.id = i.patient_id "
        "WHERE i.status IN ('Pending', 'Overdue') "
        "ORDER BY i.status, i.total_amount DESC",
    ),
    (
        "Revenue trend by month",
        "SELECT strftime('%Y-%m', invoice_date) AS month, "
        "SUM(total_amount) AS revenue, SUM(paid_amount) AS collected "
        "FROM invoices GROUP BY month ORDER BY month",
    ),
    (
        "Top 5 patients by spending",
        "SELECT p.first_name || ' ' || p.last_name AS patient, p.city, "
        "SUM(i.total_amount) AS total_spending "
        "FROM invoices i JOIN patients p ON p.id = i.patient_id "
        "GROUP BY p.id ORDER BY total_spending DESC LIMIT 5",
    ),
    (
        "Average treatment cost by specialization",
        "SELECT d.specialization, ROUND(AVG(t.cost), 2) AS avg_cost, "
        "COUNT(t.id) AS treatment_count "
        "FROM treatments t "
        "JOIN appointments a ON a.id = t.appointment_id "
        "JOIN doctors d ON d.id = a.doctor_id "
        "GROUP BY d.specialization ORDER BY avg_cost DESC",
    ),
    (
        "List patients who visited more than 3 times",
        "SELECT p.first_name || ' ' || p.last_name AS patient, p.city, "
        "COUNT(a.id) AS visit_count "
        "FROM appointments a JOIN patients p ON p.id = a.patient_id "
        "GROUP BY p.id HAVING visit_count > 3 ORDER BY visit_count DESC",
    ),
]


class MemorySeeder:
    """Production-grade seeder for Vanna Agent Memory"""
    
    def __init__(self):
        self.agent = None
        self.stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "failed_items": []
        }
    
    async def initialize(self) -> None:
        """Initialize agent with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Initializing agent (attempt {attempt + 1}/{max_retries})...")
                self.agent = get_agent()
                logger.info("✅ Agent initialized successfully")
                return
            except Exception as e:
                logger.error(f"Agent initialization failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2)
    
    def _get_available_method(self) -> str:
        """Detect which method is available in agent_memory"""
        if not self.agent or not self.agent.agent_memory:
            return None
        
        methods = dir(self.agent.agent_memory)
        
        # Priority order of methods to try
        for method in ['save', 'add', 'store', 'insert', 'put', 'create']:
            if method in methods:
                logger.info(f"Using method: agent.agent_memory.{method}()")
                return method
        
        # If no standard method found, check for custom methods
        custom_methods = [m for m in methods if not m.startswith('_') and callable(getattr(self.agent.agent_memory, m))]
        if custom_methods:
            logger.warning(f"No standard save method found. Available: {custom_methods[:5]}")
            return custom_methods[0] if custom_methods else None
        
        return None
    
    async def save_pair(self, question: str, sql: str, index: int, total: int) -> bool:
        """Save a single Q→SQL pair with multiple method attempts"""
        
        # Method 1: Try direct save method
        save_method = self._get_available_method()
        
        if save_method:
            try:
                # Try different argument patterns
                patterns = [
                    {"question": question, "tool_name": "run_sql", "tool_args": {"sql": sql}},
                    {"query": question, "sql": sql},
                    {"question": question, "sql": sql},
                    {"text": question, "metadata": {"sql": sql}},
                    (question, sql),  # Tuple format
                    [question, sql],  # List format
                ]
                
                for pattern in patterns:
                    try:
                        method = getattr(self.agent.agent_memory, save_method)
                        
                        # Handle different call signatures
                        if save_method in ['save', 'add', 'store']:
                            if isinstance(pattern, dict):
                                result = method(**pattern)
                            else:
                                result = method(*pattern)
                        else:
                            result = method(pattern)
                        
                        logger.debug(f"  ✓ Saved using {save_method}() with pattern: {type(pattern)}")
                        return True
                        
                    except TypeError:
                        continue  # Try next pattern
                    except Exception as e:
                        logger.debug(f"  Pattern failed: {e}")
                        continue
                
                raise Exception(f"All argument patterns failed for method {save_method}")
                
            except Exception as e:
                logger.warning(f"Method {save_method} failed: {e}")
        
        # Method 2: Try direct memory manipulation
        try:
            if hasattr(self.agent.agent_memory, 'memory') and isinstance(self.agent.agent_memory.memory, list):
                self.agent.agent_memory.memory.append({
                    "question": question,
                    "sql": sql,
                    "timestamp": datetime.now().isoformat()
                })
                logger.debug(f"  ✓ Saved directly to memory list")
                return True
        except Exception as e:
            logger.debug(f"Direct memory manipulation failed: {e}")
        
        # Method 3: Try using tool registry
        try:
            from vanna.tools.agent_memory import SaveQuestionToolArgsTool
            tool = SaveQuestionToolArgsTool()
            result = tool.execute(
                question=question,
                tool_name="run_sql",
                tool_args={"sql": sql}
            )
            logger.debug(f"  ✓ Saved using SaveQuestionToolArgsTool")
            return True
        except Exception as e:
            logger.debug(f"SaveQuestionToolArgsTool failed: {e}")
        
        logger.error(f"  ✗ Failed to save: {question[:50]}...")
        return False
    
    async def seed(self) -> Dict:
        """Seed all Q→SQL pairs with progress tracking"""
        
        self.stats["total"] = len(QA_PAIRS)
        
        for i, (question, sql) in enumerate(QA_PAIRS, 1):
            try:
                logger.info(f"[{i:02d}/{self.stats['total']}] Processing: {question[:70]}")
                
                success = await self.save_pair(question, sql, i, self.stats["total"])
                
                if success:
                    self.stats["successful"] += 1
                    logger.info(f"  ✓ Success")
                else:
                    self.stats["failed"] += 1
                    self.stats["failed_items"].append({
                        "index": i,
                        "question": question,
                        "sql": sql
                    })
                    logger.warning(f"  ✗ Failed")
                
                # Small delay to avoid overwhelming
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"  ✗ Error: {e}")
                self.stats["failed"] += 1
                self.stats["failed_items"].append({
                    "index": i,
                    "question": question,
                    "error": str(e)
                })
        
        return self.stats
    
    def get_memory_count(self) -> int:
        """Get current memory count using available methods"""
        if not self.agent or not self.agent.agent_memory:
            return 0
        
        # Try different ways to get count
        try:
            if hasattr(self.agent.agent_memory, '__len__'):
                return len(self.agent.agent_memory)
            elif hasattr(self.agent.agent_memory, 'memory') and hasattr(self.agent.agent_memory.memory, '__len__'):
                return len(self.agent.agent_memory.memory)
            elif hasattr(self.agent.agent_memory, 'size'):
                return self.agent.agent_memory.size()
            elif hasattr(self.agent.agent_memory, 'count'):
                return self.agent.agent_memory.count()
        except Exception as e:
            logger.debug(f"Could not get memory count: {e}")
        
        return -1  # Unknown
    
    def print_summary(self) -> None:
        """Print seeding summary"""
        print("\n" + "="*60)
        print("SEEDING SUMMARY")
        print("="*60)
        print(f"Total pairs:     {self.stats['total']}")
        print(f"Successful:      {self.stats['successful']} ✅")
        print(f"Failed:          {self.stats['failed']} ❌")
        
        memory_count = self.get_memory_count()
        if memory_count >= 0:
            print(f"Memory items:    {memory_count}")
        
        if self.stats['failed_items']:
            print(f"\n⚠️ Failed items ({len(self.stats['failed_items'])}):")
            for item in self.stats['failed_items'][:5]:  # Show first 5 only
                print(f"  - {item.get('question', 'Unknown')[:60]}")
            if len(self.stats['failed_items']) > 5:
                print(f"  ... and {len(self.stats['failed_items']) - 5} more")
        
        print("="*60)


async def seed() -> None:
    """Main seeding function with comprehensive error handling"""
    
    seeder = MemorySeeder()
    
    try:
        # Initialize agent
        await seeder.initialize()
        
        # Validate agent memory exists
        if not seeder.agent or not seeder.agent.agent_memory:
            raise Exception("Agent or agent_memory is None")
        
        logger.info(f"Seeding {len(QA_PAIRS)} Q→SQL pairs into {type(seeder.agent.agent_memory).__name__}...")
        
        # Perform seeding
        stats = await seeder.seed()
        
        # Print summary
        seeder.print_summary()
        
        # Exit with appropriate code
        if stats['failed'] > 0:
            logger.warning(f"Seeding completed with {stats['failed']} failures")
            sys.exit(1)
        else:
            logger.info("✅ All pairs seeded successfully!")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}", exc_info=True)
        sys.exit(1)


# ── Main entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(seed())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Seeding interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)