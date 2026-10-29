"""Human-in-the-loop confirmation for sensitive actions.
The agent can only REQUEST a change (status 'pending'): nothing is executed. The student must press Approve in the
chat window (a separate authenticated request, not chat text), so the model can never approve on its own or be talked
into it. Only the owner of a request can decide it, and it expires after APPROVAL_TTL_MIN minutes."""
import uuid

import audit
import config
from database import connect
from pydantic import ValidationError
from schemas import ChangeInput

# fixed SQL per field (no string-building from user input)
_APPLY = {"email": "UPDATE contacts SET email=? WHERE student_id=?", "phone": "UPDATE contacts SET phone=? WHERE student_id=?"}
_READ = {"email": "SELECT email AS v FROM contacts WHERE student_id=?", "phone": "SELECT phone AS v FROM contacts WHERE student_id=?"}
_AGE = "CAST((strftime('%s','now') - strftime('%s', requested_at)) AS INTEGER) AS age_s"


def request_change(student_id, field, new_value, session_id="", db_path=None):
    """Create a pending request. Does NOT change the record."""
    try:
        data = ChangeInput(field=field, new_value=new_value)
    except ValidationError:
        aid = audit.record(student_id, "student", "request_change", "denied", "blocked", student_id,
                           {"field": str(field)[:20], "reason": "invalid value"}, session_id, db_path)
        return {"ok": False, "error": "Invalid request: give a valid email address or a 10-digit phone number.", "audit_id": aid}
    conn = connect(db_path)
    try:
        old = conn.execute(_READ[data.field], (student_id,)).fetchone()
        if not old:
            return {"ok": False, "error": "No contact record found."}
        approval_id = "APR-" + uuid.uuid4().hex[:8].upper()
        with conn:
            conn.execute("INSERT INTO approvals(approval_id,student_id,field,old_value,new_value) VALUES(?,?,?,?,?)",
                         (approval_id, student_id, data.field, old["v"], data.new_value))
    finally:
        conn.close()
    aid = audit.record(student_id, "student", "request_change_" + data.field, "approval_required", "not_executed",
                       student_id, {"approval_id": approval_id, "field": data.field}, session_id, db_path)
    return {"ok": True, "status": "pending_confirmation", "approval_id": approval_id, "audit_id": aid,
            "message": "NOT changed yet. The student must press Approve on the confirmation card in the chat."}


def list_for_student(student_id, db_path=None):
    """Only this student's own requests. `expired` is computed, a pending request older than the TTL."""
    conn = connect(db_path)
    rows = conn.execute(f"SELECT approval_id,field,old_value,new_value,status,requested_at,decided_at,{_AGE} FROM approvals "
                        "WHERE student_id=? ORDER BY requested_at DESC, rowid DESC", (student_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        r = dict(r)
        r["expired"] = r["status"] == "pending" and r["age_s"] > config.APPROVAL_TTL_MIN * 60
        out.append(r)
    return out


def decide(approval_id, actor_id, decision, session_id="", db_path=None):
    """The signed-in student approves or rejects THEIR OWN request.
    approve = apply the change once. reject = the change is never executed."""
    conn = connect(db_path)
    try:
        if decision not in ("approve", "reject"):
            return {"ok": False, "error": "Decision must be approve or reject."}
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(f"SELECT *, {_AGE} FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if not row or row["student_id"] != actor_id:  # not found OR somebody else's request: same answer, and audited
            conn.rollback()
            audit.record(actor_id, "student", "decide_" + decision, "denied", "blocked", str(approval_id)[:20],
                         {"reason": "not the owner or not found"}, session_id, db_path)
            return {"ok": False, "error": "Request not found."}
        if row["status"] != "pending":  # stops double execution
            conn.rollback()
            return {"ok": False, "error": "This request was already decided."}
        if row["age_s"] > config.APPROVAL_TTL_MIN * 60:
            conn.rollback()
            audit.record(actor_id, "student", "decide_" + decision, "denied", "blocked", approval_id,
                         {"reason": "expired"}, session_id, db_path)
            return {"ok": False, "error": f"This request expired after {config.APPROVAL_TTL_MIN} minutes. Ask again."}
        status = "executed" if decision == "approve" else "rejected"
        if decision == "approve":
            conn.execute(_APPLY[row["field"]], (row["new_value"], row["student_id"]))
        conn.execute("UPDATE approvals SET status=?, decided_by=?, decided_at=CURRENT_TIMESTAMP WHERE approval_id=?",
                     (status, actor_id, approval_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": f"Could not complete the decision: {type(e).__name__}"}
    finally:
        conn.close()
    aid = audit.record(actor_id, "student", f"confirm_{row['field']}_change", "approved" if decision == "approve" else "rejected",
                       "executed" if decision == "approve" else "not_executed", row["student_id"],
                       {"approval_id": approval_id, "field": row["field"], "via": "confirmation button"}, session_id, db_path)
    return {"ok": True, "status": status, "field": row["field"], "new_value": row["new_value"] if decision == "approve" else None,
            "audit_id": aid}
