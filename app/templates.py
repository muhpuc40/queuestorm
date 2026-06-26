"""
Safe customer-reply and next-action templates.

Every template is pre-vetted against the Section 8 safety rules:
  * No reply asks for PIN / OTP / password.
  * Every reply *warns* the customer not to share credentials.
  * No reply promises a refund — financial outcomes use the approved phrase
    "any eligible amount will be returned through official channels".
  * Replies only ever point to official support channels.

Replies are produced in the complaint's language (en / bn). For 'mixed' we use
English, which is universally understood by BD support customers and avoids
awkward machine-mixed text.
"""
from __future__ import annotations

# Standard credential-safety warning appended to most replies.
WARN_EN = "Please do not share your PIN or OTP with anyone."
WARN_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"


def _txid(txid):
    return txid if txid else "the reported transaction"


# Each entry: (customer_reply_en, customer_reply_bn, next_action_en)
def reply_for(case_type: str, lang: str, txid, *, user_type: str = "customer") -> dict:
    bn = lang == "bn"
    t = _txid(txid)

    if case_type == "phishing_or_social_engineering":
        cr_en = (
            "Thank you for reaching out before sharing any information. We never "
            "ask for your PIN, OTP, or password under any circumstances. Please do "
            "not share these with anyone, even if they claim to be from us. Our "
            "fraud team has been notified of this incident."
        )
        cr_bn = (
            "কোনো তথ্য শেয়ার করার আগে আমাদের জানানোর জন্য ধন্যবাদ। আমরা কখনোই "
            "আপনার পিন, ওটিপি বা পাসওয়ার্ড চাই না। কেউ আমাদের পরিচয় দিলেও এগুলো "
            "কারো সাথে শেয়ার করবেন না। আমাদের ফ্রড টিমকে বিষয়টি জানানো হয়েছে।"
        )
        na = (
            f"Escalate to fraud_risk immediately. Confirm to the customer that the "
            f"company never asks for OTP. Log the reported contact for fraud pattern "
            f"analysis."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "wrong_transfer":
        cr_en = (
            f"We have noted your concern about transaction {t}. {WARN_EN} Our dispute "
            f"team will review the case and contact you through official support "
            f"channels."
        )
        cr_bn = (
            f"আপনার লেনদেন {t} এর বিষয়ে আমরা অবগত হয়েছি। {WARN_BN} আমাদের ডিসপিউট "
            f"টিম বিষয়টি যাচাই করে অফিসিয়াল চ্যানেলে আপনার সাথে যোগাযোগ করবে।"
        )
        na = (
            f"Verify {t} details with the customer and initiate the wrong-transfer "
            f"dispute workflow per policy."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "payment_failed":
        cr_en = (
            f"We have noted that transaction {t} may have caused an unexpected "
            f"balance deduction. Our payments team will review the case and any "
            f"eligible amount will be returned through official channels. {WARN_EN}"
        )
        cr_bn = (
            f"লেনদেন {t} এর কারণে আপনার ব্যালেন্স অপ্রত্যাশিতভাবে কাটা যেতে পারে বলে "
            f"আমরা অবগত হয়েছি। আমাদের পেমেন্ট টিম বিষয়টি যাচাই করবে এবং প্রযোজ্য যেকোনো "
            f"পরিমাণ অর্থ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। {WARN_BN}"
        )
        na = (
            f"Investigate {t} ledger status. If balance was deducted on a failed "
            f"payment, initiate the automatic reversal flow within standard SLA."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "duplicate_payment":
        cr_en = (
            f"We have noted the possible duplicate payment for transaction {t}. Our "
            f"payments team will verify with the biller and any eligible amount will "
            f"be returned through official channels. {WARN_EN}"
        )
        cr_bn = (
            f"লেনদেন {t} এর জন্য সম্ভাব্য ডুপ্লিকেট পেমেন্টের বিষয়ে আমরা অবগত হয়েছি। "
            f"আমাদের পেমেন্ট টিম বিলারের সাথে যাচাই করবে এবং প্রযোজ্য যেকোনো পরিমাণ অর্থ "
            f"অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। {WARN_BN}"
        )
        na = (
            f"Verify the duplicate with payments_ops. If the biller confirms only one "
            f"payment was received, initiate reversal of {t}."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "refund_request":
        cr_en = (
            "Thank you for reaching out. Refunds for completed merchant payments "
            "depend on the merchant's own policy. We recommend contacting the "
            "merchant directly. If you need help reaching them, please reply and we "
            f"will guide you. {WARN_EN}"
        )
        cr_bn = (
            "যোগাযোগ করার জন্য ধন্যবাদ। সম্পন্ন হওয়া মার্চেন্ট পেমেন্টের রিফান্ড "
            "মার্চেন্টের নিজস্ব নীতির উপর নির্ভর করে। আমরা সরাসরি মার্চেন্টের সাথে "
            "যোগাযোগ করার পরামর্শ দিচ্ছি। প্রয়োজনে আমরা আপনাকে সহায়তা করব। " + WARN_BN
        )
        na = (
            "Inform the customer that refund eligibility depends on the merchant's "
            "own policy. Provide guidance on contacting the merchant directly for a "
            "refund."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "merchant_settlement_delay":
        # Merchant tone — slightly more business-formal, no PIN/OTP warning needed
        # for a merchant settlement query (matches SAMPLE-09).
        cr_en = (
            f"We have noted your concern about settlement {t}. Our merchant "
            f"operations team will check the batch status and update you on the "
            f"expected settlement time through official channels."
        )
        cr_bn = (
            f"সেটেলমেন্ট {t} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের মার্চেন্ট অপারেশন্স টিম "
            f"ব্যাচ স্ট্যাটাস যাচাই করে অফিসিয়াল চ্যানেলে আপনাকে প্রত্যাশিত সেটেলমেন্ট "
            f"সময় জানাবে।"
        )
        na = (
            f"Route to merchant_operations to verify settlement batch status. If the "
            f"batch is delayed, communicate a revised ETA to the merchant."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    if case_type == "agent_cash_in_issue":
        cr_en = (
            f"We have noted your concern about transaction {t}. Our agent operations "
            f"team will verify it promptly and update you through official channels. "
            f"{WARN_EN}"
        )
        cr_bn = (
            f"আপনার লেনদেন {t} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল "
            f"এটি দ্রুত যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। {WARN_BN}"
        )
        na = (
            f"Investigate {t} pending status with agent operations. Confirm "
            f"settlement state and resolve within the standard cash-in SLA."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    # ---- ambiguous / vague (case_type often 'other' or unresolved match) ----
    if case_type == "_clarify_ambiguous":
        cr_en = (
            "Thank you for reaching out. We see multiple transactions that could "
            "match your description. Could you share the recipient's number or the "
            f"transaction ID so we can identify the right one? {WARN_EN}"
        )
        cr_bn = (
            "যোগাযোগ করার জন্য ধন্যবাদ। আপনার বর্ণনার সাথে মেলে এমন একাধিক লেনদেন "
            "আমরা দেখতে পাচ্ছি। সঠিক লেনদেনটি শনাক্ত করতে অনুগ্রহ করে প্রাপকের নম্বর বা "
            f"লেনদেন আইডি জানান। {WARN_BN}"
        )
        na = (
            "Reply to customer asking for the disambiguating detail (recipient number "
            "or transaction ID). Do not initiate any dispute until the transaction is "
            "confirmed."
        )
        return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}

    # default: other / vague-insufficient
    cr_en = (
        "Thank you for reaching out. To help you faster, please share the "
        "transaction ID, the amount involved, and a short description of what went "
        f"wrong. {WARN_EN}"
    )
    cr_bn = (
        "যোগাযোগ করার জন্য ধন্যবাদ। আপনাকে দ্রুত সহায়তা করতে অনুগ্রহ করে লেনদেন "
        "আইডি, সংশ্লিষ্ট পরিমাণ এবং সংক্ষেপে কী সমস্যা হয়েছে তা জানান। " + WARN_BN
    )
    na = (
        "Reply to the customer asking for specific details: which transaction, what "
        "amount, what went wrong, and approximate time."
    )
    return {"customer_reply": cr_bn if bn else cr_en, "next_action": na}
