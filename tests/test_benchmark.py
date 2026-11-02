"""Tests for the benchmark cache: reading external corpora without the network.

No puzzle data is committed and no test touches the network: every source is a
file in a temporary directory, so what is pinned here is the shape of the
reading (rows, solutions, ratings, buckets), the record of what was fetched,
and that the engine never looks back at the benchmark.
"""

import csv
import hashlib
import signal
import time
from pathlib import Path
from typing import NamedTuple

import pytest

import csp.sudoku
from benchmark import bench, corpus, fetch
from benchmark.run import BASE
from csp.core import DEFAULT_RULES

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


def test_fetch_redownloads_a_cached_file_that_was_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "CACHE", tmp_path / "cache")
    original = tmp_path / "puzzles.txt"
    original.write_text(PUZZLE + "\n")
    source = corpus.Source("local", "grid-lines", (("puzzles.txt", original.as_uri()),))
    cached = corpus.fetch(source)[0]

    cached.unlink()
    assert corpus.fetch(source) == [cached]
    assert cached.read_text() == PUZZLE + "\n"


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


# --- the runner: what it judges, and what it reports ------------------------


class _Step(NamedTuple):
    """The part of `csp.core.Step` the audit reads."""

    var: str
    value: int
    asserted: bool
    rule: str

    @property
    def literal(self) -> str:
        return f"{self.var}={self.value}"


def _outcome(**overrides: object) -> bench.Outcome:
    fields: dict[str, object] = {
        "index": 0,
        "origin": "top95.txt",
        "group": "top95",
        "rating": None,
        "grade": "single",
        "solved": True,
        "agrees": True,
        "unsound": (),
        "contradiction": None,
        "timed_out": False,
        "ms": 10.0,
        "iterations": 3,
        "steps": 40,
        "what_if": 0,
        "counts": {"single": 3},
    }
    return bench.Outcome(**(fields | overrides))


def test_audit_only_judges_steps_the_answer_speaks_about():
    answer = {"r1c1": 5, "r1c2": 3}
    steps = [
        _Step("r1c1", 5, True, "single"),
        _Step("r1c2", 3, False, "cover2"),
        _Step("r1c1", 4, False, "cover2"),
        _Step("r1c1", 7, True, "given"),
        _Step("r9c9", 1, True, "chains"),
    ]
    assert bench._audit(steps, answer) == ("cover2 x r1c2=3",)


def test_measure_solves_a_puzzle_and_agrees_with_its_answer():
    job = bench.Job(
        0,
        "tiny.txt",
        "easy",
        None,
        "sudoku",
        corpus.grid(PUZZLE),
        corpus.oracle(SOLVED),
        "full",
        60,
    )
    outcome = bench.measure(job)
    assert outcome.solved
    assert outcome.agrees
    assert outcome.unsound == ()
    assert not outcome.suspect
    assert outcome.grade != "timeout"


def test_measure_gives_up_at_its_time_limit():
    job = bench.Job(
        0,
        "tiny.txt",
        "easy",
        None,
        "sudoku",
        corpus.grid(PUZZLE),
        corpus.oracle(SOLVED),
        "full",
        1e-6,
    )
    outcome = bench.measure(job)
    assert outcome.timed_out
    assert not outcome.solved
    assert outcome.grade == "timeout"


def test_measure_time_limit_covers_generating_an_answer(monkeypatch):
    job = bench.Job(
        0,
        "tiny.txt",
        "easy",
        None,
        "sudoku",
        corpus.grid(PUZZLE),
        None,
        "full",
        0.01,
    )

    def slow_oracle(*args, **kwargs):
        time.sleep(0.1)
        return []

    monkeypatch.setattr(bench.bruteforce, "solutions", slow_oracle)
    outcome = bench.measure(job)
    assert outcome.timed_out
    assert outcome.grade == "timeout"


def test_a_timed_out_run_does_not_arm_the_one_after_it():
    """The limit belongs to one job: an expired alarm must not cut the next run."""
    quick = bench.Job(
        0,
        "tiny.txt",
        "easy",
        None,
        "sudoku",
        corpus.grid(PUZZLE),
        corpus.oracle(SOLVED),
        "full",
        1e-6,
    )
    assert bench.measure(quick).timed_out
    outcome = bench.measure(quick._replace(timeout=60))
    assert outcome.solved
    assert not outcome.timed_out
    assert signal.getsignal(signal.SIGALRM) is not bench._raise_timeout


def test_measure_refuses_to_judge_a_puzzle_with_two_answers():
    empty = bench.Job(
        0, "empty.txt", "easy", None, "sudoku", corpus.grid("." * 81), None, "full", 60
    )
    outcome = bench.measure(empty)
    assert outcome.grade == "ambiguous"
    assert not outcome.solved
    assert "solutions" in (outcome.contradiction or "")


def test_ladders_keep_the_default_order_and_only_add_cover4():
    names = [rule.name for rule in bench.LADDERS["full"]]
    assert names == [rule.name for rule in DEFAULT_RULES]
    assert [rule.name for rule in bench.LADDERS["cover4"]] == [
        *names[: names.index("chains")],
        "cover4",
        *names[names.index("chains") :],
    ]
    assert "what_if" not in [rule.name for rule in bench.LADDERS["no-what-if"]]
    assert "chains" not in [rule.name for rule in bench.LADDERS["no-chains"]]
    assert "what_if" not in [rule.name for rule in bench.LADDERS["cover4-no-what-if"]]


def test_percentile_ranks_and_spearman_read_an_ordering():
    assert bench.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert bench.percentile([4, 1, 3], 1.0) == 4
    assert bench.percentile([], 0.5) == 0.0
    assert bench.ranks([10, 10, 20]) == [1.5, 1.5, 3.0]
    assert bench.spearman([(1, 1), (2, 2), (3, 3)]) == pytest.approx(1.0)
    assert bench.spearman([(1, 3), (2, 2), (3, 1)]) == pytest.approx(-1.0)
    assert bench.spearman([(1, 1), (2, 1), (3, 1)]) is None
    assert bench.spearman([(1, 1), (2, 2)]) is None


def test_bands_use_the_rating_when_there_is_one_and_the_group_otherwise():
    rated = [_outcome(index=index, rating=float(index)) for index in range(1, 9)]
    labels = [label for label, _ in bench.bands(rated)]
    assert labels == ["rating 1 to 3", "rating 4 to 5", "rating 6", "rating 7 to 8"]
    assert [members for _, members in bench.bands(rated)] == [
        rated[0:3],
        rated[3:5],
        rated[5:6],
        rated[6:8],
    ]
    unrated = [_outcome(group="top95"), _outcome(group="easy50"), _outcome(group="easy50")]
    assert [label for label, _ in bench.bands(unrated)] == ["easy50", "top95"]


def test_report_separates_bad_runs_from_hard_ones():
    outcomes = [
        _outcome(index=1, origin="easy50.txt", group="easy50", grade="single", ms=5.0),
        _outcome(index=2, origin="top95.txt", grade="what_if", what_if=2, ms=800.0),
        _outcome(
            index=3,
            origin="top95.txt",
            grade="unsolved",
            solved=False,
            agrees=False,
            contradiction="the rules ran out",
            ms=900.0,
        ),
        _outcome(
            index=4,
            origin="hardest.txt",
            group="hardest",
            grade="what_if",
            what_if=1,
            unsound=("single = r1c1=5",),
            ms=90.0,
        ),
        _outcome(
            index=5,
            origin="top95.txt",
            grade="timeout",
            solved=False,
            agrees=False,
            timed_out=True,
            ms=30_000.0,
        ),
    ]
    text = bench.report(outcomes, title="test run", ladder="full", timeout=30)
    assert "Solved: **3 of 5** (60.0%)" in text
    assert "Wrong solution: 0; unsound steps: 1" in text
    assert "| `what_if` | 2 | 40% " in text
    assert "what_if` fired on 2 of 5 puzzles (40%), 3 times in all" in text
    assert "Empty: every puzzle" not in text
    assert "unsound: single = r1c1=5" in text
    assert "timed out" in text
    assert "the rules ran out" in text
    assert "| 5 | top95.txt | top95 |  | `timeout` | 30000 |" in text


def test_rank_correlation_only_reads_the_puzzles_the_ladder_solved():
    """Folding the failures in turns the source's rating into the wall clock.

    The three solved puzzles climb with the rating; the three it could not
    finish have the *lowest* ratings and the *last* grades, so measuring all six
    gives a strongly negative number while the grade itself is perfectly in step.
    """
    outcomes = [
        _outcome(index=1, rating=1.0, grade="unsolved", solved=False, agrees=False, iterations=1),
        _outcome(
            index=2,
            rating=2.0,
            grade="timeout",
            solved=False,
            agrees=False,
            timed_out=True,
            ms=30_000.0,
            iterations=0,
        ),
        _outcome(index=3, rating=3.0, grade="unsolved", solved=False, agrees=False, iterations=1),
        _outcome(index=4, rating=5.0, grade="single", ms=5.0, iterations=5),
        _outcome(index=5, rating=6.0, grade="subsumption", ms=6.0, iterations=6),
        _outcome(index=6, rating=7.0, grade="chains", ms=7.0, iterations=7),
    ]
    text = bench.report(outcomes, title="rated", ladder="full", timeout=30)
    assert "over the 3 of 6 rated puzzles it solved (2 unsolved, 1 timed out)" in text
    assert "grade +1.00, iterations +1.00, ms +1.00" in text

    grades = bench.grades_for("full")
    naive = bench.spearman([(o.rating, grades.index(o.grade)) for o in outcomes])
    assert naive is not None and naive < -0.5


def test_rank_correlation_says_when_it_cannot_read_the_ranking():
    text = bench.report(
        [
            _outcome(index=1, rating=1.0, grade="single"),
            _outcome(index=2, rating=2.0, grade="unsolved", solved=False, agrees=False),
            _outcome(index=3, rating=3.0, grade="unsolved", solved=False, agrees=False),
        ],
        title="rated",
        ladder="full",
        timeout=30,
    )
    assert "only 1 of 3 rated puzzles were solved" in text
    assert "Rank correlation with the source's rating" not in text


def test_report_says_so_when_nothing_went_wrong():
    text = bench.report([_outcome()], title="clean", ladder="full", timeout=30)
    assert "Empty: every puzzle was solved" in text
    assert "Failure index" in text


def test_report_handles_a_run_where_every_puzzle_timed_out():
    timed_out = _outcome(
        grade="timeout",
        solved=False,
        agrees=False,
        timed_out=True,
        ms=30_000.0,
    )
    text = bench.report([timed_out], title="all timed out", ladder="full", timeout=30)
    assert "Time where it finished: median n/a ms, p90 n/a ms, max n/a ms" in text
    assert "timed out: 1" in text


def test_csv_rows_are_flat_and_hold_no_puzzle_text(tmp_path):
    path = tmp_path / "reports" / "run.csv"
    bench.write_csv(path, [_outcome(counts={"single": 2, "chains": 1})])
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(bench.CSV_COLUMNS)
    assert rows[0]["origin"] == "top95.txt"
    assert rows[0]["rules"] == '{"chains": 1, "single": 2}'
    assert len(rows[0]) == len(bench.CSV_COLUMNS)


def test_example_jobs_leave_murdoku_to_its_own_tools():
    jobs = bench.example_jobs("full", 30)
    assert len(jobs) > 50
    assert all(job.kind != "murdoku" for job in jobs)
    assert all(job.answer is None for job in jobs)  # the brute force supplies it
    assert [job.index for job in jobs] == list(range(len(jobs)))
    assert {job.group for job in jobs} >= {"sudoku", "akari", "tango"}


def test_corpus_jobs_name_the_file_and_carry_the_samples_answer(tmp_path):
    path = tmp_path / "sample.csv"
    corpus.store(path, [corpus.Row(0, "top95.txt", PUZZLE, SOLVED, None, None)])
    jobs = bench.corpus_jobs(corpus.Sample(path, 1, 1, 0, False), "full", 5)
    assert len(jobs) == 1
    assert jobs[0].origin == "top95.txt"
    assert jobs[0].group == "top95"  # no group column: the file name stands in
    assert jobs[0].answer == corpus.oracle(SOLVED)
    assert jobs[0].text == corpus.grid(PUZZLE)
