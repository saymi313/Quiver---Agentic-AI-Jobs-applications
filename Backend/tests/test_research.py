"""
The research aggregation (FR-S8).

Research is only ever a view of what discovery already gathered — so the test
is that it aggregates faithfully: a company with roles appears, an empty one
does not, and a company's people and roles come back attached to it.
"""

from __future__ import annotations


def _company_with_jobs(store, name, titles):
    cid = store.upsert_company({"name": name, "source": "yc", "domain": f"{name.lower()}.com"})
    for i, t in enumerate(titles):
        store.upsert_job({"company_id": cid, "title": t, "url": f"https://{name}.com/j/{i}",
                          "source": "yc"}, company_name=name)
    return cid


def test_research_list_only_shows_companies_with_roles(fresh_store):
    a = _company_with_jobs(fresh_store, "Acme", ["Backend Engineer", "Frontend Engineer"])
    # A company with no jobs must not appear — there is nothing to research.
    fresh_store.upsert_company({"name": "Empty", "source": "yc"})

    rows = fresh_store.research_list()
    names = {r["name"] for r in rows}
    assert "Acme" in names and "Empty" not in names
    acme = next(r for r in rows if r["id"] == a)
    assert acme["job_count"] == 2


def test_research_list_orders_by_how_much_is_known(fresh_store):
    _company_with_jobs(fresh_store, "Small", ["One Role"])
    _company_with_jobs(fresh_store, "Big", ["A", "B", "C"])
    rows = fresh_store.research_list()
    assert rows[0]["name"] == "Big"  # most roles first


def test_research_company_attaches_people_and_jobs(fresh_store):
    cid = _company_with_jobs(fresh_store, "Acme", ["Backend Engineer"])
    fresh_store.upsert_person({"company_id": cid, "email": "cto@acme.com",
                               "full_name": "A Founder", "role": "founder",
                               "email_status": "valid", "email_score": 0.9})

    detail = fresh_store.research_company(cid)
    assert detail["company"]["name"] == "Acme"
    assert [p["email"] for p in detail["people"]] == ["cto@acme.com"]
    assert [j["title"] for j in detail["jobs"]] == ["Backend Engineer"]


def test_research_company_unknown_is_empty(fresh_store):
    assert fresh_store.research_company(999999) == {}
