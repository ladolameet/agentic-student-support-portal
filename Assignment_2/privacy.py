"""Privacy helpers: remove secrets from text before it reaches the model, traces or logs,
and spot questions that ask about another student before the model is even called."""
import re

from database import list_students

# keyword followed by its value, e.g. "password is hunter2", "OTP 482913"
_KEY = r"(one[- ]time (?:password|code)|password|passcode|passwd|otp|pin|cvv)"
# "password is hunter2", "pin: 4321"  (keyword + connector + value)
_SECRET_CONN = re.compile(r"(?i)\b" + _KEY + r"\b(\s*(?:is|was|:|=)\s*)([^\s,;?!]+)")
# "OTP 482913"  (keyword + a value that contains a digit)
_SECRET_DIGIT = re.compile(r"(?i)\b" + _KEY + r"\b(\s+)([^\s,;?!]*\d[^\s,;?!]*)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_ID = re.compile(r"\bS\d{3}\b", re.I)


def redact(text):
    """Replace passwords, OTPs, PINs, CVVs and card numbers with [REDACTED]. Phone numbers are kept."""
    keep = lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]"
    text = _SECRET_CONN.sub(keep, text)
    text = _SECRET_DIGIT.sub(keep, text)
    return _CARD.sub("[REDACTED]", text)


def other_student_mentioned(question, actor_id, db_path=None):
    """Return the other student's id/name if the question names one, else None."""
    for sid in _ID.findall(question):
        if sid.upper() != actor_id.upper():
            return sid.upper()
    q = question.lower()
    try:
        students = list_students(db_path)
    except Exception:
        return None
    for s in students:
        full = re.sub(r"\(.*?\)", "", s["name"]).strip().lower()  # "Harsh Shah (fictional)" -> "harsh shah"
        if s["student_id"] == actor_id or not full:
            continue
        if re.search(r"\b" + re.escape(full) + r"\b", q):
            return s["student_id"]
        first = full.split()[0]  # first name alone: only when written capitalised, so "a harsh rule" is not blocked
        if len(first) >= 3 and re.search(r"\b" + re.escape(first.capitalize()) + r"\b", question):
            return s["student_id"]
    return None
