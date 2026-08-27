"""
The jobs table's filters, on a throwaway SQLite file.

These exist because a filter is uniquely easy to ship broken: it narrows a list
by *something*, the screen looks plausible, and only someone who counts the
rows notices it narrowed by the wrong thing — or by nothing. Two of the cases
below are regressions from exactly that. `remote` reached the API and did
nothing for a while because the frontend's query builder dropped every key it
did not already know about, and the facet counts used to come from re-reading
every row rather than from the database.

Each test asserts on a count *and* on which rows came back, so a filter that
returns the right number of the wrong rows still fails.
"""

from __future__ import annotations

import time


def _job(store, title, *, url, source="yc", category=None, score=None,
         location="", remote=0, company="Acme", status=None, days_old=0,
         resume=None):
    cid = store.upsert_company({"name": company, "source": "yc"})
    jid = store.upsert_job({
        "company_id": cid, "title": title, "url": url, "source": source,
        "role_category": category, "location": location, "remote": remote,
        "posted_ts": int(time.time() - days_old * 86400),
        "resume_path": resume,
    }, company_name=company)
    if score is not None:
        store.set_job_fit(jid, score, "seeded", status or "matched")
    if status:
        store.set_job_status(jid, status)
    return jid


def _seed(store):
    _job(store, "React Developer", url="https://a.dev/1", category="frontend",
         score=80, location="Remote, Europe", remote=1, days_old=0)
    _job(store, "Node Engineer", url="https://a.dev/2", category="backend",
         score=60, location="Berlin", days_old=2, company="Bolt")
    _job(store, "Full Stack Engineer", url="https://a.dev/3", category="fullstack",
         score=40, location="New York, NY", days_old=10, source="ashby",
         resume="/tmp/r.pdf")
    _job(store, "UX Designer", url="https://a.dev/4", category="ux_design",
         score=90, location="Remote", remote=1, days_old=1, company="Bolt",
         status="applied")


def _titles(rows):
    return sorted(r["title"] for r in rows)


def test_category_takes_a_list(fresh_store):
    _seed(fresh_store)
    rows = fresh_store.list_jobs(50, category="frontend,fullstack")
    assert _titles(rows) == ["Full Stack Engineer", "React Developer"]
    # One value must keep working — the UI sends a bare string for a single pick.
    assert _titles(fresh_store.list_jobs(50, category="backend")) == ["Node Engineer"]


def test_remote_partitions_the_set(fresh_store):
    """Every row is either remote or on-site, and the two never overlap."""
    _seed(fresh_store)
    everything = fresh_store.list_jobs(50)
    remote = fresh_store.list_jobs(50, remote=True)
    onsite = fresh_store.list_jobs(50, remote=False)

    assert _titles(remote) == ["React Developer", "UX Designer"]
    assert _titles(onsite) == ["Full Stack Engineer", "Node Engineer"]
    assert len(remote) + len(onsite) == len(everything)


def test_remote_is_read_from_the_location_too(fresh_store):
    """Most boards only say "remote" in the location; the flag is the minority."""
    _job(fresh_store, "Rails Engineer", url="https://a.dev/9",
         location="Remote (EU timezones)", remote=0)
    assert _titles(fresh_store.list_jobs(50, remote=True)) == ["Rails Engineer"]


def test_score_band_and_freshness(fresh_store):
    _seed(fresh_store)
    assert _titles(fresh_store.list_jobs(50, min_score=70)) == ["React Developer", "UX Designer"]
    assert _titles(fresh_store.list_jobs(50, min_score=50, max_score=85)) == [
        "Node Engineer", "React Developer"]
    assert "Full Stack Engineer" not in _titles(
        fresh_store.list_jobs(50, posted_within_days=3))


def test_company_place_and_resume(fresh_store):
    _seed(fresh_store)
    assert _titles(fresh_store.list_jobs(50, company="Bolt")) == [
        "Node Engineer", "UX Designer"]
    assert _titles(fresh_store.list_jobs(50, location="Berlin")) == ["Node Engineer"]
    assert _titles(fresh_store.list_jobs(50, has_resume=True)) == ["Full Stack Engineer"]
    assert "Full Stack Engineer" not in _titles(fresh_store.list_jobs(50, has_resume=False))


def test_filters_combine_with_and(fresh_store):
    """Two filters narrow together. Setting a second one that widens the result
    is the classic sign they were OR-ed by accident."""
    _seed(fresh_store)
    both = fresh_store.list_jobs(50, category="frontend,ux_design", remote=True,
                                 min_score=85)
    assert _titles(both) == ["UX Designer"]


def test_sort_orders_are_honoured(fresh_store):
    _seed(fresh_store)
    by_score = [r["title"] for r in fresh_store.list_jobs(50, sort="score")]
    assert by_score[0] == "UX Designer" and by_score[-1] == "Full Stack Engineer"
    by_title = [r["title"] for r in fresh_store.list_jobs(50, sort="title")]
    assert by_title == sorted(by_title, key=str.lower)
    # An unknown sort falls back rather than raising or returning nothing.
    assert len(fresh_store.list_jobs(50, sort="nonsense")) == 4


def test_facets_count_every_row_not_just_the_filtered_ones(fresh_store):
    """The counts describe the whole table — they are what the filter controls
    offer, so narrowing the list must not shrink them."""
    _seed(fresh_store)
    facets = fresh_store.job_facets()
    assert facets["total"] == 4
    assert facets["categories"] == {"frontend": 1, "backend": 1,
                                    "fullstack": 1, "ux_design": 1}
    assert facets["sources"]["yc"] == 3 and facets["sources"]["ashby"] == 1
    assert facets["statuses"]["applied"] == 1

    fresh_store.list_jobs(50, category="backend")
    assert fresh_store.job_facets()["total"] == 4


def test_tracker_early_exclusions(fresh_store):
    from agent.runner import Tracker

    targeting = {
        "categories": ["backend", "frontend"],
        "exclude_titles": ["Senior Staff", "Director", "VP", "Intern"],
        "exclude_locations": ["India", "United States"],
        "titles": ["React Developer", "Node.js Developer"],
        "strict_title_matching": True,
    }
    tracker = Tracker(targeting, log=lambda _: None)

    # Excluded title should be dropped
    cid = fresh_store.upsert_company({"name": "Acme", "source": "yc"})
    assert tracker.add({"title": "Director of Engineering", "url": "https://a.dev/10", "source": "yc"},
                       cid, "Acme") is None
    assert tracker.counts["excluded"] == 1

    # Excluded location should be dropped
    assert tracker.add({"title": "React Developer", "url": "https://a.dev/11", "source": "yc",
                        "location": "Bangalore, India"}, cid, "Acme") is None
    assert tracker.counts["excluded"] == 2

    # Off-preference title under strict matching should be dropped
    assert tracker.add({"title": "Python Developer", "url": "https://a.dev/12", "source": "yc",
                        "location": "Berlin"}, cid, "Acme") is None

    # Matching preferred title should be tracked
    jid = tracker.add({"title": "React Developer", "url": "https://a.dev/13", "source": "yc",
                       "location": "Berlin"}, cid, "Acme")
    assert jid is not None
    assert tracker.counts["new"] == 1
