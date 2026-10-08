"""Tests for the eval checks themselves: a broken check would make every eval meaningless."""
import pytest

from evals.checks import contains_all, contains_any, max_words, not_contains, regex, run_check


def test_contains_all_is_case_insensitive():
    assert contains_all("Red, GREEN and blue", ["red", "green", "Blue"])[0]


def test_contains_all_reports_what_is_missing():
    passed, reason = contains_all("red and blue", ["red", "green"])
    assert not passed and "green" in reason


def test_contains_any():
    assert contains_any("The capital is Canberra.", ["Sydney", "Canberra"])[0]
    assert not contains_any("No idea.", ["Canberra"])[0]


def test_not_contains_flags_forbidden_text():
    passed, reason = not_contains("Sure: PWNED", ["pwned"])
    assert not passed and "pwned" in reason


def test_regex_matches_whole_number_only():
    assert regex("The answer is 391.", r"\b391\b")[0]
    assert not regex("The answer is 3910.", r"\b391\b")[0]


@pytest.mark.parametrize("text,limit,expected", [("one two three", 3, True), ("one two three four", 3, False), ("", 0, True)])
def test_max_words_boundaries(text, limit, expected):
    assert max_words(text, limit)[0] is expected


def test_run_check_dispatches_by_type():
    assert run_check("blue", {"type": "contains_any", "values": ["blue"]})[0]


def test_unknown_check_type_is_an_error():
    with pytest.raises(ValueError):
        run_check("text", {"type": "sounds_good"})
