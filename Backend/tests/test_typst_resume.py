"""
Tests for Sub-50ms Typst Resume Generator.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from api import typst_resume


def test_typst_options_coercion():
    opts = typst_resume.TypstRenderOptions.coerce({"font": "century_gothic", "font_size": 11.5})
    assert opts.font == "century_gothic"
    assert opts.font_size == 11.5

    opts_invalid = typst_resume.TypstRenderOptions.coerce({"font": "comic_sans", "font_size": "bad"})
    assert opts_invalid.font == "times"
    assert opts_invalid.font_size == 10.0


def test_typst_markup_generation():
    profile = {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+1 555-0199",
        "experience": [
            {
                "title": "Software Engineer",
                "company": "Acme Inc",
                "dates": "2023 - Present",
                "bullets": ["Engineered high-throughput streaming systems using Kafka and Python."],
            }
        ],
        "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
    }

    source = typst_resume.generate_typst_source(profile)
    assert 'Jane Doe' in source
    assert 'jane@example.com' in source
    assert 'Software Engineer' in source
    assert 'Kafka and Python' in source


def test_typst_compilation(tmp_path: Path):
    profile = {
        "full_name": "John Smith",
        "email": "john@example.com",
        "experience": [{"title": "Frontend Lead", "company": "Tech Corp", "bullets": ["Built apps in React."]}],
    }

    source = typst_resume.generate_typst_source(profile)
    pdf_out = tmp_path / "resume_john.pdf"
    typ_out = tmp_path / "resume_john.typ"

    result = typst_resume.compile_typst(source, output_pdf=pdf_out, output_typ=typ_out)
    assert result["ok"] is True
    assert pdf_out.is_file()
    assert typ_out.is_file()
    assert typ_out.read_text(encoding="utf-8").startswith('#set page')

