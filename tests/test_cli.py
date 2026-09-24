from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from histodiff.cli import GREEN, NO_NEWLINE, RED, RESET, main, render, split_lines
from samples import FROBNITZ_NEW, FROBNITZ_OLD


def write(path: Path, lines: list[str], trailing_newline: bool = True) -> str:
    # Bytes, so Windows doesn't turn "\n" into "\r\n" behind our back.
    text = "\n".join(lines) + ("\n" if trailing_newline else "")
    path.write_bytes(text.encode("utf-8"))
    return str(path)


@pytest.fixture
def files(tmp_path: Path) -> tuple[str, str]:
    old = write(tmp_path / "old.c", FROBNITZ_OLD)
    new = write(tmp_path / "new.c", FROBNITZ_NEW)
    return old, new


def test_prints_unified_diff_and_exits_1(files, capsys) -> None:
    old, new = files
    assert main([old, new]) == 1
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith(f"--- {old}\t")
    assert lines[1].startswith(f"+++ {new}\t")
    # With 3 lines of context, every change merges into one hunk.
    assert "@@ -1,26 +1,25 @@" in lines
    assert "+int fib(int n)" in lines
    assert "-int fact(int n)" in lines


def test_identical_files_exit_0(tmp_path, capsys) -> None:
    a = write(tmp_path / "a", ["same"])
    b = write(tmp_path / "b", ["same"])
    assert main([a, b]) == 0
    assert capsys.readouterr().out == ""


def test_missing_file_exits_2(tmp_path, capsys) -> None:
    a = write(tmp_path / "a", ["x"])
    assert main([a, str(tmp_path / "nope")]) == 2
    assert "nope" in capsys.readouterr().err


@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
def test_algorithm_flag(files, capsys, algorithm) -> None:
    old, new = files
    assert main([old, new, "--algorithm", algorithm, "-U", "0"]) == 1
    out = capsys.readouterr().out.splitlines()
    changed = [
        line for line in out if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    hunks = [line for line in out if line.startswith("@@")]
    # All three change 21 lines here, but Myers interleaves fact() and fib()
    # across 9 hunks while patience/histogram keep each function whole.
    assert len(changed) == 21
    assert len(hunks) == (9 if algorithm == "myers" else 4)


def test_bad_algorithm_is_a_usage_error(files) -> None:
    with pytest.raises(SystemExit) as exc:
        main([*files, "--algorithm", "lcs"])
    assert exc.value.code == 2


def test_color(files, capsys) -> None:
    assert main([*files, "--color"]) == 1
    out = capsys.readouterr().out
    assert f"{GREEN}+int fib(int n){RESET}\n" in out
    assert f"{RED}-int fact(int n){RESET}\n" in out


def test_no_color_by_default(files, capsys) -> None:
    main(list(files))
    assert "\x1b[" not in capsys.readouterr().out


def test_context_flag(files, capsys) -> None:
    assert main([*files, "-U", "0"]) == 1
    out = capsys.readouterr().out
    assert " #include <stdio.h>" not in out
    with pytest.raises(SystemExit):
        main([*files, "-U", "-1"])


def test_missing_trailing_newline_marker(tmp_path, capsys) -> None:
    a = write(tmp_path / "a", ["x", "y"])
    b = write(tmp_path / "b", ["x", "y"], trailing_newline=False)
    assert main([a, b]) == 1
    out = capsys.readouterr().out
    assert out.endswith(f"-y\n+y\n{NO_NEWLINE}")


def test_preserves_crlf(tmp_path, capsys) -> None:
    (tmp_path / "a").write_bytes(b"one\r\ntwo\r\n")
    (tmp_path / "b").write_bytes(b"one\r\n2\r\n")
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == 1
    assert capsys.readouterr().out.endswith(" one\r\n-two\r\n+2\r\n")


def test_stdin(tmp_path, monkeypatch, capsys) -> None:
    import io

    a = write(tmp_path / "a", ["x"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    assert main([a, "-"]) == 1
    assert capsys.readouterr().out.endswith("-x\n+y\n")


def test_stdin_cannot_be_both_inputs(monkeypatch, capsys) -> None:
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("content that must not be read\n"))
    assert main(["-", "-"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "standard input may only be specified once" in captured.err


def test_split_lines() -> None:
    assert split_lines("") == []
    assert split_lines("a\nb") == ["a\n", "b"]
    assert split_lines("a\n\n") == ["a\n", "\n"]
    assert split_lines("page\x0cbreak\n") == ["page\x0cbreak\n"]


def test_python_dash_m(files) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "histodiff", *files],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "+int fib(int n)" in result.stdout


def test_width_must_be_positive(files) -> None:
    with pytest.raises(SystemExit) as exc:
        main([*files, "-y", "-W", "0"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit):
        main([*files, "--side-by-side", "--width", "-1"])


def test_render_survives_a_malformed_hunk_header() -> None:
    # render() is also called directly with hand-built lines (as the other
    # test modules do); a header that doesn't match the usual "@@ -a,b +c,d
    # @@" shape must still be colored and passed through, with the line
    # counters left wherever they were.
    lines = [
        "--- a\n",
        "+++ b\n",
        "@@ not a real hunk header @@\n",
        " context\n",
    ]
    out = "".join(render(lines, "color"))
    assert "not a real hunk header" in out
    assert " context\n" in out


def test_broken_pipe_while_writing_is_handled(
    files, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    calls = []

    class FakeStdout:
        def write(self, chunk: str) -> int:
            raise BrokenPipeError

        def fileno(self) -> int:
            return 99

        def flush(self) -> None:
            pass

    monkeypatch.setattr(sys, "stdout", FakeStdout())
    monkeypatch.setattr(os, "open", lambda *a, **k: calls.append(("open", a, k)) or 3)
    monkeypatch.setattr(os, "dup2", lambda *a, **k: calls.append(("dup2", a, k)))

    # main() must swallow the BrokenPipeError rather than raise it, and it
    # still reports the real (non-error) exit status for the comparison.
    assert main(list(files)) == 1
    assert ("open", (os.devnull, os.O_WRONLY), {}) in calls
    assert any(name == "dup2" for name, _, _ in calls)


@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
@pytest.mark.parametrize("flag", ["-i", "--ignore-case"])
def test_ignore_case_unicode(tmp_path, capsys, algorithm, flag) -> None:
    a = write(tmp_path / "a", ["Straße", "Σ"])
    b = write(tmp_path / "b", ["STRASSE", "ς"])
    assert main([a, b, flag, "--algorithm", algorithm]) == 0
    assert capsys.readouterr().out == ""
    assert main([a, b]) == 1


@pytest.mark.parametrize("flags", [["-b"], ["-w"], ["-b", "-w"]])
def test_ignore_case_composes_with_whitespace(tmp_path, capsys, flags) -> None:
    a = write(tmp_path / "a", ["Hello   WORLD  "])
    b = write(tmp_path / "b", ["hello world"])
    assert main([a, b, "-i", *flags]) == 0
    assert capsys.readouterr().out == ""


def test_ignore_case_json_preserves_original_lines_and_matches_moves(
    tmp_path, capsys
) -> None:
    import json

    moved = "A sufficiently long moved line"
    kept = [f"kept line {i}" for i in range(5)]
    a = write(tmp_path / "a", [moved, *kept])
    b = write(tmp_path / "b", [*kept, moved.upper()])
    assert main([a, b, "-i", "-B", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["has_changes"] is True
    assert len(doc["moves"]) == 1
    assert doc["moves"][0]["a_lines"] == [moved + "\n"]
    assert doc["moves"][0]["b_lines"] == [moved.upper() + "\n"]


@pytest.mark.parametrize(
    "flags", [[], ["-y"], ["--html"], ["--json"], ["--color"], ["--stat"]]
)
def test_ignore_case_keeps_real_changes(tmp_path, capsys, flags) -> None:
    a = write(tmp_path / "a", ["UNCHANGED", "before"])
    b = write(tmp_path / "b", ["unchanged", "after"])
    assert main([a, b, "-i", *flags]) == 1
    output = capsys.readouterr().out
    if "--stat" in flags:
        assert f"{a} -> {b}: 1 insertion(+), 1 deletion(-)" in output
    else:
        assert "before" in output
        assert "after" in output


def test_cli_stat_diff(files, capsys) -> None:
    old, new = files
    assert main([old, new, "--stat"]) == 1
    out = capsys.readouterr().out
    assert out.startswith(f"{old} -> {new}: ")
    assert "insertions(+)" in out
    assert "deletions(-)" in out


def test_cli_stat_counts(tmp_path, capsys) -> None:
    old = write(tmp_path / "old.py", ["a", "b", "c"])
    new = write(tmp_path / "new.py", ["a", "b1", "b2", "b3", "c"])
    assert main([old, new, "--stat"]) == 1
    expected = f"{old} -> {new}: 3 insertions(+), 1 deletion(-)\n"
    assert capsys.readouterr().out == expected

    # Pure insertion
    add_new = write(tmp_path / "add.py", ["a", "b", "c", "d"])
    assert main([old, add_new, "--stat"]) == 1
    assert capsys.readouterr().out == f"{old} -> {add_new}: 1 insertion(+)\n"

    # Pure deletion
    del_new = write(tmp_path / "del.py", ["a", "b"])
    assert main([old, del_new, "--stat"]) == 1
    assert capsys.readouterr().out == f"{old} -> {del_new}: 1 deletion(-)\n"


def test_cli_stat_identical_exit_0(tmp_path, capsys) -> None:
    a = write(tmp_path / "a", ["same"])
    b = write(tmp_path / "b", ["same"])
    assert main([a, b, "--stat"]) == 0
    assert capsys.readouterr().out == f"{a} -> {b}: 0 insertions(+), 0 deletions(-)\n"


def test_cli_stat_ignore_blank_lines(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "", "b"])
    assert main([old, new, "-B", "--stat"]) == 0
    expected = f"{old} -> {new}: 0 insertions(+), 0 deletions(-)\n"
    assert capsys.readouterr().out == expected

    assert main([old, new, "--stat"]) == 1
    assert capsys.readouterr().out == f"{old} -> {new}: 1 insertion(+)\n"


@pytest.mark.parametrize(
    "flag", ["--color", "--color-words", "--color-moved", "--dim-moved"]
)
def test_no_color_environment(
    files,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert main([*files, flag]) == 1
    out, _ = capsys.readouterr()
    assert "\x1b[" not in out


def test_empty_no_color_environment_does_not_disable_color(
    files,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NO_COLOR", "")
    assert main([*files, "--color"]) == 1
    out, _ = capsys.readouterr()
    assert "\x1b[" in out
