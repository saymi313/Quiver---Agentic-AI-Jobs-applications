"""required_years: the strings postings actually write."""

from __future__ import annotations

from agent.experience import required_years, seniority, verdict


def test_ranges():
    assert required_years("We need 2-4 years of experience.") == (2, 4)
    assert required_years("2 to 4 years experience with React") == (2, 4)
    assert required_years("1–3 years (em dash)") == (1, 3)


def test_minimums():
    assert required_years("3+ years of experience") == (3, None)
    assert required_years("at least 5 years with Java") == (5, None)
    assert required_years("minimum of 2 years") == (2, None)
    assert required_years("two years of professional experience") == (2, None)


def test_multiple_numbers_take_the_entry_bar():
    text = "5 years of Python and 3 years of React required"
    assert required_years(text) == (3, None)


def test_silence_and_junk():
    assert required_years("") == (None, None)
    assert required_years("Great benefits and a fun team.") == (None, None)
    # A founding year is not an experience requirement.
    assert required_years("Founded 14 years ago in Berlin.") == (None, None)


def test_absurd_numbers_rejected():
    assert required_years("99 years of experience") == (None, None)


# -- seniority: the title must win over LinkedIn's coarse level bucket --------

def test_senior_title_beats_a_mid_senior_board_level():
    # LinkedIn stamps huge numbers of postings "Mid-Senior level", senior ones
    # included. The title is unambiguous and must win, or these slip the gate.
    assert seniority("Senior Software Engineer", "Mid-Senior level") == "senior"
    assert seniority("Senior Full Stack Developer", "Mid-Senior level") == "senior"
    assert seniority("Staff Engineer", "") == "senior"
    assert seniority("Lead Backend Engineer", "Associate") == "senior"


def test_neutral_title_with_mid_senior_level_stays_mid():
    # A plain title under the same bucket is a real mid role and must survive,
    # so the fix does not throw the whole middle of the market out.
    assert seniority("Software Engineer", "Mid-Senior level") == "mid"
    assert seniority("Full Stack Engineer", "Mid-Senior level") == "mid"


def test_verdict_rejects_the_senior_title_that_used_to_leak():
    fits, _ = verdict({"title": "Senior Software Engineer", "level": "Mid-Senior level",
                       "description": ""}, max_years=3)
    assert fits is False
    fits, _ = verdict({"title": "Full Stack Engineer", "level": "Mid-Senior level",
                       "description": "2-3 years of experience"}, max_years=3)
    assert fits is True
