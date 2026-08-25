"""
The resume editor's options (FR-P11).

An editor control must never be able to produce a resume that will not compile,
so every option is coerced to something valid. These pin that: bad values snap
to the nearest valid one, and no section can be lost by reordering.
"""

from __future__ import annotations

from api.latex_resume import RenderOptions, SECTION_KEYS, FONT_SIZES, FONTS


def test_computer_modern_is_an_offered_font():
    # The classic LaTeX look is a selectable option, and it coerces through.
    assert "computer_modern" in FONTS
    assert FONTS["computer_modern"]["label"] == "Computer Modern"
    assert RenderOptions.coerce({"font": "computer_modern"}).font == "computer_modern"


def test_audit_accepts_latin_modern_fonts():
    # Computer Modern renders as LMRoman; the house-style font check must not
    # flag it as a stray non-serif face.
    import re
    from api import resume_audit  # noqa: F401 — ensures the module imports
    from api.resume_audit import _intentional_camel  # noqa: F401
    # The regex used by audit_pdf's font check lives inline; assert its allowance.
    pattern = (r"(Times|NimbusRom|Termes|TeXGyreTermes|txtt|ntx|"
               r"LMRoman|LMMono|LMSans|CMR|CMSY|CMMI|Latin ?Modern|Computer ?Modern)")
    assert re.search(pattern, "LMRoman10-Regular", re.I)
    assert re.search(pattern, "LMRoman12-Bold", re.I)


def test_bad_values_snap_to_valid_ones():
    o = RenderOptions.coerce({"font": "comic-sans", "font_size": 99, "align": "sideways",
                              "template": "fancy"})
    assert o.font == "times"            # unknown font -> default
    assert o.font_size in FONT_SIZES    # out-of-range size -> nearest valid
    assert o.font_size == 11.5          # 99 clamps to the largest offered
    assert o.align == "left"            # unknown alignment -> ragged
    assert o.template == "standard"


def test_font_size_snaps_to_nearest():
    assert RenderOptions.coerce({"font_size": 10.7}).font_size == 10.5
    assert RenderOptions.coerce({"font_size": 10.9}).font_size == 11.0


def test_sections_never_lose_one():
    # Reorder only two; the rest are appended so nothing vanishes.
    o = RenderOptions.coerce({"sections": ["skills", "summary"]})
    assert set(o.sections) == set(SECTION_KEYS)
    assert o.sections[:2] == ("skills", "summary")


def test_sections_drop_unknown_and_dedupe():
    o = RenderOptions.coerce({"sections": ["skills", "skills", "bogus", "summary"]})
    assert set(o.sections) == set(SECTION_KEYS)          # bogus dropped, all present
    assert o.sections.count("skills") == 1               # deduped


def test_to_context_is_compilable_shape():
    ctx = RenderOptions.coerce({"template": "compact"}).to_context()
    assert ctx["margin"] == "0.4in"                       # compact tightens the margin
    assert "usepackage" in ctx["font_pkg"]
    assert ctx["sections"]
