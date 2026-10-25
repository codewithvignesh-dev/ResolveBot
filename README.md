# ResolveBot

Customer-support chat API for the fictional ShopSphere store. `POST /chat` on port 8000, FastAPI + Groq (Llama 3.3 70B, tool calling).

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # put your own GROQ_API_KEY in .env
# place the evaluator's data/ folder next to main.py (it is git-ignored)
uvicorn main:app --port 8000
```
```bash
curl -X POST http://127.0.0.1:8000/chat -H 'Content-Type: application/json' -H 'X-Customer-Id: C1009' \
  -d '{"session_id":"s1","message":"Return the speaker from SS-10458, I changed my mind."}'
```
Settings (all in `.env.example`): `POLICIES_PATH`, `MANIFEST_PATH`, `DB_PATH`, `APP_TODAY` (default 2026-07-01), `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `TOTAL_BUDGET_SECONDS`, `MAX_TOOL_CALLS` (6). Temperature is always 0.

## Files
| File | Role |
|---|---|
| `main.py` | HTTP only: 400 / 401 / 403 mapping, session ownership check |
| `agent.py` | Groq tool loop, proposal and confirmation handling, response contract |
| `tools.py` | The five tools (exact names) + their JSON schemas |
| `business_rules.py` | All decisions: ownership guard, return rules, warranty dates, cancellation |
| `policy_search.py` | Splits `policies.md`, joins `manifest.json`, filters, BM25 search |
| `sessions.py`, `database.py` | Session owner/history/pending proposal (2 added tables), SQLite + transactions |

## How it works
- **Identity**: customer id comes only from `X-Customer-Id`; tools never accept it from the LLM. Every `order_id` goes through one ownership query, so a missing and a foreign order both give `ORDER_NOT_FOUND` and the exact reply "I couldn't find that order on your account." (route `no_answer`).
- **Rules in Python**: return order of checks, warranty end date (`relativedelta`, end date still covered), cancellation only when `processing`. All numbers come from `policy_parameters`; "today" is `APP_TODAY`, never the system clock.
- **Policy search**: `policies.md` is split into the 10 documents and then into `§` sections, matched to the manifest by `doc_id`. Only `status=current` documents are searched; superseded ones are never returned. A document whose `effective_date` is after `APP_TODAY` is returned labelled "NOT YET IN EFFECT" so it can only be mentioned as a future change. Search is BM25 with a heading boost (no model download, runs anywhere). Only the top 5 paragraphs are sent to the LLM. The LLM lists which sections it used; citations are limited to paragraphs search actually returned. Policy beats FAQ via a small score penalty on FAQs, plus a prompt rule.
- **Propose, then do**: when the LLM calls `create_return_request` / `create_support_ticket`, Python only *checks* eligibility, stores one pending proposal in the session and reports `pending_confirmation` (nothing written). On the next message the proposal is read-and-cleared in one transaction. If the message is a clear yes (`yes`, `confirm`, `go ahead`, `please do`...) the eligibility check is repeated inside the insert transaction and one row is written (no LLM involved). Any other message just drops the proposal and is handled normally, so "just the power bank" produces a new proposal. A replayed "yes" cannot write twice.
- **Tool loop** capped at `MAX_TOOL_CALLS`; provider errors return a polite `no_answer` 200 reply, never a stack trace.

## Assumptions
- Order ids are matched case-insensitively. Cancelled orders cannot get a cancellation ticket (`ALREADY_CANCELLED`, an extra code); delivered orders return `ORDER_ALREADY_SHIPPED`.
- A warranty ticket is allowed if at least one item in the delivered order is under warranty.
- The "yes" detector is deliberately strict: "just do it" or "yes but ..." is not a confirmation.
- Session history keeps the last 10 messages.

## Not done / limitations
- I could not install FastAPI in my build sandbox (no PyPI access), so `main.py` and the real Groq call were **not run end to end by me**. `agent.py`, rules, search and sessions were tested offline with a scripted fake LLM (`DATA_DIR=<data> python tests/test_flow.py`). Please run the curl above once with a real key.
- Llama via Groq sometimes emits malformed tool calls; I retry once, then return the polite error.
- Routing, `ROUTE:`/`CITES:` footer and the ask-back questions depend on the LLM following the prompt; ownership, eligibility and writes do not.
- BM25 is keyword based, so unusual wording may miss a section.

## AI assistant use
Claude (Claude Code) helped write the code and this README; I reviewed it and can explain every module.
