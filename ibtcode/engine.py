from ibtcode.action_engine import ActionEngine


class IbtEngine:
    def __init__(self, block):
        self.block = block
        self.state = block.state
        self.action_engine = ActionEngine()

    def handle(self, intent, context):
        for t in self.block.transitions:
            if t.intent == intent:
                print(f"[MATCH] Intent: {intent}")

                high_risk_actions = []
                low_risk_actions = []

                # classify actions
                for action in t.actions:
                    risk = self.action_engine.assess_risk(action)
                    if risk == "HIGH":
                        high_risk_actions.append(action)
                    else:
                        low_risk_actions.append(action)

                # prepare context
                ctx = context.copy()
                ctx["intent"] = intent
                ctx["state"] = self.state

                #  if HIGH risk → return for confirmation
                if high_risk_actions:
                    return {
                        "status": "needs_confirmation",
                        "high_risk": high_risk_actions,
                        "low_risk": low_risk_actions,
                        "context": ctx,
                        "next_state": t.next_state
                    }

                #  if no HIGH risk → execute directly
                for action in low_risk_actions:
                    self.action_engine.commit(action, ctx)

                # update state
                self.state = t.next_state

                return {
                    "status": "executed",
                    "state": self.state
                }

        #  no matching transition
        return {
            "status": "no_match"
        }