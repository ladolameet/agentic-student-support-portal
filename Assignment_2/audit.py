"""Append-only audit log with a hash chain.
Each row stores who (actor), what (action/target), whether it was allowed (decision), and the final result.
Row hash = SHA-256(previous row hash + this row's fields), so editing or deleting an old row breaks the chain.
SQLite triggers (see database.py) also refuse UPDATE/DELETE on this table."""
import hashlib
import json
import time

from database import connect

FIELDS = ("ts", "actor_id", "actor_role", "action", "target", "details", "decision", "result", "session_id")
# decision: allowed | denied | approval_required | approved | rejected
# result:   success | failed | blocked | not_executed | executed


def _hash(prev, row):
    return hashlib.sha256((prev + "|" + "|".join(str(row[f]) for f in FIELDS)).encode()).hexdigest()


def record(actor_id, actor_role, action, decision, result, target="", details=None, session_id="", db_path=None):
    """Write one audit row and return its id. Never pass secrets in `details`."""
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "actor_id": actor_id, "actor_role": actor_role,
           "action": action, "target": target or "", "details": json.dumps(details or {}, sort_keys=True),
           "decision": decision, "result": result, "session_id": session_id or ""}
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")  # lock so two writers cannot break the chain
        last = conn.execute("SELECT row_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1").fetchone()
        prev = last["row_hash"] if last else "GENESIS"
        cur = conn.execute(
            "INSERT INTO audit_log(ts,actor_id,actor_role,action,target,details,decision,result,session_id,prev_hash,row_hash)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*[row[f] for f in FIELDS], prev, _hash(prev, row)))
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_recent(limit=50, db_path=None):
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_for_actor(actor_id, limit=25, db_path=None):
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM audit_log WHERE actor_id=? ORDER BY audit_id DESC LIMIT ?", (actor_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_since(after_id, db_path=None):
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM audit_log WHERE audit_id>? ORDER BY audit_id", (after_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def last_id(db_path=None):
    conn = connect(db_path)
    r = conn.execute("SELECT COALESCE(MAX(audit_id),0) AS m FROM audit_log").fetchone()
    conn.close()
    return r["m"]


def verify_chain(db_path=None):
    """Returns (True, None) if every row's hash matches, else (False, id_of_first_bad_row)."""
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM audit_log ORDER BY audit_id").fetchall()
    conn.close()
    prev = "GENESIS"
    for r in rows:
        if r["prev_hash"] != prev or r["row_hash"] != _hash(prev, r):
            return False, r["audit_id"]
        prev = r["row_hash"]
    return True, None
