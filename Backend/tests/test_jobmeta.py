"""
The job-detail parser (agent/jobmeta.py).

A wrong field on the panel is worse than a blank one — a made-up salary or
deadline actively misleads. So each extractor is pinned on the formats that
matter and, just as deliberately, on the cases where it must stay silent.
"""

from __future__ import annotations

from agent import jobmeta


# ---- salary ---------------------------------------------------------------

def test_salary_gbp_range_with_k_and_slash_yr():
    lo, hi, cur = jobmeta.parse_salary("Salary: GBP 43k - 64k /yr, plus equity")
    assert (lo, hi, cur) == (43000, 64000, "GBP")


def test_salary_dollar_full_numbers():
    lo, hi, cur = jobmeta.parse_salary("Compensation $120,000 - $150,000 per year")
    assert (lo, hi, cur) == (120000, 150000, "USD")


def test_salary_euro_symbol_single_value():
    lo, hi, cur = jobmeta.parse_salary("Base salary €70,000 per annum")
    assert lo == 70000 and cur == "EUR"


def test_salary_needs_context_word():
    # A stray dollar amount that is not pay must not be read as salary.
    assert jobmeta.parse_salary("Founded in 2019, raised $5,000,000 in seed funding") \
        == (None, None, None)


def test_salary_ignores_small_numbers():
    # "3 days ago", "5 years" — none of these are pay.
    assert jobmeta.parse_salary("Posted 3 days ago. 5 years experience. Salary competitive.") \
        == (None, None, None)


# ---- seniority ------------------------------------------------------------

def test_seniority_from_title_beats_body():
    assert jobmeta.detect_seniority("Senior Software Engineer",
                                    "some junior tasks included") == "senior"


def test_seniority_senior_staff_reads_as_staff():
    assert jobmeta.detect_seniority("Senior Staff Engineer", "") == "staff"


def test_seniority_entry_and_intern():
    assert jobmeta.detect_seniority("Graduate Software Engineer", "") == "entry"
    assert jobmeta.detect_seniority("Software Engineering Intern", "") == "intern"


def test_seniority_absent():
    assert jobmeta.detect_seniority("Software Engineer", "build things") is None


# ---- work arrangement -----------------------------------------------------

def test_arrangement_hybrid_wins_over_remote_mention():
    # A hybrid posting nearly always also says "remote" somewhere.
    assert jobmeta.detect_arrangement("Leeds, UK",
                                      "Hybrid role, 2 days remote per week") == "hybrid"


def test_arrangement_remote_and_onsite():
    assert jobmeta.detect_arrangement("Remote (EU)", "") == "remote"
    assert jobmeta.detect_arrangement("New York, NY", "On-site, five days a week") == "onsite"


# ---- skills ---------------------------------------------------------------

def test_skills_canonical_and_deduped():
    text = ("We use React, react.js and ReactJS with TypeScript and Node.js. "
            "Experience with AWS, Docker and Kubernetes required. Agile team.")
    skills = jobmeta.extract_skills(text)
    assert skills.count("React") == 1
    for expected in ("React", "TypeScript", "Node.js", "AWS", "Docker", "Kubernetes", "Agile"):
        assert expected in skills, f"{expected} missing from {skills}"


def test_skills_word_boundary_no_false_go():
    # "Go" the language must not match inside "Going" or "category".
    assert "Go" not in jobmeta.extract_skills("Going through the category of tasks")


def test_skills_capped():
    text = " ".join(name for name, _ in jobmeta._SKILL_DICT for _ in range(1)) \
        .replace("C++", "cpp").replace("C#", "c sharp")
    assert len(jobmeta.extract_skills(text * 1)) <= jobmeta.MAX_SKILLS


# ---- deadline -------------------------------------------------------------

def test_deadline_day_month_year():
    assert jobmeta.parse_deadline("Applications close on 30 August 2026.") == "2026-08-30"


def test_deadline_end_date_phrasing():
    assert jobmeta.parse_deadline("End Date: Sunday 30 August 2026") == "2026-08-30"


def test_deadline_iso_and_numeric():
    assert jobmeta.parse_deadline("Deadline 2026-08-30 for all applicants") == "2026-08-30"
    assert jobmeta.parse_deadline("Apply by 30/08/2026") == "2026-08-30"


def test_deadline_needs_context():
    # A date that is not a deadline must not be read as one.
    assert jobmeta.parse_deadline("The company was founded on 30 August 2019.") is None


# ---- enrich ---------------------------------------------------------------

def test_enrich_only_returns_what_it_found():
    job = {"title": "Senior Backend Engineer",
           "location": "Remote",
           "description": "Salary $130k-$160k. Python, Django, PostgreSQL, AWS. "
                          "Applications close 30 August 2026."}
    out = jobmeta.enrich(job)
    assert out["salary_min"] == 130000 and out["salary_max"] == 160000
    assert out["seniority"] == "senior"
    assert out["work_arrangement"] == "remote"
    assert "Python" in out["skills"] and "AWS" in out["skills"]
    assert out["deadline"] == "2026-08-30"


def test_enrich_leaves_employment_type_when_source_set_it():
    job = {"title": "Engineer", "employment_type": "Full Time",
           "description": "This is a contract role"}
    # Source already said Full Time; prose saying "contract" must not override it.
    assert "employment_type" not in jobmeta.enrich(job)
