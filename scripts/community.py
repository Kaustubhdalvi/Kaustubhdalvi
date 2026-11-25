"""Rebuild the profile's public garden credits and bookshelf from GitHub issues."""

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
BOOK_CONSENT = "- [x] List my suggestion and GitHub username on the public profile."
MEDALS = {1: " 🥇", 2: " 🥈", 3: " 🥉"}
COOLDOWN = timedelta(hours=12)
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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def load_github_page(variables, token):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": ISSUE_QUERY, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "User-Agent": "github-profile-garden"},
    )
    with build_opener(NoRedirect()).open(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        raise ValueError("GitHub could not read the full issue history.")
    repository = result["data"]["repository"]
    owner = repository["owner"]
    page = repository["issues"]
    for issue in page["nodes"]:
        issue["repositoryOwnerId"] = owner["id"] if owner["__typename"] == "User" else None
    return page


def load_issues(repository, token, get_page=load_github_page):
    owner, name = repository.split("/")
    variables = {"owner": owner, "name": name, "after": None}
    seen_cursors = set()
    records = {}
    while True:
        page = get_page(variables, token)
        for issue in page["nodes"]:
            records[issue["number"]] = issue
        info = page["pageInfo"]
        if not info["hasNextPage"]:
            return list(records.values())
        cursor = info["endCursor"]
        if not cursor or cursor in seen_cursors:
            raise ValueError("GitHub returned an incomplete issue history.")
        seen_cursors.add(cursor)
        variables["after"] = cursor


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
    # Markdown inside inline HTML can still be parsed by GitHub. Numeric entities
    # keep all punctuation literal, including links, images, mentions and tags.
    escaped = "".join(c if c.isalnum() or c == " " else "&#{};".format(ord(c)) for c in value)
    return "<code>" + escaped + "</code>"


def credited_user(login):
    return "[@{}](https://github.com/{})".format(login, login)


def record_meal(events, kind, request, number, when, choice):
    if events is None:
        return
    visitor = {"Cap": "cap", "Braids": "braids"}.get(choice, "cap" if number % 2 == 0 else "braids")
    events.append({"id": "{}-{}".format(kind, request), "kind": kind, "issue_number": number,
                   "issued_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "visitor": visitor})


def render(issues, repository, extra_meals=False, events=None):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+", repository):
        raise ValueError("Expected a GitHub owner/repository name.")
    free = Counter()
    extras = Counter()
    extra_requests = {}
    logins = {}
    first_meal = {}
    books = []
    last = None
    # All timestamps are generated by GitHub. Lower issue numbers break ties
    # when two submissions arrive during the same UTC second.
    def creation_key(issue):
        when = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError("GitHub issue creation time is missing its offset.")
        return when.astimezone(timezone.utc), issue["number"]

    for issue in sorted(issues, key=creation_key):
        user = issue.get("author") or {}
        if user.get("__typename") != "User" or not user.get("id") or not NAME.fullmatch(user["login"]):
            continue
        user_id = user["id"]
        logins[user_id] = user["login"]
        renames = issue["timelineItems"]["nodes"]
        original = renames[0]["previousTitle"] if renames else issue["title"]
        when, number = creation_key(issue)
        body = (issue.get("body") or "").replace("\r\n", "\n")
        if issue["transfers"]["totalCount"]:
            # Imported issues retain an older creation date from another repository.
            continue
        if original in (FEED, VISIT):
            if not has_consent(body, "Feeding credit", FEED_CONSENT, VISIT_CONSENT):
                continue
            if last and when < last[0] + COOLDOWN:
                continue
            free[user_id] += 1
            first_meal.setdefault(user_id, (when, number))
            last = (when, number, user_id)
            record_meal(events, "free", number, number, when, form_field(body, "Yard visitor"))
        elif extra_meals and original == EXTRA:
            if has_consent(body, "Extra meal credit", EXTRA_CONSENT):
                extra_requests[number] = (user_id, form_field(body, "Yard visitor"))
        elif extra_meals and user_id == issue.get("repositoryOwnerId"):
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
                    first_meal.setdefault(recipient, (when, number))
        if original == BOOK:
            if not has_consent(body, "Bookshelf credit", BOOK_CONSENT):
                continue
            title = book_field(body, "Book title", 120)
            if title:
                books.append((number, user_id, title, book_field(body, "Book author", 90)))

    issue_url = "https://github.com/{}/issues/".format(repository)
    book_form = "https://github.com/{}/issues/new?template=book.yml".format(repository)
    book_chip = "https://raw.githubusercontent.com/{}/main/assets/action-book.svg".format(repository)
    lines = [START, "", "**Bookshelf** · [![Suggest a book]({})]({})".format(book_chip, book_form)]
    if books:
        lines.append("")
        for number, person, title, author in reversed(books[-3:]):
            work = title + (" by " + author if author else "")
            lines.append("- {} · {} · [suggestion #{}]({}{})".format(
                work, credited_user(logins[person]), number, issue_url, number))

    totals = free + extras
    visits = sum(totals.values())
    noun = "visit" if visits == 1 else "visits"
    lines.extend(["", "<details><summary>Garden leaderboard · {} recorded {}</summary>".format(visits, noun), ""])
    if totals:
        lines.extend(["These visitors chose public credit through a GitHub issue. "
                      "Free leaderboard entries are at least 12 hours apart.", ""])
        if extras:
            lines.extend(["| Rank | Garden visitor | Free | Extra | Meals |", "| ---: | :--- | ---: | ---: | ---: |"])
        else:
            lines.extend(["| Rank | Garden visitor | Meals |", "| ---: | :--- | ---: |"])
        ranked = sorted(totals, key=lambda user: (-totals[user], first_meal[user]))
        for rank, person in enumerate(ranked, start=1):
            cells = [str(rank) + MEDALS.get(rank, ""), credited_user(logins[person])]
            if extras:
                cells.extend([str(free[person]), str(extras[person])])
            cells.append(str(totals[person]))
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("The first recorded visit will appear here. Playing on the profile is anonymous.")
    lines.extend(["", "</details>", "", END])
    return "\n".join(lines)


def replace_block(readme, block):
    starts = list(re.finditer(r"(?m)^" + re.escape(START) + r"\r?$", readme))
    ends = list(re.finditer(r"(?m)^" + re.escape(END) + r"\r?$", readme))
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise ValueError("README.md needs one ordered pair of community markers.")
    newline = "\r\n" if readme[starts[0].end() - 1] == "\r" else "\n"
    # Keep the original final newline and every byte outside the marker block.
    end = ends[0].end() - (1 if readme[ends[0].end() - 1] == "\r" else 0)
    return readme[:starts[0].start()] + block.replace("\n", newline) + readme[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="read a JSON array of issue nodes offline")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "Kaustubhdalvi/Kaustubhdalvi"))
    parser.add_argument("--check", action="store_true", help="exit 1 if the README needs updating")
    parser.add_argument("--garden", action="store_true", help="also reconcile the visitor scene and event files")
    parser.add_argument("--installed-at", help="UTC timestamp when the garden was added to the default branch")
    args = parser.parse_args()
    if args.garden and not args.installed_at:
        parser.error("--garden requires --installed-at from the first ledger commit")
    if args.fixture:
        issues = json.loads(args.fixture.read_text(encoding="utf-8"))
    else:
        issues = load_issues(args.repository, os.environ["GH_TOKEN"])
    before = args.readme.read_bytes()
    # The optional issue form is installed on the trusted default branch at activation.
    active_form = args.readme.parent / ".github" / "ISSUE_TEMPLATE" / "extra-meal.yml"
    events = [] if args.garden else None
    block = render(issues, args.repository, extra_meals=active_form.is_file(), events=events)
    updated_readme = replace_block(before.decode("utf-8"), block)
    files = {}
    if args.garden:
        from garden import reconcile_files
        updated_readme, files = reconcile_files(args.readme.parent, updated_readme, issues, events,
                                                args.repository, args.installed_at)
    files[args.readme] = updated_readme.encode("utf-8")
    changed = {path: data for path, data in files.items() if path.read_bytes() != data}
    if changed and args.check:
        print("Profile needs updating.", file=sys.stderr)
        return 1
    for path, data in changed.items():
        path.write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
