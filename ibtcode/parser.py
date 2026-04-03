class IbtBlock:
    def __init__(self, name):
        self.name = name
        self.state = None
        self.transitions = []


class Transition:
    def __init__(self, intent):
        self.intent = intent
        self.actions = []
        self.next_state = None


def parse_ibtcode(file_path):
    with open(file_path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    block = None
    current_transition = None

    for line in lines:
        if line.startswith("BLOCK"):
            block = IbtBlock(line.split()[1])

        elif line.startswith("STATE"):
            block.state = line.split()[1]

        elif line.startswith("ON"):
            intent = line.split("=")[1]
            current_transition = Transition(intent)
            block.transitions.append(current_transition)

        elif line.startswith("ACTION"):
            action = line.split()[1]
            current_transition.actions.append(action)

        elif line.startswith("TRANSITION"):
            current_transition.next_state = line.split()[1]

    return block