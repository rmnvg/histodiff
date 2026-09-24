"""Side-by-side, HTML and JSON output."""

from __future__ import annotations

import json
from html.parser import HTMLParser

import pytest

from histodiff import (
    HTML_STYLE,
    DiffOp,
    Move,
    SideBySideRow,
    diff,
    find_moves,
    from_json,
    html_diff,
    side_by_side,
    side_by_side_rows,
    to_json,
)
from histodiff.cli import (
    BOLD,
    CYAN,
    GREEN,
    MAGENTA,
    NO_REVERSE,
    RED,
    RESET,
    REVERSE,
    main,
    render_side_by_side,
)
from histodiff.format import _stat_summary
from test_cli import write
from test_readability import python_function

# --------------------------------------------------------------------------
# Side by side
# --------------------------------------------------------------------------


def test_side_by_side_rows() -> None:
    ops = diff(["a\n", "b\n", "c\n", "x\n"], ["a\n", "B\n", "C\n", "D\n", "x\n"])
    assert side_by_side_rows(ops) == [
        SideBySideRow(" ", 0, 0, "a\n", "a\n"),
        SideBySideRow("|", 1, 1, "b\n", "B\n"),
        SideBySideRow("|", 2, 2, "c\n", "C\n"),
        SideBySideRow(">", None, 3, None, "D\n"),
        SideBySideRow(" ", 3, 4, "x\n", "x\n"),
    ]


def test_side_by_side_rows_for_deletes() -> None:
    ops = diff(["a", "gone", "b"], ["a", "b"])
    assert side_by_side_rows(ops)[1] == SideBySideRow("<", 1, None, "gone", None)


SBS_OLD = ["a", "bb", "c"]
SBS_NEW = ["a", "BB", "c", "d"]
SBS_EXPECTED = [
    "a" + " " * 11 + "a",
    "bb" + " " * 8 + "| BB",
    "c" + " " * 11 + "c",
    " " * 10 + "> d",
]


def test_side_by_side_text() -> None:
    lines = list(side_by_side(diff(SBS_OLD, SBS_NEW), width=21))
    assert [line.rstrip("\n") for line in lines] == SBS_EXPECTED
    assert all(line.endswith("\n") for line in lines)


def test_side_by_side_truncates_and_expands_tabs() -> None:
    ops = diff(["0123456789abc", "\tx"], ["0123456789abc", "\ty"])
    lines = list(side_by_side(ops, width=21, lineterm=""))
    assert lines[0] == "012345678   012345678"
    assert lines[1] == "        x | " + "        y"


def test_side_by_side_color_drops_a_segment_with_no_room_left() -> None:
    # A highlighted word right at the column boundary: once the unchanged
    # prefix exactly fills the column, the following (changed) segment has
    # zero budget left and must be dropped entirely, not shown as an empty
    # highlighted span.
    old = ["abc def"]
    new = ["abc xyz"]
    out = "".join(render_side_by_side(diff(old, new), width=11, color=True))
    assert out == f"{RED}abc {RESET} | {GREEN}abc {RESET}\n"
    assert REVERSE not in out


def test_side_by_side_truncation_treats_combining_marks_as_zero_width() -> None:
    # "café" as "cafe" + a combining acute accent (U+0301): the accent takes
    # no column of its own, so truncating right after it must not count it
    # towards, or stop it from filling, the width budget.
    combining = "café"
    lines = list(side_by_side(diff([combining], [combining]), width=13, lineterm=""))
    assert lines == [combining + "    " + combining]


def test_side_by_side_uses_terminal_width_for_unicode() -> None:
    lines = list(side_by_side(diff(["界ab"], ["界ab"]), width=13, lineterm=""))
    assert lines == ["界ab" + " " * 4 + "界ab"]

    truncated = list(side_by_side(diff(["界abc"], ["界abc"]), width=11, lineterm=""))
    assert truncated == ["界ab" + " " * 3 + "界ab"]


def test_side_by_side_suppress_common_lines() -> None:
    lines = list(
        side_by_side(
            diff(SBS_OLD, SBS_NEW), width=21, lineterm="", suppress_common_lines=True
        )
    )
    assert lines == [SBS_EXPECTED[1], SBS_EXPECTED[3]]


def test_side_by_side_requires_text() -> None:
    with pytest.raises(TypeError, match="side_by_side renders text"):
        list(side_by_side(diff([1], [2])))
    with pytest.raises(ValueError, match="width"):
        list(side_by_side(diff(["a"], ["b"]), width=0))
    with pytest.raises(ValueError, match="context"):
        list(side_by_side(diff(["a"], ["b"]), context=-1))


def test_side_by_side_preserves_crlf_and_missing_final_newline() -> None:
    old = ["one\r\n", "two\r\n", "three"]
    new = ["one\r\n", "2\r\n", "three"]
    lines = list(side_by_side(diff(old, new), width=21, lineterm=""))
    # \r\n (and a missing final newline) are stripped before column layout,
    # like a plain "\n" - never shown raw in the middle of a padded column.
    assert lines == ["one         one", "two       | 2", "three       three"]
    assert all("\r" not in line for line in lines)


def test_cli_side_by_side(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", SBS_OLD)
    new = write(tmp_path / "new", SBS_NEW)
    assert main([old, new, "-y", "-W", "21"]) == 1
    assert capsys.readouterr().out.splitlines() == SBS_EXPECTED

    assert (
        main([old, new, "--side-by-side", "--width", "21", "--suppress-common-lines"])
        == 1
    )
    assert capsys.readouterr().out.splitlines() == [SBS_EXPECTED[1], SBS_EXPECTED[3]]

    # Identical files: exit 0, but still print both columns, like diff -y.
    assert main([old, old, "-y", "-W", "21"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "a" + " " * 11 + "a",
        "bb" + " " * 10 + "bb",
        "c" + " " * 11 + "c",
    ]


def test_cli_side_by_side_color(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["result = process(event)"])
    new = write(tmp_path / "new", ["result = process_v2(event)"])
    assert main([old, new, "-y", "--color", "-W", "80"]) == 1
    out = capsys.readouterr().out
    assert out == (
        f"{RED}result = {REVERSE}process{NO_REVERSE}(event){RESET}"
        + " " * 15
        + f" | {GREEN}result = {REVERSE}process_v2{NO_REVERSE}(event){RESET}\n"
    )


def test_side_by_side_move_inside_a_replace_disables_its_highlighting() -> None:
    # When the moved block ends up merged into a "replace" op (because the
    # reinserted line sits right next to other new content, with nothing
    # equal separating them), word highlighting for that whole op is
    # skipped - moved and highlighted are mutually exclusive per op.
    long_line = "important_configuration_value_x = compute_it(alpha, beta)"
    old = [long_line, "short_a", "short_b"]
    new = [
        "short_a",
        "totally different long replacement text goes here",
        "and one more brand new line",
        long_line,
    ]
    ops = diff(old, new)
    moves = find_moves(ops)
    assert moves
    assert any(op.tag == "replace" and op.b_end == moves[0].b_end for op in ops)

    out = "".join(render_side_by_side(ops, width=100, color=True, moves=moves))
    assert f"{BOLD}{MAGENTA}{long_line[:47]}" in out
    assert f"{BOLD}{CYAN}{long_line[:47]}" in out
    # The replace's own content is plain red/green, not reverse-highlighted,
    # because highlighting was skipped for the whole (moved) op.
    assert f"{RED}short_b{RESET}" in out
    assert REVERSE not in out


def test_side_by_side_highlights_unequal_replace_next_to_a_move() -> None:
    # A *different* replace op - unequal-sized, and not touching the move -
    # in the same diff: highlighting is computed for it, exercising both
    # the pure-insert ("no old counterpart") and pure-delete row shapes
    # together with a moved block elsewhere in the same call.
    long_line = "important_configuration_value_x = compute_it(alpha, beta)"
    old = [long_line, "short_a", "value = compute(x, y)", "short_c"]
    new = [
        "short_a",
        "value = compute(x, y, z)",
        "extra_line_here",
        "short_c",
        long_line,
    ]
    ops = diff(old, new)
    moves = find_moves(ops)
    assert moves

    out = "".join(render_side_by_side(ops, width=100, color=True, moves=moves))
    assert REVERSE in out  # "x, y)" -> "x, y, z)" was highlighted
    assert f"{GREEN}{REVERSE}extra_line_here{NO_REVERSE}{RESET}" in out


def test_side_by_side_highlights_replace_where_old_side_is_longer() -> None:
    # The mirror image: more old lines than new, so a row has no new-side
    # counterpart instead - the same shape as the HTML equivalent above.
    long_line = "important_configuration_value_x = compute_it(alpha, beta)"
    old = [long_line, "short_a", "value = compute(x, y)", "extra old line", "short_c"]
    new = ["short_a", "value = compute(x, y, z)", "short_c", long_line]
    ops = diff(old, new)
    moves = find_moves(ops)
    assert moves

    out = "".join(render_side_by_side(ops, width=100, color=True, moves=moves))
    assert f"{RED}{REVERSE}extra old line{NO_REVERSE}{RESET}" in out


def test_cli_side_by_side_moves(tmp_path, capsys) -> None:
    funcs = [python_function(i) for i in range(6)]
    old = write(tmp_path / "old", sum(funcs, []))
    new = write(tmp_path / "new", sum(funcs[:1] + funcs[2:] + [funcs[1]], []))
    assert main([old, new, "-y", "--color-moved"]) == 1
    out = capsys.readouterr().out
    assert f"{BOLD}{MAGENTA}def func_1(data):{RESET}" in out
    assert " < \n" not in out  # trailing spaces are stripped


def test_side_by_side_ignores_blank_only_hunks(tmp_path, capsys) -> None:
    old_lines = ["a\n", "b\n"]
    new_lines = ["a\n", "\n", "b\n"]
    rendered = list(
        side_by_side(diff(old_lines, new_lines), width=13, ignore_blank_lines=True)
    )
    assert [line.rstrip("\n") for line in rendered] == [
        "a" + " " * 7 + "a",
        "b" + " " * 7 + "b",
    ]

    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "", "b"])
    assert main([old, new, "-B", "-y", "-W", "13"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "a" + " " * 7 + "a",
        "b" + " " * 7 + "b",
    ]


def test_cli_output_formats_are_exclusive(tmp_path) -> None:
    old = write(tmp_path / "old", ["a"])
    for flags in (
        ["-y", "--json"],
        ["--html", "--json"],
        ["-y", "--color-words"],
        ["--stat", "--json"],
        ["--stat", "-y"],
        ["--stat", "--html"],
        ["--stat", "--color-words"],
    ):
        with pytest.raises(SystemExit) as exc:
            main([old, old, *flags])
        assert exc.value.code == 2


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------


class TagBalance(HTMLParser):
    """Checks that every opened element is closed in order."""

    VOID = {"meta", "col", "br"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag) -> None:
        assert self.stack and self.stack[-1] == tag, (tag, self.stack)
        self.stack.pop()


def assert_balanced(markup: str) -> None:
    parser = TagBalance()
    parser.feed(markup)
    parser.close()
    assert parser.stack == []


def test_html_page() -> None:
    ops = diff(["a", "<b>", "c"], ["a", "<B>", "c", "d"])
    page = html_diff(ops, fromfile="old.txt", tofile="new.txt")
    assert page.startswith("<!DOCTYPE html>")
    assert "<title>old.txt → new.txt</title>" in page
    assert '<th colspan="2">old.txt</th>' in page
    assert '<tr class="hunk"><td colspan="4">@@ -1,3 +1,4 @@</td></tr>' in page
    assert (
        '<tr class="replace"><td class="num">2</td>'
        '<td class="line old">&lt;<del>b</del>&gt;</td>'
        '<td class="num">2</td><td class="line new">&lt;<ins>B</ins>&gt;</td></tr>'
    ) in page
    assert (
        '<tr class="insert"><td class="num"></td><td class="line empty"></td>'
        '<td class="num">4</td><td class="line new">d</td></tr>'
    ) in page
    assert '<tr class="equal"><td class="num">1</td><td class="line">a</td>' in page
    assert_balanced(page)


def test_html_escapes_everything() -> None:
    evil = '</td><script>alert("x")</script>'
    page = html_diff(diff(["safe"], [evil]), fromfile="<a>", tofile='"b"')
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "<title>&lt;a&gt; → &quot;b&quot;</title>" in page
    assert_balanced(page)


def test_html_context() -> None:
    old = [f"line {i}" for i in range(20)]
    new = list(old)
    new[10] = "changed"
    ops = diff(old, new)

    def numbers(markup: str) -> set[int]:
        found = set()
        for part in markup.split('<td class="num">')[1:]:
            text = part.split("<", 1)[0]
            if text:
                found.add(int(text))
        return found

    assert numbers(html_diff(ops, context=1)) == {10, 11, 12}
    assert numbers(html_diff(ops, context=None)) == set(range(1, 21))


def test_html_no_differences() -> None:
    page = html_diff(diff(["a"], ["a"]))
    assert "No differences" in page
    assert_balanced(page)
    old = ["x", "y"]
    ops = diff(old, ["x", "", "y"])
    assert "No differences" not in html_diff(ops)
    assert "No differences" in html_diff(ops, ignore_blank_lines=True)


def test_html_moves() -> None:
    funcs = [python_function(i) for i in range(6)]
    old = sum(funcs, [])
    new = sum(funcs[:1] + funcs[2:] + [funcs[1]], [])
    ops = diff(old, new)
    page = html_diff(ops, moves=find_moves(ops))
    assert '<td class="line old moved">def func_1(data):</td>' in page
    assert '<td class="line new moved">def func_1(data):</td>' in page
    assert "<del>" not in page


def test_html_fragment_and_style() -> None:
    table = html_diff(diff(["a"], ["b"]), full_page=False)
    assert table.startswith('<table class="histodiff">')
    assert "<html" not in table and "<style>" not in table
    assert ".histodiff" in HTML_STYLE and "prefers-color-scheme: dark" in HTML_STYLE
    assert_balanced(table)


def test_html_rejects_bad_input() -> None:
    with pytest.raises(TypeError, match="html_diff renders text"):
        html_diff(diff([1], [2]))
    with pytest.raises(ValueError, match="context"):
        html_diff(diff(["a"], ["b"]), context=-1)


def test_html_explicit_title_skips_the_default() -> None:
    page = html_diff(
        diff(["a"], ["b"]), fromfile="old.py", tofile="new.py", title="Custom title"
    )
    assert "<title>Custom title</title>" in page
    assert "old.py → new.py" not in page.split("</title>")[0]


def test_html_highlights_unequal_replace_around_a_move() -> None:
    # A replace where one side has an extra line, in the same diff as (but
    # not overlapping) a moved block, exercises both the "row has no
    # a_index" case and word highlighting together in one page.
    long_line = "important_configuration_value = compute_it(alpha, beta)"
    old = [long_line, "short_a", "value = compute(x, y)", "short_c"]
    new = [
        "short_a",
        "value = compute(x, y, z)",
        "extra_line_here",
        "short_c",
        long_line,
    ]
    ops = diff(old, new)
    moves = find_moves(ops)
    assert moves, "the long line should have been detected as moved"
    page = html_diff(ops, moves=moves)
    assert '<td class="line old moved">' in page
    # The insert-only row (new has more lines than old) has an empty old cell.
    assert '<td class="num"></td><td class="line empty"></td>' in page
    assert "<ins>" in page  # "x, y)" -> "x, y, z)": word-level highlighting fired
    assert_balanced(page)


def test_html_highlights_replace_where_old_side_is_longer() -> None:
    # The mirror image of the above: more old lines than new, so a row
    # exists with no *new*-side counterpart instead.
    long_line = "important_configuration_value_x = compute_it(alpha, beta)"
    old = [long_line, "short_a", "value = compute(x, y)", "extra old line", "short_c"]
    new = ["short_a", "value = compute(x, y, z)", "short_c", long_line]
    ops = diff(old, new)
    moves = find_moves(ops)
    assert moves
    page = html_diff(ops, moves=moves)
    assert '<td class="line old moved">' in page
    assert '<td class="line empty"></td></tr>' in page
    assert "<del>" in page
    assert_balanced(page)


def test_cli_html(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "c"])
    assert main([old, new, "--html"]) == 1
    page = capsys.readouterr().out
    assert page.startswith("<!DOCTYPE html>")
    assert '<td class="line new">c</td>' in page
    assert_balanced(page)

    assert main([old, old, "--html"]) == 0
    assert "No differences" in capsys.readouterr().out


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def test_json_schema() -> None:
    ops = diff(["a\n", "b\n"], ["a\n", "c\n", "d\n"])
    doc = json.loads(
        to_json(ops, fromfile="x.txt", tofile="y.txt", algorithm="histogram")
    )
    assert doc["version"] == 1
    assert doc["algorithm"] == "histogram"
    assert doc["old"] == {"path": "x.txt", "length": 2}
    assert doc["new"] == {"path": "y.txt", "length": 3}
    assert doc["ops"] == [
        {
            "tag": "equal",
            "a_start": 0,
            "a_end": 1,
            "b_start": 0,
            "b_end": 1,
            "a_lines": ["a\n"],
            "b_lines": ["a\n"],
        },
        {
            "tag": "replace",
            "a_start": 1,
            "a_end": 2,
            "b_start": 1,
            "b_end": 3,
            "a_lines": ["b\n"],
            "b_lines": ["c\n", "d\n"],
        },
    ]
    assert "moves" not in doc


def test_json_round_trip() -> None:
    ops = diff(["one", "two", "three"], ["zero", "one", "three", "four"])
    assert from_json(to_json(ops)) == ops
    assert from_json(to_json(ops, indent=2).encode()) == ops
    numbers = diff([1, 2, 3], [1, 3, 4])
    assert from_json(to_json(numbers)) == numbers


def test_from_json_ignores_unknown_optional_fields() -> None:
    ops = diff(["old"], ["new"])
    document = json.loads(to_json(ops))
    document["future"] = {"nested": [1, 2, 3]}
    document["old"]["future"] = True
    document["new"]["future"] = None
    document["ops"][0]["future"] = "value"
    assert from_json(json.dumps(document)) == ops


def test_json_without_lines() -> None:
    ops = diff(["a"], ["b"])
    doc = json.loads(to_json(ops, include_lines=False))
    assert doc["ops"] == [
        {"tag": "replace", "a_start": 0, "a_end": 1, "b_start": 0, "b_end": 1}
    ]
    with pytest.raises(ValueError, match="include_lines"):
        from_json(to_json(ops, include_lines=False))


def test_json_moves() -> None:
    long_line = "important = compute_something(alpha, beta)"
    ops = diff([long_line, "keep = 1"], ["keep = 1", long_line])
    doc = json.loads(to_json(ops, moves=find_moves(ops)))
    assert doc["moves"] == [
        {
            "a_start": 0,
            "a_end": 1,
            "b_start": 1,
            "b_end": 2,
            "a_lines": [long_line],
            "b_lines": [long_line],
        }
    ]
    doc = json.loads(
        to_json(
            ops,
            moves=[Move(0, 1, 1, 2, (long_line,), (long_line,))],
            include_lines=False,
        )
    )
    assert doc["moves"] == [{"a_start": 0, "a_end": 1, "b_start": 1, "b_end": 2}]


def test_json_keeps_unicode_readable() -> None:
    assert "café" in to_json(diff(["café"], ["cafe"]))


def test_to_json_rejects_negative_context() -> None:
    with pytest.raises(ValueError, match="context"):
        to_json(diff(["a"], ["b"]), ignore_blank_lines=True, context=-1)


def test_from_json_rejects_other_documents() -> None:
    with pytest.raises(ValueError, match="histodiff JSON"):
        from_json("[]")
    with pytest.raises(ValueError, match="histodiff JSON"):
        from_json('{"version": 2, "ops": []}')
    bad = {
        "version": 1,
        "old": {"length": 0},
        "new": {"length": 0},
        "ops": [
            {
                "tag": "shuffle",
                "a_start": 0,
                "a_end": 0,
                "b_start": 0,
                "b_end": 0,
                "a_lines": [],
                "b_lines": [],
            }
        ],
    }
    with pytest.raises(ValueError, match="tag"):
        from_json(json.dumps(bad))


@pytest.mark.parametrize(
    "document",
    [
        {"version": 1},
        {"version": True, "old": {"length": 0}, "new": {"length": 0}, "ops": []},
        {"version": 1, "old": {"length": 0}, "new": {"length": 0}, "ops": None},
        {"version": 1, "old": {"length": 0}, "new": {"length": 0}, "ops": [1]},
        {"version": 1, "ops": []},
        {
            "version": 1,
            "old": {"length": 0},
            "new": {"length": 0},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": -1,
                    "a_end": 0,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": [],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": [],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 0},
            "ops": [
                {
                    "tag": "insert",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 0,
                    "a_lines": ["x"],
                    "b_lines": [],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 2},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 1,
                    "a_end": 2,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": ["x"],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 2},
            "new": {"length": 2},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": ["x"],
                    "b_lines": ["x"],
                },
                {
                    "tag": "equal",
                    "a_start": 1,
                    "a_end": 2,
                    "b_start": 1,
                    "b_end": 2,
                    "a_lines": ["y"],
                    "b_lines": ["y"],
                },
            ],
        },
        {"version": 1, "old": {"length": 1}, "new": {"length": 0}, "ops": []},
        # 'ignored' present but not a bool.
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": ["x"],
                    "b_lines": ["x"],
                    "ignored": "yes",
                }
            ],
        },
        # a_lines is a string, not a list of lines.
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": "x",
                    "b_lines": ["x"],
                }
            ],
        },
        # a_end before a_start: a reversed range, but *after* an op that
        # legitimately continues at a_start=3 - so this hits the reversed-
        # range check itself rather than the "does not continue" one.
        {
            "version": 1,
            "old": {"length": 3},
            "new": {"length": 3},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 3,
                    "b_start": 0,
                    "b_end": 3,
                    "a_lines": ["x", "y", "z"],
                    "b_lines": ["x", "y", "z"],
                },
                {
                    "tag": "delete",
                    "a_start": 3,
                    "a_end": 1,
                    "b_start": 3,
                    "b_end": 3,
                    "a_lines": [],
                    "b_lines": [],
                },
            ],
        },
    ],
)
def test_from_json_rejects_malformed_operations(document) -> None:
    with pytest.raises(ValueError):
        from_json(json.dumps(document))


def test_from_json_rejects_malformed_moves() -> None:
    document = json.loads(to_json(diff(["old"], ["new"])))
    document["moves"] = "not a list"
    with pytest.raises(ValueError, match="moves"):
        from_json(json.dumps(document))

    document["moves"] = [{"a_start": 0, "a_end": 2, "b_start": 0, "b_end": 2}]
    with pytest.raises(ValueError, match="outside"):
        from_json(json.dumps(document))


def _document_with_two_moves(move_a: dict, move_b: dict | None = None) -> dict:
    # A 6-line file on each side gives enough room for two non-overlapping
    # moves, or for the overlap test to actually overlap.
    ops = diff([f"line{i}" for i in range(6)], [f"line{i}" for i in range(6)])
    document = json.loads(to_json(ops))
    document["moves"] = [move_a] if move_b is None else [move_a, move_b]
    return document


@pytest.mark.parametrize(
    ("move", "match"),
    [
        ("not a dict", "must be an object"),
        ({"a_start": 0, "a_end": 0, "b_start": 0, "b_end": 0}, "invalid ranges"),
        ({"a_start": 2, "a_end": 1, "b_start": 0, "b_end": 1}, "invalid ranges"),
        ({"a_start": 0, "a_end": 1, "b_start": 0, "b_end": 2}, "invalid ranges"),
        (
            {"a_start": 0, "a_end": 1, "b_start": 0, "b_end": 1, "a_lines": ["x"]},
            "incomplete line data",
        ),
        (
            {
                "a_start": 0,
                "a_end": 1,
                "b_start": 0,
                "b_end": 1,
                "a_lines": "x",
                "b_lines": ["x"],
            },
            "lines must be lists",
        ),
        (
            {
                "a_start": 0,
                "a_end": 2,
                "b_start": 0,
                "b_end": 2,
                "a_lines": ["x"],
                "b_lines": ["x", "y"],
            },
            "range and line counts differ",
        ),
    ],
)
def test_from_json_rejects_malformed_single_move(move, match) -> None:
    document = _document_with_two_moves(move)
    with pytest.raises(ValueError, match=match):
        from_json(json.dumps(document))


def test_from_json_rejects_overlapping_moves() -> None:
    document = _document_with_two_moves(
        {"a_start": 0, "a_end": 2, "b_start": 0, "b_end": 2},
        {"a_start": 1, "a_end": 3, "b_start": 3, "b_end": 5},
    )
    with pytest.raises(ValueError, match="overlaps another move"):
        from_json(json.dumps(document))


def test_from_json_accepts_moves_without_lines() -> None:
    # Moves are allowed to omit their lines independently of the ops (which
    # from_json requires lines for); it must not try to line-count-check
    # what isn't there.
    long_line = "important = compute_something(alpha, beta)"
    ops = diff([long_line, "keep = 1"], ["keep = 1", long_line])
    moves = find_moves(ops)
    assert moves
    document = json.loads(to_json(ops, moves=moves))  # ops keep their lines
    for move in document["moves"]:
        del move["a_lines"], move["b_lines"]
    assert from_json(json.dumps(document)) == ops


def test_json_marks_blank_only_hunks_as_ignored(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "", "b"])
    assert main([old, new, "-B", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["ignore_blank_lines"] is True
    assert document["has_changes"] is False
    assert [entry.get("ignored", False) for entry in document["ops"]] == [
        False,
        True,
        False,
    ]


def test_cli_json(tmp_path, capsys) -> None:
    funcs = [python_function(i) for i in range(4)]
    old = write(tmp_path / "old.py", sum(funcs, []))
    new = write(tmp_path / "new.py", sum(funcs[1:] + funcs[:1], []))
    assert main([old, new, "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["old"]["path"] == old and doc["algorithm"] == "histogram"
    assert [op["tag"] for op in doc["ops"]] == ["delete", "equal", "insert"]
    assert len(doc["moves"]) == 1
    assert doc["moves"][0]["a_lines"][0] == "def func_0(data):\n"
    rebuilt = from_json(json.dumps(doc))
    assert all(isinstance(op, DiffOp) for op in rebuilt)

    assert main([old, old, "--json"]) == 0
    assert [op["tag"] for op in json.loads(capsys.readouterr().out)["ops"]] == ["equal"]


# --------------------------------------------------------------------------
# Stat summary
# --------------------------------------------------------------------------


def test_stat_summary() -> None:
    ops = diff(["a\n", "b\n", "c\n"], ["a\n", "b2\n", "b3\n", "c\n", "d\n"])
    assert _stat_summary(ops, "old.py", "new.py") == (
        "old.py -> new.py: 3 insertions(+), 1 deletion(-)\n"
    )

    identical_ops = diff(["a\n", "b\n"], ["a\n", "b\n"])
    assert _stat_summary(identical_ops, "a.py", "b.py") == (
        "a.py -> b.py: 0 insertions(+), 0 deletions(-)\n"
    )

    pure_insert_ops = diff(["a\n"], ["a\n", "b\n"])
    assert _stat_summary(pure_insert_ops, "a", "b") == "a -> b: 1 insertion(+)\n"

    pure_delete_ops = diff(["a\n", "b\n"], ["a\n"])
    assert _stat_summary(pure_delete_ops, "a", "b") == "a -> b: 1 deletion(-)\n"


def test_stat_summary_ignore_blank_lines() -> None:
    ops = diff(["a\n", "b\n"], ["a\n", "\n", "b\n"])
    assert (
        _stat_summary(ops, "a.py", "b.py", ignore_blank_lines=True)
        == "a.py -> b.py: 0 insertions(+), 0 deletions(-)\n"
    )
    assert (
        _stat_summary(ops, "a.py", "b.py", ignore_blank_lines=False)
        == "a.py -> b.py: 1 insertion(+)\n"
    )
