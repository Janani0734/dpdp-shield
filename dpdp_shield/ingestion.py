"""PDF / text ingestion and chunking (500-token chunks, 50-token overlap)."""
from __future__ import annotations

import io
import re
from functools import lru_cache
from dataclasses import dataclass, field

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHARS_PER_TOKEN = 4  # rule-of-thumb approximation; avoids downloading a tokenizer


class PolicyIngestError(ValueError):
    """Raised for user-fixable input problems (bad PDF, too long, no text...)."""


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    section: str = ""
    section_key: str = ""
    page: int = 0  # 0 = not applicable
    origin: str = ""
    extra: dict = field(default_factory=dict)

    def metadata(self) -> dict:
        return {
            "source": self.source,
            "section": self.section,
            "section_key": self.section_key,
            "page": self.page,
            "origin": self.origin,
        }


def make_splitter(tokens: int = 500, overlap: int = 50) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=tokens * CHARS_PER_TOKEN,
        chunk_overlap=overlap * CHARS_PER_TOKEN,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def extract_pdf_pages(data: bytes, max_pages: int = 50, max_mb: int = 20) -> list[Page]:
    if not data:
        raise PolicyIngestError("The uploaded file is empty.")
    if len(data) > max_mb * 1024 * 1024:
        raise PolicyIngestError(f"PDF is larger than {max_mb} MB.")
    if not data.lstrip().startswith(b"%PDF"):
        raise PolicyIngestError("This file is not a valid PDF.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n = len(pdf.pages)
            if n > max_pages:
                raise PolicyIngestError(f"PDF has {n} pages; the limit is {max_pages}.")
            pages = [Page(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(pdf.pages)]
    except PolicyIngestError:
        raise
    except Exception as exc:  # corrupt / encrypted / unsupported
        raise PolicyIngestError(f"Could not read the PDF ({type(exc).__name__}: {exc}).") from exc
    if not any(p.text for p in pages):
        raise PolicyIngestError(
            "No extractable text found. The PDF may be a scan; OCR is not supported - paste the text instead."
        )
    return pages


def pages_from_text(text: str) -> list[Page]:
    text = (text or "").strip()
    if len(text) < 20:
        raise PolicyIngestError("Please provide the policy text (at least a few sentences).")
    return [Page(1, text)]


def chunk_pages(
    pages: list[Page], prefix: str, source: str, tokens: int = 500, overlap: int = 50
) -> list[Chunk]:
    """Chunk page by page so every chunk keeps an exact page number for citations."""
    splitter = make_splitter(tokens, overlap)
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text:
            continue
        for i, piece in enumerate(splitter.split_text(page.text)):
            chunks.append(
                Chunk(id=f"{prefix}-p{page.number}-c{i}", text=piece, source=source, page=page.number)
            )
    return chunks


# --------------------------------------------------------------------------- official Gazette PDFs
_GAZETTE_NOISE = re.compile(r"the gazette of india|^\s*\[?part ii|^\s*sec\.\s*\d|^\s*\d{1,3}\s*$", re.I)
_EN_WORDS = frozenset("the of and to shall in a is be for by or as".split())
_SCHEDULE_LINE = re.compile(r"^\s*(THE|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH)\s+SCHEDULE\s*$")
_RULE_TITLE = re.compile(r"^\s*\d{1,2}\.\s+([A-Z][^—–]{3,170}?)\s*\.?\s*[—–]")


def clean_gazette_page(text: str) -> str:
    """Drop running headers/footers and bare page numbers."""
    return "\n".join(
        line for line in text.splitlines()
        if not _GAZETTE_NOISE.search(line) and not re.search(r"[\u0900-\u097f]{3}", line)  # Hindi running headers
    )


def english_ratio(text: str) -> float:
    toks = re.findall(r"[A-Za-z]+", text.lower())
    return sum(t in _EN_WORDS for t in toks) / len(toks) if toks else 0.0


def keep_english_pages(pages: list[Page], min_ratio: float = 0.10) -> list[Page]:
    """Gazette PDFs often print a Hindi version first (legacy-font text is gibberish to us); keep English pages."""
    cleaned = [Page(p.number, clean_gazette_page(p.text)) for p in pages]
    return [p for p in cleaned if p.text and english_ratio(p.text) >= min_ratio]


@lru_cache(maxsize=None)
def _start_re(n: int) -> re.Pattern:
    # Act: the margin heading is printed before the number ("Processing of 9. (1) The Data...");
    # Rules: the number starts the line ("10. Verifiable consent ... child.—(1)").
    # The margin heading may end in a full stop ("Notice. 5. (1) Every request..."), so '.' is allowed in the prefix.
    return re.compile(rf"^(?:[A-Za-z][A-Za-z ,’'()\-–.]{{0,45}}?\s)?{n}\.\s+(?:\(\d+\)|[A-Z“\"])")


def chunk_official_pdf(
    pages: list[Page], prefix: str, source: str, label: str, tokens: int, overlap: int
) -> list[Chunk]:
    """Chunk an official Act/Rules PDF, labelling each chunk with its section/rule/schedule.

    Section numbers are tracked sequentially (only the next expected number is accepted), which keeps
    numbered list items and cross-references from being mistaken for new sections.
    """
    splitter = make_splitter(tokens, overlap)
    out: list[Chunk] = []
    cur = 0
    sec_label, sec_key, in_schedule = "", "", False
    for page in pages:
        segments: list[tuple[str, str, list[str]]] = []
        buf: list[str] = []

        def flush() -> None:
            if buf and "".join(buf).strip():
                segments.append((sec_label, sec_key, list(buf)))
            buf.clear()

        for line in page.text.splitlines():
            ms = _SCHEDULE_LINE.match(line)
            if ms:
                flush()
                name = ms.group(1).title()
                sec_label = sec_key = "Schedule" if name == "The" else f"{name} Schedule"
                in_schedule = True
            elif not in_schedule:
                for n in (cur + 1, cur + 2):
                    if _start_re(n).match(line):
                        flush()
                        cur = n
                        mt = _RULE_TITLE.match(line)
                        sec_key = f"{label} {n}"
                        sec_label = f"{sec_key} - {mt.group(1).strip()}" if mt else sec_key
                        break
            buf.append(line)
        flush()
        for seg_i, (lab, key, lines) in enumerate(segments):
            for i, piece in enumerate(splitter.split_text("\n".join(lines))):
                out.append(
                    Chunk(
                        id=f"{prefix}-p{page.number}-s{seg_i}-c{i}",
                        text=piece,
                        source=source,
                        section=lab,
                        section_key=key,
                        page=page.number,
                        origin="official-pdf",
                    )
                )
    return out
