"""Classifier: golden-set accuracy floor plus the ordering invariants that
make the ten overlapping category names resolve deterministically."""

from __future__ import annotations

from agent.categories import classify

from golden_titles import GOLDEN

ACCURACY_FLOOR = 0.95


def test_golden_set_accuracy():
    misses = [(title, expected, classify(title))
              for title, expected in GOLDEN
              if classify(title) != expected]
    accuracy = 1 - len(misses) / len(GOLDEN)
    detail = "\n".join(f"  {t!r}: expected {e}, got {g}" for t, e, g in misses[:15])
    assert accuracy >= ACCURACY_FLOOR, (
        f"classifier accuracy {accuracy:.1%} is below the {ACCURACY_FLOOR:.0%} floor "
        f"({len(misses)} miss(es)):\n{detail}")


def test_ordering_invariants():
    """The documented tie-breaks: most specific category wins."""
    assert classify("AI Software Engineer") == "ai_software_engineer"
    assert classify("AI Engineer") == "ai_engineer"
    assert classify("UI/UX Designer") == "ui_ux"
    assert classify("Senior Product Designer") == "product_design"
    assert classify("Product Engineer") == "software_engineer"
    assert classify("Full Stack Software Engineer") == "fullstack"


def test_out_of_scope_beats_everything():
    """OUT_OF_SCOPE runs before the rules — tech stack words cannot rescue it."""
    assert classify("Data Engineer (Python, React)") is None
    assert classify("DevOps Engineer - Node.js") is None
    assert classify("QA Engineer, Frontend") is None
    assert classify("Firmware Engineer (C++)") is None
    assert classify("Embedded Software Engineer") is None
    assert classify("Hardware Engineer") is None
    assert classify("Salesforce Developer") is None
    assert classify("SAP Consultant") is None


def test_empty_and_junk():
    assert classify("") is None
    assert classify("   ") is None
    assert classify("Bartender") is None
