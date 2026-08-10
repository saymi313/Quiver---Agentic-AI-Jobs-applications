"""The two-page fitter and relevance-driven project selection: relevant
projects lead, floors hold, and (when a LaTeX engine is installed) the
compiled PDF passes the house audit."""

from __future__ import annotations

import pytest

from api import latex_resume as L


def _content():
    return L.from_profile()


def _score(p):
    return sum(b.score for b in p.bullets)


def test_profile_has_projects_with_bullet_floors():
    content = _content()
    assert len(content.projects) >= 4
    for p in content.projects:
        assert len(p.bullets) >= L.MIN_PROJECT_BULLETS, \
            f"{p.name} has {len(p.bullets)} bullet(s), floor is {L.MIN_PROJECT_BULLETS}"


def test_tailor_orders_projects_by_relevance():
    content = _content()
    jd_text = ("UI/UX Designer. Figma wireframes, user research, usability "
               "testing, design systems, prototyping.")
    from api.ats import analyze_jd
    L.tailor(content, jd_text, analyze_jd(jd_text), use_llm=False)
    scores = [_score(p) for p in content.projects]
    assert scores == sorted(scores, reverse=True), "most relevant project must lead"
    assert len(content.projects) >= L.MIN_PROJECTS
    for p in content.projects:
        assert len(p.bullets) <= L.MAX_PROJECT_BULLETS


def test_select_projects_drops_irrelevant_keeps_floor():
    from api.latex_resume import Block, Bullet, select_projects

    def proj(name, score):
        return Block(name=name, bullets=[Bullet(f"{name} work", score=score)])

    picked = select_projects([proj("A", 0.0), proj("B", 3.0), proj("C", 1.0)])
    assert [p.name for p in picked] == ["B", "C"], "zero-score project is dropped"

    # Only one relevant project: the floor wins over strict relevance.
    picked = select_projects([proj("A", 0.0), proj("B", 3.0)])
    assert [p.name for p in picked] == ["B", "A"]

    # Nothing scored: a generic posting keeps profile order, up to the cap.
    picked = select_projects([proj("A", 0.0), proj("B", 0.0), proj("C", 0.0)])
    assert len(picked) == 3

    # The section never runs past MAX_PROJECTS_SHOWN, however many score.
    many = [proj(f"P{i}", float(10 - i)) for i in range(8)]
    picked = select_projects(many)
    assert [p.name for p in picked] == ["P0", "P1", "P2", "P3"]


def test_drop_weakest_sheds_least_relevant_project_first():
    content = _content()
    # Give every bullet a score so relevance ordering is deterministic.
    for i, p in enumerate(content.projects):
        for b in p.bullets:
            b.score = float(len(content.projects) - i)
    for blk in content.experience:
        for b in blk.bullets:
            b.score = 10.0
    strongest = content.projects[0].name
    # Exhaust the fitter completely.
    while L._drop_weakest(content):
        pass
    assert len(content.projects) == L.MIN_PROJECTS, \
        "fitter must stop at the project floor"
    assert content.projects[0].name == strongest, \
        "the most relevant project must be the last standing"
    for blk in content.experience:
        assert len(blk.bullets) >= L.MIN_ROLE_BULLETS


@pytest.mark.skipif(L.find_engine() is None, reason="no LaTeX engine installed")
def test_compiled_pdf_is_two_pages_and_passes_audit(tmp_path):
    from api.ats import analyze_jd
    from api.resume_audit import audit_pdf

    content = _content()
    jd_text = ("Full Stack Engineer. React, Node.js, MongoDB, TypeScript, "
               "REST APIs, real time features. 1 to 3 years experience.")
    L.tailor(content, jd_text, analyze_jd(jd_text), use_llm=False)
    out = L.build(content, tmp_path, "Test_Resume", log=lambda _: None)
    assert out["pdf"] is not None
    assert out["pages"] <= L.MAX_PAGES
    assert audit_pdf(out["pdf"]) == []
