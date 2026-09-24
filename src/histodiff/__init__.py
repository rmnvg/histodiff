"""Human-readable diffs for moved, repeated, or reformatted content."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Any, Callable

from ._core import DiffOp, T
from .compat import SequenceMatcher
from .format import (
    SideBySideRow,
    from_json,
    side_by_side,
    side_by_side_rows,
    to_json,
    unified_diff,
)
from .histogram import histogram_diff
from .html_format import HTML_STYLE, html_diff
from .moves import Move, find_moves
from .myers import myers_diff
from .patience import patience_diff
from .whitespace import ignore_all_space, ignore_space_change
from .words import highlight_words, inline_word_diff, split_words

__all__ = [
    "ALGORITHMS",
    "HTML_STYLE",
    "DiffOp",
    "Move",
    "SequenceMatcher",
    "SideBySideRow",
    "diff",
    "find_moves",
    "from_json",
    "highlight_words",
    "histogram_diff",
    "html_diff",
    "ignore_all_space",
    "ignore_space_change",
    "inline_word_diff",
    "myers_diff",
    "patience_diff",
    "side_by_side",
    "side_by_side_rows",
    "split_words",
    "to_json",
    "unified_diff",
]
__version__ = "0.2.0"

#: Algorithm name -> implementation, for :func:`diff` and the CLI.
ALGORITHMS: dict[str, Callable[..., list[DiffOp[Any]]]] = {
    "myers": myers_diff,
    "patience": patience_diff,
    "histogram": histogram_diff,
}


def diff(
    a: Sequence[T],
    b: Sequence[T],
    algorithm: str = "histogram",
    *,
    minimal: bool = False,
    key: Callable[[T], Hashable] | None = None,
) -> list[DiffOp[T]]:
    """Diff two sequences.

    The items are usually lines of text, but can be any hashable values:
    words, tokens, numbers, tuples, named tuples, frozen dataclasses. They
    are compared the way :class:`difflib.SequenceMatcher` compares them, by
    hash and ``==``.

    :param a: the old items.
    :param b: the new items.
    :param algorithm: ``"histogram"`` (default), ``"patience"`` or ``"myers"``.
    :param minimal: never trade diff size for speed. By default Myers (and
        the Myers fallback inside patience and histogram) caps its search on
        large, very different inputs, like ``git diff`` does; with
        ``minimal=True`` it always finds the smallest edit script, which can
        take quadratic time.
    :param key: compare ``key(item)`` instead of the items themselves, like
        the ``key`` of :func:`sorted`. Use it to diff unhashable records
        (``key=lambda row: tuple(sorted(row.items()))``) or to ignore
        differences that don't matter (``key=str.strip``,
        ``key=str.casefold``). It is called once per item. The ops still hold
        the original items, so the two sides of an ``equal`` op may differ
        in ways the key ignores.
    :returns: :class:`DiffOp` objects that together cover all of ``a`` and ``b``.
    :raises ValueError: if ``algorithm`` is not recognised.
    :raises TypeError: if an item (or its key) is unhashable.
    """
    try:
        func = ALGORITHMS[algorithm]
    except KeyError:
        choices = ", ".join(repr(name) for name in ALGORITHMS)
        raise ValueError(
            f"unknown algorithm {algorithm!r}; expected one of {choices}"
        ) from None
    return func(a, b, minimal=minimal, key=key)
