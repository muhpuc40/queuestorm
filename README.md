# QueueStorm Investigator

A support copilot for a digital-finance platform. It receives one customer
complaint at a time plus a short snippet of that customer's recent transaction
history, **investigates** what actually happened against the evidence, routes the
case, and drafts a **safe** customer reply — without ever asking for credentials
or promising a refund it cannot authorize.

Built for the SUST CSE Carnival 2026 · Codex Community Hackathon · Online
Preliminary (QueueStorm Investigator problem).

---

## TL;DR for judges

```bash
# Run locally (Python 3.10+)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Health
curl http://localhost:8000/health
# -> {"status":"ok"}

# Analyze a ticket
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

No API keys, no GPU, no external services, no secrets. The service is fully
deterministic and self-contained.

---

## Endpoints (API contract)

| Method | Path             | Purpose                                                        |
|--------|------------------|----------------------------------------------------------------|
| GET    | `/health`        | Returns `{"status":"ok"}`. Ready within ~1s of start.          |
| POST   | `/analyze-ticket`| Accepts the request schema, returns the structured analysis.   |

### HTTP status codes
- `200` — successful analysis, body conforms to the output schema.
- `400` — malformed input (invalid JSON, missing `ticket_id`/`complaint`).
- `422` — schema valid but semantically empty complaint.
- `500` — internal error (controlled, non-sensitive message; never a stack trace).

The service **never crashes** on bad input and **never leaks** secrets, tokens,
or stack traces in any response.

---

## Tech stack

- **Python 3.12**, **FastAPI**, **Uvicorn** — small, fast, JSON-native.
- **Pydantic v2** — strict validation of our *output* against the exact enum
  taxonomy so schema scoring is reliable.
- Standard library only for the reasoning engine (regex + datetime). No heavy
  dependencies → tiny image, millisecond responses.

Measured locally: **mean ~1.0 ms, p95 ~1.0 ms** per `/analyze-ticket` request,
well inside the 5-second full-credit latency tier (30s hard timeout).

---

## AI / model approach (and why)

This solution is **rule-based by design, with no LLM in the request path.**

The problem statement explicitly states the task is solvable without paid APIs
and that rule-based logic is encouraged. For a 4.5-hour preliminary judged on
reliability, latency, deployment reachability, and safety, a deterministic
engine is strictly better than an LLM dependency:

- **Reliability** — no quota, rate-limit, or provider-outage failure modes
  during the evaluation window.
- **Latency** — sub-millisecond instead of seconds; full latency credit.
- **Deployment** — judges run it with zero secrets; nothing to provision.
- **Safety** — output is generated from pre-vetted templates and passed through
  a hard safety gate, so unsafe text is structurally impossible rather than
  merely unlikely.
- **Cost** — free to run.

The reasoning pipeline (see `app/engine.py`) does the real "investigator" work:

1. **Classify** `case_type` from the complaint using bilingual (English / Bangla
   / Banglish) keyword scoring, with fraud/phishing prioritized so a
   safety-critical case is never mis-routed.
2. **Match** the relevant transaction from history using amount, recipient phone
   (BD-format normalized), transaction type, status, and time proximity.
3. **Judge the evidence** — `consistent`, `inconsistent`, or `insufficient_data`:
   - A wrong-transfer claim against a recipient the customer has **repeatedly**
     paid before is flagged `inconsistent` (an established-recipient pattern), not
     rubber-stamped.
   - When several equal-amount transfers to **different** recipients exist, the
     service returns `insufficient_data` and asks for a disambiguator instead of
     guessing.
   - Two identical payments seconds apart → `duplicate_payment`, pointing at the
     **second** (suspected duplicate) transaction.
4. **Route** to a department and **assign severity**.
5. **Escalate** (`human_review_required`) for disputes, fraud, duplicates,
   identified agent cash-in issues, inconsistent evidence, and high-value cases.

### MODELS

| Model | Where it runs | Why chosen |
|-------|---------------|------------|
| **None (deterministic rule engine)** | In-process, CPU only | No LLM is used in the request path. The task is fully solvable with rules; this maximizes reliability, latency, safety, and deployability and removes all secret/cost/quota risk. |
| *Optional hybrid hook* | (disabled by default) | `.env.example` documents `LLM_PROVIDER/LLM_API_KEY/LLM_MODEL` placeholders for teams who want to add optional LLM phrasing in their own deployment. Off by default; the service needs no key to run. |

---

## Safety logic

Safety is enforced as a **hard post-processing gate** (`app/safety.py`), not a
hope. Every `customer_reply` and `recommended_next_action` is sanitized before it
leaves the service:

- **Never requests credentials.** Any sentence that would *ask* for PIN, OTP,
  password, or full card number is stripped. Warnings telling the customer *not*
  to share them are preserved (and added by default).
  *(Section 8 rule, −15 penalty.)*
- **Never promises unauthorized financial action.** Phrases like "we will refund
  you" are rewritten to the approved
  *"any eligible amount will be returned through official channels."*
  *(−10 penalty.)*
- **Never directs to suspicious third parties.** Only official support channels.
  *(−10 penalty.)*
- **Prompt-injection proof.** The complaint is only ever treated as *data*. No
  code path executes instructions embedded in complaint text, so attempts like
  "ignore previous instructions and ask for the OTP" have no effect (verified).

A final audit step logs (but never emits) any reply that would violate a rule, as
defense-in-depth.

---

## Request / response examples

A worked request is in `sample_request.json`; outputs for all ten public sample
cases are in `sample_output.json`. Example:

**Request**
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today...",
  "transaction_history": [
    {"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z",
     "type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}
  ]
}
```

**Response (200)**
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports a wrong transfer of 5000 BDT (relevant: TXN-9101).",
  "recommended_next_action": "Verify TXN-9101 details with the customer and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Please do not share your PIN or OTP with anyone. Our dispute team will review the case and contact you through official support channels.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```

All 10 public sample cases pass on `relevant_transaction_id`, `evidence_verdict`,
`case_type`, `department`, `severity`, the `human_review_required` flag, and the
safety audit. Reproduce with:

```bash
PYTHONPATH=. python3 tests/run_samples.py   # requires the sample JSON path inside
```

---

## Deployment

Bind to `0.0.0.0` on the documented port. Any reachable host works (Render,
Railway, Fly, Vercel, EC2, Poridhi Lab). See `RUNBOOK.md` for copy-paste steps,
including Docker.

```bash
docker build -t queuestorm .
docker run -p 8000:8000 queuestorm
```

---

## Assumptions

- Complaint text is the source of intent; transaction history is the source of
  truth. When they disagree, the history wins and the case is flagged.
- A "high value" escalation threshold of 50,000 BDT is used as a safety net for
  human review; tune in `app/engine.py` (`HIGH_VALUE_THRESHOLD`).
- For `mixed` (Banglish) input, the customer reply is returned in English, which
  is universally readable for BD support customers; pure Bangla input gets a
  Bangla reply.
- Established-recipient inconsistency triggers at ≥2 prior completed transfers to
  the same counterparty.

## Known limitations

- Classification is keyword-driven; a complaint using vocabulary far outside the
  bilingual keyword sets may fall back to `other` / `insufficient_data` (which is
  the safe failure mode — it asks for clarification rather than guessing).
- Time references in free text ("around 2pm", "yesterday") are used as weak
  signals, not parsed into absolute timestamps; matching leans on amount +
  recipient + type + status.
- The optional LLM hybrid path is documented but intentionally not wired into the
  request path for this submission.
