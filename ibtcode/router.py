import os
from ibtcode.parser import parse_ibtcode

BASE_DIR = os.path.dirname(__file__)

class Router:
    def __init__(self):
        self.blocks = {
            "PASSWORD_RESET": parse_ibtcode(
                os.path.join(BASE_DIR, "flows", "password_reset.ibt")
            ),
            "ESCALATE": parse_ibtcode(
                os.path.join(BASE_DIR, "flows", "password_reset.ibt")
            ),
            "ACCOUNT_HACKED": parse_ibtcode(
                os.path.join(BASE_DIR, "flows", "account_hacked.ibt")
            ),
            "PATIENT_QUERY": None,
            "DOCTOR_QUERY": None,
            "APPOINTMENT_QUERY": None,
            "FINANCIAL_QUERY": None,
            "SENSITIVE_QUERY": None,
            "AGGREGATION_QUERY": None,
            "TIME_QUERY": None,
            "GENERAL_QUERY": None,
        }

    def get_block(self, intent):
        return self.blocks.get(intent)