"""Embedding backends.

* GeminiEmbedder  - Gemini embedding model (used when GEMINI_API_KEY is set).
* LocalHashEmbedder - deterministic, dependency-free feature-hashing embedder with a small
  legal-domain synonym map. Lets the whole app (and the tests) run offline with no model
  download. Retrieval quality is lower than a neural embedder; it is a fallback, not a replacement.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an and are as at be been by for from has have in into is it its of on or that the their "
    "this to was were will with you your we our us may can shall any all not no".split()
)
# Normalise legal paraphrases so "deletion" and "erase", "minor" and "child" land on the same feature.
_SYN = {
    "retention": "retain", "retained": "retain", "retaining": "retain", "retains": "retain",
    "deletion": "erase", "delete": "erase", "deleted": "erase", "erasure": "erase", "erased": "erase",
    "minor": "child", "minors": "child", "children": "child", "childs": "child", "kids": "child",
    "guardian": "parent", "parental": "parent", "parents": "parent", "guardians": "parent",
    "incident": "breach", "breaches": "breach", "incidents": "breach",
    "complaint": "grievance", "complaints": "grievance", "grievances": "grievance", "redressal": "grievance",
    "redress": "grievance",
    "notify": "notif", "notification": "notif", "notified": "notif", "notifying": "notif",
    "intimation": "notif", "intimate": "notif", "intimating": "notif",
    "withdraw": "withdraw", "withdrawal": "withdraw", "withdrawn": "withdraw", "revoke": "withdraw",
    "correct": "correct", "correction": "correct", "rectify": "correct", "rectification": "correct",
}


class LocalHashEmbedder:
    name = "local"
    dim = 1024

    def _vec(self, text: str) -> list[float]:
        raw = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        toks = [_SYN.get(t, t) for t in raw]
        feats = Counter(toks)
        for a, b in zip(toks, toks[1:]):
            feats[f"{a}_{b}"] += 0.5  # bigrams count for less than unigrams
        v = [0.0] * self.dim
        for feat, count in feats.items():
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            sign = 1.0 if (h >> 63) & 1 else -1.0
            v[h % self.dim] += sign * (1.0 + math.log(count)) if count >= 1 else sign * count
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class GeminiEmbedder:
    name = "gemini"

    def __init__(self, client, types_module, model: str):
        self._client = client
        self._types = types_module
        self._model = model

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        """Embed in small batches. The free tier counts every text as a request (100/min), so on a 429 we
        wait the time Google asks for and retry instead of crashing (first-time KB indexing needs ~134)."""
        import re
        import time

        out: list[list[float]] = []
        for i in range(0, len(texts), 20):
            batch = texts[i : i + 20]
            for attempt in range(8):
                try:
                    resp = self._client.models.embed_content(
                        model=self._model,
                        contents=batch,
                        config=self._types.EmbedContentConfig(task_type=task),
                    )
                    break
                except Exception as exc:
                    msg = str(exc)
                    if attempt == 7 or not ("429" in msg or "RESOURCE_EXHAUSTED" in msg):
                        raise
                    m = re.search(r"retry in ([\d.]+)s", msg)
                    time.sleep(min(70.0, (float(m.group(1)) if m else 15.0) + 3))
            out.extend([list(e.values) for e in resp.embeddings])
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]
