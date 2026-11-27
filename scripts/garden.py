"""Render the profile yard and preserve its opt-in visit records."""

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sys

VISITORS_START = "<!-- visitors:start -->"
VISITORS_END = "<!-- visitors:end -->"
DURATION = 60
PUBLIC_STATE = Path("garden/last-feeding.json")
LEDGER = Path(".github/garden-ledger.json")
YARD_ALT = ("Two puppies play in the grass by their doghouse. A visitor arrives with a bowl, "
            "plays fetch, and waves goodbye.")


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Garden times must include their UTC offset.")
    return parsed.astimezone(timezone.utc)


def utc_string(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def free_visit_svg(next_free_at, now):
    opens = instant(next_free_at) if next_free_at else None
    if opens and opens > now:
        india = opens.astimezone(timezone(timedelta(hours=5, minutes=30)))
        heading = "Next free visit"
        status = india.strftime("%d %b %Y at %I:%M:%S %p IST")
    else:
        heading = "Free visit"
        status = "The puppies are ready for a visit 🐾"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="318" height="64" viewBox="0 0 318 64" role="img" aria-labelledby="title">
  <title id="title">{heading}. {status}</title>
  <rect x=".5" y=".5" width="317" height="63" rx="8" fill="#f1f7f2" stroke="#a6bfad"/>
  <g font-family="system-ui, sans-serif">
    <text x="14" y="23" fill="#365442" font-size="13">{heading}</text>
    <text x="14" y="47" fill="#192f23" font-size="16" font-weight="600">{status}</text>
  </g>
</svg>
""".encode("utf-8")


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


def yard_picture(repository, guestbook_number, next_free_at, now, care_words):
    owner, name = repository.split("/")
    pages = f"https://{owner.lower()}.github.io/{name}"
    base = "https://raw.githubusercontent.com/{}/main/assets/".format(repository)
    section = [
        "<!-- yard:start -->", "<p><picture>",
        '  <source type="image/svg+xml" media="(prefers-reduced-motion: no-preference)" srcset="{}pip-guest-yard-hd.svg?v=234e95f">'.format(base),
        '  <source media="(prefers-reduced-motion: no-preference)" srcset="{}pip-guest-yard.gif?v=234e95f">'.format(base),
        '  <img src="{}pip-guest-yard-hd-still.png?v=234e95f" width="100%" alt="{}">'.format(base, YARD_ALT),
        "</picture></p>", "", VISITORS_START, VISITORS_END, "", "<p>",
        '  <a name="science-puzzles"></a><a name="puzzle-notebook"></a><a name="which-run-would-you-ship"></a><a name="puzzles"></a>',
    ]
    if guestbook_number is not None:
        if type(guestbook_number) is not int or guestbook_number < 1:
            raise ValueError("The guestbook discussion number must be a positive integer.")
        guestbook = f"https://github.com/{repository}/discussions/{guestbook_number}"
        biscuits = f"{pages}/feed-and-play.html#methods"
        section.extend([
            f'  <a href="{guestbook}"><img src="{base}action-sit.svg" alt="Sit with the pups 🐾"></a>',
            f'  <a href="{biscuits}"><img src="{base}action-biscuit.svg" alt="Buy the pups a biscuit 🦴"></a>',
        ])
    section.extend([
        f'  <a href="{pages}/puzzles.html"><img src="{base}action-notebook.svg" alt="Can you crack it?"></a>',
        "</p>", "", "<!-- yard:end -->",
    ])
    return "\n".join(section)


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
                    *, care_words, guestbook_number=None):
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
    picture = yard_picture(repository, guestbook_number, next_free_at, now, care_words)
    files = {path: (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
             for path, value in [(public_path, public), (ledger_path, ledger)]}
    if guestbook_number is not None:
        files[root / "garden/free-visit.svg"] = free_visit_svg(next_free_at, now)
    return replace_yard(readme, picture), files


if __name__ == "__main__":
    # The workflow waits only for a currently published visit.
    if sys.argv[1:] != ["--remaining"]:
        sys.exit("usage: python3 scripts/garden.py --remaining")
    state = json.loads(PUBLIC_STATE.read_bytes())
    print(seconds_remaining(state["event"], datetime.now(timezone.utc)))
