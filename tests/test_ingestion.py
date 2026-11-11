import pytest

from dpdp_shield.ingestion import (Page, PolicyIngestError, chunk_pages, extract_pdf_pages, pages_from_text)


def test_extracts_pages(good_pdf):
    pages = extract_pdf_pages(good_pdf)
    assert len(pages) == 2 and "GreenLeaf" in pages[0].text


@pytest.mark.parametrize("data", [b"", b"hello world", b"%PDF-1.4 garbage that is not a pdf"])
def test_invalid_pdfs_raise_friendly_error(data):
    with pytest.raises(PolicyIngestError):
        extract_pdf_pages(data)


def test_page_limit(good_pdf):
    with pytest.raises(PolicyIngestError, match="limit"):
        extract_pdf_pages(good_pdf, max_pages=1)


def test_size_limit(good_pdf):
    with pytest.raises(PolicyIngestError, match="MB"):
        extract_pdf_pages(good_pdf, max_mb=0)


def test_text_too_short():
    with pytest.raises(PolicyIngestError):
        pages_from_text("hi")


def test_chunking_respects_size_overlap_and_pages():
    text = " ".join(f"Sentence number {i} about personal data processing." for i in range(400))
    chunks = chunk_pages([Page(1, text), Page(2, "Short page two.")], "x", "doc", tokens=500, overlap=50)
    assert all(len(c.text) <= 500 * 4 for c in chunks)
    assert len(chunks) > 2
    assert [c.page for c in chunks][-1] == 2
    first, second = chunks[0].text, chunks[1].text
    assert any(second.startswith(first[-k:]) or first[-200:][:40] in second for k in (200, 150, 100)) or first[-60:] in second
