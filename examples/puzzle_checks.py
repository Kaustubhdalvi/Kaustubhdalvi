#!/usr/bin/env python3
"""Exact arithmetic for three short profile puzzles. Run with Python 3."""
from fractions import Fraction


def transit_minutes():
    """Use radius units in which period squared equals radius cubed."""
    inner_period, outer_period = 8, 27
    inner_radius, outer_radius = 4, 9
    assert inner_period ** 2 == inner_radius ** 3
    assert outer_period ** 2 == outer_radius ** 3
    # The common 2*pi factor in both circular speeds cancels.
    speed_ratio = Fraction(inner_radius, inner_period) / Fraction(outer_radius, outer_period)
    return 64 * speed_ratio


def bell_distribution(phase_sign):
    """Apply H tensor H to (|00> + phase_sign * |11>) / sqrt(2)."""
    outcomes = {}
    for left in (0, 1):
        for right in (0, 1):
            # The 00 column of H tensor H contributes +1/2 to every outcome.
            # The 11 column has sign (-1) ** (left + right); square to measure.
            numerator = 1 + phase_sign * (-1) ** (left + right)
            outcomes[left, right] = Fraction(numerator ** 2, 8)
    assert sum(outcomes.values()) == 1
    return outcomes


def bell_match_chance():
    clean, flipped = bell_distribution(1), bell_distribution(-1)
    mixed = {bits: (3 * clean[bits] + flipped[bits]) / 4 for bits in clean}
    for index in (0, 1):
        assert sum(p for bits, p in mixed.items() if bits[index] == 0) == Fraction(1, 2)
    return mixed[0, 0] + mixed[1, 1]


def coin_race_chance():
    """Verify the first-step equations exactly for every unfinished prefix."""
    values = {"": Fraction(2, 3), "H": Fraction(2, 3), "HH": Fraction(1), "HT": Fraction(1, 3)}
    winners = {"HHT": Fraction(1), "HTH": Fraction(0)}
    for prefix, answer in values.items():
        branches = []
        for flip in "HT":
            history = prefix + flip
            if history in winners:
                branches.append(winners[history])
            else:
                suffix = max((s for s in values if history.endswith(s)), key=len)
                branches.append(values[suffix])
        assert sum(branches) / 2 == answer, prefix
    # An HHT block forces the race to end, so these equations have a unique solution.
    return values[""]


if __name__ == "__main__":
    answers = transit_minutes(), bell_match_chance(), coin_race_chance()
    assert answers == (96, Fraction(3, 4), Fraction(2, 3))
    print("Outer planet transit:", answers[0], "minutes")
    print("Bell pair gives matching bits:", answers[1])
    print("HHT appears before HTH:", answers[2])
