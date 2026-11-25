"""Measure generic reach/cut on grids and paths, without puzzle-family search.

uv run python -m benchmark.graph_constraints --size 25 --runs 5
"""

import argparse
import statistics
import time

from csp.core import Kind, Model, rule_closure, rule_cut, rule_reach


def build(size: int, *, path: bool) -> Model:
    model = Model()
    nodes = {str(i): None for i in range(size * size)}
    pairs = (
        [(str(i), str(i + 1)) for i in range(size * size - 1)]
        if path
        else [
            (str(row * size + col), str(other_row * size + other_col))
            for row in range(size)
            for col in range(size)
            for other_row, other_col in ((row + 1, col), (row, col + 1))
            if other_row < size and other_col < size
        ]
    )
    edges = []
    for index, (left, right) in enumerate(pairs):
        var = f"edge{index}"
        yes, no = model.literal(var, True), model.literal(var, False)
        model.constrain(f"{var} domain", Kind.EXACTLY_ONE, (yes, no), defines=var)
        edges.append((left, right, yes))
    model.connect("network", nodes, edges)
    return model


def closure_case() -> Model:
    """A count choice that would saturate an internal link and remove both exits."""
    model = Model()
    options = [model.literal("internal count", value) for value in range(3)]
    model.constrain("count domain", Kind.EXACTLY_ONE, options, defines="internal count")
    presences = []
    for name in ("internal", "extra unit", "exit a", "exit b"):
        yes, no = model.literal(name, True), model.literal(name, False)
        model.constrain(f"{name} domain", Kind.EXACTLY_ONE, (yes, no), defines=name)
        presences.append(yes)
    internal, extra, exit_a, exit_b = presences
    model.constrain(
        "internal presence", Kind.COUNT, options[1:], allowed_counts=(1,), reified_by=internal
    )
    model.constrain(
        "extra presence", Kind.COUNT, options[2:], allowed_counts=(1,), reified_by=extra
    )
    model.constrain("a total", Kind.COUNT, (internal, extra, exit_a), allowed_counts=(2,))
    model.constrain("b total", Kind.COUNT, (internal, extra, exit_b), allowed_counts=(2,))
    model.connect(
        "network",
        {"a": None, "b": None, "c": None},
        (("a", "b", internal), ("a", "c", exit_a), ("b", "c", exit_b)),
    )
    model.assign(internal, "given", "present")
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=25)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.size < 2 or args.runs < 1:
        parser.error("size must be at least 2 and runs positive")
    for path in (False, True):
        model = build(args.size, path=path)
        for rule in (rule_reach, rule_cut):
            timings = []
            for _ in range(args.runs):
                twin = model.clone()
                start = time.perf_counter()
                changed = rule(twin)
                timings.append((time.perf_counter() - start) * 1000)
            print(
                f"{'path' if path else 'grid'} {args.size}x{args.size} "
                f"{rule.__name__}: {statistics.median(timings):.2f} ms; changed={changed}"
            )
    timings = []
    model = closure_case()
    for _ in range(args.runs):
        twin = model.clone()
        start = time.perf_counter()
        changed = rule_closure(twin)
        timings.append((time.perf_counter() - start) * 1000)
    print(f"count closure: {statistics.median(timings):.2f} ms; changed={changed}")


if __name__ == "__main__":
    main()
