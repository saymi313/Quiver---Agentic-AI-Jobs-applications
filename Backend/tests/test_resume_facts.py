"""The fact gate: a rewrite may not assert what the profile does not.

"Never invent a metric" has been in the rewrite prompt since the beginning, and
models mostly obey it. These tests exist because "mostly" is the wrong standard
for a document that goes to a real employer with the candidate's name on it.
"""

from __future__ import annotations

import pytest

from api import latex_resume as L
from api import resume_facts as F

PROFILE = {
    "experience": [
        {"company": "BangoPure Limited",
         "bullets": [{"text": "Lead the frontend team, mentoring 10 developers."},
                     {"text": "Build platforms in React and Node.js for European clients."}]},
    ],
    "skills": [{"line": "Languages: JavaScript, C++, SQL, MongoDB"}],
}

VOCAB = F.profile_vocabulary(PROFILE)


# ------------------------------------------------------------ the bad cases

def test_invented_metric_is_caught():
    """The one that matters most. A fabricated number on a resume is the
    difference between tailoring and lying."""
    problems = F.check_rewrite(
        "Built platforms in React",
        "Built React platforms serving 4M monthly users", VOCAB)
    assert problems
    assert "4M" in problems[0]


def test_invented_percentage_is_caught():
    problems = F.check_rewrite(
        "Optimized frontend performance",
        "Optimized frontend performance, cutting p95 render time 38%", VOCAB)
    assert problems


def test_unsupported_technology_is_caught():
    problems = F.check_rewrite(
        "Build platforms in React and Node.js",
        "Build platforms in React, Node.js and Kubernetes", VOCAB)
    assert problems
    assert "Kubernetes" in problems[0]


def test_unsupported_employer_is_caught():
    problems = F.check_rewrite(
        "Lead the frontend team",
        "Lead the frontend team at Stripe", VOCAB)
    assert problems


# ----------------------------------------------------------- the good cases

def test_pure_rewording_passes():
    assert F.check_rewrite(
        "Build platforms in React and Node.js for European clients",
        "Shipped React and Node.js platforms for clients across Europe", VOCAB) == []


def test_a_number_already_in_the_bullet_may_be_kept():
    assert F.check_rewrite(
        "Lead the frontend team, mentoring 10 developers.",
        "Led a frontend team of 10 developers.", VOCAB) == []


def test_a_number_from_elsewhere_in_the_profile_may_be_used():
    """The profile is one document. A fact stated under one role may be
    restated in another bullet — it is still the candidate's own fact."""
    assert F.check_rewrite(
        "Managed the team", "Managed 10 developers", VOCAB) == []


def test_small_ordinals_are_not_claims():
    assert F.check_rewrite("Built the API", "Built the API in 3 sprints", VOCAB) == []


def test_a_name_in_the_first_position_is_still_checked():
    """The leading word is skipped as a sentence-initial verb, which is very
    nearly a hole: without the verb-shape test, "Stripe payments were
    integrated" would smuggle an employer past the one position nobody looks
    at."""
    assert F.check_rewrite("Built the payments flow",
                           "Stripe payments were integrated end to end", VOCAB)
    assert F.check_rewrite("Built the platform",
                           "Kubernetes ran every service", VOCAB)


def test_sentence_capitals_are_not_proper_nouns():
    for verb in ("Shipped", "Delivered", "Architected", "Migrated"):
        assert F.check_rewrite("Did work", f"{verb} the platform", VOCAB) == [], verb


def test_camel_case_technology_needs_support():
    supported = F.check_rewrite("Used mongoDB", "Used mongoDB widely", VOCAB)
    unsupported = F.check_rewrite("Used a database", "Used dynamoDB", VOCAB)
    assert supported == []
    assert unsupported


# ----------------------------------------------------------------- the modes

def test_three_modes_exist_and_aggressive_forces_review():
    assert L.MODES == ("off", "honest", "aggressive")
    assert "aggressive" in L.FORCES_REVIEW
    assert "honest" not in L.FORCES_REVIEW


def test_both_modes_carry_the_same_factual_constraints():
    """Aggressive loosens the prose, never the facts. If these ever diverge,
    'aggressive' has quietly become permission to invent."""
    honest, aggressive = L.system_for("honest"), L.system_for("aggressive")
    for constraint in ("Never invent an employer",
                       "Preserve every number exactly as written",
                       "checked against the candidate's profile"):
        assert constraint in honest, constraint
        assert constraint in aggressive, constraint


def test_off_mode_makes_no_model_call(monkeypatch):
    content = L.from_profile()
    called = []
    monkeypatch.setattr(L, "_llm_rewrite",
                        lambda *a, **k: called.append(1) or {"llm": None})
    out = L.tailor(content, "Backend Engineer. Node.js.", {"keywords": []}, mode="off")
    assert called == [], "off mode must not reach the model at all"
    assert out["mode"] == "off"
    assert out["rewritten"] == 0


def test_use_llm_false_still_means_off(monkeypatch):
    """Several callers predate the modes and pass use_llm=False."""
    content = L.from_profile()
    monkeypatch.setattr(L, "_llm_rewrite",
                        lambda *a, **k: pytest.fail("should not be called"))
    out = L.tailor(content, "Backend Engineer.", {"keywords": []},
                   use_llm=False, mode="aggressive")
    assert out["mode"] == "off"


def test_unknown_mode_falls_back_to_honest(monkeypatch):
    content = L.from_profile()
    monkeypatch.setattr(L, "_llm_rewrite", lambda *a, **k: {"llm": None})
    out = L.tailor(content, "Backend Engineer.", {"keywords": []}, mode="nonsense")
    assert out["mode"] == "honest"
