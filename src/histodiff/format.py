"""Render :class:`DiffOp` lists as text: unified, side by side, and JSON."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from ._core import DiffOp
from .moves import Move
from .whitespace import is_blank

__all__ = [
    "JSON_VERSION",
    "SideBySideRow",
    "from_json",
    "side_by_side",
    "side_by_side_rows",
    "to_json",
    "unified_diff",
]

_Opcode = tuple[str, int, int, int, int]

#: ``(text, changed)`` pieces of one line, as from
#: :func:`histodiff.highlight_words`.
Segments = list[tuple[str, bool]]

#: Version of the document written by :func:`to_json`.
JSON_VERSION = 1

_TAGS = ("equal", "insert", "delete", "replace")


def _require_text(ops: Iterable[DiffOp[Any]], name: str) -> None:
    for op in ops:
        for item in op.a_lines + op.b_lines:
            if not isinstance(item, str):
                raise TypeError(
                    f"{name} renders text, but the ops contain a "
                    f"{type(item).__name__} item; diff strings, or convert "
                    "items with str() first"
                )


def _strip_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line


def _display_width(text: str) -> int:
    """Approximate the number of terminal columns occupied by ``text``."""
    width = 0
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("M") or category == "Cf":
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
    return width


def _expand_tabs(text: str, tabsize: int) -> str:
    """Expand tabs using terminal columns rather than Python character count."""
    parts: list[str] = []
    column = 0
    for char in text:
        if char == "\t":
            spaces = tabsize - column % tabsize if tabsize > 0 else 0
            parts.append(" " * spaces)
            column += spaces
        else:
            parts.append(char)
            column += _display_width(char)
    return "".join(parts)


def _truncate_width(text: str, width: int) -> tuple[str, int]:
    """Truncate text to ``width`` terminal columns and return its width."""
    parts: list[str] = []
    used = 0
    for char in text:
        char_width = _display_width(char)
        if char_width and used + char_width > width:
            break
        parts.append(char)
        used += char_width
    return "".join(parts), used


def _format_range(start: int, stop: int) -> str:
    """Convert a half-open range to unified-diff ``start,length`` (1-based)."""
    beginning = start + 1
    length = stop - start
    if length == 1:
        return str(beginning)
    if not length:
        beginning -= 1  # empty ranges point at the line before
    return f"{beginning},{length}"


def _group(codes: list[_Opcode], context: int) -> Iterator[list[_Opcode]]:
    """Split opcodes into hunks with ``context`` lines around each change.

    Same rules as :meth:`difflib.SequenceMatcher.get_grouped_opcodes`.
    """
    if not codes:
        return
    tag, i1, i2, j1, j2 = codes[0]
    if tag == "equal":
        codes[0] = (tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)
    tag, i1, i2, j1, j2 = codes[-1]
    if tag == "equal":
        codes[-1] = (tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context))

    group: list[_Opcode] = []
    for tag, i1, i2, j1, j2 in codes:
        # A long unchanged stretch ends one hunk and starts the next.
        if tag == "equal" and i2 - i1 > 2 * context:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            yield group
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        yield group


def _is_blank_group(group: list[_Opcode], a: Sequence[str], b: Sequence[str]) -> bool:
    """Whether every change in a hunk only adds or removes blank lines."""
    return all(
        tag == "equal"
        or (
            all(is_blank(line) for line in a[i1:i2])
            and all(is_blank(line) for line in b[j1:j2])
        )
        for tag, i1, i2, j1, j2 in group
    )


def _ignored_blank_opcodes(
    ops: Sequence[DiffOp[str]], context: int
) -> frozenset[_Opcode]:
    """Change opcodes hidden by ``ignore_blank_lines`` at this context size."""
    a = [line for op in ops for line in op.a_lines]
    b = [line for op in ops for line in op.b_lines]
    ignored: set[_Opcode] = set()
    for group in _group([op.as_opcode() for op in ops], context):
        if _is_blank_group(group, a, b):
            ignored.update(code for code in group if code[0] != "equal")
    return frozenset(ignored)


# --------------------------------------------------------------------------
# Unified diff
# --------------------------------------------------------------------------


def unified_diff(
    ops: Iterable[DiffOp[str]],
    context: int = 3,
    *,
    fromfile: str = "",
    tofile: str = "",
    fromfiledate: str = "",
    tofiledate: str = "",
    lineterm: str = "\n",
    ignore_blank_lines: bool = False,
) -> Iterator[str]:
    """Render diff ops in unified diff format.

    Works like :func:`difflib.unified_diff`, except it takes the ops from
    :func:`histodiff.diff` instead of the two sequences, so the output is
    byte-for-byte what difflib would print for the same alignment::

        ops = histodiff.diff(old.splitlines(True), new.splitlines(True))
        sys.stdout.writelines(histodiff.unified_diff(ops, fromfile="old"))

    As with difflib, ``lineterm`` only applies to the ``---``/``+++``/``@@``
    header lines; content lines are yielded exactly as given (so pass lines
    with their newlines, or use ``lineterm=""`` for lines without them).
    Yields nothing when there are no changes.

    Unchanged lines are printed from ``a``. That matters when the ops come
    from a ``key`` such as :func:`histodiff.ignore_space_change`, where the
    two sides of an unchanged line may differ in whitespace: like GNU diff,
    the old file's version is shown.

    :param ops: the result of :func:`histodiff.diff` or an algorithm function.
    :param context: number of unchanged lines shown around each change.
    :param ignore_blank_lines: skip hunks whose changes only add or remove
        blank (empty or whitespace-only) lines, like ``diff -B``. A hunk that
        also contains a real change is shown in full, blank lines included,
        so every hunk's line counts stay consistent.
    :raises ValueError: if ``context`` is negative.
    :raises TypeError: if the ops hold anything but strings; unified diff is
        a text format, so convert other items first (e.g. with ``str``).
    """
    if context < 0:
        raise ValueError(f"context must be >= 0, got {context}")
    ops = list(ops)
    _require_text(ops, "unified_diff")
    return _unified_diff(
        ops,
        context,
        fromfile,
        tofile,
        fromfiledate,
        tofiledate,
        lineterm,
        ignore_blank_lines,
    )


def _unified_diff(
    ops: list[DiffOp[str]],
    context: int,
    fromfile: str,
    tofile: str,
    fromfiledate: str,
    tofiledate: str,
    lineterm: str,
    ignore_blank_lines: bool,
) -> Iterator[str]:
    a = [line for op in ops for line in op.a_lines]
    b = [line for op in ops for line in op.b_lines]
    started = False
    for group in _group([op.as_opcode() for op in ops], context):
        if ignore_blank_lines and _is_blank_group(group, a, b):
            continue
        if not started:
            started = True
            fromdate = f"\t{fromfiledate}" if fromfiledate else ""
            todate = f"\t{tofiledate}" if tofiledate else ""
            yield f"--- {fromfile}{fromdate}{lineterm}"
            yield f"+++ {tofile}{todate}{lineterm}"

        first, last = group[0], group[-1]
        old_range = _format_range(first[1], last[2])
        new_range = _format_range(first[3], last[4])
        yield f"@@ -{old_range} +{new_range} @@{lineterm}"

        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in a[i1:i2]:
                    yield " " + line
                continue
            if tag in ("replace", "delete"):
                for line in a[i1:i2]:
                    yield "-" + line
            if tag in ("replace", "insert"):
                for line in b[j1:j2]:
                    yield "+" + line


# --------------------------------------------------------------------------
# Side by side
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SideBySideRow:
    """One row of a side-by-side diff.

    ``mark`` is ``" "`` for unchanged lines, ``"|"`` for a changed pair,
    ``"<"`` for a line only on the left (deleted) and ``">"`` for a line only
    on the right (inserted), as in ``diff -y``. The indices are 0-based
    positions in the old/new sequences and the texts are the original items
    (line endings included); both are ``None`` on the empty side.
    """

    mark: str
    a_index: int | None
    b_index: int | None
    left: str | None
    right: str | None


def _rows(
    tag: str,
    a_start: int,
    a_lines: Sequence[str],
    b_start: int,
    b_lines: Sequence[str],
) -> Iterator[SideBySideRow]:
    """Rows for one opcode, given its lines on each side. A replaced block
    is paired line by line; the longer side's extra lines become one-sided
    rows."""
    for k in range(max(len(a_lines), len(b_lines))):
        has_old = k < len(a_lines)
        has_new = k < len(b_lines)
        if tag == "equal":
            mark = " "
        elif has_old and has_new:
            mark = "|"
        else:
            mark = "<" if has_old else ">"
        yield SideBySideRow(
            mark,
            a_start + k if has_old else None,
            b_start + k if has_new else None,
            a_lines[k] if has_old else None,
            b_lines[k] if has_new else None,
        )


def side_by_side_rows(ops: Iterable[DiffOp[str]]) -> list[SideBySideRow]:
    """Pair up the lines of a diff for side-by-side display.

    Use this to lay out your own columns; :func:`side_by_side` renders them
    as plain text.
    """
    rows: list[SideBySideRow] = []
    for op in ops:
        rows.extend(_rows(op.tag, op.a_start, op.a_lines, op.b_start, op.b_lines))
    return rows


def side_by_side(
    ops: Iterable[DiffOp[str]],
    *,
    width: int = 130,
    suppress_common_lines: bool = False,
    tabsize: int = 8,
    lineterm: str = "\n",
    ignore_blank_lines: bool = False,
    context: int = 3,
) -> Iterator[str]:
    """Render diff ops in two columns, like ``diff -y``.

    Each column is ``(width - 3) // 2`` terminal columns wide; longer lines are
    cut off and tabs are expanded so the columns line up. The gutter between
    them holds the row's mark (see :class:`SideBySideRow`).

    :param width: total line width (``diff -W``).
    :param suppress_common_lines: leave out unchanged lines.
    :param tabsize: tab stop for expanding tabs.
    :param lineterm: appended to each output line.
    :param ignore_blank_lines: hide changes in hunks that only add or remove
        blank lines, using the same rules as :func:`unified_diff`.
    :param context: hunk context used to decide which blank changes belong to
        a hunk containing a real change.
    :raises TypeError: if the ops hold anything but strings.
    :raises ValueError: if ``width`` is less than 1 or ``context`` is negative.
    """
    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")
    if context < 0:
        raise ValueError(f"context must be >= 0, got {context}")
    ops = list(ops)
    _require_text(ops, "side_by_side")
    ignored = (
        _ignored_blank_opcodes(ops, context) if ignore_blank_lines else frozenset()
    )
    return _side_by_side(ops, width, suppress_common_lines, tabsize, lineterm, ignored)


def _side_by_side(
    ops: list[DiffOp[str]],
    width: int,
    suppress_common_lines: bool,
    tabsize: int,
    lineterm: str,
    ignored: frozenset[_Opcode],
) -> Iterator[str]:
    column = max((width - 3) // 2, 1)

    def cell(text: str | None) -> tuple[str, int]:
        if text is None:
            return "", 0
        return _truncate_width(_expand_tabs(_strip_ending(text), tabsize), column)

    for op in ops:
        if op.as_opcode() in ignored:
            continue
        for row in side_by_side_rows([op]):
            if suppress_common_lines and row.mark == " ":
                continue
            left, left_width = cell(row.left)
            right, _ = cell(row.right)
            line = f"{left}{' ' * (column - left_width)} {row.mark} {right}"
            yield line.rstrip(" ") + lineterm


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def to_json(
    ops: Iterable[DiffOp[Any]],
    *,
    fromfile: str | None = None,
    tofile: str | None = None,
    algorithm: str | None = None,
    moves: Iterable[Move] | None = None,
    include_lines: bool = True,
    indent: int | None = None,
    ignore_blank_lines: bool = False,
    context: int = 3,
) -> str:
    """Serialize diff ops (and optionally moved blocks) as JSON.

    The document looks like::

        {"version": 1, "algorithm": "histogram",
         "old": {"path": "a.py", "length": 10},
         "new": {"path": "b.py", "length": 11},
         "ops": [{"tag": "equal", "a_start": 0, "a_end": 4,
                  "b_start": 0, "b_end": 4, "a_lines": [...], "b_lines": [...]},
                 ...],
         "moves": [{"a_start": ..., "a_end": ..., "b_start": ..., "b_end": ...,
                    "a_lines": [...], "b_lines": [...]}]}

    Indices are 0-based and ranges half-open, as in :class:`DiffOp`. Items
    must be JSON-serializable; lines keep their line endings.

    :param moves: moved blocks to include under ``"moves"`` (omitted if None).
    :param include_lines: include ``a_lines``/``b_lines``; without them the
        document is smaller but :func:`from_json` can't rebuild the ops.
    :param indent: passed to :func:`json.dumps`.
    :param ignore_blank_lines: mark blank-only changes as ignored and include
        the effective ``has_changes`` value used by the CLI.
    :param context: hunk context used to classify blank-only changes.
    """
    ops = list(ops)
    if context < 0:
        raise ValueError(f"context must be >= 0, got {context}")
    if ignore_blank_lines:
        _require_text(ops, "to_json(ignore_blank_lines=True)")
        ignored = _ignored_blank_opcodes(ops, context)
    else:
        ignored = frozenset()
    entries = []
    for op in ops:
        entry: dict[str, Any] = {
            "tag": op.tag,
            "a_start": op.a_start,
            "a_end": op.a_end,
            "b_start": op.b_start,
            "b_end": op.b_end,
        }
        if include_lines:
            entry["a_lines"] = list(op.a_lines)
            entry["b_lines"] = list(op.b_lines)
        if op.as_opcode() in ignored:
            entry["ignored"] = True
        entries.append(entry)

    doc: dict[str, Any] = {
        "version": JSON_VERSION,
        "algorithm": algorithm,
        "old": {"path": fromfile, "length": sum(op.a_end - op.a_start for op in ops)},
        "new": {"path": tofile, "length": sum(op.b_end - op.b_start for op in ops)},
        "ops": entries,
    }
    if moves is not None:
        move_entries = []
        for move in moves:
            move_entry: dict[str, Any] = {
                "a_start": move.a_start,
                "a_end": move.a_end,
                "b_start": move.b_start,
                "b_end": move.b_end,
            }
            if include_lines:
                move_entry["a_lines"] = list(move.a_lines)
                move_entry["b_lines"] = list(move.b_lines)
            move_entries.append(move_entry)
        doc["moves"] = move_entries
    if ignore_blank_lines:
        doc["ignore_blank_lines"] = True
        doc["has_changes"] = any(
            op.tag != "equal" and op.as_opcode() not in ignored for op in ops
        )
    return json.dumps(doc, indent=indent, ensure_ascii=False)


def from_json(data: str | bytes) -> list[DiffOp[Any]]:
    """Rebuild :class:`DiffOp` objects from :func:`to_json` output.

    Unknown fields are ignored so versioned documents can gain optional fields
    without breaking existing readers.

    :raises ValueError: if the document isn't structurally valid histodiff JSON
        of a supported version, its operations do not tile the declared input
        ranges, or it was written without lines.
    """
    doc = json.loads(data)
    if (
        not isinstance(doc, dict)
        or type(doc.get("version")) is not int
        or doc["version"] != JSON_VERSION
    ):
        raise ValueError(f"not histodiff JSON (expected version {JSON_VERSION})")
    entries = doc.get("ops")
    if not isinstance(entries, list):
        raise ValueError("histodiff JSON field 'ops' must be a list")
    old = doc.get("old")
    new = doc.get("new")
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("histodiff JSON must contain 'old' and 'new' objects")
    if old.get("path") is not None and not isinstance(old["path"], str):
        raise ValueError("histodiff JSON field 'old.path' must be a string or null")
    if new.get("path") is not None and not isinstance(new["path"], str):
        raise ValueError("histodiff JSON field 'new.path' must be a string or null")
    if doc.get("algorithm") is not None and not isinstance(doc["algorithm"], str):
        raise ValueError("histodiff JSON field 'algorithm' must be a string or null")
    for name in ("ignore_blank_lines", "has_changes"):
        if name in doc and not isinstance(doc[name], bool):
            raise ValueError(f"histodiff JSON field {name!r} must be boolean")

    def integer(value: Any, name: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"histodiff JSON field {name!r} must be a non-negative integer"
            )
        return value

    old_length = integer(old.get("length"), "old.length")
    new_length = integer(new.get("length"), "new.length")
    ops: list[DiffOp[Any]] = []
    a_next = b_next = 0
    previous_tag: str | None = None
    for number, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"histodiff JSON op {number} must be an object")
        if "ignored" in entry and not isinstance(entry["ignored"], bool):
            raise ValueError(
                f"histodiff JSON op {number} field 'ignored' must be boolean"
            )
        if entry.get("tag") not in _TAGS:
            raise ValueError(f"unknown op tag {entry.get('tag')!r}")
        if "a_lines" not in entry or "b_lines" not in entry:
            raise ValueError(
                "the JSON has no lines (written with include_lines=False), "
                "so the ops can't be rebuilt"
            )
        a_lines = entry["a_lines"]
        b_lines = entry["b_lines"]
        if not isinstance(a_lines, list) or not isinstance(b_lines, list):
            raise ValueError(f"histodiff JSON op {number} lines must be lists")
        a_start = integer(entry.get("a_start"), f"ops[{number}].a_start")
        a_end = integer(entry.get("a_end"), f"ops[{number}].a_end")
        b_start = integer(entry.get("b_start"), f"ops[{number}].b_start")
        b_end = integer(entry.get("b_end"), f"ops[{number}].b_end")
        if (a_start, b_start) != (a_next, b_next):
            raise ValueError(
                f"histodiff JSON op {number} does not continue the sequences"
            )
        if a_end < a_start or b_end < b_start:
            raise ValueError(f"histodiff JSON op {number} has a reversed range")
        a_size, b_size = a_end - a_start, b_end - b_start
        if len(a_lines) != a_size or len(b_lines) != b_size:
            raise ValueError(f"histodiff JSON op {number} range and line counts differ")
        tag = entry["tag"]
        if previous_tag is not None and (previous_tag == "equal") == (tag == "equal"):
            raise ValueError(
                f"histodiff JSON op {number} is not in canonical alternating order"
            )
        valid_shape = {
            "equal": a_size == b_size and a_size > 0,
            "delete": a_size > 0 and b_size == 0,
            "insert": a_size == 0 and b_size > 0,
            "replace": a_size > 0 and b_size > 0,
        }[tag]
        if not valid_shape:
            raise ValueError(
                f"histodiff JSON op {number} has a range invalid for {tag!r}"
            )
        ops.append(
            DiffOp(
                tag,
                a_start,
                a_end,
                b_start,
                b_end,
                tuple(a_lines),
                tuple(b_lines),
            )
        )
        a_next, b_next = a_end, b_end
        previous_tag = tag
    if (a_next, b_next) != (old_length, new_length):
        raise ValueError(
            "histodiff JSON ops do not cover the declared sequence lengths"
        )

    move_entries = doc.get("moves", [])
    if not isinstance(move_entries, list):
        raise ValueError("histodiff JSON field 'moves' must be a list")
    old_moved: set[int] = set()
    new_moved: set[int] = set()
    for number, entry in enumerate(move_entries):
        if not isinstance(entry, dict):
            raise ValueError(f"histodiff JSON move {number} must be an object")
        a_start = integer(entry.get("a_start"), f"moves[{number}].a_start")
        a_end = integer(entry.get("a_end"), f"moves[{number}].a_end")
        b_start = integer(entry.get("b_start"), f"moves[{number}].b_start")
        b_end = integer(entry.get("b_end"), f"moves[{number}].b_end")
        size = a_end - a_start
        if size <= 0 or b_end - b_start != size:
            raise ValueError(f"histodiff JSON move {number} has invalid ranges")
        if a_end > old_length or b_end > new_length:
            raise ValueError(f"histodiff JSON move {number} lies outside the inputs")
        a_range = set(range(a_start, a_end))
        b_range = set(range(b_start, b_end))
        if old_moved.intersection(a_range) or new_moved.intersection(b_range):
            raise ValueError(f"histodiff JSON move {number} overlaps another move")
        old_moved.update(a_range)
        new_moved.update(b_range)
        has_a_lines = "a_lines" in entry
        has_b_lines = "b_lines" in entry
        if has_a_lines != has_b_lines:
            raise ValueError(f"histodiff JSON move {number} has incomplete line data")
        if has_a_lines:
            a_lines = entry["a_lines"]
            b_lines = entry["b_lines"]
            if not isinstance(a_lines, list) or not isinstance(b_lines, list):
                raise ValueError(f"histodiff JSON move {number} lines must be lists")
            if len(a_lines) != size or len(b_lines) != size:
                raise ValueError(
                    f"histodiff JSON move {number} range and line counts differ"
                )
    return ops


# --------------------------------------------------------------------------
# Stat summary
# --------------------------------------------------------------------------


def _stat_summary(
    ops: Iterable[DiffOp[Any]],
    fromfile: str,
    tofile: str,
    *,
    ignore_blank_lines: bool = False,
    context: int = 3,
) -> str:
    """Format a diffstat-style single-line summary of insertions and deletions.

    Example::

        old.py -> new.py: 3 insertions(+), 1 deletion(-)
    """
    ops = list(ops)
    if ignore_blank_lines:
        _require_text(ops, "_stat_summary(ignore_blank_lines=True)")
        ignored = _ignored_blank_opcodes(ops, context)
    else:
        ignored = frozenset()

    insertions = sum(
        len(op.b_lines)
        for op in ops
        if op.tag != "equal" and op.as_opcode() not in ignored
    )
    deletions = sum(
        len(op.a_lines)
        for op in ops
        if op.tag != "equal" and op.as_opcode() not in ignored
    )
    parts: list[str] = []
    if insertions > 0:
        parts.append(
            "1 insertion(+)" if insertions == 1 else f"{insertions} insertions(+)"
        )
    if deletions > 0:
        parts.append("1 deletion(-)" if deletions == 1 else f"{deletions} deletions(-)")
    if not parts:
        parts = ["0 insertions(+)", "0 deletions(-)"]
    return f"{fromfile} -> {tofile}: {', '.join(parts)}\n"
