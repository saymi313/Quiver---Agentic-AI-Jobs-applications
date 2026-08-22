"""
Reading a finished resume back into a profile (FR-P10).

The mapping is where this can go quietly wrong: a bullet dropped, a company and
a role swapped, contact links lost. So the converter is pinned against a parsed
resume built by hand, asserting the profile comes out in the shape the tailor
and the LaTeX builder expect.
"""

from __future__ import annotations

import types

from api import resume_profiles


def _entry(**kw):
    return types.SimpleNamespace(
        header=kw.get("header", ""), title=kw.get("title", ""),
        organization=kw.get("organization", ""), period=kw.get("period", ""),
        bullets=kw.get("bullets", []))


def _parsed():
    return types.SimpleNamespace(
        name="Jane Doe",
        headline="Senior Software Engineer",
        contact={"email": "jane@x.com", "phone": "+1 555 0100", "location": "Berlin",
                 "linkedin": "https://linkedin.com/in/jane", "github": "https://github.com/jane"},
        sections={"skills": ["Languages: Python, Go", "Cloud: AWS, GCP"],
                  "education": ["MSc Computer Science, TU Berlin, 2020"],
                  "summary": ["Engineer with 6 years building backends."]},
        experience=[_entry(title="Backend Engineer", organization="Acme", period="2021–2024",
                           bullets=["Built the billing service.", "Cut latency 40%.", "  "])],
        projects=[_entry(header="Sidequest", bullets=["A CLI for job hunting."])],
    )


def test_contact_and_headline_map_across():
    p = resume_profiles._parsed_to_profile(_parsed())
    c = p["candidate"]
    assert c["name"] == "Jane Doe"
    assert c["title"] == "Senior Software Engineer"
    assert c["email"] == "jane@x.com" and c["location"] == "Berlin"
    labels = {l["label"] for l in c["links"]}
    assert labels == {"LinkedIn", "GitHub"}
    assert "6 years" in c["summary"]


def test_experience_keeps_company_role_and_nonblank_bullets():
    p = resume_profiles._parsed_to_profile(_parsed())
    exp = p["experience"][0]
    assert exp["company"] == "Acme" and exp["role"] == "Backend Engineer"
    # The blank bullet is dropped; the two real ones survive with their text.
    assert [b["text"] for b in exp["bullets"]] == ["Built the billing service.", "Cut latency 40%."]


def test_projects_use_the_header_as_the_role():
    p = resume_profiles._parsed_to_profile(_parsed())
    assert p["projects"][0]["role"] == "Sidequest"


def test_skills_and_education_carry_as_lines():
    p = resume_profiles._parsed_to_profile(_parsed())
    assert p["skills"] == [{"line": "Languages: Python, Go"}, {"line": "Cloud: AWS, GCP"}]
    assert p["education"][0]["institution"].startswith("MSc Computer Science")


def test_import_rejects_a_pathish_name(tmp_path):
    # A name with a slash or dot could escape the profiles directory.
    out = resume_profiles.import_document("../evil", tmp_path / "x.pdf")
    assert out["ok"] is False
