"""Validate the engine against all 10 public sample cases (functional equivalence)."""
import json, sys
from app.analyzer import analyze
from app.schemas import AnalyzeResponse
from app.safety import audit

with open("/mnt/user-data/uploads/SUST_Preli_Sample_Cases.json") as f:
    data = json.load(f)

cases = data["cases"]
hard_keys = ["relevant_transaction_id", "evidence_verdict", "case_type", "department"]
passed = 0
report = []
for c in cases:
    got = analyze(c["input"])
    # schema must validate
    AnalyzeResponse(**got)
    exp = c["expected_output"]
    diffs = {k: (exp.get(k), got.get(k)) for k in hard_keys if exp.get(k) != got.get(k)}
    sev_ok = got["severity"] == exp["severity"]
    safe, viol = audit(got["customer_reply"])
    ok = (not diffs) and safe
    if ok: passed += 1
    report.append((c["id"], c["label"], diffs, ("sev:%s/%s"%(got["severity"],exp["severity"]) if not sev_ok else "sev✓"), ("SAFE" if safe else "UNSAFE:%s"%viol), got["human_review_required"], exp["human_review_required"]))

for r in report:
    cid, label, diffs, sev, safe, hr_g, hr_e = r
    status = "PASS" if (not diffs and "UNSAFE" not in safe) else "FAIL"
    print(f"[{status}] {cid} {label}")
    if diffs: print(f"        HARD DIFFS: {diffs}")
    if "UNSAFE" in safe: print(f"        {safe}")
    if sev != "sev✓": print(f"        {sev}")
    hr_flag = "" if hr_g==hr_e else f"  <-- human_review got={hr_g} exp={hr_e}"
    if hr_flag: print(f"        {hr_flag}")

print(f"\n{passed}/{len(cases)} cases pass hard-key + safety equivalence")
