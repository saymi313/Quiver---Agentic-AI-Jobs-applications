# Jobenzy browser extension

One click on any job posting sends its URL to Jobenzy running on your own
machine. Jobenzy reads the page, works out the role, scores it against your
profile and adds it to the tracked jobs table — the same pipeline a discovered
job goes through, entered at the point where the URL is already known.

## Install

It is not on the Chrome Web Store, so load it unpacked:

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. **Load unpacked**, and choose this `Extension` folder.
4. Pin Jobenzy to the toolbar so the button is one click away.

Firefox and Edge load it the same way (`about:debugging` and `edge://extensions`).

## Use

Open a job posting and click the Jobenzy button. It reports what happened in the
extension's own words rather than a generic success:

- **Tracked** — the role, the company, its category and its match score.
- **Already tracked** — you or a discovery run found it first.
- **That posting is closed** — the board says the role is no longer open, so
  nothing was added.
- **That link opens a job board** — the posting was taken down, or the link
  points at the board rather than one role.
- **Jobenzy is not running** — start it from `Backend/` with
  `python run_dashboard.py`.

## What it sends, and where

Only the URL of the tab you clicked on, and only to `127.0.0.1:8000` or
`localhost:8000`. The extension holds no credentials, stores nothing, and talks
to no server but yours — `host_permissions` in the manifest allows exactly those
two addresses and nothing else.

It asks for `activeTab`, which grants access to a tab's URL **only** at the
moment you click the button, and not to any other tab or to browsing history.

## A note for anyone testing it

Opening `popup.html` directly as a page shows "No page open". That is correct
behaviour, not a bug: `activeTab` deliberately withholds the URL until the user
invokes the extension from the toolbar, so there is no tab to read when the
popup is opened any other way.
