from parser import parse_ibtcode
from engine import IbtEngine
from perception import detect_intent
from validation import validate_perception
from context import Context
from router import Router

router = Router()
ctx = Context()

# keep last engine reference (for rollback)
last_engine = None

print("Ibtcode AI Started (type 'exit' to quit)\n")

while True:
    user_input = input("You: ").strip()

    # EXIT
    if user_input.lower() == "exit":
        print("Exiting...")
        break

    # IGNORE standalone yes/no
    if user_input.lower() in ["yes", "no"]:
        print("No active action to confirm. Enter a valid request.")
        continue

    # GLOBAL ROLLBACK
    if user_input.lower() == "rollback":
        if last_engine:
            last_engine.action_engine.rollback.execute()
        else:
            print("No actions to rollback")
        continue

    # PERCEPTION
    perception = detect_intent(user_input)
    print(f"[PERCEPTION] {perception}")

    # VALIDATION
    result = validate_perception(perception)

    # CLARIFICATION
    if result["status"] == "CLARIFY":
        print("[VALIDATION] Need clarification")
        print(f"Did you mean: {', '.join(result['candidates'])}?")

        clarification_input = input("Clarify: ").strip()

        clar_perception = detect_intent(clarification_input)
        print(f"[CLARIFICATION PERCEPTION] {clar_perception}")

        clar_intent = clar_perception["intent"]

        if clar_intent in result["candidates"]:
            intent = clar_intent
            print(f"[CLARIFIED] Using intent: {intent}")
        else:
            print("Could not understand clarification. Try again.")
            continue
    else:
        intent = result["intent"]
        print(f"[VALIDATION] Accepted: {intent}")

    # ROUTER
    block = router.get_block(intent)

    if not block:
        print("No block found for this intent")
        continue

    # ENGINE
    engine = IbtEngine(block)

    # CONTEXT
    context_data = {
        "intent": intent,
        "state": ctx.state
    }

    # EXECUTION
    new_state = engine.handle(intent, context_data)

    # 🔥 IMPORTANT: if execution was cancelled, skip update
    if new_state is None:
        print("Execution cancelled")
        continue

    # STORE engine AFTER successful execution (for rollback)
    last_engine = engine

    # UPDATE CONTEXT
    ctx.update(user_input, intent, new_state)

    print(f"[CONTEXT] last_intent={ctx.last_intent}, state={ctx.state}")