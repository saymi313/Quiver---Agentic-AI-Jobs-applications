"""dedupe_hash: one identity per real-world role, stable across boards."""

from __future__ import annotations

from agent.sources import dedupe_hash


def test_same_job_across_boards_collides():
    a = dedupe_hash("Acme", "Backend Engineer", "Remote, EU",
                    "https://remoteok.com/jobs/1")
    b = dedupe_hash("Acme", "Backend Engineer", "Remote, EU",
                    "https://remotive.com/jobs/999?utm_source=x")
    assert a == b


def test_normalisation():
    a = dedupe_hash("Acme Inc", "Backend Engineer (Remote)", "Berlin")
    b = dedupe_hash("acme inc", "Backend   Engineer", "berlin")
    assert a == b


def test_different_titles_differ():
    a = dedupe_hash("Acme", "Backend Engineer", "Berlin")
    b = dedupe_hash("Acme", "Frontend Engineer", "Berlin")
    assert a != b


def test_anonymous_employers_fall_back_to_url():
    a = dedupe_hash("Unknown", "Software Engineer", "Europe", "https://x.com/j/1")
    b = dedupe_hash("Unknown", "Software Engineer", "Europe", "https://x.com/j/2")
    assert a != b
    # ...and tracking parameters do not split the same URL in two.
    c = dedupe_hash("", "Software Engineer", "", "https://x.com/j/1?ref=abc")
    d = dedupe_hash("", "Software Engineer", "", "https://x.com/j/1")
    assert c == d


def test_stability():
    """The hash is persisted in the DB — the algorithm must not drift."""
    assert dedupe_hash("Acme", "Backend Engineer", "Berlin") == \
        dedupe_hash("Acme", "Backend Engineer", "Berlin")
    assert len(dedupe_hash("Acme", "Backend Engineer", "Berlin")) == 20
