# QueueStorm Investigator

**Team:** puc_cats&dogs — Premier University  
**Members:** Shafayet Ullah Ramim · Minhaj Uddin Hassan · Khaledul Belal  
**Event:** SUST CSE Carnival 2026 · Codex Community Hackathon

---

## Live Endpoint

```
GET  https://queuestorm-klcj.onrender.com/health
POST https://queuestorm-klcj.onrender.com/analyze-ticket
```

No login, no API key, no private access required.

---

## Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Docker

```bash
docker build -t queuestorm .
docker run -p 8000:8000 queuestorm
```

---

## API

| Method | Path              | Response                 |
| ------ | ----------------- | ------------------------ |
| GET    | `/health`         | `{"status":"ok"}`        |
| POST   | `/analyze-ticket` | Structured JSON analysis |

**Status codes:** `200` success · `400` bad input · `422` empty complaint · `500` internal error

---

## Sample Request

```bash
curl -X POST https://queuestorm-klcj.onrender.com/analyze-ticket \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

**Response:**

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

---

## AI / Model Usage

**No LLM used.** Fully rule-based engine — no API keys, no GPU, no external calls.

| Model              | Where           | Why                                                                                 |
| ------------------ | --------------- | ----------------------------------------------------------------------------------- |
| None (rule engine) | In-process, CPU | Maximizes reliability, latency, and safety. No quota or outage risk during judging. |

---

## Safety Logic

Enforced as a hard post-processing gate in `app/safety.py`:

- Never asks for PIN, OTP, password, or card number
- Never promises a refund — uses _"any eligible amount will be returned through official channels"_
- Never directs customers to third parties outside official channels
- Prompt injection attempts in complaint text have zero effect — complaint is treated as data only

---

## Tech Stack

Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · stdlib only for reasoning engine

**Latency:** ~1ms mean, ~1ms p95 (tested over 300 requests)

---

## Environment Variables

None required. See `.env.example` for optional overrides.
