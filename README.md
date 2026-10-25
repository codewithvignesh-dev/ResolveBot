# ResolveBot --- Build Plan & Implementation Checklist

> **Document status:** Initial implementation plan\
> **Purpose:** Working checklist for building the ResolveBot assessment
> project. Update this file as implementation decisions are verified.\
> **Runtime:** Python 3.10+\
> **API framework:** FastAPI\
> **Primary endpoint:** `POST /chat` on port `8000`\
> **UI:** No custom frontend is required; the API alone is sufficient.

------------------------------------------------------------------------

## 1. Project Goal

Build ResolveBot, a small HTTP customer-support assistant for the
fictional ShopSphere store. It must answer questions about a customer's
own orders and store policies, evaluate return and warranty rules
deterministically in Python, and create return requests or support
tickets only after explicit confirmation.

### Core principles

-   [ ] Treat the supplied assessment files and task instructions as the
    source of truth.
-   [ ] Inspect the task PDF, policy document, policy manifest, and
    actual SQLite schema before implementing rules.
-   [ ] Do not invent policy rules, database fields, sample records, or
    requirements.
-   [ ] Do not hardcode business values that are stored in the database.
-   [ ] Keep business decisions and eligibility checks in deterministic
    Python code; use the LLM for language understanding and response
    composition.
-   [ ] Verify order ownership for every order-related operation.
-   [ ] Never write to the database when merely proposing an action.
-   [ ] Keep the implementation modular, readable, testable, and easy to
    explain in an interview.
-   [ ] Keep real secrets and confidential assessment data out of the
    submitted repository.

## 2. Scope

### In scope

-   [ ] `POST /chat` API endpoint.
-   [ ] Customer identity supplied through `X-Customer-Id`.
-   [ ] Session ownership and short conversation state.
-   [ ] Order lookup, item details, shipment status, and ETA.
-   [ ] Policy retrieval from `policies.md`, filtered using
    `manifest.json`.
-   [ ] Citations for policy sources actually used.
-   [ ] Deterministic return eligibility checks.
-   [ ] Return request creation after confirmation.
-   [ ] Warranty support-ticket creation after confirmation.
-   [ ] Cancellation support-ticket creation after confirmation when
    allowed.
-   [ ] Clarification for missing or ambiguous order/item/reason
    details.
-   [ ] Out-of-scope handling.
-   [ ] Input validation, safe database access, useful errors, and
    bounded LLM tool use.
-   [ ] README, environment template, ignore rules, and focused tests.

### Explicitly out of scope for the assessment

-   [ ] Custom web/mobile UI.
-   [ ] Implementing a full customer login/authentication system.
-   [ ] Real payment processing or refund transfer.
-   [ ] Sending emails or contacting carriers.
-   [ ] Adding unrelated features not required by the task.
-   [ ] Docker/container orchestration unless later shown to be
    necessary.

## 3. Source-of-Truth Audit

Before coding, verify the following files and record any uncertainty
rather than guessing.

-   [ ] Read `TASK.pdf` completely.
-   [ ] Read `data/policies.md` completely.
-   [ ] Read `data/manifest.json` completely.
-   [ ] Inspect the actual SQLite schema and sample values in
    `data/shopsphere.db`.
-   [ ] Compare task descriptions with actual database columns.
-   [ ] Confirm required API request and response fields.
-   [ ] Confirm the five required tool names and their arguments.
-   [ ] Confirm all specified error codes and HTTP status mappings.
-   [ ] Record any unresolved ambiguity and the minimal assumption used.
-   [ ] Keep assessment-provided `data/` files out of the final
    submission if the task requires it.

### Existing SQLite tables to preserve

Do not rename, remove, or modify existing tables/columns. Inspect the
database before writing queries.

-   `customers`
-   `products`
-   `orders`
-   `order_items`
-   `shipments`
-   `policy_parameters`
-   `return_requests`
-   `support_tickets`

The actual columns in the supplied database are authoritative. Do not
rely solely on abbreviated schemas in task prose. Additional tables may
be added only where needed for session ownership or conversation state.

## 4. Required API Contract

### Endpoint

`POST /chat`

### Request

Required header:

-   `X-Customer-Id: <customer_id>`

JSON body:

``` json
{
  "session_id": "session-unique-id",
  "message": "Where is my order?"
}
```

### Response shape

Keep the response fields and route values exactly aligned with
`TASK.pdf`.

``` json
{
  "request_id": "request-unique-id",
  "answer": "Response for the customer",
  "route": "answer",
  "citations": [],
  "tool_calls": [],
  "pending_confirmation": false
}
```

Required response fields:

-   [ ] `request_id`
-   [ ] `answer`
-   [ ] `route`
-   [ ] `citations`
-   [ ] `tool_calls`
-   [ ] `pending_confirmation`

Allowed route values:

-   `answer`
-   `clarify`
-   `no_answer`
-   `out_of_scope`

### HTTP status handling

-   [ ] `400` --- invalid JSON or missing `session_id` / `message`.
-   [ ] `401` --- missing or unknown `X-Customer-Id`.
-   [ ] `403` --- the session belongs to a different customer.
-   [ ] `200` --- business outcomes, including an order not found on the
    customer's account.

For an order that is missing or belongs to another customer, return the
exact required answer:

`I couldn't find that order on your account.`

Do not reveal whether an order exists for a different customer.

## 5. Required Tools

Implement exactly these five tool names. Keep tool schemas clear and
validate every argument in Python.

### 5.1 `get_orders(order_id optional, status optional)`

-   [ ] Return only orders owned by the current customer.
-   [ ] Support optional order ID and status filters.
-   [ ] Include relevant order items and delivery/shipment details.
-   [ ] Derive delivery date and days since delivery where possible.
-   [ ] Derive warranty end date and whether warranty is active for each
    item.
-   [ ] Avoid exposing another customer's order data.

### 5.2 `search_policy(query)`

-   [ ] Search relevant sections of `policies.md`.
-   [ ] Use `manifest.json` to determine document status and effective
    date.
-   [ ] Include only documents marked current and effective on or before
    `APP_TODAY`.
-   [ ] Give policy documents precedence over FAQs when sources
    conflict, as required by the task.
-   [ ] Return citations identifying the document and section.
-   [ ] Cite only sources actually used in the answer.
-   [ ] Return `no_answer` when no applicable source supports an answer.

### 5.3 `check_return_eligibility(order_id, item_ids, reason)`

-   [ ] Accept only supported reasons: `changed_mind` or `defective`.
-   [ ] Validate customer ownership and order existence.
-   [ ] Validate that every requested item belongs to the specified
    order.
-   [ ] Require the order to be delivered.
-   [ ] Check the product's returnability.
-   [ ] Read `return_window_days` from `policy_parameters`.
-   [ ] Apply opened-item restrictions for `unopened_only` products and
    `changed_mind` returns.
-   [ ] Permit a defective reason for an opened item when all other
    eligibility rules pass.
-   [ ] Return structured eligibility results and the specified error
    codes.

### 5.4 `create_return_request(order_id, item_ids, reason)`

-   [ ] Require a valid, eligible return proposal.
-   [ ] Do not write at proposal time.
-   [ ] Recheck ownership and eligibility immediately before writing.
-   [ ] Use a database transaction.
-   [ ] Create a unique request ID.
-   [ ] Set initial status to `requested`.
-   [ ] Use a current timestamp for the record's creation time.
-   [ ] Prevent duplicate or stale confirmations from creating
    unintended extra records.

### 5.5 `create_support_ticket(order_id, ticket_type, summary)`

-   [ ] Accept only `warranty` or `cancellation`.
-   [ ] Verify order ownership.
-   [ ] For warranty tickets, require a delivered order and at least one
    item with active warranty.
-   [ ] For cancellation tickets, allow only orders with status
    `processing`.
-   [ ] If already shipped, return `ORDER_ALREADY_SHIPPED`.
-   [ ] Do not write at proposal time.
-   [ ] Recheck eligibility immediately before writing.
-   [ ] Use a transaction, unique ticket ID, creation timestamp, and
    initial status `open`.

## 6. Deterministic Business Rules

Implement these in a dedicated Python module; do not ask the LLM to
decide eligibility.

### Return eligibility --- check in the required order

-   [ ] Verify the order exists and belongs to the requesting customer.
-   [ ] Verify all item IDs belong to that order.
-   [ ] Verify the order is delivered.
-   [ ] Verify the product is returnable.
-   [ ] Calculate days since delivery using the configured business
    date.
-   [ ] Compare against the database's `return_window_days` parameter.
-   [ ] If product returnability is `unopened_only`, reject an opened
    item for `changed_mind`.
-   [ ] Allow an opened item with `defective` reason if the other checks
    pass.
-   [ ] Return the exact required error code for the first failing rule.

Error codes to cover:

-   `ORDER_NOT_FOUND`
-   `INVALID_ITEM`
-   `INVALID_REASON`
-   `NOT_DELIVERED`
-   `NON_RETURNABLE`
-   `OPENED_NOT_RETURNABLE`
-   `RETURN_WINDOW_EXPIRED`

### Warranty calculation

-   [ ] Read standard and extended warranty durations from
    `policy_parameters`.
-   [ ] Handle products with warranty class `standard`, `extended`, or
    `none`.
-   [ ] Use the delivery date as the warranty start reference when
    required by the task.
-   [ ] Calculate month-based dates with calendar-aware logic such as
    `dateutil.relativedelta`.
-   [ ] If the target month lacks the original day, use the final day of
    that month.
-   [ ] Treat the calculated warranty end date as inclusive.
-   [ ] Use `APP_TODAY` for business-date decisions, not the machine's
    current date.
-   [ ] Cover `WARRANTY_EXPIRED` and `NO_WARRANTY`.

### Cancellation

-   [ ] Allow cancellation-ticket proposals only when order status is
    `processing`.
-   [ ] If order status indicates shipped, return
    `ORDER_ALREADY_SHIPPED`.
-   [ ] Recheck status immediately before the write.

### Error behavior

-   [ ] Include `ORDER_NOT_FOUND` for missing/foreign orders internally
    while returning the exact same customer-facing message for both
    cases.
-   [ ] Cover `INVALID_TICKET_TYPE`.
-   [ ] Cover `WARRANTY_EXPIRED`, `NO_WARRANTY`, and
    `ORDER_ALREADY_SHIPPED`.
-   [ ] Do not leak SQL, stack traces, provider details, or secrets to
    customers.

## 7. Session and Confirmation Safety

No database mutation may occur until the customer confirms a proposal in
the very next message of the same session.

-   [ ] Associate every session with the customer ID that first created
    it.
-   [ ] Reject session reuse by another customer with HTTP `403`.
-   [ ] Keep at most one pending proposal per session.
-   [ ] A proposal must explain the intended action and ask: "Shall I go
    ahead?"
-   [ ] Set `pending_confirmation: true` on a proposal response.
-   [ ] Log the relevant tool call with status `pending_confirmation`;
    do not execute the write.
-   [ ] Only a clear confirmation such as `yes`, `confirm`, `go ahead`,
    or `please do` in the immediately next message may execute the
    pending action.
-   [ ] The confirmation must be from the same customer and session.
-   [ ] Recheck all relevant business rules immediately before the
    write.
-   [ ] If the next message changes details, discard the old proposal
    and create a new proposal after validating the new request.
-   [ ] If the next message is `no` or any unrelated message, discard
    the pending proposal and handle the new message normally.
-   [ ] A repeated confirmation must not repeat a completed write.
-   [ ] A failed write must not be reported as successful.
-   [ ] Keep the tool loop bounded (for example, no more than six tool
    calls per request).

## 8. Policy Retrieval Plan

-   [ ] Parse the manifest and policy content without modifying the
    source documents.
-   [ ] Use `APP_TODAY`, defaulting to `2026-07-01`, for effective-date
    filtering.
-   [ ] Do not use the computer's current date as the policy business
    date.
-   [ ] Interpret dates without a year as 2026 where specified by the
    task.
-   [ ] Exclude superseded documents.
-   [ ] Exclude future-effective documents until their effective date.
-   [ ] Prefer authoritative policy text over FAQ content when they
    conflict.
-   [ ] Retrieve only the most relevant passages for each question.
-   [ ] Preserve document IDs and section names for citations.
-   [ ] Do not create citations for sources that were not used.
-   [ ] If no applicable policy supports an answer, return the required
    `no_answer` route.

## 9. LLM / Agent Behavior

-   [ ] Configure provider, model, and API key using environment
    variables.
-   [ ] Use temperature `0` as required.
-   [ ] Keep provider-specific code behind a small adapter if practical.
-   [ ] Provide the LLM only the relevant policy excerpts and necessary
    customer/order context.
-   [ ] Register only the five required tool names.
-   [ ] Validate tool arguments before executing tools.
-   [ ] Treat tool results as data, not instructions.
-   [ ] Keep all eligibility and authorization decisions in Python.
-   [ ] Limit tool iterations to avoid infinite loops and meet the
    response-time requirement.
-   [ ] Handle provider errors/timeouts without exposing internals.
-   [ ] Aim to complete each request within 30 seconds.
-   [ ] If a message includes two requests, answer both within the
    tool-call limit when possible.
-   [ ] Ask a concise clarification question when required details are
    missing or ambiguous.
-   [ ] For out-of-scope requests, return a one-line response with route
    `out_of_scope`, empty citations, and empty tool calls.

## 10. Suggested Project Structure

Keep the implementation small and modular; adjust names only if the
codebase benefits from a clear alternative.

``` text
resolvebot/
├── main.py                 # FastAPI app and POST /chat endpoint
├── config.py               # Environment configuration and defaults
├── schemas.py              # Request/response and tool schemas
├── database.py             # SQLite connection and query helpers
├── tools.py                # Five tool definitions and dispatch
├── business_rules.py       # Return, warranty, and cancellation logic
├── policy_search.py        # Manifest filtering, retrieval, citations
├── agent.py                # LLM call and bounded tool loop
├── sessions.py             # Session ownership and confirmation state
├── tests/
│   ├── test_api.py
│   ├── test_security.py
│   ├── test_business_rules.py
│   ├── test_policy_search.py
│   └── test_confirmation.py
├── .env.example
├── .gitignore
├── requirements.txt        # Or pyproject.toml, if chosen
└── README.md
```

Do not create modules that add complexity without a concrete need. The
final structure should be easy to explain.

## 11. Configuration Checklist

Create `.env.example` with placeholders/defaults only; never commit a
real key.

``` dotenv
POLICIES_PATH=./data/policies.md
MANIFEST_PATH=./data/manifest.json
DB_PATH=./data/shopsphere.db
APP_TODAY=2026-07-01
LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL=
```

-   [ ] Load configuration from environment variables.
-   [ ] Validate required settings at startup and provide actionable
    error messages.
-   [ ] Keep `.env` ignored by Git.
-   [ ] Ensure logs never print API keys or sensitive headers.
-   [ ] Do not include the supplied `data/` folder in the final
    submission if prohibited by the assessment.
-   [ ] Document how the reviewer provides the required data files
    locally without committing them.

## 12. Implementation Roadmap

### Phase 1 --- Requirements audit

-   [ ] Read all supplied files.
-   [ ] Record exact endpoint, tools, response contract, rules, and
    error mappings.
-   [ ] Inspect actual SQLite schema and parameter values.
-   [ ] List uncertainties and decide only source-supported minimal
    assumptions.

**Exit criteria:** A source-backed checklist exists; no coding
assumptions remain hidden.

### Phase 2 --- Project foundation

-   [ ] Create the project structure.
-   [ ] Add configuration loading and `.env.example`.
-   [ ] Add `.gitignore`.
-   [ ] Add FastAPI health/startup basics only if useful; do not invent
    extra public endpoints unless needed.
-   [ ] Add SQLite connection helpers without modifying existing tables.

**Exit criteria:** App imports and starts; configuration errors are
understandable.

### Phase 3 --- Database access and deterministic rules

-   [ ] Implement parameterized SQL queries.
-   [ ] Implement customer ownership checks.
-   [ ] Implement `get_orders`.
-   [ ] Implement return eligibility and all specified error codes.
-   [ ] Implement warranty calculations.
-   [ ] Implement cancellation checks.
-   [ ] Write unit tests for business rules before connecting the LLM.

**Exit criteria:** Core decisions can be tested without an LLM.

### Phase 4 --- Policy retrieval and citations

-   [ ] Parse policy manifest and document sections.
-   [ ] Apply status/effective-date filtering.
-   [ ] Implement relevant passage search.
-   [ ] Implement source precedence and citation tracking.
-   [ ] Test current, superseded, future-effective, conflicting, and
    missing-policy cases.

**Exit criteria:** Policy answers use only applicable sources and
accurate citations.

### Phase 5 --- Session ownership and pending proposals

-   [ ] Persist or safely manage session ownership and pending proposal
    state.
-   [ ] Enforce customer/session ownership.
-   [ ] Implement next-message confirmation behavior.
-   [ ] Ensure proposals do not write.
-   [ ] Ensure `no`, unrelated messages, changed details, and repeated
    confirmations behave correctly.
-   [ ] Recheck eligibility at commit time.

**Exit criteria:** No write can occur without the required explicit
next-message confirmation.

### Phase 6 --- LLM and tool orchestration

-   [ ] Configure the chosen provider through environment variables.
-   [ ] Register exactly the five required tools.
-   [ ] Validate tool arguments and results.
-   [ ] Implement a bounded tool loop.
-   [ ] Implement clarification, out-of-scope, no-answer, and
    normal-answer paths.
-   [ ] Handle timeouts and provider failures safely.

**Exit criteria:** Natural-language messages route to correct tools
without bypassing deterministic rules.

### Phase 7 --- API contract and security tests

-   [ ] Implement exact request/response schemas.
-   [ ] Implement HTTP `400`, `401`, and `403` cases.
-   [ ] Test identical customer-facing responses for nonexistent and
    foreign orders.
-   [ ] Test session ownership.
-   [ ] Test return-window boundary and altered database parameters.
-   [ ] Test confirmation safety and duplicate prevention.
-   [ ] Test policy filtering and citations.
-   [ ] Test tool-call limit and multi-intent requests.
-   [ ] Verify response-time target.

**Exit criteria:** All five assessment must-pass checks pass.

### Phase 8 --- Documentation and submission

-   [ ] Complete installation and run instructions.
-   [ ] Add example requests and response flows.
-   [ ] Document architecture, tools, policy retrieval, and confirmation
    behavior.
-   [ ] Document assumptions, limitations, and known issues.
-   [ ] Disclose AI coding assistant use as required by the assessment.
-   [ ] Verify `.env.example` contains no real secrets.
-   [ ] Verify `data/` is excluded where required.
-   [ ] Test from a clean environment using only README instructions.
-   [ ] Review final Git diff and commit history.
-   [ ] Submit the GitHub link or private ZIP according to the
    assessment instructions.

**Exit criteria:** A reviewer can install, run, understand, and test the
project without undocumented steps.

## 13. Must-Pass Evaluation Checklist

-   [ ] The application starts using the documented command.
-   [ ] The API response contains the exact required fields and valid
    route values.
-   [ ] No return/ticket row is created before explicit next-message
    confirmation.
-   [ ] Return eligibility changes correctly when `policy_parameters`
    values change.
-   [ ] One customer's request cannot reveal another customer's order.
-   [ ] A session cannot be reused by another customer.
-   [ ] A missing order and a foreign order return the same exact
    user-facing message.
-   [ ] Policy citations refer only to applicable sources actually used.
-   [ ] No secrets or prohibited assessment data are committed.

## 14. Critical Test Matrix

### API and identity

-   [ ] Valid customer header and valid request.
-   [ ] Missing customer header.
-   [ ] Unknown customer ID.
-   [ ] Invalid JSON.
-   [ ] Missing `session_id`.
-   [ ] Missing `message`.
-   [ ] Session reused by another customer.
-   [ ] Nonexistent order versus another customer's order.

### Returns

-   [ ] Valid return within the configured window.
-   [ ] Return on the final eligible day.
-   [ ] Return one day after the configured window.
-   [ ] Non-returnable product.
-   [ ] Opened `unopened_only` item with `changed_mind`.
-   [ ] Opened `unopened_only` item with `defective`.
-   [ ] Invalid item ID.
-   [ ] Invalid reason.
-   [ ] Order not delivered.
-   [ ] Database return-window parameter changed between test runs.

### Warranty and cancellation

-   [ ] Standard warranty active and expired.
-   [ ] Extended warranty active and expired.
-   [ ] No-warranty product.
-   [ ] Warranty end date is inclusive.
-   [ ] Month-end warranty date, such as a date starting on the 31st.
-   [ ] Warranty ticket for an undelivered order.
-   [ ] Cancellation proposal for `processing`.
-   [ ] Cancellation request for shipped order.

### Confirmation

-   [ ] Proposal response creates no database row.
-   [ ] Immediate valid `yes` creates exactly one row.
-   [ ] `no` discards proposal.
-   [ ] Unrelated next message discards proposal and is handled
    normally.
-   [ ] Changed details trigger a fresh proposal.
-   [ ] Confirmation from a different session does not execute the
    proposal.
-   [ ] Confirmation from a different customer is rejected.
-   [ ] Repeated confirmation does not create a duplicate row.
-   [ ] Eligibility is rechecked before the write.

### Policies and agent

-   [ ] Current policy document is considered.
-   [ ] Superseded document is excluded.
-   [ ] Future-effective document is excluded before its effective date.
-   [ ] Policy text takes precedence over conflicting FAQ where
    required.
-   [ ] No supporting policy produces `no_answer`.
-   [ ] Citations contain the correct document ID and section.
-   [ ] Out-of-scope response has empty citations and tool calls.
-   [ ] Tool loop stops at its configured limit.
-   [ ] Two requests in one message are handled within the limit when
    possible.

## 15. Manual API Smoke Test

Start the service using the documented command, for example:

``` bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then call the endpoint with a known test customer ID supplied by the
assessment data:

``` bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -H "X-Customer-Id: <CUSTOMER_ID>" \
  -d '{
    "session_id": "smoke-test-session",
    "message": "Can you show my orders?"
  }'
```

-   [ ] Confirm the server starts.
-   [ ] Confirm response JSON parses and contains every required field.
-   [ ] Confirm the HTTP status is correct.
-   [ ] Confirm no private data is logged unnecessarily.
-   [ ] Confirm a policy question returns citations where applicable.
-   [ ] Confirm a write action first produces a proposal only.

Use only test IDs from the authorized assessment data; do not invent
real customer data.

## 16. README / Submission Hygiene

-   [ ] Use Python 3.10 or later.
-   [ ] Provide one clear install/run path.
-   [ ] Pin or constrain dependencies appropriately.
-   [ ] Provide `.env.example`; do not commit `.env`.
-   [ ] Keep `__pycache__/`, virtual environments, test caches, logs,
    and local database copies out of Git.
-   [ ] Keep API keys, tokens, passwords, and personal data out of
    source code and commits.
-   [ ] Follow the assessment's confidentiality and data-sharing
    instructions.
-   [ ] Do not include the supplied `data/` directory in the submission
    if the task says not to.
-   [ ] Include a concise explanation of how AI coding tools were used,
    as requested by the assessment.
-   [ ] Be prepared to explain each module, business rule, test, and
    design decision yourself.

## 17. Known Decisions and Items to Confirm

-   [ ] Confirm the final LLM provider and model supported by the
    assessment environment.
-   [ ] Confirm whether the evaluator supplies the data files separately
    and how paths should be configured.
-   [ ] Confirm any unclear date or business-rule interpretation
    directly from the task files.
-   [ ] Keep `APP_TODAY` configurable with default `2026-07-01`; do not
    substitute the machine date for business calculations.
-   [ ] Confirm the final repository visibility and license choice
    comply with assessment confidentiality requirements.
-   [ ] Update this section as decisions are verified; do not present an
    unverified assumption as a confirmed requirement.

## 18. Progress Tracker

Update this table as work is completed.

  Phase                                Status        Evidence / Notes
  ------------------------------------ ------------- ------------------
  Requirements audit                   Not started   
  Project foundation                   Not started   
  Database access and business rules   Not started   
  Policy retrieval and citations       Not started   
  Session and confirmation safety      Not started   
  LLM tool orchestration               Not started   
  API contract and security tests      Not started   
  Documentation and submission         Not started   

**Status values:** `Not started`, `In progress`, `Blocked`, `Complete`.

------------------------------------------------------------------------

## 19. Definition of Done

The project is ready for submission only when:

-   [ ] The service starts from a clean environment using the README
    instructions.
-   [ ] `POST /chat` matches the required contract.
-   [ ] All five tools work and enforce authorization.
-   [ ] Business rules are deterministic and read configurable policy
    parameters from SQLite.
-   [ ] Policy retrieval filters sources correctly and citations are
    grounded.
-   [ ] No write occurs without valid immediate confirmation.
-   [ ] The critical tests pass.
-   [ ] Secrets and prohibited assessment data are excluded.
-   [ ] README setup, assumptions, examples, limitations, and
    AI-assistant disclosure are current.
-   [ ] The implementation is understood well enough to explain without
    relying on the coding assistant.
