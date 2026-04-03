class RollbackManager:
    def __init__(self):
        self.compensations = []

    def register(self, action_name, rollback_fn, context):
        self.compensations.append({
            "action": action_name,
            "rollback": rollback_fn,
            "context": context.copy()
        })

    def execute(self):
        print("\n[ROLLBACK] Starting rollback...")

        # reverse order (important)
        for item in reversed(self.compensations):
            try:
                print(f"[ROLLBACK] Reversing {item['action']}")
                item["rollback"](item["context"])
            except Exception as e:
                print(f"[ROLLBACK ERROR] {e}")

        print("[ROLLBACK] Completed")