"""House style helpers: the rules every rendered line passes through."""

from __future__ import annotations

from api import resume_style as S


def test_enforce_kills_hyphens_and_dashes():
    assert "-" not in S.enforce("full-stack real-time end-to-end")
    assert "–" not in S.enforce("2022–2026") and "—" not in S.enforce("a—b")


def test_enforce_date_ranges_use_to():
    out = S.enforce("August 2022 - July 2026")
    assert " to " in out and "-" not in out


def test_enforce_keeps_urls_intact():
    url = "https://usairam-saeed.vercel.app/"
    assert url in S.enforce(f"Portfolio at {url}")


def test_lint_flags_violations():
    assert S.lint("I built a full-stack app") != []
    assert S.lint("Responsible for the frontend") != []
    assert S.lint("Built a payments platform serving real users") == []


def test_file_stem_house_naming():
    stem = S.file_stem("Usairam Saeed", "SpaceX", "Frontend Engineer")
    assert stem.startswith("Usairam_Saeed_SpaceX_")
    assert " " not in stem and "-" not in stem


def test_file_stem_company_from_title():
    """'Frontend Engineer at SpaceX' style titles split the company out."""
    stem = S.file_stem("Usairam Saeed", "", "Frontend Engineer at SpaceX")
    assert "SpaceX" in stem
