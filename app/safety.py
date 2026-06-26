"""
Safety enforcement layer.

The Problem Statement (Section 8) and Rubric attach direct point penalties to
unsafe replies:
  -15  asking for PIN / OTP / password / full card number
  -10  promising a refund / reversal / unblock without authority
  -10  directing the customer to a suspicious third party

We treat safety as a *hard post-processing gate*, not a hope. Every customer_reply
and recommended_next_action passes through `sanitize_*` before it leaves the
service. Templates are already safe; the guard is defence-in-depth and also
neutralises any wording that could have leaked from dynamic text.
"""
from __future__ import annotations

import re
from typing import Tuple

# --------------------------------------------------------------------------- #
# Patterns that REQUEST credentials (forbidden). We must never *ask* for these.
# Note: it is fine — and required — to *warn* the customer not to share them.
# --------------------------------------------------------------------------- #
_CREDENTIAL_REQUEST = re.compile(
    r"\b(?:send|share|provide|give|tell|enter|type|confirm|verify)\b[^.!?\n]{0,40}"
    r"\b(?:your\s+)?(?:pin|otp|password|passcode|cvv|card\s+number|"
    r"full\s+card)\b",
    re.IGNORECASE,
)

# Unauthorized financial promises (forbidden). Replace with safe phrasing.
_REFUND_PROMISE = re.compile(
    r"\b(?:we\s+will|we'll|i\s+will|i'll|we\s+have|we'll\s+be|will\s+be)\b"
    r"[^.!?\n]{0,30}\b(?:refund(?:ed)?|reverse(?:d)?|reversal|unblock(?:ed)?|"
    r"recover(?:ed)?|return(?:ed)?\s+your\s+money|credit(?:ed)?\s+back)\b",
    re.IGNORECASE,
)
_REFUND_PROMISE_2 = re.compile(
    r"\b(?:guarantee|guaranteed|definitely|surely)\b[^.!?\n]{0,30}"
    r"\b(?:refund|reversal|money\s+back)\b",
    re.IGNORECASE,
)

# Directing to suspicious third parties (forbidden).
_THIRD_PARTY = re.compile(
    r"\b(?:call|contact|message|whatsapp|reach)\b[^.!?\n]{0,40}"
    r"\b(?:this\s+number|that\s+number|the\s+agent\s+who\s+called|"
    r"telegram|external|third[-\s]?party)\b",
    re.IGNORECASE,
)

_SAFE_REFUND_PHRASE = "any eligible amount will be returned through official channels"


def _scrub_credential_requests(text: str) -> str:
    """Remove any sentence that *requests* a credential, keep warnings intact."""
    if not text:
        return text
    # Split into sentences, drop those that request credentials.
    parts = re.split(r"(?<=[.!?।])\s+", text)
    kept = []
    for p in parts:
        # A warning like "do not share your PIN or OTP" must be preserved.
        is_warning = re.search(
            r"\b(?:do\s+not|don't|never|kindly\s+do\s+not)\b[^.!?\n]{0,30}"
            r"\b(?:share|give|provide|send)\b",
            p,
            re.IGNORECASE,
        )
        if _CREDENTIAL_REQUEST.search(p) and not is_warning:
            continue
        kept.append(p)
    return " ".join(kept).strip()


def _scrub_refund_promises(text: str) -> str:
    if not text:
        return text
    text = _REFUND_PROMISE.sub(_SAFE_REFUND_PHRASE, text)
    text = _REFUND_PROMISE_2.sub(_SAFE_REFUND_PHRASE, text)
    return text


def _scrub_third_party(text: str) -> str:
    if not text:
        return text
    parts = re.split(r"(?<=[.!?।])\s+", text)
    kept = [
        p
        for p in parts
        if not _THIRD_PARTY.search(p)
        or "official" in p.lower()  # "contact official support" is fine
    ]
    return " ".join(kept).strip()


def sanitize_customer_reply(text: str) -> str:
    text = _scrub_credential_requests(text)
    text = _scrub_refund_promises(text)
    text = _scrub_third_party(text)
    return re.sub(r"\s{2,}", " ", text).strip()


def sanitize_next_action(text: str) -> str:
    # recommended_next_action is also penalty-checked for refund promises.
    return _scrub_refund_promises(text or "").strip()


def audit(text: str) -> Tuple[bool, list]:
    """
    Return (is_safe, violations) for a finished reply. Used by tests and by an
    optional self-check log line. Never raises.
    """
    violations = []
    if _CREDENTIAL_REQUEST.search(text or ""):
        # Confirm it is not purely a warning sentence.
        for p in re.split(r"(?<=[.!?।])\s+", text or ""):
            if _CREDENTIAL_REQUEST.search(p) and not re.search(
                r"\b(?:do\s+not|don't|never)\b", p, re.IGNORECASE
            ):
                violations.append("credential_request")
                break
    if _REFUND_PROMISE.search(text or "") or _REFUND_PROMISE_2.search(text or ""):
        violations.append("unauthorized_refund_promise")
    if _THIRD_PARTY.search(text or "") and "official" not in (text or "").lower():
        violations.append("suspicious_third_party")
    return (len(violations) == 0, violations)
