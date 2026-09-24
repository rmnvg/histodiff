"""Property tests for invariants shared across diff algorithms and formats."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Hashable, Sequence
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from histodiff import (
    DiffOp,
    from_json,
    histogram_diff,
    ignore_all_space,
    ignore_space_change,
    myers_diff,
    patience_diff,
    side_by_side,
    to_json,
    unified_diff,
)
from histodiff._core import build_ops, intern_items
from histodiff.format import _display_width, _stat_summary

ALGORITHMS = [myers_diff, patience_diff, histogram_diff]
ITEMS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-5, max_value=5),
    st.text(alphabet="abc ", max_size=5),
)
SEQUENCES = st.lists(ITEMS, max_size=25)
LINES = st.lists(
    st.text(alphabet="abc \t", max_size=8),
    max_size=25,
)


def assert_valid_ops(
    a: Sequence[Any],
    b: Sequence[Any],
    ops: list[DiffOp[Any]],
    key: Callable[[Any], Hashable] | None = None,
) -> None:
    """Assert that canonical ops tile ``a`` and ``b`` and rebuild ``b``."""
    a_next = b_next = 0
    rebuilt: list[Any] = []
    previous_tag: str | None = None
    compare = key or (lambda item: item)
    for op in ops:
        assert (op.a_start, op.b_start) == (a_next, b_next)
        assert list(op.a_lines) == list(a[op.a_start : op.a_end])
        assert list(op.b_lines) == list(b[op.b_start : op.b_end])
        a_size = op.a_end - op.a_start
        b_size = op.b_end - op.b_start
        if op.tag == "equal":
            assert a_size == b_size > 0
            assert [compare(item) for item in op.a_lines] == [
                compare(item) for item in op.b_lines
            ]
        elif op.tag == "delete":
            assert a_size > 0 and b_size == 0
        elif op.tag == "insert":
            assert a_size == 0 and b_size > 0
        else:
            assert op.tag == "replace"
            assert a_size > 0 and b_size > 0
        if previous_tag is not None:
            assert (previous_tag == "equal") != (op.tag == "equal")
        rebuilt.extend(op.b_lines)
        a_next, b_next = op.a_end, op.b_end
        previous_tag = op.tag
    assert (a_next, b_next) == (len(a), len(b))
    assert rebuilt == list(b)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@settings(max_examples=200, deadline=None)
@given(a=SEQUENCES, b=SEQUENCES)
def test_algorithms_always_produce_valid_canonical_ops(algorithm, a, b) -> None:
    assert_valid_ops(a, b, algorithm(a, b))


def lcs_length(a: Sequence[Any], b: Sequence[Any]) -> int:
    previous = [0] * (len(b) + 1)
    for left in a:
        current = [0]
        for index, right in enumerate(b, 1):
            if left == right:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


@settings(max_examples=300, deadline=None)
@given(
    a=st.lists(st.integers(min_value=0, max_value=4), max_size=14),
    b=st.lists(st.integers(min_value=0, max_value=4), max_size=14),
)
def test_minimal_myers_matches_the_lcs_oracle(a, b) -> None:
    ops = myers_diff(a, b, minimal=True)
    changed = sum(
        (op.a_end - op.a_start) + (op.b_end - op.b_start)
        for op in ops
        if op.tag != "equal"
    )
    assert changed == len(a) + len(b) - 2 * lcs_length(a, b)


@st.composite
def insertion_cases(draw) -> tuple[list[str], list[str], list[tuple[int, int]]]:
    alphabet = st.sampled_from(["", " ", "x", "y", "    body", "return 0"])
    original = draw(st.lists(alphabet, max_size=30))
    position = draw(st.integers(min_value=0, max_value=len(original)))
    inserted = draw(st.lists(alphabet, min_size=1, max_size=10))
    changed = original[:position] + inserted + original[position:]
    matches = [
        (index, index if index < position else index + len(inserted))
        for index in range(len(original))
    ]
    return original, changed, matches


@settings(max_examples=500, deadline=None)
@given(case=insertion_cases())
def test_slider_preserves_ambiguous_insertions_and_deletions(case) -> None:
    old, new, matches = case
    old_ids, new_ids = intern_items(old, new)
    inserted = build_ops(old, new, matches, old_ids, new_ids)
    assert_valid_ops(old, new, inserted)

    reverse_matches = [(new_index, old_index) for old_index, new_index in matches]
    deleted = build_ops(new, old, reverse_matches, new_ids, old_ids)
    assert_valid_ops(new, old, deleted)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("key", [ignore_space_change, ignore_all_space])
@settings(max_examples=100, deadline=None)
@given(a=LINES, b=LINES)
def test_keyed_diffs_preserve_raw_items_and_compare_normalized_keys(
    algorithm, key, a, b
) -> None:
    assert_valid_ops(a, b, algorithm(a, b, key=key), key)


@settings(max_examples=200, deadline=None)
@given(a=SEQUENCES, b=SEQUENCES)
def test_json_round_trip_preserves_arbitrary_json_scalars(a, b) -> None:
    ops = histogram_diff(a, b)
    assert from_json(to_json(ops)) == ops


JSON_VALUES = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=20),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=15,
)
META_OBJECTS = st.one_of(
    JSON_VALUES,
    st.fixed_dictionaries({"length": JSON_VALUES}, optional={"path": JSON_VALUES}),
)
OP_OBJECTS = st.dictionaries(
    st.sampled_from(
        [
            "tag",
            "a_start",
            "a_end",
            "b_start",
            "b_end",
            "a_lines",
            "b_lines",
            "ignored",
        ]
    ),
    JSON_VALUES,
    max_size=8,
)
HISTODIFF_DOCUMENTS = st.fixed_dictionaries(
    {
        "version": st.just(1),
        "old": META_OBJECTS,
        "new": META_OBJECTS,
        "ops": st.one_of(JSON_VALUES, st.lists(OP_OBJECTS, max_size=5)),
    },
    optional={
        "algorithm": JSON_VALUES,
        "moves": st.one_of(JSON_VALUES, st.lists(OP_OBJECTS, max_size=5)),
        "ignore_blank_lines": JSON_VALUES,
        "has_changes": JSON_VALUES,
    },
)


@settings(max_examples=300, deadline=None)
@given(document=HISTODIFF_DOCUMENTS)
def test_json_parser_never_leaks_internal_exceptions(document) -> None:
    try:
        ops = from_json(json.dumps(document))
    except ValueError:
        return
    assert isinstance(ops, list)
    assert all(isinstance(op, DiffOp) for op in ops)


@settings(max_examples=200, deadline=None)
@given(text=st.text())
def test_whitespace_keys_are_idempotent(text) -> None:
    assert ignore_all_space(ignore_all_space(text)) == ignore_all_space(text)
    assert ignore_space_change(ignore_space_change(text)) == ignore_space_change(text)


@settings(max_examples=200, deadline=None)
@given(
    left=st.text(alphabet="abc界e\u0301\t", max_size=30),
    right=st.text(alphabet="abc界e\u0301\t", max_size=30),
    width=st.integers(min_value=5, max_value=80),
)
def test_side_by_side_never_exceeds_requested_terminal_width(
    left, right, width
) -> None:
    for line in side_by_side(
        [DiffOp("replace", 0, 1, 0, 1, (left,), (right,))], width=width, lineterm=""
    ):
        assert _display_width(line) <= width


# Blank and whitespace-only lines exercise -B's hunk-level filtering.
STAT_LINES = st.lists(st.sampled_from(["x\n", "y\n", "z\n", "\n", " \n"]), max_size=25)


@settings(max_examples=300, deadline=None)
@given(
    a=STAT_LINES,
    b=STAT_LINES,
    ignore_blank_lines=st.booleans(),
    context=st.integers(min_value=0, max_value=4),
)
def test_stat_counts_match_unified_diff_lines(
    a, b, ignore_blank_lines, context
) -> None:
    ops = histogram_diff(a, b)
    summary = _stat_summary(
        ops, "a", "b", ignore_blank_lines=ignore_blank_lines, context=context
    )
    patch = list(
        unified_diff(
            ops,
            context,
            fromfile="a",
            tofile="b",
            ignore_blank_lines=ignore_blank_lines,
        )
    )
    body = [line for line in patch[2:] if not line.startswith("@@")]

    def reported(noun: str) -> int:
        match = re.search(rf"(\d+) {noun}s?\(", summary)
        return int(match[1]) if match else 0

    assert reported("insertion") == sum(line.startswith("+") for line in body)
    assert reported("deletion") == sum(line.startswith("-") for line in body)
