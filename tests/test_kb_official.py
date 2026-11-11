"""Checks the bundled official PDFs are parsed with the right section/rule labels and page numbers."""
import re

import pytest

from dpdp_shield.config import Settings
from dpdp_shield.retrieval import load_knowledge_base

S = Settings.from_env()
pytestmark = pytest.mark.skipif(
    not (S.kb_dir / "dpdp_act_2023.pdf").exists() or not (S.kb_dir / "dpdp_rules_2025.pdf").exists(),
    reason="official PDFs not present",
)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base(S)


def text(kb, source, key):
    return re.sub(r"\s+", " ", " ".join(c.text for c in kb if c.source == source and c.section_key == key)).lower()


def test_every_act_section_is_labelled(kb):
    keys = {c.section_key for c in kb if c.source == "DPDP Act 2023"}
    assert [n for n in range(1, 44) if f"Section {n}" not in keys] == []


def test_key_act_provisions_are_under_the_right_section(kb):
    A = "DPDP Act 2023"
    assert "verifiable consent of the parent" in text(kb, A, "Section 9")
    assert "tracking or behavioural monitoring" in text(kb, A, "Section 9")
    assert "reasonable security safeguards" in text(kb, A, "Section 8")
    assert "intimation of such breach" in text(kb, A, "Section 8")
    assert "make a complaint to the board" in text(kb, A, "Section 5")
    assert "erase her personal data" in text(kb, A, "Section 12")
    assert "fifty crore" in text(kb, A, "Schedule")


def test_key_rules_are_under_the_right_rule(kb):
    R = "DPDP Rules 2025"
    assert "seventy-two hours" in text(kb, R, "Rule 7")
    assert "forty-eight hours" in text(kb, R, "Rule 8")
    assert "digital locker" in text(kb, R, "Rule 10")
    assert "ninety days" in text(kb, R, "Rule 14")
    assert "fourth schedule" in text(kb, R, "Rule 12")  # child-data exemptions are Rule 12, not 11
    assert "three years" in text(kb, R, "Third Schedule")


def test_pages_are_positive_and_no_hindi_noise(kb):
    official = [c for c in kb if c.origin == "official-pdf"]
    assert all(c.page >= 1 for c in official)
    assert not any(sum("\u0900" <= ch <= "\u097f" for ch in c.text) > 20 for c in official)


def test_every_rules_py_reference_exists_in_the_kb(kb):
    from dpdp_shield.retrieval import section_keys
    from dpdp_shield.rules import CHECKS
    have = {c.section_key for c in kb}
    for chk in CHECKS:
        for key in section_keys(chk.dpdp_ref):
            if key.startswith("Direction"):
                continue
            assert key in have, f"{chk.id}: {key} not found in knowledge base"
