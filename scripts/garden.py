"""Render the profile yard and preserve its opt-in visit records."""

from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import quote

DURATION = 60
PUBLIC_STATE = Path("garden/last-feeding.json")
LEDGER = Path(".github/garden-ledger.json")
GUEST_SIGN = Path("assets/yard-guest-sign.svg")
YARD_ALT = ("Two puppies play in the grass by their doghouse. A visitor arrives with a bowl, "
            "plays fetch, and waves goodbye.")


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Garden times must include their UTC offset.")
    return parsed.astimezone(timezone.utc)


def utc_string(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds_remaining(event, now):
    if not event:
        return 0
    age = (now - instant(event["started_at"])).total_seconds()
    return max(0, math.ceil(DURATION - age)) if age >= 0 else 0


def reconcile(issues, accepted, public, ledger, now, installed_at):
    cutoff = instant(installed_at)

    # Keep post-install issue numbers, including rejections. Edits or withdrawals
    # cannot promote an already scanned issue into a new visit.
    observed = set(ledger["observed"])
    valid = {e["id"]: e["issue_number"] for e in accepted}
    pending = [e for e in ledger["pending"] if valid.get(e["id"]) == e["issue_number"]]
    consumed_extras = set(ledger["extra_requests"])
    for event in accepted:
        number = event["issue_number"]
        new_extra = event["kind"] != "extra" or event["id"] not in consumed_extras
        if new_extra and number not in observed and cutoff <= instant(event["issued_at"]) <= now:
            pending.append(event.copy())
        # An extra request can receive multiple confirmation issues, even long after its first.
        if event["kind"] == "extra" and cutoff <= instant(event["issued_at"]) <= now:
            consumed_extras.add(event["id"])
    for issue in issues:
        created = instant(issue["createdAt"])
        if cutoff <= created <= now:
            observed.add(issue["number"])

    event = public["event"]
    if not seconds_remaining(event, now) and pending:
        event = dict(pending.pop(0), started_at=utc_string(now), duration_seconds=DURATION)
    # Retain the last event after expiry. Its fixed start makes browser refreshes read-only.
    return ({"version": 1, "event": event},
            {"observed": sorted(observed), "extra_requests": sorted(consumed_extras), "pending": pending})


def guest_sign(login):
    label = "@" + login if login else "Be the first guest"
    alt = "Garden sign for " + label if login else "Garden sign awaiting its first guest."
    # Center the sign under the doghouse door (x=406 in the 576px-wide scene).
    # Managed enterprise handles can be longer than personal GitHub usernames.
    display = label if len(label) <= 40 else label[:23] + "…" + label[-14:]
    size = 15 if len(display) < 26 else 12
    width = max(132, round(len(display) * size * .63) + 24)
    left = 406 - width // 2
    right = left + width
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 46" width="576" height="46" role="img" aria-labelledby="title">
  <title id="title">{escape(alt)}</title>
  <g shape-rendering="crispEdges">
    <path fill="#739462" d="M379 40h6v2h-6zm6-3h2v3h-2zm38 3h7v2h-7zm7-3h2v3h-2z"/>
    <path fill="#9cab75" d="M393 41h6v2h-6zm31 2h11v2h-11z"/>
    <path fill="#8e6a47" d="M398 0h4v40h-4zm14 0h4v40h-4z"/>
    <rect x="{left}" y="3" width="{width}" height="33" rx="2" fill="#72543b"/>
    <rect x="{left + 2}" y="5" width="{width - 4}" height="28" rx="1" fill="#edd8a7"/>
    <path fill="#92704d" d="M{left + 5} 16h2v2h-2zm{width - 14} 0h2v2h-2z"/>
    <path fill="#9d805d" d="M{right - 18} 30h10v1h-10z"/>
  </g>
  <g font-family="ui-monospace, SFMono-Regular, Consolas, monospace" text-anchor="middle" fill="#42392b">
    <text x="406" y="14" font-size="8" letter-spacing="1.1">LATEST GUEST</text>
    <text x="406" y="29" font-size="{size}" font-weight="600">{escape(display)}</text>
  </g>
</svg>
"""
    return alt, svg


def yard_picture(repository, guestbook_number, next_free_at, latest_login, now):
    base = "https://raw.githubusercontent.com/{}/main/assets/".format(repository)
    sign_alt, svg = guest_sign(latest_login)
    sign = GUEST_SIGN.name + "?guest=" + quote(latest_login or "", safe="")
    section = [
        "<!-- yard:start -->", "<p><picture>",
        '  <source media="(prefers-reduced-motion: no-preference)" srcset="{}pip-guest-yard.gif">'.format(base),
        '  <img src="{}pip-ball-yard-still.png" width="576" height="84" alt="{}">'.format(base, YARD_ALT),
        '</picture><br><img src="{}{}" width="576" height="46" alt="{}"></p>'.format(base, sign, escape(sign_alt, quote=True)),
    ]
    if guestbook_number is not None:
        if type(guestbook_number) is not int or guestbook_number < 1:
            raise ValueError("The guestbook discussion number must be a positive integer.")
        url = "https://github.com/{}/discussions/{}".format(repository, guestbook_number)
        line = "[Sign the guestbook]({}) · Post `feed` or `fetch` as a top-level comment. ".format(url)
        if next_free_at and instant(next_free_at) > now:
            opens = utc_string(instant(next_free_at)).replace("T", " ").replace("Z", " UTC")
            owner, name = repository.split("/")
            options = "https://{}.github.io/{}/feed-and-play.html#methods".format(owner.lower(), name)
            line += "The next free visit opens at {}. [Extra visit options]({})".format(opens, options)
        else:
            line += "One free visit every 12 hours. The bowl is ready."
        section.extend(["", line])
    section.extend(["", "<!-- yard:end -->"])
    return "\n".join(section), svg


def replace_yard(readme, picture):
    start, end = "<!-- yard:start -->", "<!-- yard:end -->"
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise ValueError("README needs one yard marker pair.")
    pattern = r"(?ms)^" + re.escape(start) + r"\r?$.*?^" + re.escape(end) + r"(?=\r?$)"
    if "\r\n" in readme:
        picture = picture.replace("\n", "\r\n")
    result, count = re.subn(pattern, lambda _: picture, readme)
    if count != 1:
        raise ValueError("Yard markers must be in order on their own lines.")
    return result


def reconcile_files(root, readme, issues, events, repository, installed_at, next_free_at,
                    guestbook_number=None, latest_login=None):
    now = datetime.now(timezone.utc)
    public_path, ledger_path = root / PUBLIC_STATE, root / LEDGER
    previous = json.loads(public_path.read_bytes())
    ledger = json.loads(ledger_path.read_bytes())
    # A discussion's number is shared by all its comments. Keep those records
    # out of the historical ledger, which deduplicates GitHub issue numbers.
    issue_events = [event for event in events if "comment_id" not in event]
    public, ledger = reconcile(issues, issue_events, previous, ledger, now, installed_at)
    if guestbook_number is not None:
        recent = [event for event in events if instant(installed_at) <= instant(event["issued_at"]) <= now]
        latest = recent[-1] if recent else None
        current = previous["event"]
        if latest and current and latest["id"] == current["id"]:
            public["event"] = current
        elif latest:
            # Readers of the original state endpoint can still identify a visit.
            # Its time and ID are stable across workflow retries and comment edits.
            record = {key: value for key, value in latest.items() if key != "login"}
            public["event"] = dict(record, started_at=latest["issued_at"], duration_seconds=DURATION)
        elif current and "comment_id" in current:
            public["event"] = None
    public["next_free_at"] = next_free_at
    picture, sign = yard_picture(repository, guestbook_number, next_free_at, latest_login, now)
    files = {path: (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
             for path, value in [(public_path, public), (ledger_path, ledger)]}
    files[root / GUEST_SIGN] = sign.encode("utf-8")
    return replace_yard(readme, picture), files


if __name__ == "__main__":
    # The workflow waits only for a currently published visit.
    if sys.argv[1:] != ["--remaining"]:
        sys.exit("usage: python3 scripts/garden.py --remaining")
    state = json.loads(PUBLIC_STATE.read_bytes())
    print(seconds_remaining(state["event"], datetime.now(timezone.utc)))
