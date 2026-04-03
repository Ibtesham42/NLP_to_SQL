def verify_identity(ctx):
    print(" Identity verified")


def send_reset_link(ctx):
    print(" Reset link sent")


def create_ticket(ctx):
    print(" Ticket created")


#  SECURITY ACTIONS
def lock_account(ctx):
    print(" Account locked for security")


def create_emergency_ticket(ctx):
    print(" Emergency ticket created")


def notify_user_security_alert(ctx):
    print(" User notified: Security alert triggered")
def unlock_account(ctx):
    print("Account unlocked (rollback)")

def cancel_emergency_ticket(ctx):
    print("Emergency ticket cancelled (rollback)")

#  ACTION MAP (VERY IMPORTANT)
ACTION_MAP = {
    "verify_identity": verify_identity,
    "send_reset_link": send_reset_link,
    "create_ticket": create_ticket,

    #  NEW SECURITY ACTIONS
    "lock_account": lock_account,
    "create_emergency_ticket": create_emergency_ticket,
    "notify_user_security_alert": notify_user_security_alert,
    "unlock_account": unlock_account,
    "cancel_emergency_ticket": cancel_emergency_ticket,
}