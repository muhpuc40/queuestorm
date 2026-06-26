"""
Language-aware text utilities for the investigator.

Handles English, Bangla (bn) and mixed "Banglish" complaints. Everything here is
deterministic and dependency-free so it runs in milliseconds and cannot be
steered by adversarial text embedded in the complaint.
"""
from __future__ import annotations

import re
from typing import List, Optional

# --------------------------------------------------------------------------- #
# Bangla digit handling
# --------------------------------------------------------------------------- #
_BANGLA_DIGITS = "০১২৩৪৫৬৭৮৯"
_BANGLA_TO_ASCII = {ord(b): str(i) for i, b in enumerate(_BANGLA_DIGITS)}


def normalize_digits(text: str) -> str:
    """Convert Bangla numerals to ASCII so amount extraction works uniformly."""
    return (text or "").translate(_BANGLA_TO_ASCII)


# --------------------------------------------------------------------------- #
# Language detection (used to pick the customer_reply language)
# --------------------------------------------------------------------------- #
_BANGLA_RANGE = re.compile(r"[\u0980-\u09FF]")
_LATIN_RANGE = re.compile(r"[A-Za-z]")


def detect_language(text: str, declared: Optional[str] = None) -> str:
    """
    Return one of 'en', 'bn', 'mixed'. The harness may declare a language; we
    trust a sane declaration but fall back to script analysis (declarations can
    be wrong or missing).
    """
    if declared in ("en", "bn", "mixed"):
        # Still sanity-check against the actual script for robustness.
        has_bn = bool(_BANGLA_RANGE.search(text or ""))
        has_en = bool(_LATIN_RANGE.search(text or ""))
        if declared == "en" and has_bn and not has_en:
            return "bn"
        return declared

    has_bn = bool(_BANGLA_RANGE.search(text or ""))
    has_en = bool(_LATIN_RANGE.search(text or ""))
    if has_bn and has_en:
        return "mixed"
    if has_bn:
        return "bn"
    return "en"


# --------------------------------------------------------------------------- #
# Amount extraction
# --------------------------------------------------------------------------- #
# Match numbers like 5000, 5,000, 1200.50 — optionally followed by a currency word.
_AMOUNT_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def extract_amounts(text: str) -> List[float]:
    """All monetary-looking numbers in the complaint, Bangla digits included."""
    norm = normalize_digits(text or "")
    amounts: List[float] = []
    for m in _AMOUNT_RE.finditer(norm):
        raw = m.group(0).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        # Ignore obviously non-monetary tokens (e.g. years, tiny noise) only if
        # they are absurd; keep everything plausible as an amount.
        amounts.append(val)
    return amounts


# --------------------------------------------------------------------------- #
# Phone / counterparty extraction
# --------------------------------------------------------------------------- #
# BD mobile numbers in various forms: 01712345678, +8801712345678, 8801712345678
_PHONE_RE = re.compile(r"(?:\+?880|0)1[3-9]\d{8}")


def _normalize_phone(p: str) -> str:
    """Reduce a phone string to its trailing 10 significant digits for matching."""
    digits = re.sub(r"\D", "", p or "")
    return digits[-10:] if len(digits) >= 10 else digits


def extract_phones(text: str) -> List[str]:
    norm = normalize_digits(text or "")
    return [_normalize_phone(m.group(0)) for m in _PHONE_RE.finditer(norm)]


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return _normalize_phone(a) == _normalize_phone(b)


# --------------------------------------------------------------------------- #
# Keyword sets (English + Bangla + common Banglish). Lowercased matching.
# Order of evaluation is handled in engine.py; this is just vocabulary.
# --------------------------------------------------------------------------- #
KW = {
    "phishing": [
        "otp", "pin", "password", "passcode", "cvv", "card number",
        "verification code", "verify code", "scam", "fraud", "phishing",
        "suspicious call", "suspicious sms", "fake call", "asked for my",
        "account will be blocked", "account blocked if", "share my otp",
        "ওটিপি", "পিন", "পাসওয়ার্ড", "প্রতারণা", "প্রতারক", "ফাঁদ",
        "ভুয়া কল", "সন্দেহজনক", "ব্লক করে দেবে", "ব্লক হয়ে যাবে",
    ],
    "duplicate": [
        "twice", "two times", "double", "duplicate", "deducted twice",
        "charged twice", "deducted two times", "double charge",
        "দুইবার", "দুবার", "দুই বার", "ডাবল", "দুইবার কাটা",
    ],
    "payment_failed": [
        "failed", "failure", "transaction failed", "payment failed",
        "showed failed", "but deducted", "balance deducted", "money deducted",
        "deducted but", "recharge failed", "but my balance",
        "ফেইল", "ব্যর্থ", "কেটে নিয়েছে", "টাকা কেটে", "ব্যালেন্স কেটে",
        "কাটা হয়েছে কিন্তু",
    ],
    "wrong_transfer": [
        "wrong number", "wrong person", "wrong recipient", "wrong account",
        "sent to wrong", "mistakenly sent", "by mistake", "typed it wrong",
        "reverse it", "reverse the", "wrong transfer", "didn't get it",
        "did not get it", "didn't receive", "did not receive", "hasn't received",
        "ভুল নম্বর", "ভুল মানুষ", "ভুল ব্যক্তি", "ভুল করে", "ভুলে পাঠিয়েছি",
        "রিভার্স", "ফেরত", "পায়নি", "পাইনি",
    ],
    "refund": [
        "refund", "money back", "return my money", "changed my mind",
        "don't want", "do not want", "cancel", "want my money back",
        "ফেরত চাই", "টাকা ফেরত", "রিফান্ড", "বাতিল",
    ],
    "merchant_settlement": [
        "settlement", "settled", "not settled", "merchant", "my sales",
        "payout", "disbursement", "settle to my account",
        "সেটেলমেন্ট", "নিষ্পত্তি", "মার্চেন্ট", "বিক্রির টাকা",
    ],
    "agent_cash_in": [
        "cash in", "cash-in", "cashin", "agent", "deposited", "deposit",
        "through agent", "agent gave", "agent sent", "not reflected",
        "এজেন্ট", "ক্যাশ ইন", "ক্যাশইন", "জমা", "ব্যালেন্সে আসেনি",
        "টাকা আসেনি", "টাকা পাঠিয়েছে কিন্তু",
    ],
    "vague": [
        "something is wrong", "something wrong", "please check", "check my",
        "problem with my money", "issue with my account",
        "কিছু একটা সমস্যা", "সমস্যা হয়েছে", "চেক করুন",
    ],
}


def contains_any(text_lower: str, keys: List[str]) -> List[str]:
    """Return the subset of keywords present in the text (for explainability)."""
    return [k for k in keys if k in text_lower]
