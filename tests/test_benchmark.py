"""Tests for the benchmark cache: reading external corpora without the network.

No puzzle data is committed and no test touches the network: every source is a
file in a temporary directory, so what is pinned here is the shape of the
reading (rows, solutions, ratings, buckets), the record of what was fetched,
and that the engine never looks back at the benchmark.
"""

import hashlib
from pathlib import Path

import pytest

import csp.sudoku
from benchmark import corpus, fetch
from benchmark.run import BASE

ROOT = Path(__file__).resolve().parent.parent
SOLVED = "".join(str(BASE[r][c]) for r in range(9) for c in range(9))
PUZZLE = "".join("." if index % 6 == 0 else digit for index, digit in enumerate(SOLVED))
FIRST_GIVEN = next(index for index, cell in enumerate(PUZZLE) if cell != ".")
WRONG = (
    PUZZLE[:FIRST_GIVEN] + ("1" if PUZZLE[FIRST_GIVEN] == "2" else "2") + PUZZLE[FIRST_GIVEN + 1 :]
)


def test_grid_is_the_nine_lines_the_engine_reads():
    lines = [PUZZLE[start : start + 9] for start in range(0, 81, 9)]
    assert corpus.grid(PUZZLE).splitlines() == lines
    parsed = csp.sudoku.parse(corpus.grid(PUZZLE))
    assert len(parsed.grid) == 9
    assert parsed.grid[0][0] == 0
    assert parsed.grid[1] == [0 if cell == "." else int(cell) for cell in PUZZLE[9:18]]


def test_oracle_is_the_engines_own_assignment():
    cells = [f"r{row}c{col}" for row in range(1, 10) for col in range(1, 10)]
    assert list(corpus.oracle(SOLVED)) == cells
    assert corpus.oracle(SOLVED)["r1c1"] == int(SOLVED[0])
    assert corpus.oracle(SOLVED)["r9c9"] == int(SOLVED[-1])


def test_oracle_is_what_the_brute_force_finds():
    assert corpus.solved(PUZZLE) == SOLVED
    assert list(corpus.oracle(SOLVED).values()) == [int(character) for character in SOLVED]


def test_a_puzzle_without_one_answer_has_no_solution_to_offer():
    assert corpus.solved("." * 81) is None


def test_consistent_notices_an_answer_that_contradicts_its_givens():
    assert corpus.consistent(PUZZLE, SOLVED)
    assert not corpus.consistent(PUZZLE, WRONG)


def test_grid_lines_reads_both_norvig_layouts(tmp_path):
    path = tmp_path / "easy.txt"
    nine_lines = [PUZZLE[start : start + 9] for start in range(0, 81, 9)]
    path.write_text("\n".join([*nine_lines, "=" * 8, SOLVED]) + "\n")
    rows = list(corpus.rows(corpus.NORVIG, path))
    assert [row.puzzle for row in rows] == [PUZZLE, SOLVED]
    assert [row.index for row in rows] == [1, 2]
    assert {(row.origin, row.solution, row.rating, row.group) for row in rows} == {
        ("easy.txt", None, None, None)
    }


def test_grid_lines_refuses_half_a_puzzle(tmp_path):
    path = tmp_path / "half.txt"
    path.write_text(PUZZLE[:80] + "\n")
    with pytest.raises(ValueError, match="80 characters left over"):
        list(corpus.rows(corpus.NORVIG, path))


def test_csv81_takes_the_columns_it_was_told(tmp_path):
    path = tmp_path / "test.csv"
    path.write_text(f"source,question,answer,rating,extra\nclue,{PUZZLE},{SOLVED},3,ignored\n")
    assert list(corpus.rows(corpus.SUDOKU_EXTREME, path)) == [
        corpus.Row(1, "test.csv", PUZZLE, SOLVED, 3.0, "clue")
    ]


def test_csv81_leaves_an_answer_or_rating_it_cannot_read_empty(tmp_path):
    path = tmp_path / "test.csv"
    path.write_text(f"source,question,answer,rating\nclue,{PUZZLE},,hard\n")
    assert list(corpus.rows(corpus.SUDOKU_EXTREME, path)) == [
        corpus.Row(1, "test.csv", PUZZLE, None, None, "clue")
    ]


def test_csv81_refuses_a_puzzle_that_is_not_81_characters(tmp_path):
    path = tmp_path / "test.csv"
    path.write_text(f"source,question,answer,rating\nclue,{PUZZLE[:-1]},{SOLVED},1\n")
    with pytest.raises(ValueError, match="80 characters, expected 81"):
        list(corpus.rows(corpus.SUDOKU_EXTREME, path))


def test_csv81_refuses_an_answer_that_is_not_a_grid(tmp_path):
    path = tmp_path / "test.csv"
    path.write_text(f"source,question,answer,rating\nclue,{PUZZLE},{SOLVED[:-1]},1\n")
    with pytest.raises(ValueError, match="the solution is not 81 digits"):
        list(corpus.rows(corpus.SUDOKU_EXTREME, path))


def test_unknown_file_kinds_are_named_not_guessed():
    source = corpus.Source("unseen", "arff81", ())
    with pytest.raises(ValueError, match="unknown file kind 'arff81'"):
        list(corpus.rows(source, ROOT / "unused.arff"))


def _rows() -> list[corpus.Row]:
    return [
        corpus.Row(index, "f.txt", PUZZLE, SOLVED, float(index % 5), f"set{index % 3}")
        for index in range(1, 31)
    ]


def test_pick_gives_the_same_sample_for_the_same_seed():
    rows = _rows()
    once = corpus.pick(iter(rows), 2, seed=7, bucket=corpus.by_group)
    assert once == corpus.pick(iter(rows), 2, seed=7, bucket=corpus.by_group)


def test_pick_takes_count_rows_per_bucket():
    picked = corpus.pick(iter(_rows()), 2, seed=7, bucket=corpus.by_group)
    assert [row.group for row in picked] == ["set0", "set0", "set1", "set1", "set2", "set2"]
    assert len({row.index for row in picked}) == len(picked)


def test_pick_without_a_bucket_or_a_count():
    rows = _rows()
    assert len(corpus.pick(iter(rows), 5, seed=7)) == 5
    assert corpus.pick(iter(rows), None, seed=7) == rows


def test_pick_by_rating_bands_the_sources_own_scale():
    picked = corpus.pick(iter(_rows()), 1, seed=7, bucket=corpus.by_rating)
    assert [corpus.by_rating(row) for row in picked] == ["0", "1", "2", "3", "4"]


def test_pick_refuses_a_sample_size_below_one():
    with pytest.raises(ValueError, match="at least 1"):
        corpus.pick([], 0, seed=1)


def test_store_and_load_round_trip(tmp_path):
    rows = [
        corpus.Row(3, "test.csv", PUZZLE, SOLVED, 2.5, "clue"),
        corpus.Row(4, "test.csv", SOLVED),
    ]
    path = tmp_path / "sample.csv"
    corpus.store(path, rows)
    assert path.read_text().splitlines()[0] == "index,origin,group,rating,puzzle,solution"
    assert corpus.load(path) == rows


def test_usable_keeps_only_rows_that_can_judge_the_engine():
    tally = corpus.Tally()
    rows = [
        corpus.Row(1, "f.txt", PUZZLE, SOLVED),
        corpus.Row(2, "f.txt", PUZZLE, WRONG),
        corpus.Row(3, "f.txt", "." * 81),
        corpus.Row(4, "f.txt", PUZZLE),
    ]
    assert [row.index for row in corpus.usable(rows, tally)] == [1, 4]
    assert (tally.read, tally.dropped) == (4, 2)


def _local_source(path: Path) -> corpus.Source:
    return corpus.Source(
        "local",
        "csv81",
        (("test.csv", path.as_uri()),),
        puzzle="question",
        solution="answer",
        rating="rating",
        group="source",
    )


def test_build_reuses_a_sample_it_already_has(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "CACHE", tmp_path / "cache")
    original = tmp_path / "test.csv"
    original.write_text(f"source,question,answer,rating\nclue,{PUZZLE},{SOLVED},3\n")
    source = _local_source(original)

    first = corpus.build(source, 10, seed=1, bucket="group", key=corpus.by_group)
    assert (first.rows, first.read, first.dropped, first.reused) == (1, 1, 0, False)
    assert corpus.load(first.path) == [corpus.Row(1, "test.csv", PUZZLE, SOLVED, 3.0, "clue")]

    again = corpus.build(source, 10, seed=1, bucket="group", key=corpus.by_group)
    assert (again.reused, again.rows, again.path) == (True, 1, first.path)
    assert corpus.build(source, 10, 1, "group", corpus.by_group, force=True).reused is False


def test_build_refetches_a_source_that_changed_when_told_to(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "CACHE", tmp_path / "cache")
    original = tmp_path / "test.csv"
    original.write_text(f"source,question,answer,rating\nclue,{PUZZLE},{SOLVED},3\n")
    source = _local_source(original)
    corpus.build(source, 10, seed=1, bucket="group", key=corpus.by_group)

    original.write_text(
        f"source,question,answer,rating\nclue,{PUZZLE},{SOLVED},3\nclue,{'.' * 81},,1\n"
    )
    rebuilt = corpus.build(source, 10, 1, "group", corpus.by_group, force=True)
    assert (rebuilt.reused, rebuilt.read, rebuilt.rows, rebuilt.dropped) == (False, 2, 1, 1)


def test_fetch_caches_once_and_remembers_where_it_came_from(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "CACHE", tmp_path / "cache")
    original = tmp_path / "puzzles.txt"
    original.write_text(PUZZLE + "\n")
    source = corpus.Source("local", "grid-lines", (("puzzles.txt", original.as_uri()),))

    paths = corpus.fetch(source)
    assert [path.name for path in paths] == ["puzzles.txt"]
    assert paths[0].read_text() == PUZZLE + "\n"
    downloaded = corpus.read_manifest()["local/puzzles.txt"]
    assert downloaded["url"] == original.as_uri()
    assert downloaded["bytes"] == len(PUZZLE) + 1
    assert downloaded["sha256"] == hashlib.sha256((PUZZLE + "\n").encode()).hexdigest()

    original.write_text(SOLVED + "\n")
    assert corpus.fetch(source) == paths
    assert paths[0].read_text() == PUZZLE + "\n"
    assert corpus.fetch(source, force=True)[0].read_text() == SOLVED + "\n"
    assert corpus.read_manifest()["local/puzzles.txt"]["bytes"] == len(SOLVED) + 1


def test_sample_names_say_where_a_sample_came_from():
    grouped = corpus.sample_name(corpus.SUDOKU_EXTREME, 500, 42, "group")
    assert grouped == "sample-sudoku-extreme-group-500-42.csv"
    assert corpus.sample_name(corpus.NORVIG, None, 42, "none") == "sample-norvig-none-all-42.csv"


def test_the_cli_offers_one_bucket_mode_per_key():
    assert {"none": None, "group": corpus.by_group, "rating": corpus.by_rating} == fetch.BUCKETS


def test_every_source_says_where_its_puzzles_come_from():
    assert list(corpus.SOURCES) == ["norvig", "sudoku-extreme"]
    for source in corpus.SOURCES.values():
        assert source.note
        assert source.kind in {"grid-lines", "csv81"}
        assert all(url.startswith("https://") for _, url in source.files)
        assert len({name for name, _ in source.files}) == len(source.files)


def test_the_cache_is_inside_the_benchmark_and_outside_git():
    assert corpus.CACHE == ROOT / "benchmark" / ".cache"
    assert "benchmark/.cache/" in (ROOT / ".gitignore").read_text().splitlines()


def test_the_engine_does_not_look_back_at_the_benchmark():
    engine = sorted((ROOT / "src" / "csp").rglob("*.py"))
    assert engine
    assert [path.name for path in engine if "benchmark" in path.read_text()] == []
