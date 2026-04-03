class Context:
    def __init__(self):
        self.state = None
        self.last_intent = None
        self.history = []

    def update(self, user_input, intent, state):
        self.last_intent = intent
        self.state = state
        self.history.append({
            "input": user_input,
            "intent": intent,
            "state": state
        })