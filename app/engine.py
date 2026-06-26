"""
The investigator engine.

Pipeline per ticket:
  1. Classify case_type from complaint text (bilingual keyword scoring).
  2. Match the relevant transaction from history (amount + recipient + time +
     type signals), or decide there is no confident match.
  3. Derive evidence_verdict (consistent / inconsistent / insufficient_data)
     from the relationship between the complaint and the matched data.
  4. Route to a department and assign severity.
  5. Decide human_review_required.
  6. Produce a safe agent_summary, recommended_next_action and customer_reply.

The complaint is ALWAYS treated as untrusted data. No branch ever executes an
instruction contained in the complaint, which is what makes the service immune
to the prompt-injection attempts described in Section 8.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from .text import (
    KW,
    contains_any,
    detect_language,
    extract_amounts,
    extract_phones,
    normalize_digits,
    phones_match,
)

HIGH_VALUE_THRESHOLD = 50000.0  # BDT — escalate large-value cases for review.


# --------------------------------------------------------------------------- #
# Step 1 — case classification
# --------------------------------------------------------------------------- #
def classify_case(complaint_lower: str) -> Tuple[str, List[str]]:
    """
    Return (case_type, matched_keywords). Evaluation order encodes priority:
    safety (phishing) first, then specific operational types, then refund, then
    vague/other. Phishing must win even if other words are present, because a
    mis-routed fraud case is the most damaging error.
    """
    reasons: List[str] = []

    # --- phishing / social engineering wins outright ---
    ph = contains_any(complaint_lower, KW["phishing"])
    # Distinguish "someone asked me for OTP" (phishing) from our own safe text.
    phishing_signal = any(
        s in complaint_lower
        for s in (
            "asked for my", "asked me for", "share it", "share my otp",
            "called me", "account will be blocked", "is this real",
            "suspicious", "scam", "fraud", "ওটিপি", "চেয়েছে", "ব্লক",
            "প্রতারণা", "সন্দেহজনক",
        )
    )
    if ph and phishing_signal:
        return "phishing_or_social_engineering", ["phishing", *ph[:3]]

    # --- duplicate payment ---
    dup = contains_any(complaint_lower, KW["duplicate"])
    if dup:
        return "duplicate_payment", ["duplicate_payment", *dup[:2]]

    # --- agent cash-in ---
    ag = contains_any(complaint_lower, KW["agent_cash_in"])
    if ag and any(
        s in complaint_lower
        for s in ("cash in", "cash-in", "cashin", "ক্যাশ ইন", "ক্যাশইন",
                  "agent", "এজেন্ট", "জমা", "deposit")
    ):
        return "agent_cash_in_issue", ["agent_cash_in", *ag[:2]]

    # --- merchant settlement ---
    ms = contains_any(complaint_lower, KW["merchant_settlement"])
    if ms and any(
        s in complaint_lower
        for s in ("settlement", "settled", "settle", "সেটেলমেন্ট", "নিষ্পত্তি",
                  "sales", "বিক্রি", "payout")
    ):
        return "merchant_settlement_delay", ["merchant_settlement", *ms[:2]]

    # --- payment failed (balance deducted on failure) ---
    pf = contains_any(complaint_lower, KW["payment_failed"])
    if pf and any(
        s in complaint_lower
        for s in ("failed", "fail", "ফেইল", "ব্যর্থ", "deducted", "কেটে")
    ):
        return "payment_failed", ["payment_failed", *pf[:2]]

    # --- wrong transfer ---
    wt = contains_any(complaint_lower, KW["wrong_transfer"])
    if wt:
        return "wrong_transfer", ["wrong_transfer", *wt[:2]]

    # --- refund request (after wrong_transfer so "reverse" doesn't steal it) ---
    rf = contains_any(complaint_lower, KW["refund"])
    if rf:
        return "refund_request", ["refund_request", *rf[:2]]

    # --- vague / other ---
    return "other", ["vague_complaint"]


# --------------------------------------------------------------------------- #
# Step 2 — transaction matching
# --------------------------------------------------------------------------- #
def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def match_transaction(
    complaint: str,
    complaint_lower: str,
    case_type: str,
    history: List[dict],
) -> Tuple[Optional[str], str, List[str], dict]:
    """
    Return (relevant_transaction_id, verdict, reason_codes, debug).

    Verdict semantics:
      consistent       — a single transaction matches and supports the complaint
      inconsistent     — a transaction matches but history contradicts the claim
                         (e.g. repeated transfers to a "wrong" recipient)
      insufficient_data— no confident / unique match could be made
    """
    debug: dict = {}
    if not history:
        return None, "insufficient_data", ["no_transaction_history"], debug

    amounts = extract_amounts(complaint)
    phones = extract_phones(complaint)
    debug["amounts"] = amounts
    debug["phones"] = phones

    # ---- duplicate payment: find 2+ same-amount, same-counterparty, close-in-time
    if case_type == "duplicate_payment":
        groups: dict = {}
        for tx in history:
            key = (tx.get("amount"), tx.get("counterparty"), tx.get("type"))
            groups.setdefault(key, []).append(tx)
        for key, txs in groups.items():
            if len(txs) >= 2:
                txs_sorted = sorted(txs, key=lambda x: x.get("timestamp") or "")
                # point at the *second* (suspected duplicate), per SAMPLE-10
                dup_tx = txs_sorted[1]
                return (
                    dup_tx.get("transaction_id"),
                    "consistent",
                    ["duplicate_payment", "biller_verification_required"],
                    debug,
                )
        # claim of duplicate but no duplicate pair found
        return None, "inconsistent", ["duplicate_claim", "no_duplicate_found"], debug

    # ---- merchant settlement: find a settlement entry
    if case_type == "merchant_settlement_delay":
        sett = [t for t in history if (t.get("type") == "settlement")]
        target = sett or history
        # prefer amount match if present
        chosen = _pick_by_amount(target, amounts) or target[0]
        verdict = "consistent" if sett else "insufficient_data"
        return chosen.get("transaction_id"), verdict, ["merchant_settlement"], debug

    # ---- agent cash-in: find a cash_in entry
    if case_type == "agent_cash_in_issue":
        ci = [t for t in history if t.get("type") == "cash_in"]
        if ci:
            chosen = _pick_by_amount(ci, amounts) or ci[0]
            return chosen.get("transaction_id"), "consistent", ["agent_cash_in"], debug
        return None, "insufficient_data", ["no_cash_in_found"], debug

    # ---- payment failed: prefer a 'failed' payment; deduction claim -> consistent
    if case_type == "payment_failed":
        failed = [t for t in history if t.get("status") == "failed"]
        pool = failed or [t for t in history if t.get("type") == "payment"] or history
        chosen = _pick_by_amount(pool, amounts) or pool[0]
        verdict = "consistent" if failed else "insufficient_data"
        return chosen.get("transaction_id"), verdict, ["payment_failed"], debug

    # ---- refund request: match the completed payment in question
    if case_type == "refund_request":
        pays = [t for t in history if t.get("type") == "payment"] or history
        chosen = _pick_by_amount(pays, amounts) or (pays[0] if pays else None)
        if chosen:
            return chosen.get("transaction_id"), "consistent", ["refund_request"], debug
        return None, "insufficient_data", ["refund_no_match"], debug

    # ---- wrong transfer: the nuanced one ----
    if case_type == "wrong_transfer":
        return _match_wrong_transfer(amounts, phones, history, debug)

    # ---- other / vague: try a weak amount match, else insufficient ----
    if amounts:
        chosen = _pick_by_amount(history, amounts)
        if chosen and _unique_amount(history, amounts):
            return chosen.get("transaction_id"), "consistent", ["amount_match"], debug
    return None, "insufficient_data", ["vague_complaint", "needs_clarification"], debug


def _pick_by_amount(txs: List[dict], amounts: List[float]) -> Optional[dict]:
    if not amounts:
        return None
    for amt in amounts:
        candidates = [t for t in txs if _amt_eq(t.get("amount"), amt)]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # prefer the most recent matching one
            return sorted(candidates, key=lambda x: x.get("timestamp") or "")[-1]
    return None


def _unique_amount(txs: List[dict], amounts: List[float]) -> bool:
    for amt in amounts:
        if sum(1 for t in txs if _amt_eq(t.get("amount"), amt)) == 1:
            return True
    return False


def _amt_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 0.01
    except (TypeError, ValueError):
        return False


def _match_wrong_transfer(
    amounts: List[float], phones: List[str], history: List[dict], debug: dict
) -> Tuple[Optional[str], str, List[str], dict]:
    """
    Wrong-transfer logic with the investigator twist:
      * If the complaint amount maps to exactly one transfer -> that's the tx.
        - If the SAME counterparty appears in multiple prior transfers, the
          'wrong recipient' claim is contradicted -> inconsistent (SAMPLE-02).
        - Otherwise -> consistent (SAMPLE-01).
      * If the amount maps to MULTIPLE transfers to DIFFERENT recipients, we
        cannot know which one -> null + insufficient_data (SAMPLE-08).
    """
    transfers = [t for t in history if t.get("type") == "transfer"]
    pool = transfers or history

    # phone-based match takes precedence if the complaint names a number
    if phones:
        for t in pool:
            if any(phones_match(t.get("counterparty"), p) for p in phones):
                return t.get("transaction_id"), "consistent", [
                    "wrong_transfer", "recipient_match"
                ], debug

    if amounts:
        for amt in amounts:
            matches = [t for t in pool if _amt_eq(t.get("amount"), amt)]
            if not matches:
                continue
            # distinct recipients among the same-amount matches
            recipients = {m.get("counterparty") for m in matches}
            # completed transfers are the plausible "sent" ones
            completed = [m for m in matches if m.get("status") == "completed"]

            if len(recipients) > 1:
                # ambiguous: same amount to different people -> don't guess
                return None, "insufficient_data", [
                    "ambiguous_match", "needs_clarification"
                ], debug

            chosen = (completed or matches)
            chosen = sorted(chosen, key=lambda x: x.get("timestamp") or "")[-1]
            cp = chosen.get("counterparty")

            # established-recipient check: repeated transfers to same counterparty
            same_cp = [
                t for t in transfers
                if t.get("counterparty") == cp and t.get("status") == "completed"
            ]
            if len(same_cp) >= 2:
                return chosen.get("transaction_id"), "inconsistent", [
                    "wrong_transfer_claim", "established_recipient_pattern",
                    "evidence_inconsistent",
                ], debug

            return chosen.get("transaction_id"), "consistent", [
                "wrong_transfer", "transaction_match"
            ], debug

    # no amount, no phone -> cannot pin down
    return None, "insufficient_data", ["wrong_transfer", "needs_clarification"], debug


# --------------------------------------------------------------------------- #
# Step 4/5 — routing, severity, escalation
# --------------------------------------------------------------------------- #
DEPARTMENT_MAP = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "refund_request": "customer_support",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "other": "customer_support",
}


def route_department(case_type: str, user_type: Optional[str]) -> str:
    dept = DEPARTMENT_MAP.get(case_type, "customer_support")
    # merchant-side complaints lean to merchant_operations when ambiguous
    if user_type == "merchant" and case_type in ("other",):
        return "merchant_operations"
    return dept


def assign_severity(
    case_type: str, verdict: str, amount: Optional[float], matched: bool
) -> str:
    if case_type == "phishing_or_social_engineering":
        return "critical"
    if amount and amount >= HIGH_VALUE_THRESHOLD:
        return "high"
    if case_type in ("wrong_transfer",):
        # inconsistent / ambiguous wrong-transfer is medium, clean match is high
        return "high" if (verdict == "consistent" and matched) else "medium"
    if case_type in ("payment_failed", "duplicate_payment", "agent_cash_in_issue"):
        return "high"
    if case_type == "merchant_settlement_delay":
        return "medium"
    if case_type == "refund_request":
        return "low"
    return "low"  # other / vague


def needs_human_review(
    case_type: str, verdict: str, matched: bool, amount: Optional[float]
) -> bool:
    if case_type == "phishing_or_social_engineering":
        return True
    if amount and amount >= HIGH_VALUE_THRESHOLD:
        return True
    if case_type == "wrong_transfer":
        # confirmed dispute -> review; unresolved (need clarification) -> not yet
        return matched
    if case_type in ("duplicate_payment", "agent_cash_in_issue"):
        return matched
    if verdict == "inconsistent":
        return True
    # payment_failed (routine reversal), refund change-of-mind, settlement,
    # and vague-needs-clarification do not require review by default.
    return False
