"""
The resume editor's options (FR-P11).

An editor control must never be able to produce a resume that will not compile,
so every option is coerced to something valid. These pin that: bad values snap
to the nearest valid one, and no section can be lost by reordering.
"""

from __future__ import annotations

from api.latex_resume import RenderOptions, SECTION_KEYS, FONT_SIZES


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
