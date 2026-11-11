"""Render samples/*.txt into PDFs: python scripts/make_samples.py"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def render(txt: Path) -> Path:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=18, leading=22, spaceAfter=10)
    h = ParagraphStyle("h", parent=styles["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=6)
    bullet = ParagraphStyle("bl", parent=body, leftIndent=14)
    story = []
    paragraphs = [p.strip() for p in txt.read_text(encoding="utf-8").split("\n\n") if p.strip()]
    for i, p in enumerate(paragraphs):
        text = escape(" ".join(p.split()))
        if p.startswith("# "):
            story.append(Paragraph(escape(p[2:].strip()), title))
        elif re.match(r"^\d+\.\s", p):
            story.append(Paragraph(text, h))
        elif p.startswith("- "):
            story.append(Paragraph("&bull; " + escape(p[2:].strip()), bullet))
        else:
            story.append(Paragraph(text, body))
        # start the second half of the longer sample on a new page so page citations are meaningful
        if txt.stem == "good_policy" and p.startswith("5. How long"):
            story.insert(len(story) - 1, PageBreak())
    out = txt.with_suffix(".pdf")
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=txt.stem).build(story)
    return out


if __name__ == "__main__":
    for t in sorted(SAMPLES.glob("*.txt")):
        print("wrote", render(t))
    sys.exit(0)
