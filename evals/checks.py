"""Checks that score a model reply. Each check returns (passed, reason).

A case lists its checks as dicts, for example:
    {"type": "contains_any", "values": ["Canberra"]}
"""
import re


def _lower(text):
    return text.lower()


def contains_all(reply, values):
    missing = [v for v in values if _lower(v) not in _lower(reply)]
    return (not missing, f"missing {missing}" if missing else "ok")


def contains_any(reply, values):
    hit = any(_lower(v) in _lower(reply) for v in values)
    return (hit, "ok" if hit else f"none of {values} found")


def not_contains(reply, values):
    found = [v for v in values if _lower(v) in _lower(reply)]
    return (not found, f"should not contain {found}" if found else "ok")


def regex(reply, pattern):
    hit = re.search(pattern, reply, re.IGNORECASE | re.MULTILINE) is not None
    return (hit, "ok" if hit else f"no match for /{pattern}/")


def max_words(reply, limit):
    count = len(reply.split())
    return (count <= limit, "ok" if count <= limit else f"{count} words, limit {limit}")


CHECKS = {
    "contains_all": lambda reply, c: contains_all(reply, c["values"]),
    "contains_any": lambda reply, c: contains_any(reply, c["values"]),
    "not_contains": lambda reply, c: not_contains(reply, c["values"]),
    "regex": lambda reply, c: regex(reply, c["pattern"]),
    "max_words": lambda reply, c: max_words(reply, c["limit"]),
}


def run_check(reply, check):
    kind = check.get("type")
    if kind not in CHECKS:
        raise ValueError(f"Unknown check type: {kind!r}")
    return CHECKS[kind](reply, check)
