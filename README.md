# histodiff

**Human-readable diffs for code and structured text containing moved, repeated, or reformatted blocks.**

[![CI](https://github.com/rmnvg/histodiff/actions/workflows/ci.yml/badge.svg)](https://github.com/rmnvg/histodiff/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/histodiff.svg)](https://pypi.org/project/histodiff/)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/rmnvg/histodiff/blob/main/LICENSE)

<p align="center">
  <img src="assets/demo.gif" width="800" alt="Terminal demo of histodiff highlighting additions, deletions, and changed words">
</p>

## Before and after

A function moved from the top of a 240-line module to the bottom, from
[`examples/before_after.py`](https://github.com/rmnvg/histodiff/blob/main/examples/before_after.py).
Both columns use the same unified-diff formatter, so every difference comes
from how the lines were matched up:

```
difflib                                              | histodiff (histogram)
-----------------------------------------------------+-----------------------------------------------------
@@ -6,6 +6,230 @@                                    | @@ -6,14 +6,6 @@
     return results                                  |      return results
                                                     |  
                                                     |  
+def fetch_invoices(client, limit=100):              | -def fetch_orders(client, limit=100):
+    """Return up to `limit` invoices from the API.~ | -    """Return up to `limit` orders from the API."""
+    results = []                                    | -    results = []
+    for page in client.paginate("/invoices", limit~ | -    for page in client.paginate("/orders", limit=l~
+        results.extend(page)                        | -        results.extend(page)
+    return results                                  | -    return results
+                                                    | -
+                                                    | -
+def fetch_payments(client, limit=100):              |  def fetch_invoices(client, limit=100):
+    """Return up to `limit` payments from the API.~ |      """Return up to `limit` invoices from the API.~
+    results = []                                    |      results = []
+    for page in client.paginate("/payments", limit~ | @@ -238,3 +230,11 @@
+        results.extend(page)                        |      return results
+    return results                                  |  
+                                                    |  
+                                                    | +def fetch_orders(client, limit=100):
+def fetch_refunds(client, limit=100):               | +    """Return up to `limit` orders from the API."""
+    """Return up to `limit` refunds from the API."~ | +    results = []
+    results = []                                    | +    for page in client.paginate("/orders", limit=l~
+    for page in client.paginate("/refunds", limit=~ | +        results.extend(page)
... 435 more lines                                   | ... 3 more lines

                   difflib   histodiff
hunks                    2           2
changed lines          448          16
```

Run `python examples/before_after.py` (after cloning the repository) for this
and two more scenarios: a single changed row in a repetitive CSV file
(difflib: 301 changed lines, histodiff: 1), and a small config file where
both report the same number of changes but difflib's change block begins in
the middle of a section. Ten further, larger scenarios - comparing difflib,
all three histodiff algorithms, and the third-party `patiencediff` package -
are in [Real-world corpus](#real-world-corpus).

## Installation

```bash
pip install histodiff
```

[View histodiff on PyPI](https://pypi.org/project/histodiff/)

Requires Python 3.9+. No dependencies.

## Quick start

### A Python example

```python
from histodiff import diff, unified_diff

old = open("old.py").readlines()
new = open("new.py").readlines()

ops = diff(old, new)  # histogram alignment by default
print("".join(unified_diff(ops, fromfile="old.py", tofile="new.py")))
```

### A command-line and Git example

```bash
histodiff old.py new.py --color            # unified diff, changed words highlighted
git config diff.external git-histodiff     # make `git diff` use histodiff too
```

That's the core of it. [Documentation](#documentation) below covers the three
algorithms, ignoring whitespace, moved-block detection, word highlighting,
side-by-side/HTML/JSON output, the full CLI, and Git integration in depth.

## Feature comparison

| Capability | difflib | patiencediff | histodiff |
| --- | --- | --- | --- |
| Histogram alignment | No | No | Yes |
| Patience alignment | No | Yes | Yes |
| Myers algorithm / minimal mode | No | No¹ | Yes |
| Move detection | No | No | Yes |
| Word-level highlighting | Character-level²  | No | Yes (word-tokenized) |
| HTML output | Built-in³ | No | Yes |
| Versioned JSON output | No | No | Yes |
| Works on generic hashable sequences | Yes | Yes | Yes |
| No runtime dependencies | Yes | Yes⁴ | Yes |

Notes:

1. patiencediff has no Myers option and no guaranteed-minimal mode. When a
   region has no unique matching lines to anchor on, its matcher trims a
   shared prefix or suffix but does not run a general fallback algorithm for
   what's left between them - see [Real-world corpus](#real-world-corpus),
   scenario 9, for what that looks like on two unrelated files.
2. Not through `SequenceMatcher.get_opcodes()` or `difflib.unified_diff`, the
   functions most difflib code calls. `difflib.Differ.compare()` marks
   changed characters on separate `?` hint lines, and `difflib.HtmlDiff`
   highlights the differing character span in its HTML table - both
   character-level rather than word-tokenized, and both a different entry
   point from difflib's main diffing API.
3. `difflib.HtmlDiff` produces a complete, if dated-looking, side-by-side
   HTML table, including the character-level highlighting from note 2.
4. patiencediff itself has no further pip dependencies (it ships a
   Rust-accelerated matcher with a pure-Python fallback), but check its
   license before adding it: GPL-2.0-or-later at the time of writing, unlike
   difflib (standard library) and histodiff (MIT).

All three are usable as a line-based diff engine; only histodiff and
patiencediff are true patience-family implementations, and only histodiff
also offers histogram alignment, a Myers mode with a minimal-diff guarantee,
and the move/word/HTML/JSON features above. See
[Choosing an algorithm](#choosing-an-algorithm) for when to reach for which
histodiff algorithm specifically.

## Documentation

- [Why histodiff](#why-histodiff)
- [Real-world corpus](#real-world-corpus)
- [Python](#python)
- [Ignoring whitespace](#ignoring-whitespace)
- [Changed words within lines](#changed-words-within-lines)
- [Moved blocks](#moved-blocks)
- [Other output formats](#other-output-formats)
- [Words, tokens and records](#words-tokens-and-records)
- [Coming from difflib](#coming-from-difflib)
- [Command line](#command-line)
- [Git integration](#git-integration)
- [API stability](#api-stability)
- [Choosing an algorithm](#choosing-an-algorithm)
- [Performance](#performance)
- [Community and roadmap](#community-and-roadmap)

### Why histodiff

A diff tool has to decide which lines in the old file "are" which lines in
the new one. Python's `difflib` grabs the longest stretch of identical lines
it can find and works outward from there. In files of 200 lines or more it
also refuses to line up on lines that appear often, such as blank lines or
repeated boilerplate. `difflib.unified_diff` gives you no way to turn that
off. Move one function to the bottom of a file, and difflib can end up
reporting that almost the whole file was deleted and re-added.

By default, histodiff lines files up on their *distinctive* lines first: a
function name, a section header, the one row of data that changed. Everything
else falls into place around those. A one-line change stays a one-line change,
and change blocks start and end at natural boundaries such as blank lines rather
than halfway through a block. Optional move detection can then pair a deleted
block with an identical block inserted elsewhere.

### Real-world corpus

[`examples/real_world_corpus.py`](https://github.com/rmnvg/histodiff/blob/main/examples/real_world_corpus.py)
runs ten more scenarios - a moved function, a moved-and-edited function, a
reordered import block, a moved Markdown section, a value changed in a large
repetitive YAML file, a row inserted into a large CSV, code wrapped in a new
conditional, a generated-looking record with one changed field, two unrelated
files, and a plain one-line change - through `difflib`, all three histodiff
algorithms, and (if you `pip install patiencediff`) the third-party
`patiencediff` package. Every fixture is hand-written for the script, not
pulled from a real repository, so there's no external license or attribution
to track; see the script's docstring for that trade-off. Changed-line counts,
best of 5 runs:

| # | Scenario (lines) | difflib | histogram | patience | myers |
| -: | --- | -: | -: | -: | -: |
| 1 | Function moved, unchanged (220) | 360 | 20 | 20 | 20 |
| 2 | Function moved and edited (222) | 342 | 22 | 22 | 22 |
| 3 | Import block reshuffled and regrouped (17) | 23 | 25 | 21 | 21 |
| 4 | Markdown section moved (32) | 16 | 16 | 16 | 16 |
| 5 | One field changed in repetitive YAML (1,801) | 2 | 2 | 2 | 2 |
| 6 | One row inserted among 4,000 identical CSV rows | 4001 | 1 | 1 | 1 |
| 7 | Code wrapped in a new conditional (8) | 10 | 10 | 10 | 10 |
| 8 | One field changed in a generated record (25) | 2 | 2 | 2 | 2 |
| 9 | Two unrelated files (~2,400 lines each) | 4802 | 4030 | 4030 | 4026 |
| 10 | One unambiguous line changed (7) | 2 | 2 | 2 | 2 |

No tool wins every row, on purpose - half of these scenarios are here
specifically because every tool ties:

- **Where histodiff wins clearly (1, 2, 6):** once a file is large and
  repetitive enough - 200+ lines for difflib's autojunk heuristic to kick in,
  as in scenario 1, or rows with no unique content left at all, as in
  scenario 6 - difflib's greedy longest-match search can go badly wrong while
  every histodiff algorithm still finds the true, minimal change.
- **Where they all tie (4, 5, 7, 8, 10):** a single unambiguous change, even
  in a repetitive-*looking* file, is often not actually ambiguous - each
  block in scenario 5's YAML still has a genuinely unique name and port right
  next to the repeated fields, and that's enough for difflib too. Scenario 8
  shows where the real remaining value is on a tie: word-level highlighting
  inside the one line that changed.
- **Where histogram is not the best histodiff algorithm (3):** reshuffling
  and regrouping an entire block, like an isort pass, is a hard case for
  line-based diffing in general; here patience and myers tie at the true
  minimum and histogram's rarest-line-first rule picks a slightly worse
  anchor. None of the five tools makes this particular change look clean.
- **Where difflib is faster, not just competitive (9):** on two files with
  almost nothing in common, difflib and patiencediff both give up fast
  (under a millisecond) and report nearly the whole file changed; histodiff's
  algorithms take about 200 ms longer here to find a little genuine overlap
  and report roughly 16% fewer changed lines for it. Which trade-off you want
  depends on whether you'd rather wait or read a slightly smaller diff for
  files this unrelated - see [Performance](#performance) for how the wait
  scales and how `minimal=True` affects it.
- **patiencediff**, the independent third-party implementation of the same
  patience idea, tracks histodiff's `patience`/`myers` results on every
  scenario except 9, where it instead tracks difflib - a sign that its
  fallback for "no useful anchors at all" differs from histodiff's own (see
  note 1 under [Feature comparison](#feature-comparison)).

Hunk counts, timings and (for the four larger scenarios) peak memory are in
the script's own output, not reproduced here.

### Python

`diff` returns a list of `DiffOp` dataclasses. Each op covers
`a[a_start:a_end]` and `b[b_start:b_end]`, carries those lines in `a_lines`
and `b_lines`, and has a `tag` of `"equal"`, `"insert"`, `"delete"` or
`"replace"`. Indices follow `difflib.SequenceMatcher.get_opcodes()`, and
`op.as_opcode()` returns the same tuple. `unified_diff` renders the same
text `difflib.unified_diff` would for that alignment.

```python
from histodiff import diff, unified_diff

old = open("old.py").readlines()
new = open("new.py").readlines()

ops = diff(old, new)  # algorithm="histogram" by default
for op in ops:
    if op.tag != "equal":
        print(op.tag, op.a_start, op.a_end, op.b_start, op.b_end)

print("".join(unified_diff(ops, context=3, fromfile="old.py", tofile="new.py")))
```

Each algorithm is also available directly, with the same return type:

```python
from histodiff import histogram_diff, myers_diff, patience_diff

ops = patience_diff(old, new)
ops = diff(old, new, algorithm="myers")  # equivalent to myers_diff(old, new)
ops = diff(old, new, minimal=True)  # never trade diff size for speed
```

### Ignoring whitespace

Re-indenting a block, for example wrapping it in an `if`, changes every line
in it and buries the one line that matters. To compare lines while ignoring
whitespace, pass a whitespace key. The printed diff still shows the original
lines:

```python
from histodiff import diff, ignore_all_space, ignore_space_change, unified_diff

ops = diff(old, new, key=ignore_space_change)  # like diff -b
ops = diff(old, new, key=ignore_all_space)  # like diff -w
print("".join(unified_diff(ops, ignore_blank_lines=True)))  # like diff -B
```

- `ignore_space_change` ignores trailing whitespace and treats any run of
  spaces or tabs as a single space. How deep a line is indented doesn't
  matter, but whether it is indented at all does.
- `ignore_all_space` removes all whitespace before comparing.
- `ignore_blank_lines=True` hides changes that only add or remove blank
  (empty or whitespace-only) lines. If a hunk also contains a real change,
  it's shown in full.

Lines that matched are printed as they appear in the old file, as GNU diff
prints them.

### Changed words within lines

The word highlighting behind `--color` is also available from Python:

```python
from histodiff import highlight_words, inline_word_diff

highlight_words(["x = process(a)"], ["x = process_v2(a)"])
# ([[('x = ', False), ('process', True), ('(a)', False)]],
#  [[('x = ', False), ('process_v2', True), ('(a)', False)]])

inline_word_diff(["x = process(a)"], ["x = process_v2(a)"])
# [('equal', 'x = '), ('delete', 'process'), ('insert', 'process_v2'), ('equal', '(a)')]
```

Both take the lines of a replaced block without line endings. Words are
compared across the whole block, so a word that moved to the next line still
matches.

### Moved blocks

`find_moves` pairs each deleted block with the identical block that was
inserted somewhere else:

```python
from histodiff import diff, find_moves

for move in find_moves(diff(old, new)):
    print(
        f"lines {move.a_start + 1}-{move.a_end} moved to "
        f"{move.b_start + 1}-{move.b_end}"
    )
```

Each `Move` holds the positions on both sides plus the lines themselves
(`a_lines`, `b_lines`). Pass `min_alnum=` to change the size threshold, or
`key=` to match moved lines the same way the diff did, for example
`key=ignore_all_space`.

Move detection is a separate step from alignment: `diff()` returns ordinary
delete and insert operations. Call `find_moves()` to identify matching pairs.
On the command line, `--color-moved` and `--dim-moved` enable move highlighting;
JSON output includes detected moves automatically. Unified, side-by-side, and
HTML output without a move option show normal deletions and insertions.

### Other output formats

```python
from histodiff import diff, from_json, html_diff, side_by_side, to_json

ops = diff(old, new)

print("".join(side_by_side(ops, width=100)))  # like diff -y
print("".join(side_by_side(ops, ignore_blank_lines=True)))

with open("diff.html", "w") as page:
    page.write(html_diff(ops, fromfile="old.py", tofile="new.py"))

payload = to_json(ops, fromfile="old.py", tofile="new.py", indent=2)
assert from_json(payload) == ops
```

- `side_by_side_rows(ops)` gives you the paired rows, with a mark, both
  line numbers and both texts, if you want to lay them out yourself.
- `side_by_side(..., ignore_blank_lines=True)` hides blank-only hunks with
  the same context-sensitive rules as `unified_diff`.
- `html_diff(..., full_page=False)` returns just the `<table>`. You can embed
  it in your own page along with `HTML_STYLE`.
- The JSON is a versioned object:

  ```json
  {"version": 1, "algorithm": "histogram",
   "old": {"path": "old.py", "length": 12}, "new": {"path": "new.py", "length": 13},
   "ops": [{"tag": "replace", "a_start": 4, "a_end": 5, "b_start": 4, "b_end": 6,
            "a_lines": ["..."], "b_lines": ["...", "..."]}],
   "moves": [{"a_start": 0, "a_end": 3, "b_start": 10, "b_end": 13, "a_lines": [...], "b_lines": [...]}]}
  ```

  Indices are 0-based and ranges are half-open, as in `DiffOp`. Pass
  `include_lines=False` to leave out the text, and `moves=` to include
  moved blocks. With `ignore_blank_lines=True`, ignored operations remain in
  the document so its ranges still cover the original files; they receive an
  `"ignored": true` field, while top-level `has_changes` reports whether any
  effective difference remains.

### Words, tokens and records

`diff` works on any sequence of hashable items, not just lines:

```python
from histodiff import diff

old = "the quick brown fox jumps".split()
new = "the quick red fox jumped".split()
[(op.tag, op.a_lines, op.b_lines) for op in diff(old, new) if op.tag != "equal"]
# [('replace', ('brown',), ('red',)), ('replace', ('jumps',), ('jumped',))]

diff([1, 2, 3, 4], [1, 3, 4, 5])  # numbers, tuples, named tuples,
# frozen dataclasses...
```

Pass `key` to compare items by a derived value, as with `sorted(key=...)`.
The ops still hold your original items:

```python
diff(old_lines, new_lines, key=str.strip)  # ignore indentation/trailing spaces
diff(old_words, new_words, key=str.casefold)  # ignore case

# dicts aren't hashable, so compare them by their contents
diff(old_rows, new_rows, key=lambda row: tuple(sorted(row.items())))
```

The algorithm functions (`myers_diff` and the rest) take the same `key`.
`unified_diff` is a text format, so it only accepts ops whose items are
strings.

### Coming from difflib

`histodiff.SequenceMatcher` is a drop-in subclass of
`difflib.SequenceMatcher`. Change the import and your existing code gets
histodiff's alignment:

```python
# from difflib import SequenceMatcher
from histodiff import SequenceMatcher

sm = SequenceMatcher(None, old, new)  # same signature as difflib
sm.get_opcodes()  # [('equal', 0, 5, 0, 5), ...]
sm.get_grouped_opcodes(3)  # hunks, as in difflib
sm.ratio()  # similarity from the better alignment

SequenceMatcher(None, old, new, algorithm="patience")  # pick an algorithm
```

Like difflib's, it works on any sequences of hashable items, including
strings compared character by character. `get_diff_ops()` returns the same
alignment as `DiffOp`s, which you can pass to `unified_diff`. A few
deliberate differences:

- `isjunk` items are never used as anchors, but can still be matched between
  anchors.
- `autojunk` is accepted but has no effect, because difflib's
  frequent-line heuristic is what makes its large diffs poor.
- `find_longest_match()` keeps difflib's behavior.

To replace `difflib.unified_diff(a, b)`, use `unified_diff(diff(a, b))`.

[`examples/migrate_from_difflib.py`](https://github.com/rmnvg/histodiff/blob/main/examples/migrate_from_difflib.py)
runs both migrations - `unified_diff` and `SequenceMatcher` - side by side
against the same before/after code, on a case difflib is known to get wrong.

### Command line

```bash
histodiff old.py new.py                           # unified diff, histogram algorithm
histodiff old.py new.py --algorithm patience
histodiff old.py new.py --color                   # green/red, changed words highlighted
histodiff old.py new.py --color-words             # changed words inline, like git
histodiff old.py new.py --color-moved             # moved blocks in their own colors
histodiff old.py new.py --dim-moved               # moved blocks dimmed
histodiff old.py new.py -y -W 160                 # side by side, 160 columns wide
histodiff old.py new.py --html > diff.html        # standalone HTML page
histodiff old.py new.py --json | jq '.moves'      # machine-readable ops and moves
histodiff old.py new.py --stat                    # insertions and deletions summary
histodiff old.py new.py -U 10                     # 10 lines of context
histodiff old.py new.py -i                        # ignore case differences
histodiff old.py new.py -b                        # ignore changes in amount of whitespace
histodiff old.py new.py -w                        # ignore all whitespace
histodiff old.py new.py -B                        # ignore changes that are only blank lines
histodiff old.py new.py --minimal                 # smallest diff, however long it takes
cat new.py | histodiff old.py -                   # '-' reads stdin
```

Set `NO_COLOR` to any non-empty value to force plain terminal output, even
when a color-related flag is passed.

`-i` / `--ignore-case` compares lines using Unicode case folding, so `Straße`
and `STRASSE` compare equal. Combine it with `-b` or `-w` to ignore whitespace
differences too. Output retains the original text, and moved-block detection
uses the same comparison rules. In Python, use `diff(old, new, key=str.casefold)`.

With `--color`, when lines are replaced the words that actually changed are
shown in reverse video, so `result = process(event)` →
`result = process_v2(event)` highlights just `process` and `process_v2`.
Lines that share less than half their text aren't highlighted, since nearly
everything would be. `--color-words` goes further, like
`git diff --color-words`: each replaced block is printed once, with deleted
words in red and inserted words in green.

`--color-moved` works like `git diff --color-moved`. When a deleted block
reappears unchanged somewhere else, both copies are shown in their own
colors: bold magenta where the block was removed, bold cyan where it was
added. If two moved blocks sit right next to each other, the second one
switches to blue and yellow so you can see where one ends and the next
begins. `--dim-moved` uses faint versions of those colors, so moved code
fades into the background and real edits stand out. Blocks need at least 20
letters or digits to count, so a moved `}` or blank line isn't flagged.

`-y` prints two columns like `diff -y`. Changed pairs are marked `|`, and
lines on only one side are marked `<` or `>`. Add `--suppress-common-lines`
to see only the changes. It works with `--color`, `--color-moved` and
`--dim-moved`. `--html` writes a self-contained side-by-side page with line
numbers and word highlighting, which follows the reader's light or dark
theme; `-U` controls its context. `--json` prints the diff operations,
including their lines, and any moved blocks, for other tools to consume.
`--stat` prints a diffstat-style single-line summary of insertions and deletions.
These formats print output even when the files are identical.
`-B` is honored by every format. JSON retains ignored operations for source
fidelity, marks them as ignored, and reports the effective result in
`has_changes`.

As with `diff`, the exit status is 0 when the files are identical (or differ
only in ways you chose to ignore), 1 when they differ, and 2 on error. Try it
on the classic patience-diff example (after cloning the repository):
`histodiff examples/frobnitz_old.c examples/frobnitz_new.c`, then the same
with `--algorithm myers`.

### Git integration

Installing histodiff also installs `git-histodiff`, an adapter for Git's
external-diff protocol. Enable it for the current repository with one command:

```bash
git config diff.external git-histodiff
```

Your normal Git commands will now use histogram alignment:

```bash
git diff                                      # unstaged changes
git diff -- path/to/file.py                   # one file
git diff --cached                             # staged changes
git show --ext-diff --format= HEAD            # the change made by one commit
git diff HEAD~1 HEAD                          # compare two revisions
```

Repository-local configuration is recommended because it does not change Git's
behavior elsewhere. To use histodiff in every repository, add `--global` to the
setup command. To bypass it once, run `git diff --no-ext-diff`; to remove the
local configuration, run:

```bash
git config --unset diff.external
```

Use `git config --global --unset diff.external` if you enabled it globally.
The adapter follows Git's file-pair behavior:

- Added and deleted files are compared against `/dev/null`, and their file mode
  is shown. Git does not include untracked files until you stage them or run
  `git add -N path/to/file`.
- When Git detects a rename or copy, for example with `git diff -M` or
  `git diff -C`, histodiff shows the old and new paths, Git's similarity score,
  and any content changes.
- Files containing a NUL byte in the first 8 KiB are treated as binary and get
  a one-line `Binary files ... differ` summary rather than decoded text output.
- Unmerged paths are reported as unmerged instead of being compared as ordinary
  files.
- The adapter follows Git's external-helper exit convention. Plain `git diff`
  completes successfully after displaying differences; `git diff --exit-code`
  still returns `1` when Git found changes.

`git-histodiff` is an adapter invoked by Git, not another two-file interface.
Continue to use `histodiff OLD NEW` for direct file comparisons.

### API stability

histodiff is still in its `0.x` series, but the following interfaces are safe
to build against:

- Every name listed in `histodiff.__all__` is public. Public names will not be
  removed without a documented deprecation period. Modules whose names begin
  with `_` are internal and should not be imported directly; only objects they
  expose through the top-level `histodiff.__all__` API are public.
- `DiffOp` is a public data model. Its `tag`, `a_start`, `a_end`, `b_start`,
  `b_end`, `a_lines`, and `b_lines` fields retain the meanings documented
  above, including 0-based, half-open ranges.
- Valid JSON documents with `"version": 1` will remain readable by future
  histodiff releases. New optional fields may be added without increasing the
  schema version. Consumers, including `from_json()`, must ignore fields they
  do not recognize.
- Exact diff alignment is not frozen. A minor `0.x` release may choose different
  valid boundaries for ambiguous input as the readability heuristics improve.
  Code should rely on the documented operations and their ability to transform
  the old sequence into the new one, rather than snapshotting a particular
  ambiguous alignment.
- CLI exit status is part of the public contract: `0` means no effective
  differences, `1` means differences were found, and `2` means an error
  prevented comparison.

### Choosing an algorithm

| Algorithm | Use it when | Trade-off |
| --- | --- | --- |
| `histogram` (default) | You want readable diffs of real files: code, config, data. | Not guaranteed to be the smallest possible diff. |
| `patience` | Code with plenty of unique lines, where you want strict "only anchor on lines that appear exactly once" behavior. | If no line is unique, for example when blocks are duplicated, it falls back to Myers. |
| `myers` | You need the minimum number of changed lines (with `minimal=True` on big, very different inputs), or you're comparing against `git diff --diff-algorithm=myers`. | Readily matches stray `}` and blank lines, which splits moved or rewritten blocks into many interleaved hunks. |

- **histogram** is inspired by Git's histogram diff option
  (`git diff --diff-algorithm=histogram`). It works like patience but anchors on
  the *rarest* matching lines instead of demanding strictly unique ones. That
  keeps it readable when every line repeats somewhere. Lines that occur more
  than 64 times are never used as anchors.
- **patience** anchors on lines that occur exactly once in both files, keeps the
  longest run of them that appears in the same order, and repeats that between
  the anchors.
- **myers** is the classic O(ND) shortest-edit-script algorithm and Git's
  default. It's the right choice when diff *size* matters more than
  readability. On large, very different inputs its run time grows with the
  square of the file size, so, like Git, histodiff caps the search there and
  accepts a slightly larger diff (see [Performance](#performance)). Patience
  and histogram use Myers for the stretches they can't anchor, so the cap
  protects them too. Pass `minimal=True` or `--minimal` to turn it off.

Because patience and histogram prefer distinctive lines over the largest
possible match, they sometimes report more changed lines than Myers, most often
when whole blocks are duplicated and shuffled (see scenario 3 of the
[real-world corpus](#real-world-corpus) for a concrete case). All three
algorithms share a final pass that slides ambiguous insertions and deletions
to blank-line and indentation boundaries, similar to Git's own clean-up
heuristics.

### Performance

histodiff is pure Python. These numbers come from
[`benchmarks/bench.py`](https://github.com/rmnvg/histodiff/blob/main/benchmarks/bench.py)
on an Apple M3 Pro with Python 3.14, using 20,000-line files and keeping the
best of 3 runs. Each cell shows the time, then the number of lines the diff
marks as changed:

| Scenario | difflib | myers | patience | histogram |
| --- | --- | --- | --- | --- |
| One line changed | 6 ms (2) | 4 ms (2) | 4 ms (2) | 4 ms (2) |
| Function moved | 6 ms (39,968) | 6 ms (16) | 8 ms (16) | 6 ms (16) |
| 5% of lines edited | 830 ms (2,094) | 119 ms (1,950) | 10 ms (1,950) | 31 ms (1,950) |
| Row inserted in repeated rows | 3 ms (20,001) | 4 ms (1) | 4 ms (1) | 4 ms (1) |
| Unrelated files (worst case) | 3 ms (40,000) | 1.67 s (30,232) | 1.66 s (30,232) | 1.71 s (30,232) |

- **Everyday edits:** in these benchmark scenarios, histodiff is about as fast
  as difflib or faster and marks no more lines as changed. In the scattered-edit
  scenario shown here, histogram is about 25× faster than difflib.
- **Unrelated files:** difflib is far faster, because on large files it
  effectively gives up and marks every line as changed. histodiff still
  lines up the lines the files share, which takes longer.
- **The search cap:** without it, the worst case grows with the square of
  the file size. On 8,000-line unrelated files, histogram takes 0.67 s
  capped and 10.5 s with `minimal=True`, while the capped diff is only 0.8%
  larger (12,092 changed lines instead of 12,000). At 16,000 lines the
  uncapped search took 42 s.

Run `python benchmarks/bench.py --help` for sizes, repeats and a Markdown
output mode.

## Limitations

- histodiff works in memory. The CLI reads both inputs before comparing them,
  and diff operations retain their corresponding items. Very large inputs can
  therefore require substantial memory.
- The CLI is intended for UTF-8 text files, not binary files. Invalid UTF-8
  bytes are decoded with replacement characters, so use your own decoding and
  the Python API when byte-exact handling or another encoding is required.
- During the `0.x` series, readability improvements may change the exact valid
  alignment selected for ambiguous input. Avoid snapshotting an alignment when
  your application only needs to verify that applying the operations recreates
  the new sequence.
- The algorithms and cleanup rules are Git-inspired, but output is not
  guaranteed to match Git for every input.
- histodiff generates and renders differences; it does not apply unified diff
  patches.
- `minimal=True` and `--minimal` disable the search cap. They can take
  quadratic time on large, unrelated inputs and should be used only when a
  smallest edit script matters more than runtime.

## Community and roadmap

[ROADMAP.md](https://github.com/rmnvg/histodiff/blob/main/ROADMAP.md) lists
what's likely next, honestly and without dates. A few ways to get involved
beyond filing a bug:

- Pick up a
  [`good first issue`](https://github.com/rmnvg/histodiff/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
- Hit a diff that came out confusing or wrong-looking, from histodiff or
  anything else? [Share it](https://github.com/rmnvg/histodiff/issues/4) -
  real examples like this become permanent regression tests.

## Contributing

Issues and pull requests are welcome. See
[CONTRIBUTING.md](https://github.com/rmnvg/histodiff/blob/main/CONTRIBUTING.md)
for environment setup, what's expected of tests, formatting, type checking,
property tests and benchmarks, and the pull-request process. Participation
is governed by the
[Code of Conduct](https://github.com/rmnvg/histodiff/blob/main/CODE_OF_CONDUCT.md).
Found a security vulnerability? Please report it privately - see
[SECURITY.md](https://github.com/rmnvg/histodiff/blob/main/SECURITY.md)
rather than opening a public issue.

## License

MIT, see [LICENSE](https://github.com/rmnvg/histodiff/blob/main/LICENSE).
