"""
The region gate — keep Pakistan, Europe, the Gulf and remote; drop South Asia
and North America.

Location strings are written every possible way, so the tests pin the shapes
that matter: a US city with a state code (no "United States" in sight), South
Asian countries, and the keeps that must survive — the Gulf, Europe, Pakistan,
and a bare "Remote".
"""

from __future__ import annotations

from agent.matcher import location_excluded
from agent.schema import DEFAULT_SETTINGS

EX = DEFAULT_SETTINGS["targeting"]["exclude_locations"]


def test_south_asia_is_excluded():
    for loc in ["Bangalore, India", "Dhaka, Bangladesh", "Colombo, Sri Lanka",
                "Kathmandu, Nepal"]:
        assert location_excluded(loc, EX), loc


def test_north_america_is_excluded_even_without_the_country_name():
    for loc in ["San Francisco, CA", "New York, NY", "Austin, TX", "Remote, US",
                "Toronto, Canada", "Seattle"]:
        assert location_excluded(loc, EX), loc


def test_target_regions_are_kept():
    for loc in ["Berlin, Germany", "London, United Kingdom", "Amsterdam, Netherlands",
                "Dubai, UAE", "Vienna, Austria", "Karachi, Pakistan", "Lahore",
                "Remote", "Remote, Europe", ""]:
        assert location_excluded(loc, EX) is None, loc


def test_pakistan_is_never_excluded():
    # Even a remote-US-adjacent string keeps Pakistan when it is named.
    assert location_excluded("Remote (Pakistan / US friendly)", EX) is None


def test_no_exclude_list_keeps_everything():
    assert location_excluded("Bangalore, India", []) is None
