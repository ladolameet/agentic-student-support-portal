"""Authorization rules, enforced in normal Python code (never left to the LLM's judgement)."""

SELF_WORDS = {"", "me", "my", "myself", "mine", "self"}


def can_access_student(actor_id, target):
    """A student may touch only their own record. `target` empty/'me' means 'myself'."""
    t = (target or "").strip().lower()
    return t in SELF_WORDS or t == actor_id.strip().lower()
