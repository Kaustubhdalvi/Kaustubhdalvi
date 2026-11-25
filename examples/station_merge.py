"""A tiny weather-feed merge challenge. Run with Python 3.8+."""
import argparse
from datetime import datetime, timezone

# Each source is in chronological order. Temperatures are integer Celsius.
FEEDS = (
    (("N", "2026-01-07T05:28+05:30", 4), ("S", "2026-01-07T05:30+05:30", 7)),
    (("NORTH", "2026-01-06T23:58Z", 4), ("NORTH", "2026-01-07T00:00Z", 5)),
)
STATIONS = {"N": "NORTH", "NORTH": "NORTH", "S": "SOUTH", "SOUTH": "SOUTH"}


def merge(feeds):
    readings = {}
    for feed in feeds:
        for label, timestamp, temperature in feed:
            instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("expected a timestamp with an offset")
            instant = instant.astimezone(timezone.utc)
            if instant.second or instant.microsecond:
                raise ValueError("expected a UTC instant on a whole minute")
            key = (instant, STATIONS[label])
            if key in readings and readings[key] != temperature:
                raise ValueError("two different readings for one station and instant")
            readings[key] = temperature
    return [
        (instant.strftime("%Y-%m-%dT%H:%MZ"), station, temperature)
        for (instant, station), temperature in sorted(readings.items())
    ]


# Literal solutions keep the answer key independent of the merge implementation.
DAY_END = "2026-01-06T23:58Z"
MIDNIGHT = "2026-01-07T00:00Z"
EXPECTED = [(DAY_END, "NORTH", 4), (MIDNIGHT, "NORTH", 5), (MIDNIGHT, "SOUTH", 7)]
RUNS = {
    "A": [(MIDNIGHT, "NORTH", 5), (MIDNIGHT, "SOUTH", 7), ("2026-01-07T23:58Z", "NORTH", 4)],
    "B": [(DAY_END, "NORTH", 4), (MIDNIGHT, "NORTH", 5), (MIDNIGHT, "SOUTH", 7)],
    "C": [(DAY_END, "NORTH", 4), (MIDNIGHT, "NORTH", 7), (MIDNIGHT, "SOUTH", 5)],
}
REASONS = {
    "A": "05:28 at +05:30 was 23:58 on January 6.",
    "B": "The two 23:58 reports collapse. Both stations survive at midnight with their own readings.",
    "C": "At midnight NORTH measured 5 °C and SOUTH measured 7 °C.",
}


def check_fixture():
    assert merge(FEEDS) == EXPECTED
    assert merge(tuple(reversed(FEEDS))) == EXPECTED
    assert merge(FEEDS + FEEDS) == EXPECTED
    assert [name for name, rows in RUNS.items() if rows == EXPECTED] == ["B"]
    assert all(len(rows) == 3 and sum(t for _, _, t in rows) == 16 for rows in RUNS.values())
    try:
        merge(FEEDS + ((("N", DAY_END, 8),),))
    except ValueError as error:
        assert "two different readings" in str(error)
    else:
        raise AssertionError("conflicting duplicate went undetected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", choices=RUNS, nargs="?", help="the run you would ship")
    args = parser.parse_args()
    check_fixture()
    for name in ([args.run] if args.run else RUNS):
        verdict = "PASS" if RUNS[name] == EXPECTED else "FAIL"
        print(f"{name}  {verdict}  {REASONS[name]}")


if __name__ == "__main__":
    main()
