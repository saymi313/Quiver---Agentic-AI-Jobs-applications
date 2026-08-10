"""required_years: the strings postings actually write."""

from __future__ import annotations

from agent.experience import required_years


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
