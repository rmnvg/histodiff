# Changelog

All notable changes to histodiff will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/). During the
`0.x` series, minor releases may include documented changes to ambiguous diff
alignment while preserving the public data model and valid edit operations.

## [Unreleased]

### Added

- `--stat` CLI flag for a diffstat-style summary line reporting insertions and
  deletions separately.
- `-i` / `--ignore-case` for Unicode case-insensitive CLI comparisons,
  compatible with whitespace filtering and moved-block detection.
- `NO_COLOR` support: any non-empty value disables ANSI color output, even
  when `--color`, `--color-words`, `--color-moved` or `--dim-moved` is passed.

### Fixed

- Git adapter treats filenames beginning with `-`, including a literal `-`,
  as files instead of CLI options or standard input.
- Git adapter reports metadata-only changes (renames, mode changes, and empty
  file additions/deletions) when Git trusts the helper's exit status.

## [0.1.0] - 2026-09-14

### Added

- Histogram, patience, and Myers sequence-diff algorithms.
- Readability cleanup for ambiguous insertion and deletion boundaries.
- Unified, side-by-side, HTML, and versioned JSON output.
- Word-level highlighting and moved-block detection.
- Whitespace-aware comparison and blank-line filtering.
- A `difflib.SequenceMatcher`-compatible API and support for generic sequences.
- A dependency-free command-line interface.
- A `git-histodiff` adapter for repository, staged, and commit diffs.
- A runnable real-world corpus (`examples/real_world_corpus.py`) comparing
  difflib, all three histodiff algorithms, and the third-party
  `patiencediff` package across ten representative scenarios, with changed
  lines, hunks, timing, and peak memory for the larger ones.
- Branch coverage measurement (`pytest-cov`), enforced in CI at 95%, with
  the remaining, deliberately untested lines marked `# pragma: no cover`
  and a comment explaining why each is unreachable or untestable in-process.

[Unreleased]: https://github.com/rmnvg/histodiff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rmnvg/histodiff/releases/tag/v0.1.0
