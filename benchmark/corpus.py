"""External puzzle corpora, cached outside git, as rows the benchmark can read.

    uv run python -m benchmark.fetch --source all

A benchmark needs puzzles nobody in this repository wrote. They are test
input, not content, so they are never committed: `benchmark/.cache/` is
git-ignored and `fetch` fills it. A `Source` is a set of files plus the names
of the columns its puzzles hide behind, and `rows` streams them as `Row`, so
a sample comes out of a 79 MB CSV without the file ever landing in memory.

This module knows exactly one thing about Sudoku corpora: a puzzle is 81
characters. `grid` turns such a row into the 9 lines `csp.sudoku.parse` reads
and `oracle` into the engine's assignment, so that the answer a source ships
(or, where it ships none, the brute force) checks the engine, not the other
way round.
"""

import csv
import hashlib
import json
import random
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from csp.bruteforce import sudoku as brute
from csp.sudoku import cell_name

CACHE = Path(__file__).resolve().parent / ".cache"
SIZE = 9
CELLS = SIZE * SIZE
BLANKS = ".0"
DIGITS = "123456789"
USER_AGENT = "csp-benchmark/0.1 (human-reasoning-puzzles; puzzle grading)"


@dataclass(frozen=True)
class Source:
    """A published set of Sudoku puzzles, and how to read its files.

    `kind` is the shape of the files, not of the puzzles: "grid-lines" for
    plain text that has to be combed for digits (a separator line or a grid
    split over nine lines both work), "csv81" for comma separated rows with a
    header. The column names are None when the source does not have them.
    """

    name: str
    kind: str
    files: tuple[tuple[str, str], ...]
    puzzle: str | None = None
    solution: str | None = None
    rating: str | None = None
    group: str | None = None
    default_count: int | None = None
    note: str = ""


@dataclass(frozen=True)
class Row:
    """One puzzle as its source states it: 81 characters, maybe a solution."""

    index: int
    origin: str
    puzzle: str
    solution: str | None = None
    rating: float | None = None
    group: str | None = None


NORVIG = Source(
    name="norvig",
    kind="grid-lines",
    files=(
        ("easy50.txt", "https://www.norvig.com/easy50.txt"),
        ("top95.txt", "https://www.norvig.com/top95.txt"),
        ("hardest.txt", "https://www.norvig.com/hardest.txt"),
    ),
    note="156 classic puzzles, easy to hardest; the files carry no solutions",
)

SUDOKU_EXTREME = Source(
    name="sudoku-extreme",
    kind="csv81",
    files=(
        (
            "test.csv",
            "https://huggingface.co/datasets/sapientinc/sudoku-extreme/resolve/main/test.csv",
        ),
    ),
    puzzle="question",
    solution="answer",
    rating="rating",
    group="source",
    default_count=500,
    note="400 000+ puzzles with solutions, each tagged with the set it came from",
)

SOURCES = {source.name: source for source in (NORVIG, SUDOKU_EXTREME)}


def check(puzzle: str, index: int, origin: str) -> str:
    """A puzzle row once it is 81 characters of digits and blanks."""
    puzzle = puzzle.strip()
    if len(puzzle) != CELLS:
        raise ValueError(f"{origin} row {index}: {len(puzzle)} characters, expected {CELLS}")
    if not set(puzzle) <= set(DIGITS + BLANKS):
        raise ValueError(f"{origin} row {index}: characters outside digits and '{BLANKS}'")
    return puzzle


def grid(puzzle: str) -> str:
    """An 81-character puzzle as the 9 lines `csp.sudoku.parse` reads."""
    return "\n".join(puzzle[start : start + SIZE] for start in range(0, CELLS, SIZE)) + "\n"


def oracle(solution: str) -> dict[str, int]:
    """A solved 81-character row as the engine's `{"r1c1": 5, ...}` assignment."""
    return {cell_name(r, c): int(solution[r * SIZE + c]) for r in range(SIZE) for c in range(SIZE)}


def solved(puzzle: str) -> str | None:
    """The one solution of `puzzle` as 81 characters, or None if it is not unique.

    For sources that ship puzzles without answers (Norvig's sets). The brute
    force shares nothing with the engine but the definition of a Sudoku, so
    its answer is still an independent oracle.
    """
    found = brute.solutions(grid(puzzle), limit=2)
    if len(found) != 1:
        return None
    return "".join(str(found[0][cell_name(r, c)]) for r in range(SIZE) for c in range(SIZE))


def consistent(puzzle: str, solution: str) -> bool:
    """Whether every given agrees with the solution claimed for it.

    Cheap enough to run on every row of a corpus, and it catches the one kind
    of bad row that would otherwise blame the engine: an answer that does not
    match its own givens is not an oracle, whoever wrote it.
    """
    givens = zip(puzzle, solution, strict=True)
    return all(given == answer for given, answer in givens if given not in BLANKS)


def cache_dir(*parts: str) -> Path:
    """A directory inside the ignored cache, created on demand.

    Nothing else is written by the benchmark: everything it downloads or
    derives lives under `benchmark/.cache/`, one directory per source plus
    `samples/`, so `rm -rf benchmark/.cache` costs only the download again.
    """
    path = CACHE.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative(path: Path) -> str:
    """`path` as the manifest names it: relative to the cache, POSIX style."""
    return path.relative_to(CACHE).as_posix()


def read_manifest() -> dict[str, dict[str, object]]:
    """What earlier fetches downloaded, keyed by path relative to the cache."""
    try:
        return json.loads((CACHE / "manifest.json").read_text())
    except FileNotFoundError:
        return {}


def write_manifest(entries: dict[str, dict[str, object]]) -> None:
    """Record every download, so a report can say where its numbers came from."""
    cache_dir()
    (CACHE / "manifest.json").write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")


def fetch(source: Source, *, force: bool = False) -> list[Path]:
    """Every file of `source` in the cache, downloading whatever is missing.

    A file already in the cache with the size the manifest recorded is left
    alone, so an upstream change needs `force`; the manifest keeps the URL,
    byte size, sha256 and UTC time of each download, which is how a report
    states where its numbers came from without carrying a puzzle with it.
    """
    entries = read_manifest()
    paths = []
    for name, url in source.files:
        path = cache_dir(source.name) / name
        known = entries.get(relative(path))
        if force or known is None or path.stat().st_size != known.get("bytes"):
            known = _download(url, path)
            entries[relative(path)] = known
        paths.append(path)
    write_manifest(entries)
    return paths


def _download(url: str, path: Path) -> dict[str, object]:
    """`url` into `path` through a `.part` file; returns its manifest entry."""
    digest = hashlib.sha256()
    part = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    size = 0
    with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as handle:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            handle.write(chunk)
            size += len(chunk)
    part.replace(path)
    return {
        "url": url,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "fetched": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def rows(source: Source, path: Path) -> Iterator[Row]:
    """Every puzzle in one cached file, in file order."""
    match source.kind:
        case "grid-lines":
            yield from _grid_lines(path)
        case "csv81":
            yield from _csv_rows(source, path)
        case _:
            raise ValueError(f"{source.name}: unknown file kind {source.kind!r}")


def all_rows(source: Source, paths: Sequence[Path]) -> Iterator[Row]:
    """The rows of every file of `source`, in the order the source lists them."""
    for path in paths:
        yield from rows(source, path)


def _grid_lines(path: Path) -> Iterator[Row]:
    """Puzzles from plain text, digit by digit: 81 characters make a puzzle.

    Norvig's `easy50.txt` lays a grid out over nine lines with a line of `=`
    between puzzles, and `top95.txt` puts a whole puzzle on one line. Both are
    the same digits with different whitespace, so both read here; a separator
    carries no digits and vanishes.
    """
    digits = ""
    index = 0
    for line in path.read_text().splitlines():
        digits += "".join(character for character in line if character in DIGITS + BLANKS)
        while len(digits) >= CELLS:
            index += 1
            yield Row(index, path.name, check(digits[:CELLS], index, path.name))
            digits = digits[CELLS:]
    if digits.strip(BLANKS):
        raise ValueError(f"{path.name}: {len(digits)} characters left over, not a whole puzzle")


def _csv_rows(source: Source, path: Path) -> Iterator[Row]:
    """Puzzles from a CSV with a header: one row per puzzle, named columns."""
    if source.puzzle is None:
        raise ValueError(f"{source.name}: a csv81 source needs a puzzle column")
    with path.open(newline="") as handle:
        for index, record in enumerate(csv.DictReader(handle), 1):
            puzzle = _column(record, source.puzzle)
            if puzzle is None:
                continue
            yield Row(
                index,
                path.name,
                check(puzzle, index, path.name),
                _solution(_column(record, source.solution), index, path.name),
                _rating(_column(record, source.rating)),
                _column(record, source.group),
            )


def _column(record: dict[str, str | None], name: str | None) -> str | None:
    """One field of a CSV record, blank as None; None when there is no such column."""
    if name is None:
        return None
    value = (record.get(name) or "").strip()
    return value or None


def _solution(value: str | None, index: int, origin: str) -> str | None:
    """A shipped solution once it is 81 digits; a wrong length is a broken row."""
    if value is None:
        return None
    if len(value) != CELLS or not set(value) <= set(DIGITS):
        raise ValueError(f"{origin} row {index}: the solution is not {CELLS} digits")
    return value


def _rating(value: str | None) -> float | None:
    """A source's own difficulty, kept as it states it; None when unusable.

    Sources scale difficulty differently and some leave it blank, so a rating
    is carried along and reported next to our grade, never fed back into it.
    """
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def by_group(row: Row) -> str:
    """Bucket key: the set the source says the puzzle came from."""
    return row.group or "?"


def by_rating(row: Row) -> str:
    """Bucket key: the whole part of the source's rating, a flat spread per step."""
    return "?" if row.rating is None else str(int(row.rating))


def pick(
    rows: Iterable[Row],
    count: int | None,
    seed: int,
    bucket: Callable[[Row], str] | None = None,
) -> list[Row]:
    """`count` rows per bucket, by reservoir sampling from `seed`; None keeps all.

    The same rows in the same order under the same seed always give the same
    sample, so a report is reproducible from the seed and the row indices in
    the sample file, which is why the file name carries both. Buckets stop one
    heavy group from crowding out the rest: `by_group` and `by_rating` above.
    """
    if count is not None and count < 1:
        raise ValueError("count must be at least 1")
    rng = random.Random(seed)
    picked: dict[str, list[Row]] = {}
    seen: dict[str, int] = {}
    for row in rows:
        key = "" if bucket is None else bucket(row)
        seen[key] = seen.get(key, 0) + 1
        chosen = picked.setdefault(key, [])
        if count is None or len(chosen) < count:
            chosen.append(row)
        else:
            slot = rng.randrange(seen[key])
            if slot < count:
                chosen[slot] = row
    return [row for key in sorted(picked) for row in picked[key]]


@dataclass
class Tally:
    """What became of the rows a source offered, for the summary table."""

    read: int = 0
    dropped: int = 0


def usable(rows: Iterable[Row], tally: Tally) -> Iterator[Row]:
    """Rows that can judge the engine: a solution that agrees with the givens.

    A row goes when the source ships no answer and the brute force cannot find
    exactly one, and when the answer it ships contradicts its own puzzle. Both
    mean the row cannot mark a solve right or wrong; dropping them quietly
    would inflate a solve rate, so `Tally` counts them out loud.

    Deriving answers is the expensive part of a fetch, by far: nothing here is
    cheap on a hard puzzle but the brute force proves uniqueness by refuting
    every other filling. That is why a built sample is kept and reused.
    """
    for row in rows:
        tally.read += 1
        solution = row.solution or solved(row.puzzle)
        if solution is None or not consistent(row.puzzle, solution):
            tally.dropped += 1
            continue
        yield replace(row, solution=solution)


def file_hashes(paths: Sequence[Path]) -> dict[str, str]:
    """The sha256 of each fetched file, as the manifest recorded it."""
    entries = read_manifest()
    return {relative(path): str(entries[relative(path)]["sha256"]) for path in paths}


@dataclass(frozen=True)
class Sample:
    """A sample on disk: where it is and how much of the source went into it."""

    path: Path
    rows: int
    read: int
    dropped: int
    reused: bool


def build(
    source: Source,
    count: int | None = None,
    seed: int = 42,
    bucket: str = "none",
    key: Callable[[Row], str] | None = None,
    *,
    force: bool = False,
) -> Sample:
    """The sample of `source` these options ask for, fetched and cached.

    A sample already on disk, built from the same files under the same seed,
    bucket and size, comes back as it is: the manifest says which file hashes
    it was built from, and `force` builds it again. Sources without answers
    make that worth doing, since proving their puzzles unique takes minutes.
    """
    paths = fetch(source, force=force)
    path = sample_path(source, count, seed, bucket)
    built = read_manifest().get(relative(path))
    same_files = built is not None and built.get("sources") == file_hashes(paths)
    if not force and same_files and path.exists():
        return Sample(
            path, int(built["rows"]), int(built["read"]), int(built["dropped"]), reused=True
        )
    tally = Tally()
    rows = pick(usable(all_rows(source, paths), tally), count, seed, key)
    store(path, rows)
    record(path, sources=file_hashes(paths), rows=len(rows), tally=tally)
    return Sample(path, len(rows), tally.read, tally.dropped, reused=False)


def record(path: Path, *, sources: dict[str, str], rows: int, tally: Tally) -> None:
    """Note in the manifest how a sample was built, so `build` can reuse it."""
    entries = read_manifest()
    entries[relative(path)] = {
        "sources": sources,
        "rows": rows,
        "read": tally.read,
        "dropped": tally.dropped,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    write_manifest(entries)


COLUMNS = ("index", "origin", "group", "rating", "puzzle", "solution")


def store(path: Path, rows: Sequence[Row]) -> None:
    """Write rows as CSV: everything a report needs to name a puzzle, nothing else."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow(
                (
                    row.index,
                    row.origin,
                    row.group or "",
                    "" if row.rating is None else f"{row.rating:g}",
                    row.puzzle,
                    row.solution or "",
                )
            )


def load(path: Path) -> list[Row]:
    """The rows `store` wrote, checked again: a cache edited by hand still parses."""
    with path.open(newline="") as handle:
        return [
            Row(
                int(record["index"]),
                record["origin"],
                check(record["puzzle"], int(record["index"]), record["origin"]),
                _solution(_column(record, "solution"), int(record["index"]), record["origin"]),
                _rating(_column(record, "rating")),
                _column(record, "group"),
            )
            for record in csv.DictReader(handle)
        ]


def sample_name(source: Source, count: int | None, seed: int, bucket: str) -> str:
    """A file name saying where a sample came from and how to get it again."""
    return f"sample-{source.name}-{bucket}-{'all' if count is None else count}-{seed}.csv"


def sample_path(source: Source, count: int | None, seed: int, bucket: str) -> Path:
    """Where `sample_name` says a sample lives, in the samples directory."""
    return cache_dir("samples") / sample_name(source, count, seed, bucket)
