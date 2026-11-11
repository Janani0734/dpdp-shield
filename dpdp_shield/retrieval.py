"""ChromaDB vector store + knowledge-base loader."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import Settings
from .ingestion import Chunk, Page, chunk_official_pdf, extract_pdf_pages, keep_english_pages, make_splitter

_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)
_KEY = re.compile(r"(Section|Rule|Direction)\s+(\d+)", re.I)


@dataclass
class Hit:
    id: str
    text: str
    meta: dict
    similarity: float  # cosine similarity in [0, 1]

    @property
    def page(self) -> int | None:
        return self.meta.get("page") or None


def section_keys(ref: str) -> list[str]:
    """'Section 9(1); Rule 10' -> ['Section 9', 'Rule 10']"""
    return [f"{m.group(1).title()} {m.group(2)}" for m in _KEY.finditer(ref)]


# --------------------------------------------------------------------------- knowledge base
def _parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines) and re.match(r"^(source|origin):\s*", lines[i]):
        k, v = lines[i].split(":", 1)
        meta[k.strip()] = v.strip()
        i += 1
    return meta, "\n".join(lines[i:])


def load_markdown_kb(path: Path, tokens: int, overlap: int) -> list[Chunk]:
    meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
    source = meta.get("source", path.stem)
    origin = meta.get("origin", "working-summary")
    splitter = make_splitter(tokens, overlap)
    parts = _HEADING.split(body)
    chunks: list[Chunk] = []
    # parts = [preamble, heading1, body1, heading2, body2, ...]
    for idx in range(1, len(parts), 2):
        heading, content = parts[idx], parts[idx + 1].strip()
        section = heading.split(" - ")[0].split(" — ")[0].strip()
        km = _KEY.search(section)
        key = f"{km.group(1).title()} {km.group(2)}" if km else section
        for j, piece in enumerate(splitter.split_text(f"{heading}\n{content}")):
            chunks.append(
                Chunk(
                    id=f"{path.stem}-{idx // 2}-{j}",
                    text=piece,
                    source=source,
                    section=heading,
                    section_key=key,
                    origin=origin,
                )
            )
    return chunks


def load_pdf_kb(path: Path, tokens: int, overlap: int) -> list[Chunk]:
    stem = path.stem.lower()
    pages = keep_english_pages(extract_pdf_pages(path.read_bytes(), max_pages=2000, max_mb=100))
    if "rule" in stem:
        source, label = "DPDP Rules 2025", "Rule"
    elif "cert" in stem:
        source, label = "CERT-In Directions", "Direction"
    else:
        source, label = "DPDP Act 2023", "Section"
    return chunk_official_pdf(pages, path.stem, source, label, tokens, overlap)


def load_knowledge_base(settings: Settings) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(settings.kb_dir.glob("*")):
        if path.suffix.lower() == ".md" and not path.name.lower().startswith("readme"):
            chunks += load_markdown_kb(path, settings.chunk_tokens, settings.chunk_overlap_tokens)
        elif path.suffix.lower() == ".pdf":
            try:
                chunks += load_pdf_kb(path, settings.chunk_tokens, settings.chunk_overlap_tokens)
            except Exception as exc:  # a bad KB PDF must not take the app down
                print(f"[dpdp-shield] skipped KB file {path.name}: {exc}")
    return chunks


# --------------------------------------------------------------------------- vector store
class VectorStore:
    def __init__(self, settings: Settings, embedder):
        self.embedder = embedder
        persist = settings.data_dir / "chroma"
        persist.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(persist), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.kb_name = f"dpdp_kb_{embedder.name}"

    # ---- helpers
    def _new_collection(self, name: str, **meta):
        return self.client.get_or_create_collection(name, metadata={"hnsw:space": "cosine", **meta})

    @staticmethod
    def _fingerprint(chunks: list[Chunk], backend: str) -> str:
        h = hashlib.sha256(backend.encode())
        for c in chunks:
            h.update(c.id.encode())
            h.update(c.text.encode())
        return h.hexdigest()

    # ---- KB
    def ensure_kb(self, chunks: list[Chunk]) -> int:
        fp = self._fingerprint(chunks, self.embedder.name)
        try:
            col = self.client.get_collection(self.kb_name)
            if (col.metadata or {}).get("fingerprint") == fp and col.count() == len(chunks):
                return col.count()
            self.client.delete_collection(self.kb_name)
        except Exception:
            pass
        col = self._new_collection(self.kb_name, fingerprint=fp)
        if chunks:
            col.add(
                ids=[c.id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[c.metadata() for c in chunks],
                embeddings=self.embedder.embed_documents([c.text for c in chunks]),
            )
        return len(chunks)

    def query_kb(self, qvec: list[float], k: int) -> list[Hit]:
        return self._query(self.client.get_collection(self.kb_name), qvec, k)

    def kb_by_section(self, keys: list[str]) -> list[Hit]:
        if not keys:
            return []
        col = self.client.get_collection(self.kb_name)
        got = col.get(where={"section_key": {"$in": keys}})
        return [Hit(i, d, m, 1.0) for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])]

    # ---- policies
    def policy_collection_name(self, policy_id: str) -> str:
        return f"policy_{self.embedder.name}_{policy_id}"

    def add_policy(self, policy_id: str, chunks: list[Chunk]) -> None:
        col = self._new_collection(self.policy_collection_name(policy_id))
        col.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata() for c in chunks],
            embeddings=self.embedder.embed_documents([c.text for c in chunks]),
        )

    def drop_policy(self, policy_id: str) -> None:
        try:
            self.client.delete_collection(self.policy_collection_name(policy_id))
        except Exception:
            pass

    def query_policy(self, policy_id: str, qvec: list[float], k: int) -> list[Hit]:
        col = self.client.get_collection(self.policy_collection_name(policy_id))
        return self._query(col, qvec, k)

    @staticmethod
    def _query(col, qvec: list[float], k: int) -> list[Hit]:
        n = col.count()
        if n == 0:
            return []
        res = col.query(query_embeddings=[qvec], n_results=min(k, n))
        hits = []
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hits.append(Hit(i, d, m, max(0.0, min(1.0, 1.0 - dist))))
        return hits
