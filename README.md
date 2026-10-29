# Student Support Portal: Agentic AI Engineering (PGDM 2025-27)

One project, two assignments, kept in separate folders. Each folder runs on its own (own `requirements.txt`, `.env`, database, reports).

| Folder | Assignment | What it contains |
|---|---|---|
| [`Assignment_1/`](Assignment_1) | **Intelligent Student Support Agent** | Agent loop, tools (fee, scholarship, ticket, policy search, memory), persistent memory, BM25 policy retrieval, context selection, tracing, evaluation (T01-T13), chat UI with login |
| [`Assignment_2/`](Assignment_2) | **Safe and Production-Aware Agent** | Everything in Assignment 1 **plus** `authz.py`, `privacy.py`, `approvals.py`, `audit.py`, approval cards, audit-log panel, privacy/unsafe-action tests (P01-P06, U01-U03) and security control tests (C1-C10) |

Assignment 2 is the original combined project, unchanged. Assignment 1 is that same code with only the Assignment 2 layers removed
(see `Assignment_1/README.md` and `Assignment_2/README.md`).

## Quick start (either folder)
```
cd Assignment_1            # or Assignment_2
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     # add GROQ_API_KEY and SECRET_KEY
python scripts/initialize_db.py
python app.py              # http://127.0.0.1:5000   (demo logins: S101/meet@123, S102/harsh@123, S103/neel@123)
python evaluate.py         # writes reports/
```
To fill the "Assignment 1" column of Assignment 2's comparison table: run `evaluate.py` in `Assignment_1`, then copy
`Assignment_1/reports/evaluation_agent.csv` to `Assignment_2/reports/baseline_a1/`, then run `evaluate.py` in `Assignment_2`.
