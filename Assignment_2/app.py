"""Flask backend with password login, in-chat confirmation of sensitive actions, and audit.
Run:  python app.py  then open http://127.0.0.1:5000
Identity comes ONLY from the signed session cookie set at login - never from the request body.
Permission checks are plain Python, not LLM instructions."""
import time
from functools import wraps

import approvals
import audit
import config
import database
import memory
from agent import run_agent
from flask import Flask, jsonify, request, session
from privacy import redact

app = Flask(__name__, static_folder="static", static_url_path="")
app.config.update(SECRET_KEY=config.SECRET_KEY, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
database.init_db()  # safe: keeps existing data

FAILS = {}  # id -> [count, locked_until]  (simple brute-force guard)
START_TIME = time.time()


def _keep_alive_worker():
    """Background daemon that pings the service every 12 minutes to prevent Render idle spin-down."""
    import os
    import urllib.request
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("KEEP_ALIVE_URL")
    if not url:
        return
    health_url = url.rstrip("/") + "/health"
    print(f"[KeepAlive] Render keep-alive daemon running for {health_url}")
    while True:
        time.sleep(720)  # Ping every 12 minutes (Render idle timeout is 15 minutes)
        try:
            req = urllib.request.Request(health_url, headers={"User-Agent": "Render-KeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                print(f"[KeepAlive] Keep-alive ping status: {resp.status}")
        except Exception as e:
            print(f"[KeepAlive] Keep-alive ping notice: {e}")


import threading
threading.Thread(target=_keep_alive_worker, daemon=True, name="render_keep_alive").start()


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Lightweight health check for Render and keep-alive monitors."""
    return jsonify(status="ok", uptime_seconds=int(time.time() - START_TIME), service="student-support-portal"), 200


def student_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("student"):
            return jsonify(error="Please log in first."), 401
        return f(session["student"], *a, **kw)
    return wrapper


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    uid, pw = str(d.get("student_id", "")).strip().upper(), str(d.get("password", ""))
    key = (request.remote_addr, uid)  # per client AND id, so a stranger cannot lock a student out from elsewhere
    count, locked = FAILS.get(key, [0, 0])
    if time.time() < locked:
        return jsonify(error="Too many attempts. Try again in a minute."), 429
    if not database.verify_login(uid, pw):
        count += 1
        FAILS[key] = [count, time.time() + 60 if count >= 5 else 0]
        if database.student_name(uid):  # audit only attempts on real accounts (unknown ids would let anyone flood the log)
            audit.record(uid, "unknown", "login", "denied", "blocked")
        return jsonify(error="Wrong ID or password."), 401
    FAILS.pop(key, None)
    session.clear()
    session["student"] = uid
    audit.record(uid, "student", "login", "allowed", "success")
    return jsonify(ok=True, student=uid, name=database.student_name(uid))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    sid = session.get("student")
    return jsonify(student=sid, name=database.student_name(sid) if sid else None)


# ---------------- student endpoints ----------------
@app.post("/api/chat")
@student_required
def chat(sid):
    d = request.get_json(silent=True) or {}
    msg = redact((d.get("message") or "").strip())  # secrets never reach the model, traces or logs
    if not msg:
        return jsonify(error="Type a message."), 400
    raw = d.get("history", [])
    raw = raw if isinstance(raw, list) else []
    history = [{"role": h["role"], "content": redact(str(h.get("content", ""))[:2000])} for h in raw[-12:]
               if isinstance(h, dict) and h.get("role") in ("user", "assistant")]
    return jsonify(run_agent(msg[:1000], sid, history, d.get("session_id", "web")).model_dump())


@app.get("/api/memory")
@student_required
def get_memory(sid):
    return jsonify(memory.list_memory(sid))


@app.post("/api/memory")
@student_required
def add_memory(sid):
    d = request.get_json(silent=True) or {}
    key = str(d.get("key", "")).strip()[:50]
    val = str(d.get("value", "")).strip()[:150]
    if not key or not val:
        return jsonify(error="Key and value are required."), 400
    r = memory.save_memory(sid, key, val)
    return jsonify(r), (200 if r.get("ok") else 400)


@app.delete("/api/memory/<int:mid>")
@student_required
def del_memory(sid, mid):
    return jsonify(ok=memory.delete_memory(sid, mid))


@app.delete("/api/memory")
@student_required
def clear_all_memory(sid):
    memory.clear_memory(sid)
    return jsonify(ok=True)


@app.get("/api/requests")
@student_required
def my_requests(sid):
    return jsonify(approvals.list_for_student(sid))  # only this student's own requests


@app.post("/api/requests/<approval_id>/decide")
@student_required
def decide_request(sid, approval_id):
    """The Approve / Reject buttons call this. Identity is the session; only the owner's own request can be decided."""
    d = request.get_json(silent=True) or {}
    r = approvals.decide(approval_id, sid, d.get("decision"))
    return jsonify(r), (200 if r["ok"] else 400)


@app.get("/api/audit")
@student_required
def my_audit(sid):
    """The student's own recent audit records (what they did / tried, and the decision), plus chain status."""
    ok, bad = audit.verify_chain()
    return jsonify(rows=audit.list_for_actor(sid, 25), chain_ok=ok)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve
        print(f"Production WSGI server running on http://0.0.0.0:{port}")
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=False)
