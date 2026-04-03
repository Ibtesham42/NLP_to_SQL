import json
from datetime import datetime


class AuditLogger:
    def __init__(self, file="audit_log.json"):
        self.file = file

    def log(self, action_name, intent, state, risk):
        record = {
            "action": action_name,
            "intent": intent,
            "state": state,
            "risk": risk,
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(self.file, "r") as f:
                data = json.load(f)
        except:
            data = []

        data.append(record)

        with open(self.file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[AUDIT] Logged: {action_name}")