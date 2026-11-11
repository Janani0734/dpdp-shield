"""Gemini wrapper, prompt builders, and strict validation of model output.

Design rule: the model never invents citations. Context blocks carry ids ([K1], [P2]...) and the
model may only cite those ids; we map ids back to real source/section/page metadata ourselves.
"""
from __future__ import annotations

import json
import random
import re
import time

from .config import Settings

SYSTEM = (
    "You are a careful compliance analyst for India's Digital Personal Data Protection (DPDP) Act 2023 and Rules. "
    "Use ONLY the context blocks provided. Never invent section numbers, penalties or quotes. If the policy context "
    "does not answer the question, say it was not found. You are not a lawyer; this is not legal advice. "
    "Respond with a single JSON object and nothing else."
)


class LLMError(RuntimeError):
    pass


_TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "504", "DEADLINE_EXCEEDED", "500", "INTERNAL")


def is_transient(message: str) -> bool:
    """Overload, rate-limit, timeout and server errors are worth retrying; 400/403/404 are not."""
    return any(code in message for code in _TRANSIENT)


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError("Model did not return JSON.")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned malformed JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMError("Model JSON was not an object.")
    return obj


class GeminiLLM:
    def __init__(self, settings: Settings):
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.llm_timeout_s * 1000)),
        )
        self.model = settings.gemini_model
        self.fallback_model = settings.gemini_fallback_model

    def _thinking(self):
        """Keep latency low: minimal 'thinking' for this extraction-style task (family-specific knob)."""
        try:
            if "2.5" in self.model:
                return self._types.ThinkingConfig(thinking_budget=0)
            if "gemini-3" in self.model:
                return self._types.ThinkingConfig(thinking_level="low")
        except Exception:
            pass
        return None

    def _make_config(self, system: str, timeout_s: float | None, thinking: bool, max_tokens: int = 4096):
        base = dict(system_instruction=system, response_mime_type="application/json", temperature=0.1, max_output_tokens=max_tokens)
        extras = {}
        if thinking and (t := self._thinking()) is not None:
            extras["thinking_config"] = t
        if timeout_s:
            extras["http_options"] = self._types.HttpOptions(timeout=int(timeout_s * 1000))
        try:
            return self._types.GenerateContentConfig(**base, **extras)
        except Exception:  # older SDK without one of the optional fields
            return self._types.GenerateContentConfig(**base)

    def _once(self, model: str, prompt: str, system: str, timeout_s: float | None, max_tokens: int = 4096) -> dict:
        last: Exception | None = None
        for thinking in (True, False):
            try:
                resp = self.client.models.generate_content(
                    model=model, contents=prompt, config=self._make_config(system, timeout_s, thinking, max_tokens)
                )
                return parse_json(resp.text)
            except LLMError:
                raise
            except Exception as exc:
                last = exc
                # retry once without the thinking knob only if the API objected to it
                if thinking and self._thinking() is not None and "think" in str(exc).lower():
                    continue
                break
        raise LLMError(f"Gemini request failed: {type(last).__name__}: {last}") from last

    def generate_json(self, prompt: str, system: str = SYSTEM, timeout_s: float | None = None, retries: int = 1,
                      model: str | None = None, max_tokens: int = 4096) -> dict:
        """Call Gemini; retry transient overload/rate-limit/timeout errors with backoff, then try the fallback model."""
        models = [model or self.model]
        if self.fallback_model and self.fallback_model != models[0]:
            models.append(self.fallback_model)
        last: LLMError | None = None
        for model in models:
            for attempt in range(retries + 1):
                try:
                    return self._once(model, prompt, system, timeout_s, max_tokens)
                except LLMError as exc:
                    last = exc
                    if not is_transient(str(exc)):
                        raise
                    if attempt < retries:
                        time.sleep(2.0 * (attempt + 1) + random.random())
        raise last  # type: ignore[misc]


# --------------------------------------------------------------------------- prompts
def _block(tag: str, hit, label: str, limit: int = 650) -> str:
    page = f", page {hit.page}" if hit.page else ""
    return f"[{tag}] ({label}{page})\n{hit.text[:limit]}"


def build_query_prompt(question: str, kb_hits: list, policy_hits: list, findings: list) -> tuple[str, dict]:
    """Returns (prompt, id_map) where id_map maps [K1]/[P1] -> Hit."""
    id_map: dict = {}
    kb_blocks, pol_blocks = [], []
    for i, h in enumerate(kb_hits, 1):
        id_map[f"K{i}"] = h
        kb_blocks.append(_block(f"K{i}", h, f"{h.meta.get('source')} - {h.meta.get('section') or 'n/a'}"))
    for i, h in enumerate(policy_hits, 1):
        id_map[f"P{i}"] = h
        pol_blocks.append(_block(f"P{i}", h, "User's policy"))
    rule_lines = "\n".join(
        f"- {f.id}: {f.status.upper()} ({f.check.dpdp_ref})" + (f' evidence: "{f.evidence_snippet[:200]}"' if f.evidence_snippet else "")
        for f in findings
    ) or "- (no rule-engine finding matched this question)"
    prompt = f"""Compare the user's privacy policy against the DPDP requirements. Identify gaps. Cite the exact DPDP section. Suggest a fix.

QUESTION: {question}

DPDP REQUIREMENT CONTEXT:
{chr(10).join(kb_blocks) or '(none)'}

USER POLICY CONTEXT:
{chr(10).join(pol_blocks) or '(none)'}

RULE-ENGINE FINDINGS (deterministic keyword checks; treat as hints):
{rule_lines}

Return JSON with exactly these keys:
{{
  "answer": "1-3 short sentences answering the question, grounded in the context. Say 'not found in the policy' if absent.",
  "cited_ids": ["K1", "P2"],   // only ids that appear above and that you actually relied on
  "violations": [{{"type": "snake_case_type", "severity": "high|medium|low", "fix": "compliant clause text"}}],
  "confidence": 0.0
}}
Only list violations that the question or context supports. Use rule-engine type names when they apply."""
    return prompt, id_map


def build_review_prompt(policy_text: str, failed: list, passed: list) -> str:
    failed_lines = "\n".join(f"- {f.id} ({f.check.dpdp_ref}): {f.check.requirement}" for f in failed) or "- none"
    passed_lines = "\n".join(
        f'- {f.id}: requirement = "{f.check.requirement}"; evidence found = "{f.evidence_snippet[:160]}"' for f in passed
    ) or "- none"
    return f"""Review this privacy policy against India's DPDP Act 2023.

POLICY TEXT:
\"\"\"
{policy_text}
\"\"\"

Keyword rules found these REQUIREMENTS MISSING:
{failed_lines}

Keyword rules found these requirements PRESENT (verify the evidence is genuinely adequate):
{passed_lines}

Rules for weak_passes: flag a present requirement ONLY if the policy text genuinely falls short of the exact requirement wording quoted above. Search the WHOLE policy text before claiming something is absent (it may be in another section). Do not add requirements that are not in the quoted wording (for example formats, deadlines or procedures). If the evidence is adequate, do not list it.

Return JSON with exactly these keys:
{{
  "fixes": {{"<missing requirement id>": "ready-to-paste compliant clause tailored to this policy's wording, max 70 words"}},
  "extra_gaps": [{{"section": "short title", "issue": "what is wrong or unclear", "dpdp_ref": "Section N if you are sure, else empty", "severity": "high|medium|low", "fix": "clause text"}}],
  "weak_passes": [{{"id": "<present requirement id>", "reason": "why the evidence is inadequate"}}]
}}
Use only requirement ids listed above. Do not invent facts about the company; use [placeholders] for unknown details."""


# --------------------------------------------------------------------------- validation
_SEV = {"high", "medium", "low"}


def _sev(value) -> str:
    v = str(value or "").lower()
    return v if v in _SEV else "medium"


def citation_from_hit(hit, scope: str) -> dict:
    """Build a citation from real retrieved metadata only (never from model text)."""
    if scope == "policy":
        return {"source": "Uploaded policy", "section": "", "title": "", "page": hit.page, "origin": "user-policy", "scope": "policy"}
    heading = hit.meta.get("section", "") or ""
    key = hit.meta.get("section_key", "") or heading
    title = heading.split(" - ", 1)[1].strip() if " - " in heading else ""
    return {
        "source": hit.meta.get("source"),
        "section": key,
        "title": title,
        "page": hit.page,
        "origin": hit.meta.get("origin", ""),
        "scope": "dpdp",
    }


def resolve_citations(cited_ids, id_map: dict) -> list[dict]:
    out, seen = [], set()
    for cid in cited_ids or []:
        key = str(cid).strip("[] ").upper()
        hit = id_map.get(key)
        if not hit or hit.id in seen:
            continue
        seen.add(hit.id)
        out.append(citation_from_hit(hit, "policy" if key.startswith("P") else "dpdp"))
    return out


def clamp01(value, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def sanitize_review(raw: dict, failed_ids: set[str], passed_ids: set[str]) -> dict:
    raw_fixes = raw.get("fixes") if isinstance(raw.get("fixes"), dict) else {}
    raw_extra = raw.get("extra_gaps") if isinstance(raw.get("extra_gaps"), list) else []
    raw_weak = raw.get("weak_passes") if isinstance(raw.get("weak_passes"), list) else []
    fixes = {
        k: str(v).strip()[:1200]
        for k, v in raw_fixes.items()
        if k in failed_ids and str(v).strip()
    }
    extra = []
    for g in raw_extra[:6]:
        if isinstance(g, dict) and str(g.get("issue", "")).strip():
            extra.append(
                {
                    "section": str(g.get("section", "Additional gap"))[:120],
                    "issue": str(g["issue"])[:500],
                    "dpdp_ref": str(g.get("dpdp_ref", ""))[:60],
                    "severity": _sev(g.get("severity")),
                    "fix": str(g.get("fix", ""))[:1200],
                }
            )
    weak = {
        str(w["id"]): str(w.get("reason", ""))[:300]
        for w in raw_weak
        if isinstance(w, dict) and w.get("id") in passed_ids
    }
    return {"fixes": fixes, "extra_gaps": extra, "weak_passes": weak}


def sanitize_violations(raw_list, known_ids: set[str]) -> list[dict]:
    out = []
    for v in (raw_list if isinstance(raw_list, list) else [])[:10]:
        if not isinstance(v, dict) or not str(v.get("type", "")).strip():
            continue
        vtype = re.sub(r"[^a-z0-9_]+", "_", str(v["type"]).lower()).strip("_")
        out.append(
            {
                "type": vtype,
                "severity": _sev(v.get("severity")),
                "fix": str(v.get("fix", ""))[:1200],
                "source": "rules+llm" if vtype in known_ids else "llm",
            }
        )
    return out
