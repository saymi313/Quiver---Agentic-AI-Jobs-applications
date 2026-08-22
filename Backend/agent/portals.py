"""
What Quiver can do with each applicant tracking system, as data.

Two capabilities, tracked separately, because they genuinely are separate and
conflating them is how a job ends up in the table with an Apply button that was
never going to work:

  * **detects** — Quiver can read this system's public board and pull its open
    roles, so jobs from it appear during discovery.
  * **submits** — Quiver can fill and submit this system's application form.

Tsenta states the same distinction in their docs ("Tsenta may recognize a job
page even when that page does not have an active submission workflow"), and
it is worth adopting as a rule rather than a footnote: the UI shows this table
so the user knows what to expect before selecting a row, instead of finding out
from a failure.

`submits` is claimed only where a real application has gone through, or where
the form is the same engine as one that has. Everything else says `unproven`,
which is an honest third answer and not the same as "no".
"""

from __future__ import annotations

from typing import Any

# Submission confidence.
#   proven    an application has actually been submitted through this system
#   likely    same form engine as a proven one, or verified filling end to end
#   unproven  the generic driver will try; nobody has seen it succeed
#   no        known not to work, with a reason
PROVEN, LIKELY, UNPROVEN, NO = "proven", "likely", "unproven", "no"

PORTALS: tuple[dict[str, Any], ...] = (
    # ---- read and submit ------------------------------------------------
    {"slug": "greenhouse", "name": "Greenhouse", "detects": True, "submits": PROVEN,
     "note": "Board API plus a form the applier fills end to end."},
    {"slug": "ashby", "name": "Ashby", "detects": True, "submits": PROVEN,
     "note": "Submitted successfully. Needs a visible browser: its anti-bot "
             "scoring rejects headless as spam."},
    {"slug": "lever", "name": "Lever", "detects": True, "submits": LIKELY,
     "note": "Board API reads cleanly; the form is a standard multipart post."},
    {"slug": "smartrecruiters", "name": "SmartRecruiters", "detects": True, "submits": UNPROVEN},
    {"slug": "workable", "name": "Workable", "detects": True, "submits": UNPROVEN,
     "note": "Posting body is rendered client side."},
    {"slug": "recruitee", "name": "Recruitee", "detects": True, "submits": UNPROVEN},
    {"slug": "breezy", "name": "Breezy HR", "detects": True, "submits": UNPROVEN,
     "note": "Public JSON board at {token}.breezy.hr/json."},
    {"slug": "rippling", "name": "Rippling", "detects": True, "submits": UNPROVEN,
     "note": "Public board API. Descriptions need a second fetch per role."},

    # ---- forms only: no public board to read ----------------------------
    {"slug": "workday", "name": "Workday", "detects": False, "submits": UNPROVEN,
     "note": "Board needs a POST with a tenant-specific body; no public GET. "
             "Jobs arrive from aggregators instead."},
    {"slug": "teamtailor", "name": "Teamtailor", "detects": False, "submits": UNPROVEN,
     "note": "Public API requires a key."},
    {"slug": "personio", "name": "Personio", "detects": True, "submits": UNPROVEN,
     "note": "Reads the public XML feed at {token}.jobs.personio.de/xml."},
    {"slug": "jazzhr", "name": "JazzHR", "detects": False, "submits": UNPROVEN},
    {"slug": "bamboohr", "name": "BambooHR", "detects": True, "submits": UNPROVEN,
     "note": "Reads the public careers list at {token}.bamboohr.com/careers/list."},
    {"slug": "join", "name": "Join.com", "detects": False, "submits": UNPROVEN,
     "note": "Public API rejects anonymous paging parameters."},
    {"slug": "icims", "name": "iCIMS", "detects": False, "submits": UNPROVEN},
    {"slug": "jobvite", "name": "Jobvite", "detects": False, "submits": UNPROVEN},
    {"slug": "adp", "name": "ADP", "detects": False, "submits": UNPROVEN},
    {"slug": "oracle", "name": "Oracle Recruiting", "detects": False, "submits": UNPROVEN},
    {"slug": "successfactors", "name": "SuccessFactors", "detects": False, "submits": UNPROVEN},
    {"slug": "dayforce", "name": "Dayforce", "detects": False, "submits": UNPROVEN},
    {"slug": "ukg", "name": "UltiPro / UKG", "detects": False, "submits": UNPROVEN},
    {"slug": "phenom", "name": "Phenom", "detects": False, "submits": UNPROVEN},
    {"slug": "paylocity", "name": "Paylocity", "detects": False, "submits": UNPROVEN},
    {"slug": "zoho", "name": "Zoho Recruit", "detects": False, "submits": UNPROVEN},
    {"slug": "pinpoint", "name": "Pinpoint", "detects": False, "submits": UNPROVEN},
    {"slug": "polymer", "name": "Polymer", "detects": False, "submits": UNPROVEN},
    {"slug": "hireology", "name": "Hireology", "detects": False, "submits": UNPROVEN},
    {"slug": "dover", "name": "Dover", "detects": False, "submits": UNPROVEN},
    {"slug": "gem", "name": "Gem", "detects": False, "submits": UNPROVEN},

    # ---- aggregators ----------------------------------------------------
    # Not ATS systems: they list other people's postings and hand off. The
    # applier follows their Apply link through to the real form.
    {"slug": "arbeitnow", "name": "Arbeitnow", "detects": True, "submits": NO,
     "note": "Aggregator. The Apply link is followed to the employer's own form."},
    {"slug": "remoteok", "name": "RemoteOK", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "remotive", "name": "Remotive", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "weworkremotely", "name": "WeWorkRemotely", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "workingnomads", "name": "Working Nomads", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "landingjobs", "name": "Landing.jobs", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "themuse", "name": "The Muse", "detects": True, "submits": NO,
     "note": "Aggregator."},
    {"slug": "yc", "name": "Y Combinator", "detects": True, "submits": NO,
     "note": "Company directory; roles link out to each company's own board."},
    {"slug": "hn", "name": "HN Who is hiring", "detects": True, "submits": NO,
     "note": "Forum thread. Applying means emailing the poster."},
)

BY_SLUG: dict[str, dict[str, Any]] = {p["slug"]: p for p in PORTALS}


def get(slug: str | None) -> dict[str, Any]:
    return BY_SLUG.get((slug or "").strip().lower(), {})


def name_of(slug: str | None) -> str:
    return get(slug).get("name") or (slug or "unknown")


def can_detect(slug: str | None) -> bool:
    return bool(get(slug).get("detects"))


def submit_support(slug: str | None) -> str:
    """PROVEN | LIKELY | UNPROVEN | NO, defaulting to unproven for the unknown."""
    return get(slug).get("submits") or UNPROVEN


def can_submit(slug: str | None) -> bool:
    """Whether it is worth pointing the applier at this system at all.

    `unproven` counts as yes: the generic driver handles most standard forms,
    and refusing to try would mean never learning which ones work."""
    return submit_support(slug) != NO


def table() -> list[dict[str, Any]]:
    """The whole table, for the API and the UI."""
    return [dict(p) for p in PORTALS]


def summary() -> dict[str, int]:
    return {
        "total": len(PORTALS),
        "detects": sum(1 for p in PORTALS if p["detects"]),
        "proven": sum(1 for p in PORTALS if p["submits"] == PROVEN),
        "likely": sum(1 for p in PORTALS if p["submits"] == LIKELY),
    }
