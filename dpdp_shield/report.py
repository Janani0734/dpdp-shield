"""Gap-report assembly: {section, status, dpdp_ref, fix_suggestion, ...} rows + summary."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .rules import Finding

_SEV_RANK = {"high": 0, "medium": 1, "low": 2}
_CRORE = re.compile(r"₹\s*(\d+)\s*crore")


def build_report(doc, findings: list[Finding], review: dict | None, mode: str, warnings: list[str]) -> dict:
    review = review or {"fixes": {}, "extra_gaps": [], "weak_passes": {}}
    rows: list[dict] = []
    for f in findings:
        c = f.check
        failed = f.status == "fail"
        llm_fix = review["fixes"].get(f.id, "")
        rows.append(
            {
                "section": c.section,
                "status": f.status,
                "severity": c.severity,
                "dpdp_ref": c.dpdp_ref,
                "violation_type": f.id if failed else "",
                "requirement": c.requirement,
                "evidence": {"snippet": f.evidence_snippet, "page": f.evidence_page},
                "fix_suggestion": (llm_fix or c.fix_template) if failed else "",
                "fix_source": ("gemini" if llm_fix else "template") if failed else "",
                "penalty_exposure": c.penalty if failed else "",
                "review_note": review["weak_passes"].get(f.id, ""),
                "detected_by": "rules",
            }
        )
    rows.sort(key=lambda r: (r["status"] == "pass", _SEV_RANK[r["severity"]]))

    extra_rows = [
        {
            "section": g["section"],
            "status": "fail",
            "severity": g["severity"],
            "dpdp_ref": (g["dpdp_ref"] + " (LLM-suggested, verify)") if g["dpdp_ref"] else "LLM-suggested, verify",
            "violation_type": "llm_semantic_gap",
            "requirement": g["issue"],
            "evidence": {"snippet": "", "page": None},
            "fix_suggestion": g["fix"],
            "fix_source": "gemini",
            "penalty_exposure": "",
            "review_note": "",
            "detected_by": "llm",
        }
        for g in review["extra_gaps"]
    ]

    failed_rule = [r for r in rows if r["status"] == "fail"]
    by_sev = {s: sum(1 for r in failed_rule + extra_rows if r["severity"] == s) for s in ("high", "medium", "low")}
    crores = [int(m.group(1)) for r in failed_rule if (m := _CRORE.search(r["penalty_exposure"]))]
    return {
        "policy_id": doc.id,
        "policy_name": doc.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "summary": {
            "total_checks": len(rows),
            "passed": len(rows) - len(failed_rule),
            "failed": len(failed_rule),
            "llm_extra_gaps": len(extra_rows),
            "by_severity": by_sev,
            "highest_penalty_ceiling_crore": max(crores) if crores else 0,
            "note": "Penalty figures are the statutory maximums in the Act's Schedule, not a prediction.",
        },
        "rows": rows + extra_rows,
        "warnings": warnings,
        "disclaimer": "Automated analysis. This is not legal advice; have counsel review before relying on it.",
    }
