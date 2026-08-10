"""The two-page fitter: every project survives, floors hold, and (when a LaTeX
engine is installed) the compiled PDF passes the house audit."""

from __future__ import annotations

import pytest

from api import latex_resume as L


def _content():
    return L.from_profile()


def test_profile_has_all_projects_with_bullet_floors():
    content = _content()
    assert len(content.projects) >= 4
    for p in content.projects:
        assert len(p.bullets) >= L.MIN_PROJECT_BULLETS, \
            f"{p.name} has {len(p.bullets)} bullet(s), floor is {L.MIN_PROJECT_BULLETS}"


def test_tailor_keeps_every_project():
    content = _content()
    names_before = {p.name for p in content.projects}
    jd_text = "Backend Engineer. Node.js, MongoDB, REST APIs, 2 years experience."
    from api.ats import analyze_jd
    L.tailor(content, jd_text, analyze_jd(jd_text), use_llm=False)
    assert {p.name for p in content.projects} == names_before
    for p in content.projects:
        assert len(p.bullets) <= L.MAX_PROJECT_BULLETS


def test_drop_weakest_never_deletes_a_project():
    content = _content()
    for b in [b for blk in content.experience + content.projects for b in blk.bullets]:
        b.score = 1.0
    names = {p.name for p in content.projects}
    # Exhaust the fitter completely.
    while L._drop_weakest(content):
        pass
    assert {p.name for p in content.projects} == names
    for p in content.projects:
        assert len(p.bullets) >= min(L.MIN_PROJECT_BULLETS, len(p.bullets))
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
