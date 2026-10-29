"""LangChain tools. They are built per student: the student_id is bound here in Python,
so the LLM can never choose (or be tricked into choosing) another student's id."""
import re
import uuid
from typing import Optional
from langchain_core.tools import tool
from pydantic import ValidationError

import approvals
import audit
import authz
import memory
from database import connect
from retrieval import BM25, load_chunks
from schemas import MemoryInput, TicketInput

_bm25 = None
# the model may phrase the category loosely; map common wordings to the allowed values
ALIASES = {"payment_portal": "portal", "portal_failure": "portal", "payment": "fee", "fees": "fee", "fee_payment": "fee",
           "scholarships": "scholarship", "course": "course_change", "course_change_request": "course_change",
           "course_changes": "course_change", "general": "other", "others": "other"}

MEMORY_ALIASES = {
    "program": "programme", "academic_program": "programme", "major": "programme", "degree": "programme",
    "lang": "language", "preferred_language": "language", "mother_tongue": "language",
    "pref": "preference", "timing": "timing_preference", "mode": "study_mode",
    "room": "hostel_room", "room_no": "hostel_room", "room_number": "hostel_room",
    "hostel_name": "hostel", "dorm": "hostel",
    "goal": "career_goal", "ambition": "career_goal",
}


def get_bm25():
    global _bm25
    if _bm25 is None:
        _bm25 = BM25(load_chunks())
    return _bm25


def fee_status(student_id, db_path=None):
    try:
        conn = connect(db_path)
        r = conn.execute("SELECT fee_total,fee_paid,due_date FROM fees WHERE student_id=?", (student_id,)).fetchone()
        conn.close()
    except Exception as e:
        return {"ok": False, "error": f"Database error: {e}"}
    if not r:
        return {"ok": False, "error": "No fee record found."}
    paid, total = r["fee_paid"], r["fee_total"]
    return {"ok": True, "total": total, "paid": paid, "outstanding": total - paid, "due_date": r["due_date"],
            "status": "paid" if paid >= total else "partially paid" if paid else "unpaid"}


def scholarship_status(student_id, db_path=None):
    try:
        conn = connect(db_path)
        r = conn.execute("SELECT status,detail FROM scholarships WHERE student_id=?", (student_id,)).fetchone()
        conn.close()
    except Exception as e:
        return {"ok": False, "error": f"Database error: {e}"}
    if not r:
        return {"ok": False, "error": "No scholarship record found."}
    return {"ok": True, "status": r["status"], "detail": r["detail"]}


def new_ticket(student_id, category, description, db_path=None):
    norm = re.sub(r"[\s-]+", "_", str(category).strip().lower())
    category = ALIASES.get(norm, norm)  # "Payment Portal" -> portal, "course change" -> course_change
    try:
        data = TicketInput(category=category, description=str(description).strip())  # validate
    except ValidationError:
        return {"ok": False, "error": "Invalid ticket: use a valid category and a 5-300 character description."}
    ticket_id = "TCK-" + uuid.uuid4().hex[:8].upper()
    try:
        conn = connect(db_path)
        with conn:  # commit happens when this block ends
            conn.execute("INSERT INTO tickets(ticket_id,student_id,category,description) VALUES(?,?,?,?)",
                         (ticket_id, student_id, data.category, data.description))
        conn.close()
    except Exception as e:
        return {"ok": False, "error": f"Ticket was NOT created: {e}"}
    return {"ok": True, "ticket_id": ticket_id}


def make_tools(actor, db_path=None, evidence=None, session_id="", audit_log=None):
    """Return the allow-listed tools for ONE signed-in student (`actor`).
    Authorization is enforced here in Python: a tool may only touch the actor's own record,
    whatever the model asks for. Every important action writes an audit record.
    `evidence` collects retrieved policy chunks; `audit_log` collects this run's audit records (for the trace/UI)."""
    evidence = evidence if evidence is not None else []
    audit_log = audit_log if audit_log is not None else []

    def log(action, decision, result, target=None, details=None):
        try:
            aid = audit.record(actor, "student", action, decision, result, target or actor, details, session_id, db_path)
        except Exception:  # audit storage down: report it in the trace, do not crash the run
            aid = 0
        audit_log.append({"id": aid, "action": action, "decision": decision, "result": result})

    def denied(target, action):
        """Return an error dict (and audit it) if `target` is not the signed-in student, else None."""
        if authz.can_access_student(actor, target):
            return None
        log(action, "denied", "blocked", str(target)[:40])
        return {"ok": False, "error": "Access denied. You can only access your own record."}

    @tool
    def get_fee_status(student_id: Optional[str] = "") -> dict:
        """Get a student's fee status: total, paid, outstanding balance, due date. Leave student_id empty for the logged-in student."""
        if (d := denied(student_id, "read_fee_status")):
            return d
        r = fee_status(actor, db_path)
        log("read_fee_status", "allowed", "success" if r["ok"] else "failed")
        return r

    @tool
    def check_scholarship_status(student_id: Optional[str] = "") -> dict:
        """Get a student's scholarship status and details. Leave student_id empty for the logged-in student."""
        if (d := denied(student_id, "read_scholarship_status")):
            return d
        r = scholarship_status(actor, db_path)
        log("read_scholarship_status", "allowed", "success" if r["ok"] else "failed")
        return r

    @tool
    def create_support_ticket(category: str, description: str) -> dict:
        """Create a support ticket. category: fee, scholarship, course_change, portal or other."""
        r = new_ticket(actor, category, description, db_path)
        log("create_ticket", "allowed", "success" if r["ok"] else "failed", details={"ticket_id": r.get("ticket_id")})
        return r

    @tool
    def search_policy(query: str) -> dict:
        """Search the student handbook for policy rules. Use for any policy/procedure question."""
        hits = get_bm25().search(query)
        evidence.extend(hits)
        if not hits:
            return {"ok": True, "chunks": [], "note": "No relevant policy found. Do not guess."}
        return {"ok": True, "chunks": [{"id": h["id"], "title": h["title"], "text": h["text"]} for h in hits]}

    @tool
    def save_memory(key: str, value: str) -> dict:
        """Save a personalized fact, preference, personal detail, or context discussed by the student.
        Use this whenever the student discusses their personal details (programme, major, year, hostel, room,
        language, career interest, study habits, specific situation) or asks you to remember something.
        key: descriptive snake_case key (e.g. programme, hostel, hostel_room, language, career_goal, preference).
        value: the fact to remember (up to 150 characters)."""
        norm_key = re.sub(r"[^a-zA-Z0-9_]+", "_", str(key).strip().lower()).strip("_")
        norm_key = MEMORY_ALIASES.get(norm_key, norm_key or "preference")
        try:
            m = MemoryInput(key=norm_key, value=str(value).strip())
        except ValidationError:
            log("save_memory", "denied", "blocked", details={"reason": "invalid key or value"})
            return {"ok": False, "error": "Invalid memory input."}
        r = memory.save_memory(actor, m.key, m.value, db_path)
        log("save_memory", "allowed" if r["ok"] else "denied", "success" if r["ok"] else "blocked",
            details={"key": m.key} if r["ok"] else {"reason": "sensitive content"})
        return r

    @tool
    def get_saved_memory() -> dict:
        """Retrieve all personalized facts, preferences, and profile details saved in memory for the logged-in student."""
        rows = memory.list_memory(actor, db_path)
        log("read_memory", "allowed", "success")
        return {"ok": True, "memories": [{k: x[k] for k in ("memory_id", "key", "value")} for x in rows]}

    @tool
    def request_record_change(field: str, new_value: str) -> dict:
        """Ask to change the student's registered email or phone. field: email or phone.
        This only creates a REQUEST; the student must then press Approve on the confirmation card. It never changes the record itself."""
        r = approvals.request_change(actor, field, new_value, session_id, db_path)
        if r.get("audit_id"):
            audit_log.append({"id": r["audit_id"], "action": "request_change_" + str(field)[:10],
                              "decision": "approval_required" if r["ok"] else "denied",
                              "result": "not_executed" if r["ok"] else "blocked"})
        return r

    @tool
    def check_request_status() -> dict:
        """Show the status of the logged-in student's own change requests."""
        rows = approvals.list_for_student(actor, db_path)
        log("read_requests", "allowed", "success")
        return {"ok": True, "requests": [{k: x[k] for k in ("approval_id", "field", "status")} for x in rows]}

    return [get_fee_status, check_scholarship_status, create_support_ticket, search_policy,
            save_memory, get_saved_memory, request_record_change, check_request_status]
