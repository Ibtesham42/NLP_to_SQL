from ibtcode.actions import ACTION_MAP
from ibtcode.audit import AuditLogger
from ibtcode.rollback import RollbackManager


class ActionEngine:

    def __init__(self):
        self.audit = AuditLogger()
        self.rollback = RollbackManager()

    #  Risk classification
    def assess_risk(self, action_name):
        HIGH_RISK = ["lock_account", "create_emergency_ticket"]

        if action_name in HIGH_RISK:
            return "HIGH"
        return "LOW"

    #  Execute action + audit + register rollback
    def commit(self, action_name, context):
        if action_name not in ACTION_MAP:
            print(f"[ERROR] Unknown action: {action_name}")
            return

        # 1. Execute action
        ACTION_MAP[action_name](context)

        # 2. Audit log
        self.audit.log(
            action_name=action_name,
            intent=context.get("intent"),
            state=context.get("state"),
            risk=self.assess_risk(action_name)
        )

        # 3. Register rollback (compensation)
        rollback_map = {
            "lock_account": "unlock_account",
            "create_emergency_ticket": "cancel_emergency_ticket"
        }

        if action_name in rollback_map:
            rollback_action = rollback_map[action_name]
            rollback_fn = ACTION_MAP.get(rollback_action)

            if rollback_fn:
                self.rollback.register(
                    action_name=action_name,
                    rollback_fn=rollback_fn,
                    context=context
                )