"""Fetch the external Sudoku corpora into the ignored benchmark cache.

    uv run python -m benchmark.fetch --source all
    uv run python -m benchmark.fetch --source norvig
    uv run python -m benchmark.fetch --source sudoku-extreme --count 500 --seed 42
    uv run python -m benchmark.fetch --source sudoku-extreme --count 200 --bucket group

Nothing is written outside `benchmark/.cache/`, and nothing there is
committed: a sample is test input, not content. `manifest.json` records every
download (URL, byte size, sha256, UTC time) and every sample (which file
hashes went into it), and a sample's file name carries its source, bucket,
size and seed, so `--count 500 --seed 42` reproduces one exactly.

| Source | Puzzles | Solutions | Rating | From |
|---|---|---|---|---|
| norvig | 156 | no, the brute force supplies them | no | norvig.com easy50, top95, hardest |
| sudoku-extreme | 400 000+ | yes | yes | sapientinc on Hugging Face |

`--count` is the sample size *per bucket*, defaulting to the source's own idea
of a sample (every puzzle for norvig, 500 for sudoku-extreme). Buckets:

    none    one sample of the whole source
    group   per `source` column: puzzles2_17_clue, puzzles4_forum_hardest_1905, ...
    rating  per whole rating: a flat spread over the source's own scale

A row is dropped and counted when its answer cannot serve as an oracle: no
answer and none the brute force finds exactly one of, or an answer that
contradicts the puzzle's own givens. What is left lands in
`benchmark/.cache/samples/`, read back with `benchmark.corpus.load`.

A sample already on disk, built from the same files with the same options, is
reused; `--force` builds it again. That matters most for norvig, whose hardest
puzzles take the brute force minutes to prove unique, and a rebuild of the
same sample is otherwise paid again on every fetch.

`-m` rather than a path because `benchmark` is a package, so the sample format
and its reading have one definition, the one the tests import. Not wired yet,
in this same shape: radcliffe's three million via OpenML, Tatham's generated
grids, and ZebraLogic, which is gated on Hugging Face and will want `HF_TOKEN`.
"""

import argparse
import time
import urllib.error
from collections.abc import Callable

from benchmark import corpus

BUCKETS: dict[str, Callable[[corpus.Row], str] | None] = {
    "none": None,
    "group": corpus.by_group,
    "rating": corpus.by_rating,
}


def megabytes(source: corpus.Source) -> float:
    """What the source's files take in the cache, whether fetched now or earlier."""
    return sum(path.stat().st_size for path in (corpus.CACHE / source.name).glob("*")) / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=[*corpus.SOURCES, "all"], default="all")
    parser.add_argument("--count", type=int, default=None, help="rows per bucket")
    parser.add_argument("--seed", type=int, default=42, help="which rows the sample keeps")
    parser.add_argument("--bucket", choices=sorted(BUCKETS), default="none")
    parser.add_argument("--force", action="store_true", help="download and build again")
    args = parser.parse_args()

    names = list(corpus.SOURCES) if args.source == "all" else [args.source]
    print("| Source | Files (MB) | Rows read | Rows kept | Dropped | Reused | Seconds |")
    print("|---|---:|---:|---:|---:|---|---:|")
    samples: list[corpus.Sample] = []
    for name in names:
        source = corpus.SOURCES[name]
        count = source.default_count if args.count is None else args.count
        started = time.perf_counter()
        try:
            sample = corpus.build(
                source, count, args.seed, args.bucket, BUCKETS[args.bucket], force=args.force
            )
        except urllib.error.URLError as problem:
            raise SystemExit(f"error: {name}: {problem.reason}; check the network") from problem
        except (OSError, ValueError) as problem:
            raise SystemExit(f"error: {name}: {problem}") from problem
        seconds = time.perf_counter() - started
        print(
            f"| {name} | {megabytes(source):.1f} | {sample.read} | {sample.rows} "
            f"| {sample.dropped} | {'yes' if sample.reused else 'no'} | {seconds:.1f} |"
        )
        samples.append(sample)

    print("\nSamples in benchmark/.cache/samples, read back with benchmark.corpus.load:")
    for sample in samples:
        print(f"- {sample.path.name}: {sample.rows} rows")
    print("Downloads, hashes and sample recipes: benchmark/.cache/manifest.json")


if __name__ == "__main__":
    main()
