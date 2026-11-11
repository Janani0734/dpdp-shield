"""Rule-based DPDP compliance checks (deterministic layer of the violation detector).

Each Check says what DPDP requires, which regexes must ALL be found in the policy for a pass,
and a compliant clause template used as the fallback fix text.

These are heuristics over wording, not legal conclusions: a pass means the policy *mentions* the
required element, a fail means no such language was found.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CHILD = r"child(ren)?|minors?|under\s*(the age of\s*)?(18|eighteen)"
_DUR = r"(\d+|one|two|three|six|twelve)\s*(\(\d+\)\s*)?(day|week|month|year)s?"


@dataclass(frozen=True)
class Check:
    id: str
    section: str
    dpdp_ref: str
    severity: str
    requirement: str
    all_of: tuple[str, ...]
    topic_terms: tuple[str, ...]
    penalty: str
    fix_template: str
    evidence_idx: int = 0


PEN_SECURITY = "Up to ₹250 crore (Schedule: security safeguards)"
PEN_BREACH = "Up to ₹200 crore (Schedule: breach intimation)"
PEN_CHILD = "Up to ₹200 crore (Schedule: children's data)"
PEN_OTHER = "Up to ₹50 crore (Schedule: residual penalty)"

CHECKS: tuple[Check, ...] = (
    Check(
        id="missing_notice",
        section="Notice: data collected and purpose",
        dpdp_ref="Section 5; Rule 3",
        severity="high",
        requirement="Give a notice, understandable on its own, that itemises the personal data, states the specific purpose and the goods or services it enables, and says how to withdraw consent, exercise rights and complain to the Board.",
        all_of=(r"\bcollect(s|ed|ion|ing)?\b", r"\bpurposes?\b"),
        topic_terms=("notice", "purpose", "what data", "collect"),
        penalty=PEN_OTHER,
        fix_template=(
            "What we collect and why: We collect only the personal data listed below, and only for the stated purpose.\n"
            "- [Data item, e.g. name, mobile number] - used to [specific purpose, e.g. create and secure your account].\n"
            "- [Data item] - used to [specific purpose].\n"
            "You can exercise your rights and complain to the Data Protection Board of India as described in this policy."
        ),
    ),
    Check(
        id="missing_consent_withdrawal",
        section="Consent and withdrawal",
        dpdp_ref="Section 6(4); Rule 3",
        severity="high",
        requirement="Consent must be free, specific, informed and unambiguous, and withdrawing it must be as easy as giving it.",
        all_of=(
            r"\bconsent\b",
            r"\b(withdraw\w*|revoke\w*)\b[^.]{0,80}\bconsent\b|\bconsent\b[^.]{0,80}\b(withdraw\w*|revok\w*|withdrawn)\b",
        ),
        topic_terms=("consent", "withdraw", "opt out", "opt-out"),
        penalty=PEN_OTHER,
        fix_template=(
            "We process your personal data only with your free, specific, informed and unambiguous consent, given by a clear "
            "affirmative action. You may withdraw your consent at any time, as easily as you gave it, from Settings > Privacy "
            "or by writing to [grievance email]. Withdrawal does not affect processing done before you withdrew."
        ),
        evidence_idx=1,
    ),
    Check(
        id="missing_child_consent",
        section="Children's data: verifiable parental consent",
        dpdp_ref="Section 9(1); Rule 10",
        severity="high",
        requirement="Obtain verifiable consent of a parent or lawful guardian before processing personal data of anyone under 18.",
        all_of=(
            r"verifiable[^.]{0,80}consent|consent[^.]{0,80}verif\w+",
            r"parent(al|s)?|lawful guardian|guardian",
            _CHILD,
        ),
        topic_terms=("child", "minor", "parental", "parent", "guardian", "under-18", "under 18", "verifiable", "underage", "kids"),
        penalty=PEN_CHILD,
        fix_template=(
            "We collect personal data from children (persons under 18 years of age) only with the verifiable consent of their "
            "parent or lawful guardian, obtained before any processing begins. We verify the parent or guardian using "
            "[verification method, e.g. a DigiLocker-based token or other reliable identity and age details]. "
            "If we learn we hold a child's data without such consent, we delete it."
        ),
    ),
    Check(
        id="missing_child_tracking_ban",
        section="Children's data: no tracking or targeted ads",
        dpdp_ref="Section 9(3)",
        severity="medium",
        requirement="Do not track or behaviourally monitor children, or direct targeted advertising at them.",
        all_of=(
            r"\b(no|not|never|prohibit\w*|refrain\w*|do not|does not|will not|shall not)\b[^.]{0,80}(track\w*|behaviou?ral (monitor\w*|track\w*)|targeted (advertis\w*|ads?))",
            _CHILD,
        ),
        topic_terms=("tracking", "behavioural", "behavioral", "targeted ad", "advertis", "monitor"),
        penalty=PEN_CHILD,
        fix_template=(
            "We do not undertake tracking or behavioural monitoring of children, and we do not show targeted advertising "
            "directed at children."
        ),
    ),
    Check(
        id="missing_retention_period",
        section="Data retention period",
        dpdp_ref="Section 8(7); Rule 8",
        severity="medium",
        requirement="State how long data is kept, and erase it once consent is withdrawn or the purpose is no longer served (unless law requires retention). Logs and related data must be kept for at least one year (Rule 8(3)).",
        all_of=(
            rf"(retain\w*|retention|stored|kept|keep)[^.]{{0,150}}({_DUR})"
            r"|(retain\w*|retention|stored|kept|keep)[^.]{0,120}(\buntil\b|no longer (necessary|required|needed)|purpose[^.]{0,30}(served|fulfilled|achieved))",
        ),
        topic_terms=("retention", "retain", "retained", "how long", "period", "stored for", "kept"),
        penalty=PEN_OTHER,
        fix_template=(
            "We retain your personal data only until the purpose it was collected for is served. Account data is kept while your "
            "account is active and for [N] months after closure; transaction records are kept for [N] years as required by law. "
            "Once consent is withdrawn or the purpose is no longer served, we erase the data and ask our processors to do the same, "
            "unless retention is required by law. We also keep security logs and related records for at least one year, as the DPDP Rules require."
        ),
    ),
    Check(
        id="missing_breach_notification",
        section="Personal data breach notification",
        dpdp_ref="Section 8(6); Rule 7; CERT-In Directions 2022",
        severity="high",
        requirement="Intimate the Data Protection Board and each affected person of a personal data breach (details to the Board within 72 hours), and report cyber incidents to CERT-In within 6 hours.",
        all_of=(
            r"(notif\w*|intimat\w*|inform\w*|report\w*|alert\w*)[^.]{0,120}\bbreach(es)?\b|\bbreach(es)?\b[^.]{0,150}(notif\w*|intimat\w*|inform\w*|report\w*|alert\w*)",
        ),
        topic_terms=("breach", "incident", "notification", "notify", "cert-in", "certin", "leak"),
        penalty=PEN_BREACH,
        fix_template=(
            "If a personal data breach occurs, we will, without delay, inform each affected user of what happened, the likely "
            "consequences, the steps we have taken and the steps they can take, and we will intimate the Data Protection Board "
            "of India, providing full details within 72 hours. We also report cyber incidents to CERT-In within 6 hours as required."
        ),
    ),
    Check(
        id="missing_erasure_right",
        section="Right to erasure",
        dpdp_ref="Section 12(3); Rule 14",
        severity="medium",
        requirement="Data Principals can request erasure of their personal data, which must be honoured unless retention is legally required.",
        all_of=(
            r"(right|request|ask)[^.]{0,80}(eras\w+|delet\w+)|(eras\w+|delet\w+)[^.]{0,80}(right|request|upon your|on your)|you (may|can|have the right to)[^.]{0,60}(delete|erase)",
        ),
        topic_terms=("delete", "deletion", "erase", "erasure", "forgotten"),
        penalty=PEN_OTHER,
        fix_template=(
            "You have the right to request erasure of your personal data. Write to [grievance email] or use Settings > Delete "
            "Account; we will erase your data unless we must retain it to comply with law, and we will confirm once done."
        ),
    ),
    Check(
        id="missing_access_right",
        section="Right to access information",
        dpdp_ref="Section 11; Rule 14",
        severity="low",
        requirement="Provide a summary of personal data processed, the processing activities, and who it has been shared with.",
        all_of=(
            r"(right to|you (may|can|have the right to)|request)[^.]{0,60}(access|obtain|receive|summary|copy)[^.]{0,80}(personal (data|information)|data|summary)|(summary|copy)[^.]{0,40}(of )?(your )?personal (data|information)",
        ),
        topic_terms=("access", "copy of", "summary of data", "right to know"),
        penalty=PEN_OTHER,
        fix_template=(
            "You have the right to obtain a summary of the personal data we process about you, the processing activities, and the "
            "identities of the other Data Fiduciaries and processors with whom it has been shared. Write to [grievance email]."
        ),
    ),
    Check(
        id="missing_correction_right",
        section="Right to correction and update",
        dpdp_ref="Section 12(1)-(2); Rule 14",
        severity="low",
        requirement="Let Data Principals correct inaccurate or misleading data, complete incomplete data and update it.",
        all_of=(
            r"(correct\w*|rectif\w*|updat\w*|complet\w*)[^.]{0,80}(right|request|your (personal )?(data|information))|(right|request)[^.]{0,60}(correct\w*|rectif\w*)",
        ),
        topic_terms=("correct", "correction", "rectify", "update my", "inaccurate"),
        penalty=PEN_OTHER,
        fix_template=(
            "You may ask us to correct inaccurate or misleading personal data, complete incomplete data, or update it. "
            "Write to [grievance email] or edit your profile."
        ),
    ),
    Check(
        id="missing_grievance_redressal",
        section="Grievance redressal contact",
        dpdp_ref="Section 8(9)-(10); Section 13; Rule 9; Rule 14(3)",
        severity="medium",
        requirement="Publish contact details of the DPO or person who answers privacy questions, and run an effective grievance redressal mechanism with a published response time of at most 90 days.",
        all_of=(
            r"grievance",
            r"[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d\s-]{8,}\d",
        ),
        topic_terms=("grievance", "redress", "complaint", "contact", "officer", "dpo"),
        penalty=PEN_OTHER,
        fix_template=(
            "Grievance Officer / Data Protection contact: [Name], [Designation], [Company], [postal address]. Email: "
            "[grievance@company.in], Phone: [+91-XXXXXXXXXX]. We respond to every grievance within [N] days (never more than 90 days). "
            "If it is not resolved you may complain to the Data Protection Board of India."
        ),
    ),
    Check(
        id="missing_nomination_right",
        section="Right to nominate",
        dpdp_ref="Section 14; Rule 14(4)",
        severity="low",
        requirement="Let Data Principals nominate another person to exercise their rights on death or incapacity.",
        all_of=(r"\bnominat\w*\b",),
        topic_terms=("nominate", "nominee", "nomination", "death", "incapacity"),
        penalty=PEN_OTHER,
        fix_template=(
            "You have the right to nominate another individual who may exercise your rights under the DPDP Act on your behalf "
            "in the event of your death or incapacity. To nominate, write to [grievance email]."
        ),
    ),
    Check(
        id="missing_security_safeguards",
        section="Security safeguards",
        dpdp_ref="Section 8(5); Rule 6",
        severity="high",
        requirement="Protect personal data with reasonable security safeguards: encryption/masking/tokens, access control, logs and monitoring, backups, processor contracts, and log retention of one year (Rule 6).",
        all_of=(r"security (safeguards|measures|practices|controls)|encrypt\w*|access controls?|technical and organi[sz]ational",),
        topic_terms=("security", "safeguard", "encrypt", "protect", "safe"),
        penalty=PEN_SECURITY,
        fix_template=(
            "We protect personal data with reasonable security safeguards, including encryption in transit and at rest, role-based "
            "access controls, activity logging and monitoring (logs kept for at least one year), and regular backups, so as to prevent personal data breaches."
        ),
    ),
    Check(
        id="missing_cross_border_disclosure",
        section="Transfers outside India",
        dpdp_ref="Section 16",
        severity="low",
        requirement="Be transparent about where data is processed; transfers abroad are allowed except to countries the Government restricts.",
        all_of=(
            r"(outside|beyond) (of )?india|cross[- ]border|international(ly)? transfer|transfer\w*[^.]{0,60}(outside|abroad|other countr\w*)|(stored|processed|hosted)[^.]{0,40}(in|within) india",
        ),
        topic_terms=("outside india", "cross-border", "cross border", "abroad", "international", "transfer"),
        penalty=PEN_OTHER,
        fix_template=(
            "Your personal data is stored and processed in India. If we transfer it outside India, we will do so only to countries "
            "or territories not restricted by the Central Government and under safeguards that protect your data."
        ),
    ),
    Check(
        id="missing_board_complaint_info",
        section="Complaint to the Data Protection Board",
        dpdp_ref="Section 5(1)(iii); Section 13(3); Rule 3",
        severity="low",
        requirement="Tell people how to complain to the Data Protection Board of India (after using the grievance channel first).",
        all_of=(r"data protection board",),
        topic_terms=("board", "data protection board", "regulator"),
        penalty=PEN_OTHER,
        fix_template=(
            "If you are not satisfied with our response to your grievance, you may make a complaint to the Data Protection Board "
            "of India in the manner prescribed under the DPDP Rules."
        ),
    ),
)

CHECKS_BY_ID = {c.id: c for c in CHECKS}
_COMPILED = {c.id: [re.compile(p, re.I) for p in c.all_of] for c in CHECKS}
_WS = re.compile(r"\s+")
_DURATION = re.compile(_DUR, re.I)


@dataclass
class Finding:
    check: Check
    status: str  # "pass" | "fail"
    evidence_snippet: str = ""
    evidence_page: int | None = None
    note: str = ""

    @property
    def id(self) -> str:
        return self.check.id


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _snippet(text: str, m: re.Match, width: int = 120) -> str:
    s = text.rfind(". ", 0, m.start())
    s = s + 2 if s != -1 and m.start() - s < 260 else max(0, m.start() - width)
    e = text.find(". ", m.end())
    e = e + 1 if e != -1 and e - m.end() < 260 else min(len(text), m.end() + width)
    return text[s:e].strip()


def run_checks(pages: list[tuple[int, str]]) -> list[Finding]:
    norm_pages = [(n, _norm(t)) for n, t in pages if t and t.strip()]
    full = " ".join(t for _, t in norm_pages)
    findings: list[Finding] = []
    for check in CHECKS:
        compiled = _COMPILED[check.id]
        if not all(rx.search(full) for rx in compiled):
            findings.append(Finding(check, "fail"))
            continue
        rx = compiled[check.evidence_idx]
        page, snip = None, ""
        for n, t in norm_pages:
            m = rx.search(t)
            if m:
                page, snip = n, _snippet(t, m)
                break
        else:
            m = rx.search(full)
            if m:
                snip = _snippet(full, m)
        findings.append(Finding(check, "pass", snip, page))
    return findings


def relevant_findings(question: str, findings: list[Finding]) -> list[Finding]:
    """Findings whose topic best matches the question (ties kept; empty if nothing matches)."""
    q = question.lower()
    scored = []
    for f in findings:
        score = sum(1 for term in f.check.topic_terms if term in q)
        if score:
            scored.append((score, f))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    return [f for s, f in scored if s == best][:3]


def extract_durations(text: str) -> list[str]:
    return [m.group(0) for m in _DURATION.finditer(text)]
