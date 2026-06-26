"""
Orchestration: turn a validated request into a complete, safety-gated response.
"""
from __future__ import annotations

from typing import Optional

from . import engine, templates
from .safety import sanitize_customer_reply, sanitize_next_action
from .text import detect_language, extract_amounts


def _amount_for_severity(complaint: str, matched_tx: Optional[dict]) -> Optional[float]:
    if matched_tx and matched_tx.get("amount") is not None:
        try:
            return float(matched_tx["amount"])
        except (TypeError, ValueError):
            pass
    amts = extract_amounts(complaint)
    return max(amts) if amts else None


def _summarize(case_type, txid, verdict, amount, user_type) -> str:
    who = "Merchant" if user_type == "merchant" else "Customer"
    amt = f"{int(amount)} BDT" if amount and amount == int(amount) else (
        f"{amount} BDT" if amount else "an unspecified amount"
    )
    tx = txid or "no matching transaction"

    base = {
        "wrong_transfer": (
            f"{who} reports a wrong transfer of {amt}"
            + (f" (relevant: {txid})" if txid else "")
            + (
                "; transaction history shows an established recipient pattern, so the "
                "claim is flagged as inconsistent for review."
                if verdict == "inconsistent"
                else (
                    "; multiple equal-amount transfers to different recipients exist, "
                    "so the correct transaction cannot be confirmed without more detail."
                    if not txid
                    else "."
                )
            )
        ),
        "payment_failed": (
            f"{who} attempted a {amt} payment ({tx}) which failed, but reports a "
            f"balance deduction. Requires payments operations investigation."
        ),
        "duplicate_payment": (
            f"{who} reports a duplicate payment of {amt}. Two matching payments were "
            f"completed close together; {txid or 'the second entry'} is the likely "
            f"duplicate."
        ),
        "refund_request": (
            f"{who} requests a refund of {amt} for {tx}. Treated as a "
            f"merchant-policy-dependent refund, not a service failure."
        ),
        "merchant_settlement_delay": (
            f"{who} reports a {amt} settlement ({tx}) delayed beyond the expected "
            f"window. Settlement status is pending."
        ),
        "agent_cash_in_issue": (
            f"{who} reports a {amt} agent cash-in ({tx}) not reflected in balance. "
            f"Requires agent operations verification."
        ),
        "phishing_or_social_engineering": (
            f"{who} reports a suspected social-engineering attempt requesting "
            f"credentials. No credentials confirmed shared. Likely fraud."
        ),
        "other": (
            f"{who} raised a vague concern without enough detail to identify a "
            f"relevant transaction. Clarification required."
        ),
    }
    return base.get(case_type, base["other"])


def _confidence(verdict, matched, case_type) -> float:
    if case_type == "phishing_or_social_engineering":
        return 0.95
    if verdict == "consistent" and matched:
        return 0.9
    if verdict == "inconsistent":
        return 0.75
    if verdict == "insufficient_data" and not matched:
        return 0.62
    return 0.7


def analyze(req: dict) -> dict:
    complaint = req.get("complaint") or ""
    complaint_lower = complaint.lower()
    ticket_id = req.get("ticket_id")
    user_type = req.get("user_type")
    # Normalise transaction_history entries to plain dicts.
    history = [
        t if isinstance(t, dict) else t.model_dump()
        for t in (req.get("transaction_history") or [])
    ]

    lang = detect_language(complaint, req.get("language"))

    # 1. classify
    case_type, reasons = engine.classify_case(complaint_lower)

    # 2. match + verdict
    txid, verdict, match_reasons, _debug = engine.match_transaction(
        complaint, complaint_lower, case_type, history
    )
    matched = txid is not None

    matched_tx = next(
        (t for t in history if t.get("transaction_id") == txid), None
    )
    amount = _amount_for_severity(complaint, matched_tx)

    # 3. route + severity + escalation
    department = engine.route_department(case_type, user_type)
    severity = engine.assign_severity(case_type, verdict, amount, matched)
    review = engine.needs_human_review(case_type, verdict, matched, amount)

    # 4. text generation (safe templates)
    # Choose ambiguous clarification template when wrong_transfer is unresolved.
    template_key = case_type
    if case_type == "wrong_transfer" and not matched and verdict == "insufficient_data":
        template_key = "_clarify_ambiguous"
    tmpl = templates.reply_for(template_key, lang, txid, user_type=user_type or "customer")

    customer_reply = sanitize_customer_reply(tmpl["customer_reply"])
    next_action = sanitize_next_action(tmpl["next_action"])
    summary = _summarize(case_type, txid, verdict, amount, user_type)

    reason_codes = list(dict.fromkeys([*reasons, *match_reasons]))[:5]

    return {
        "ticket_id": ticket_id,
        "relevant_transaction_id": txid,
        "evidence_verdict": verdict,
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "agent_summary": summary,
        "recommended_next_action": next_action,
        "customer_reply": customer_reply,
        "human_review_required": review,
        "confidence": round(_confidence(verdict, matched, case_type), 2),
        "reason_codes": reason_codes,
    }
