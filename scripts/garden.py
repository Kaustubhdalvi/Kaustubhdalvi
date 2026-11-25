"""Persist one 60-second yard visit per newly accepted feeding."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

DURATION = 60
PUBLIC_STATE = Path("garden/last-feeding.json")
LEDGER = Path(".github/garden-ledger.json")
VISIT_VIDEO = "https://github.com/user-attachments/assets/7e79b9cf-6f3f-4ce1-b587-f981b0a55db6"


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


def yard_player(repository, next_free_at, now):
    if next_free_at and now < instant(next_free_at):
        owner, name = repository.split("/")
        deadline = instant(next_free_at).isoformat(sep=" ").replace("+00:00", " UTC")
        query = urlencode({"visit": 1, "free_at": next_free_at})
        options = "https://{}.github.io/{}/feed-and-play.html?{}#methods".format(owner.lower(), name, query)
        credit = "Next free leaderboard credit · {} · [Extra visit options]({})".format(deadline, options)
    else:
        form = "https://github.com/{}/issues/new?template=feed.yml".format(repository)
        credit = "[Record a leaderboard visit on GitHub]({}) · Free now · every 12h".format(form)
    # A standalone uploaded-video URL is rendered by GitHub as an inline player.
    return "\n\n".join(["<!-- yard:start -->", "Feed & Play · 1 min", VISIT_VIDEO, credit, "<!-- yard:end -->"])


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


def reconcile_files(root, readme, issues, events, repository, installed_at, next_free_at):
    now = datetime.now(timezone.utc)
    public_path, ledger_path = root / PUBLIC_STATE, root / LEDGER
    previous = json.loads(public_path.read_bytes())
    ledger = json.loads(ledger_path.read_bytes())
    public, ledger = reconcile(issues, events, previous, ledger, now, installed_at)
    # The scoring clock covers the full issue history, including meals before scene installation.
    public["next_free_at"] = next_free_at
    player = yard_player(repository, next_free_at, now)
    files = {path: (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
             for path, value in [(public_path, public), (ledger_path, ledger)]}
    return replace_yard(readme, player), files


if __name__ == "__main__":
    # Playback is local to each viewer. Wait only when a queued event must be published.
    if sys.argv[1:] != ["--remaining"]:
        sys.exit("usage: python3 scripts/garden.py --remaining")
    ledger = json.loads(LEDGER.read_bytes())
    if ledger["pending"]:
        state = json.loads(PUBLIC_STATE.read_bytes())
        # Keep the workflow running if the previous event expired during a push.
        print(max(1, seconds_remaining(state["event"], datetime.now(timezone.utc))))
    else:
        print(0)
