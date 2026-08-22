"""
The saved-answer bank — the long tail a profile cannot hold.

The point of these is that they reuse the user's own words, so a forgiving match
is safe. The tests pin that a small wording difference still connects, that an
unrelated field does not, and that a free-text answer is not mistaken for a
Yes/No on a button group.
"""

from __future__ import annotations

from agent import answers

BANK = [
    {"match": "open to co-living", "answer": "Yes"},
    {"match": "favourite programming language", "answer": "JavaScript"},
    {"match": "three most impressive things you have built",
     "answer": "A trading platform, a CV attendance system, a blockchain marketplace"},
]


def test_a_direct_substring_matches():
    assert answers.match("Are you open to co-living?", saved=BANK) == "Yes"


def test_a_small_wording_difference_still_connects():
    # "you have built" vs the form's "you've built" — most keywords still line up.
    assert answers.match("Three most impressive things you've built",
                         saved=BANK).startswith("A trading platform")


def test_an_unrelated_field_gets_no_answer():
    assert answers.match("Upload your passport photo", saved=BANK) is None
    assert answers.match("First name", saved=BANK) is None


def test_blank_label_is_safe():
    assert answers.match("", saved=BANK) is None


def test_yes_no_coercion_only_accepts_a_yes_or_no():
    assert answers.as_yes_no("Yes") == "Yes"
    assert answers.as_yes_no("no") == "No"
    assert answers.as_yes_no("agree") == "Yes"
    # A free-text answer is not a button choice.
    assert answers.as_yes_no("JavaScript") is None
    assert answers.as_yes_no("") is None


def test_load_drops_half_filled_entries(monkeypatch):
    from agent import store
    monkeypatch.setattr(store, "get_setting",
                        lambda key, default=None: [
                            {"match": "co-living", "answer": "Yes"},
                            {"match": "", "answer": "orphan"},      # no question
                            {"match": "salary", "answer": ""},        # no answer
                            "not a dict",
                        ] if key == "custom_answers" else default)
    loaded = answers.load()
    assert loaded == [{"match": "co-living", "answer": "Yes"}]
