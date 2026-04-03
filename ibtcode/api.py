from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from ibtcode.engine import IbtEngine
from ibtcode.perception import detect_intent
from ibtcode.validation import validate_perception
from ibtcode.router import Router
from ibtcode.context import Context

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = Router()
ctx = Context()

pending = None


# =========================
# MODELS
# =========================

class UserInput(BaseModel):
    message: str


class ConfirmInput(BaseModel):
    confirm: bool


# =========================
# PROCESS
# =========================

@app.post("/process")
def process(input: UserInput):
    global pending

    user_input = input.message

    # 1. PERCEPTION
    perception = detect_intent(user_input)

    # 2. VALIDATION (🔥 FIXED INTEGRATION)
    validation = validate_perception(perception, {
        "last_intent": ctx.last_intent
    })

    print("[PERCEPTION]", perception)
    print("[VALIDATION]", validation)

    # 3. HANDLE CLARIFICATION FIRST
    if validation["status"] == "CLARIFY":
        return {
            "status": "clarify",
            "reason": validation.get("reason"),
            "candidates": validation.get("candidates", [])
        }

    # 4. SAFE INTENT EXTRACTION
    intent = validation["intent"]

    # 5. ROUTER
    block = router.get_block(intent)

    if not block:
        return {"status": "error", "message": "No block found"}

    # 6. ENGINE
    engine = IbtEngine(block)

    context_data = {
        "intent": intent,
        "state": ctx.state
    }

    result = engine.handle(intent, context_data)

    # 7. HIGH RISK → CONFIRMATION
    if result["status"] == "needs_confirmation":
        pending = {
            "engine": engine,
            "data": result
        }

        return {
            "status": "needs_confirmation",
            "actions": result["high_risk"]
        }

    # 8. SAFE EXECUTION
    if result["status"] == "executed":
        ctx.update(user_input, intent, result["state"])

        return {
            "status": "success",
            "intent": intent,
            "state": result["state"]
        }

    return {"status": "error"}


# =========================
# CONFIRM
# =========================

@app.post("/confirm")
def confirm(input: ConfirmInput):
    global pending

    if not pending:
        return {"status": "no_pending"}

    if not input.confirm:
        pending = None
        return {"status": "cancelled"}

    engine = pending["engine"]
    data = pending["data"]

    ctx_data = data["context"]

    # EXECUTE HIGH RISK FIRST
    for action in data["high_risk"]:
        engine.action_engine.commit(action, ctx_data)

    # EXECUTE LOW RISK
    for action in data["low_risk"]:
        engine.action_engine.commit(action, ctx_data)

    engine.state = data["next_state"]

    ctx.update("confirmed", ctx_data["intent"], engine.state)

    pending = None

    return {
        "status": "executed",
        "state": engine.state
    }


# =========================
# ROLLBACK
# =========================

@app.post("/rollback")
def rollback():
    global pending

    if pending:
        pending["engine"].action_engine.rollback.execute()
        return {"status": "rolled_back"}

    return {"status": "no_actions"}


# =========================
# LOGS
# =========================

@app.get("/logs")
def logs():
    import json

    try:
        with open("audit_log.json") as f:
            data = json.load(f)
            return data[-20:]  # 🔥 limit logs
    except:
        return []