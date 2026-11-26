"""Rebuild public garden credits and bookshelf from GitHub issues and one guestbook."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.request import build_opener, HTTPRedirectHandler, Request


START = "<!-- community:start -->"
END = "<!-- community:end -->"
FEED = "Feed the profile puppies"
VISIT = "Record a feed & play visit"
BOOK = "Suggest a book for the bookshelf"
EXTRA = "Request an extra meal for the profile puppies"
EXTRA_CONFIRMATION = re.compile(r"Confirm extra meal #([1-9][0-9]{0,14})")
EXTRA_CONSENT = "- [x] List my GitHub username for this extra meal once the owner verifies it."
FEED_CONSENT = "- [x] Credit my GitHub username on the public feeding leaderboard if this meal is accepted."
VISIT_CONSENT = "- [x] List my GitHub username on the garden leaderboard for this visit."
YARD_CONSENT = "- [x] Credit my GitHub username for this visit to [Pip’s yard](https://github.com/Kaustubhdalvi#pips-yard)."
BOOK_CONSENT = "- [x] List my suggestion and GitHub username on the public profile."
MEDALS = {1: " 🥇", 2: " 🥈", 3: " 🥉"}
COOLDOWN = timedelta(hours=12)
CARE_WORDS = ("pet", "cuddle", "treat", "play", "comfort", "boop")
# Replay each comment under the vocabulary posted in the guestbook at that time.
CARE_WORDS_SINCE = datetime(2026, 11, 26, 7, 52, tzinfo=timezone.utc)
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}")
ISSUE_QUERY = """
query CommunityIssues($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    owner { __typename id }
    issues(first: 100, after: $after, states: [OPEN, CLOSED],
           orderBy: {field: CREATED_AT, direction: ASC}) {
      nodes {
        number title body createdAt
        author { __typename login ... on User { id } }
        transfers: timelineItems(first: 1, itemTypes: [TRANSFERRED_EVENT]) { totalCount }
        timelineItems(first: 1, itemTypes: [RENAMED_TITLE_EVENT]) {
          nodes { ... on RenamedTitleEvent { previousTitle } }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


DISCUSSION_QUERY = """
query GardenGuestbook($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      number createdAt
      comments(first: 100, after: $after) {
        nodes {
          id databaseId body createdAt lastEditedAt deletedAt isMinimized
          author { __typename login ... on User { id } }
          replyTo { id }
          discussion { number }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def github_repository(query, variables, token):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "User-Agent": "github-profile-garden"},
    )
    with build_opener(NoRedirect()).open(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        raise ValueError("GitHub could not read the complete community history.")
    return result["data"]["repository"]


def load_github_page(variables, token):
    repository = github_repository(ISSUE_QUERY, variables, token)
    owner = repository["owner"]
    page = repository["issues"]
    for issue in page["nodes"]:
        issue["repositoryOwnerId"] = owner["id"] if owner["__typename"] == "User" else None
    return page


def pages(variables, token, get_page):
    seen_cursors = set()
    while True:
        page = get_page(variables, token)
        yield page
        info = page["pageInfo"]
        if not info["hasNextPage"]:
            return
        cursor = info["endCursor"]
        if not cursor or cursor in seen_cursors:
            raise ValueError("GitHub returned an incomplete community history.")
        seen_cursors.add(cursor)
        variables["after"] = cursor


def load_issues(repository, token, get_page=load_github_page):
    owner, name = repository.split("/")
    variables = {"owner": owner, "name": name, "after": None}
    records = {}
    for page in pages(variables, token, get_page):
        for issue in page["nodes"]:
            records[issue["number"]] = issue
    return list(records.values())


def guestbook_page(variables, token):
    discussion = github_repository(DISCUSSION_QUERY, variables, token)["discussion"]
    if discussion is None or discussion["number"] != variables["number"]:
        raise ValueError("The configured guestbook discussion is unavailable.")
    return {**discussion["comments"], "createdAt": discussion["createdAt"]}


def load_guestbook(repository, number, token, get_page=guestbook_page):
    owner, name = repository.split("/")
    variables = {"owner": owner, "name": name, "number": number, "after": None}
    records = {}
    opened = None
    for page in pages(variables, token, get_page):
        if opened is not None and page["createdAt"] != opened:
            raise ValueError("The configured guestbook changed during pagination.")
        opened = page["createdAt"]
        for comment in page["nodes"]:
            if comment is not None:
                records[comment["id"]] = comment
    return {"number": number, "createdAt": opened, "comments": list(records.values())}


def guestbook_config(root):
    path = root / "garden" / "guestbook.json"
    if not path.exists():
        return None
    number = json.loads(path.read_bytes()).get("number")
    if type(number) is not int or not 0 < number <= 2147483647:
        raise ValueError("garden/guestbook.json must contain a positive GitHub discussion number.")
    return number


def utc_time(value):
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("GitHub creation time is missing its offset.")
    return when.astimezone(timezone.utc)


def submissions(issues, guestbook):
    records = []
    unique_issues = {issue["number"]: issue for issue in issues}
    for number, issue in unique_issues.items():
        records.append(((utc_time(issue["createdAt"]), 0, number, ""), issue))
    if guestbook:
        discussion_number = guestbook["number"]
        opened = utc_time(guestbook["createdAt"])
        comments = {comment["id"]: comment for comment in guestbook["comments"]}
        for node_id, comment in comments.items():
            if (comment["discussion"]["number"] != discussion_number or comment.get("replyTo") is not None
                    or comment.get("isMinimized") or comment.get("deletedAt") or comment.get("lastEditedAt")):
                continue
            when = utc_time(comment["createdAt"])
            words = CARE_WORDS if when >= CARE_WORDS_SINCE else ("feed", "fetch")
            if when < opened or (comment.get("body") or "").strip().casefold() not in words:
                continue
            database_id = comment.get("databaseId")
            # GitHub's original numeric ID orders simultaneous comments when available.
            # Null IDs sort after numbered comments, then by their immutable node ID.
            tie = database_id if type(database_id) is int else float("inf")
            records.append(((when, 1, tie, node_id), comment))
    return sorted(records, key=lambda item: item[0])


def form_field(body, label):
    # Each issue-form heading occurs once. A repeated heading is ambiguous.
    pattern = r"^### " + re.escape(label) + r"[ \t]*\n(.*?)(?=^#{1,6}[ \t]|\Z)"
    fields = re.findall(pattern, body, re.MULTILINE | re.DOTALL)
    return fields[0].strip() if len(fields) == 1 else ""


def has_consent(body, label, *checkboxes):
    return form_field(body, label).replace("- [X] ", "- [x] ", 1) in checkboxes


def book_field(body, label, limit):
    value = form_field(body, label)
    if not value or value == "_No response_" or len(value) > limit:
        return ""
    if len(value.splitlines()) != 1 or any(unicodedata.category(c).startswith("C") for c in value):
        return ""
    # Keep punctuation in the submitted title and author literal in Markdown.
    return "".join(c if c.isalnum() or c == " " else "&#{};".format(ord(c)) for c in value)


def credited_user(login):
    return "[@{}](https://github.com/{})".format(login, login)


def record_meal(events, kind, request, number, when, choice, comment=None):
    if events is None:
        return
    visitor = {"Cap": "cap", "Braids": "braids"}.get(choice, "cap" if number % 2 == 0 else "braids")
    event = {"id": "{}-{}".format(kind, request), "kind": kind, "issue_number": number,
             "issued_at": when.isoformat().replace("+00:00", "Z"), "visitor": visitor}
    if comment:
        event.update(id="discussion-" + comment["id"], comment_id=comment["id"], discussion_number=number,
                     login=comment["author"]["login"])
    events.append(event)


def build_community(issues, repository, extra_meals=False, events=None, guestbook=None, *, yard_caption=None):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+", repository):
        raise ValueError("Expected a GitHub owner/repository name.")
    free = Counter()
    extras = Counter()
    extra_requests = {}
    logins = {}
    first_meal = {}
    books = []
    last = None
    cutoff = utc_time(guestbook["createdAt"]) if guestbook else None
    for order, record in submissions(issues, guestbook):
        when, is_comment, _, _ = order
        user = record.get("author") or {}
        if user.get("__typename") != "User" or not user.get("id") or not NAME.fullmatch(user.get("login") or ""):
            continue
        user_id = user["id"]
        logins[user_id] = user["login"]
        body = (record.get("body") or "").replace("\r\n", "\n")
        if is_comment:
            number = guestbook["number"]
            original = None
            is_free = True
            choice = "Braids" if body.strip().casefold() == "fetch" else "Cap"
        else:
            if record["transfers"]["totalCount"]:
                continue
            number = record["number"]
            renames = record["timelineItems"]["nodes"]
            original = renames[0]["previousTitle"] if renames else record["title"]
            is_free = original in (FEED, VISIT)
            if is_free and (cutoff is not None and when >= cutoff
                            or not has_consent(body, "Feeding credit", FEED_CONSENT, VISIT_CONSENT, YARD_CONSENT)):
                continue
            choice = form_field(body, "Yard visitor") if is_free or original == EXTRA else ""

        # Preserve previously approved extra meals when the old request form is retired.
        count_extras = extra_meals or (cutoff is not None and when < cutoff)
        if is_free:
            if last and when < last[0] + COOLDOWN:
                continue
            free[user_id] += 1
            first_meal.setdefault(user_id, order)
            last = (when, number, user_id)
            record_meal(events, "free", number, number, when, choice, record if is_comment else None)
        elif count_extras and original == EXTRA:
            if has_consent(body, "Extra meal credit", EXTRA_CONSENT):
                extra_requests[number] = (user_id, choice)
        elif count_extras and user_id == record.get("repositoryOwnerId"):
            confirmation = EXTRA_CONFIRMATION.fullmatch(original)
            if confirmation:
                # The referenced request must already exist and belong to the visitor.
                # Consuming its number makes repeat confirmations idempotent.
                request_number = int(confirmation.group(1))
                claim = extra_requests.pop(request_number, None)
                if claim:
                    recipient, choice = claim
                    record_meal(events, "extra", request_number, number, when, choice)
                    extras[recipient] += 1
                    first_meal.setdefault(recipient, order)
        if original == BOOK:
            if not has_consent(body, "Bookshelf credit", BOOK_CONSENT):
                continue
            title = book_field(body, "Book title", 120)
            if title:
                books.append((number, user_id, title, book_field(body, "Book author", 90)))

    issue_url = "https://github.com/{}/issues/".format(repository)
    book_form = "https://github.com/{}/issues/new?template=book.yml".format(repository)
    heading = "Readers’ picks" if len(books) > 1 else "Reader’s pick"
    lines = [START, "", f"**{heading}**<br>"]
    for number, person, title, author in reversed(books[-3:]):
        byline = f" by {author}" if author else ""
        lines.append(f"*[{title}]({issue_url}{number})*{byline}, picked by {credited_user(logins[person])}<br>")
    lines.append(f"[Leave a recommendation ↗]({book_form})")

    totals = free + extras
    ranked = sorted(totals, key=lambda user: (-totals[user], first_meal[user]))
    if yard_caption is not None:
        if ranked:
            entries = (f"{credited_user(logins[user])} · {totals[user]}" for user in ranked)
            yard_caption.append("*" + " &#92; ".join(entries) + "*")
    else:
        visits = sum(totals.values())
        noun = "visit" if visits == 1 else "visits"
        summary = f"Garden leaderboard · {visits} recorded {noun}"
        lines.extend(["", f"<details><summary>{summary}</summary>", ""])
        if ranked:
            lines.extend(["Free leaderboard entries are at least 12 hours apart.", ""])
            if extras:
                lines.extend(["| Rank | Garden visitor | Free | Extra | Meals |", "| ---: | :--- | ---: | ---: | ---: |"])
            else:
                lines.extend(["| Rank | Garden visitor | Meals |", "| ---: | :--- | ---: |"])
            for rank, person in enumerate(ranked, start=1):
                cells = [str(rank) + MEDALS.get(rank, ""), credited_user(logins[person])]
                if extras:
                    cells.extend([str(free[person]), str(extras[person])])
                cells.append(str(totals[person]))
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.append("The first credited visit will appear here.")
        lines.extend(["", "</details>"])
    lines.extend(["", END])
    next_free_at = (last[0] + COOLDOWN).isoformat().replace("+00:00", "Z") if last else None
    return "\n".join(lines), next_free_at


def render(issues, repository, extra_meals=False, events=None, guestbook=None):
    """Return the profile Markdown for callers that only render the community section."""
    block, _ = build_community(issues, repository, extra_meals, events, guestbook)
    return block


def replace_block(readme, block, start=START, finish=END):
    starts = list(re.finditer(r"(?m)^" + re.escape(start) + r"\r?$", readme))
    ends = list(re.finditer(r"(?m)^" + re.escape(finish) + r"\r?$", readme))
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise ValueError(f"README.md needs one ordered pair of markers: {start} and {finish}.")
    newline = "\r\n" if readme[starts[0].end() - 1] == "\r" else "\n"
    # Keep the original final newline and every byte outside the marker block.
    end = ends[0].end() - (1 if readme[ends[0].end() - 1] == "\r" else 0)
    return readme[:starts[0].start()] + block.replace("\n", newline) + readme[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="read issue nodes or an object with issues and guestbook offline")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "Kaustubhdalvi/Kaustubhdalvi"))
    parser.add_argument("--check", action="store_true", help="exit 1 if the README needs updating")
    parser.add_argument("--garden", action="store_true", help="also reconcile the visitor scene and event files")
    parser.add_argument("--installed-at", help="UTC timestamp when the garden was added to the default branch")
    args = parser.parse_args()
    if args.garden and not args.installed_at:
        parser.error("--garden requires --installed-at from the first ledger commit")
    root = args.readme.parent
    guestbook_number = guestbook_config(root)
    guestbook = None
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        if isinstance(fixture, list):
            issues = fixture
        else:
            issues = fixture["issues"]
            guestbook = fixture.get("guestbook")
            if guestbook and guestbook["number"] != guestbook_number:
                raise ValueError("Fixture discussion must match garden/guestbook.json.")
    else:
        token = os.environ["GH_TOKEN"]
        issues = load_issues(args.repository, token)
        if guestbook_number:
            guestbook = load_guestbook(args.repository, guestbook_number, token)
    from garden import VISITORS_START, VISITORS_END
    before = args.readme.read_bytes()
    yard_caption = [] if args.garden or VISITORS_START.encode() in before else None
    # The optional issue form is installed on the trusted default branch at activation.
    active_form = args.readme.parent / ".github" / "ISSUE_TEMPLATE" / "extra-meal.yml"
    events = [] if args.garden else None
    block, next_free_at = build_community(issues, args.repository, extra_meals=active_form.is_file(), events=events,
                                          guestbook=guestbook, yard_caption=yard_caption)
    updated_readme = replace_block(before.decode("utf-8"), block)
    files = {}
    if args.garden:
        from garden import reconcile_files
        updated_readme, files = reconcile_files(args.readme.parent, updated_readme, issues, events,
                                                args.repository, args.installed_at, next_free_at,
                                                guestbook_number=guestbook_number, care_words=CARE_WORDS)
    if yard_caption is not None:
        caption = "\n".join([VISITORS_START, "", *yard_caption, "", VISITORS_END])
        updated_readme = replace_block(updated_readme, caption, VISITORS_START, VISITORS_END)
    files[args.readme] = updated_readme.encode("utf-8")
    changed = {path: data for path, data in files.items() if not path.is_file() or path.read_bytes() != data}
    if changed and args.check:
        print("Profile needs updating.", file=sys.stderr)
        return 1
    for path, data in changed.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
