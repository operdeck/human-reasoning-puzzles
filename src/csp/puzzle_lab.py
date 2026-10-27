#!/usr/bin/env python3
"""Generate, rate, and search non-Murdoku puzzle examples with the repository solver."""

import argparse
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path
from typing import Any, cast

from csp import bruteforce, cli, fresh, report
from csp.core import Solver
from csp.puzzlefile import detect, read_sections

TIERS = {
    "easy": frozenset({"single", "count"}),
    "medium": frozenset({"relations", "subsumption", "cover2"}),
    "hard": frozenset({"cover3", "chains", "what_if"}),
}
# A board with fewer open cells than this share is a prefilled exercise, not a puzzle.
PREFILLED_OPEN_SHARE = 0.25


@dataclass(frozen=True)
class Rating:
    path: str
    family: str
    solved: bool
    solutions: str
    grade: str
    tier: str
    rule_firings: dict[str, int]
    placements: int
    eliminations: int
    initial_open: int


def family_of(text: str) -> str:
    """The display-level family, retaining aliases such as DogDoku and Tango."""
    section = read_sections(text).get("Family")
    return section[0].casefold() if section else detect(text)


def rate(text: str, path: str = "<memory>") -> Rating:
    """Rate with the deductive solver and check uniqueness independently."""
    family = family_of(text)
    if family == "murdoku":
        raise ValueError("Murdoku has its own puzzle tools and is out of scope here")
    kind = detect(text)
    model = cli.load(text, kind).model
    fired: list[str] = []
    solving_model = model.clone()
    solve_start = len(solving_model.log)
    initial_open = sum(solving_model.chosen(var) is None for var in solving_model.variables)
    result = Solver(solving_model).solve(on_step=lambda rule, steps: fired.append(rule))
    grade = report.grade(fired) if result.solved else "unsolved"
    if result.solved:
        solutions = bruteforce.solutions(text, kind, limit=2)
        count = "unique" if len(solutions) == 1 else "multiple" if solutions else "none"
    else:
        count = "not checked"
    tier = next((name for name, grades in TIERS.items() if grade in grades), "unrated")
    variable_count = len(model.variables)
    board_size = int(variable_count**0.5)
    open_share = initial_open / max(1, variable_count)
    if grade == "relations" and (
        (family in {"calcudoku", "kakurasu", "tango"} and variable_count <= 16)
        or (family == "logicgrid" and variable_count <= 9)
    ):
        tier = "easy"
    if grade == "relations" and family in {"binairo", "tango"}:
        tier = "easy" if open_share <= 0.5 else "medium"
    if grade == "count" and family == "battleships":
        tier = "easy" if variable_count <= 16 else "medium"
    if family in {"suguru", "tectonic"} and grade in {"single", "count"}:
        givens = sum(
            token not in {".", "?"}
            for line in read_sections(text).get("Givens", [])
            for token in line.split()
        )
        density = givens / max(1, variable_count)
        if board_size < 6 or density >= 0.68:
            tier = "easy"
        elif density >= 0.48:
            tier = "medium"
        elif density >= 0.3:
            tier = "hard"
    if initial_open < 2 or not any(fired) or open_share < PREFILLED_OPEN_SHARE:
        tier = "trivial"
    return Rating(
        path=path,
        family=family,
        solved=result.solved,
        solutions=count,
        grade=grade,
        tier=tier if result.solved and count == "unique" else "invalid",
        rule_firings=dict(Counter(fired)),
        placements=sum(step.asserted for step in solving_model.log[solve_start:]),
        eliminations=sum(not step.asserted for step in solving_model.log[solve_start:]),
        initial_open=initial_open,
    )


def _replace_section(
    text: str, section: str, change: Callable[[str], str | list[str]]
) -> tuple[str, bool]:
    lines = text.splitlines()
    out: list[str] = []
    active = False
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped.endswith(":") and " " not in stripped[:-1]:
            active = stripped[:-1] == section
            out.append(line)
            continue
        if active and stripped and not stripped.startswith("#"):
            replacement = change(line)
            if replacement != line:
                changed = True
            out.extend(replacement if isinstance(replacement, list) else [replacement])
        else:
            out.append(line)
    return "\n".join(out) + "\n", changed


def _grid_masker(rng: random.Random, fraction: float) -> Callable[[str], str]:
    def change(line: str) -> str:
        tokens = line.split()
        values = [i for i, token in enumerate(tokens) if token not in {".", "?", "W"}]
        if not values:
            return line
        chosen = [i for i in values if rng.random() < fraction]
        for i in chosen:
            tokens[i] = "."
        return " ".join(tokens)

    return change


def _mutate(text: str, rng: random.Random, fraction: float | None = None) -> str | None:
    """Remove a random subset of explicit clues without changing rule semantics."""
    sections = read_sections(text)
    family = family_of(text)
    fraction = fraction if fraction is not None else rng.uniform(0.04, 0.22)
    candidates: list[tuple[str, Callable[[str], str | list[str]]]] = []

    if family == "sudoku" and "Givens" not in sections:
        rows = text.splitlines()
        found = False
        for index, row in enumerate(rows):
            is_grid = re.fullmatch(r"[\d.0|+\-\s]+", row.strip())
            has_clue = any(ch.isdigit() and ch != "0" for ch in row)
            if is_grid and has_clue:
                tokens = row.split()
                for i, token in enumerate(tokens):
                    if token not in {".", "0"} and rng.random() < fraction:
                        tokens[i] = "."
                        found = True
                rows[index] = " ".join(tokens)
        return "\n".join(rows) + "\n" if found else None

    if "Givens" in sections:
        lines = sections["Givens"]
        if lines and any(re.fullmatch(r"\S+\s+r\d+c\d+", line) for line in lines):
            candidates.append(("Givens", lambda line: [] if rng.random() < fraction else line))
        else:
            candidates.append(("Givens", _grid_masker(rng, fraction)))
    if family == "minesweeper":
        candidates.append(("Clues", _grid_masker(rng, fraction)))
    elif family == "logicgrid":
        candidates.append(("Clues", lambda line: [] if rng.random() < fraction else line))
    if family in {"tango", "binairo"}:
        candidates.extend(
            (name, lambda line: [] if rng.random() < fraction else line)
            for name in ("Equal", "Different")
            if name in sections
        )
    if family in {"akari", "lightup"} and "Grid" in sections:

        def hide_akari_counts(line: str) -> str:
            if rng.random() < fraction:
                return re.sub(r"(?<!\S)[0-4](?!\S)", "W", line)
            return line

        candidates.append(("Grid", hide_akari_counts))
    if family == "futoshiki":
        for name in ("Signs", "Givens"):
            if name in sections:
                candidates.append((name, lambda line: [] if rng.random() < fraction else line))

    rng.shuffle(candidates)
    for section, transform in candidates:
        candidate, changed = _replace_section(text, section, transform)
        if changed:
            return candidate
    return None


def _add_givens(
    text: str,
    family: str,
    solution: Mapping[str, Any],
    rng: random.Random,
    fraction: float,
) -> str | None:
    """Add solution values as givens for grid families, or true clues for logic grids."""
    if family == "minesweeper":
        return _add_minesweeper_clues(text, solution, rng, fraction)
    if family in {"akari", "lightup"}:
        return _add_akari_clues(text, solution, rng, fraction)
    if family == "tents":
        return _regenerate_tents(text, solution, rng)
    if family in {"battleships", "kakurasu"}:
        return _regenerate_count_grid(text, family, solution, rng)
    if family == "queens" or family == "dogdoku":
        existing = read_sections(text).get("Givens", [])
        regions = {str(region): cell for region, cell in solution.items()}
        absent = [
            f"{region} {cell}"
            for region, cell in regions.items()
            if f"{region} {cell}" not in existing
        ]
        chosen = [line for line in absent if rng.random() < fraction]
        if not chosen and absent:
            chosen = [rng.choice(absent)]
        if not chosen:
            return None
        return _append_section(text, "Givens", chosen)

    if family == "logicgrid":
        categories = read_sections(text).get("Categories", [])
        groups = [line.split(":", 1)[1].split() for line in categories if ":" in line]
        pairs = [
            (left, right)
            for i, group in enumerate(groups)
            for other in groups[i + 1 :]
            for left in group
            for right in other
        ]
        clues = read_sections(text).get("Clues", [])
        candidates = []
        for left, right in pairs:
            same = solution.get(left) == solution.get(right)
            clue = f"{'same' if same else 'different'} {left} {right}"
            if clue not in clues:
                candidates.append(clue)
        chosen = [clue for clue in candidates if rng.random() < fraction]
        if not chosen and candidates:
            chosen = [rng.choice(candidates)]
        return _append_section(text, "Clues", chosen) if chosen else None

    if family not in {
        "sudoku",
        "calcudoku",
        "futoshiki",
        "suguru",
        "tectonic",
        "binairo",
        "tango",
        "starbattle",
    }:
        return None

    cells = {key: value for key, value in solution.items() if re.fullmatch(r"r\d+c\d+", key)}
    if not cells:
        return None
    size = max(int(match.group(1)) for key in cells if (match := re.fullmatch(r"r(\d+)c\d+", key)))
    selected = {key for key in cells if rng.random() < fraction}
    grid_section = "Grid" if family == "futoshiki" else "Givens"
    selected |= _existing_given_cells(text, size, grid_section)
    if not selected:
        selected = {rng.choice(list(cells))}
    if family == "sudoku" and "Givens" not in read_sections(text):
        rows = text.splitlines()
        row_index = 0
        for index, line in enumerate(rows):
            if re.fullmatch(r"[\d.0|+\-\s]+", line.strip()):
                tokens = line.split()
                for c, _token in enumerate(tokens, 1):
                    cell = f"r{row_index + 1}c{c}"
                    if cell in selected:
                        tokens[c - 1] = str(cells[cell])
                rows[index] = " ".join(tokens)
                row_index += 1
        return "\n".join(rows) + "\n"

    if family == "starbattle":
        matrix = [
            " ".join(
                ("*" if cells[f"r{r}c{c}"] else ".") if f"r{r}c{c}" in selected else "?"
                for c in range(1, size + 1)
            )
            for r in range(1, size + 1)
        ]
    else:
        matrix = [
            " ".join(
                _display_value(cells[f"r{r}c{c}"]) if f"r{r}c{c}" in selected else "."
                for c in range(1, size + 1)
            )
            for r in range(1, size + 1)
        ]
    return _replace_or_append_section(text, grid_section, matrix)


def _generate_calcudoku(source: str, solution: Mapping[str, Any], rng: random.Random) -> str | None:
    from csp.calcudoku import cell_name, parse

    puzzle = parse(source)
    size = puzzle.size
    multi_cell_cages = [cage for cage in puzzle.cages if len(cage.cells) > 1]
    if not multi_cell_cages:
        return None
    rng.shuffle(multi_cell_cages)
    kept = []
    kept_cells: set[tuple[int, int]] = set()
    for cage in multi_cell_cages:
        if len(kept_cells) >= max(4, min(8, size)):
            break
        kept.append(cage)
        kept_cells.update(cage.cells)
    cages = [(list(cage.cells), cage.label) for cage in kept] + [
        ([cell], str(solution[cell_name(cell)]))
        for cage in puzzle.cages
        if cage not in kept
        for cell in cage.cells
    ]

    ids = [f"cage{index}" for index in range(len(cages))]
    grid = [["" for _ in range(size)] for _ in range(size)]
    cage_lines = []
    for cage_id, (cells, rule) in zip(ids, cages, strict=True):
        cage_lines.append(f"{cage_id}: {rule}")
        for row, col in cells:
            grid[row][col] = cage_id
    return (
        f"Size: {size}\nGrid:\n"
        + "\n".join(" ".join(row) for row in grid)
        + "\nCages:\n"
        + "\n".join(cage_lines)
        + "\n"
    )


def _generate_minesweeper(text: str, rng: random.Random, tier: str) -> str:
    sections = read_sections(text)
    size = int(sections["Size"][0])
    mine_count = int(sections["TotalMines"][0])
    mines = set(rng.sample(range(size * size), mine_count))
    visibility = {"easy": 0.9, "medium": 0.65, "hard": 0.4}[tier]
    rows = []
    for row in range(size):
        cells = []
        for col in range(size):
            index = row * size + col
            if index in mines or rng.random() > visibility:
                cells.append(".")
                continue
            count = sum(
                (near_row * size + near_col) in mines
                for near_row in range(max(0, row - 1), min(size, row + 2))
                for near_col in range(max(0, col - 1), min(size, col + 2))
                if (near_row, near_col) != (row, col)
            )
            cells.append(str(count))
        rows.append(" ".join(cells))
    return (
        f"Family: minesweeper\nSize: {size}\nClues:\n"
        + "\n".join(rows)
        + f"\nTotalMines:\n{mine_count}\n"
    )


def _generate_suguru(
    text: str, solution: Mapping[str, Any], rng: random.Random, tier: str
) -> str | None:
    sections = read_sections(text)
    size = int(sections["Size"][0])
    fraction = {"easy": 0.82, "medium": 0.64, "hard": 0.5}[tier]
    fraction = min(0.9, max(0.35, fraction + rng.uniform(-0.05, 0.05)))
    matrix = [
        " ".join(
            _display_value(solution[f"r{row}c{col}"]) if rng.random() < fraction else "."
            for col in range(1, size + 1)
        )
        for row in range(1, size + 1)
    ]
    return _replace_or_append_section(text, "Givens", matrix)


def _add_minesweeper_clues(
    text: str, solution: Mapping[str, Any], rng: random.Random, fraction: float
) -> str | None:
    sections = read_sections(text)
    size = int(sections["Size"][0])
    grid = [line.split() for line in sections["Clues"]]
    mines = {
        (row, col)
        for row in range(size)
        for col in range(size)
        if solution.get(f"r{row + 1}c{col + 1}", False)
    }
    hidden = [
        (row, col)
        for row in range(size)
        for col in range(size)
        if grid[row][col] == "." and (row, col) not in mines and rng.random() < fraction
    ]
    if not hidden:
        return None
    for row, col in hidden:
        grid[row][col] = str(
            sum(
                (near_row, near_col) in mines
                for near_row in range(max(0, row - 1), min(size, row + 2))
                for near_col in range(max(0, col - 1), min(size, col + 2))
                if (near_row, near_col) != (row, col)
            )
        )
    return _replace_or_append_section(text, "Clues", [" ".join(row) for row in grid])


def _add_akari_clues(
    text: str, solution: Mapping[str, Any], rng: random.Random, fraction: float
) -> str | None:
    sections = read_sections(text)
    size = int(sections["Size"][0])
    grid = [line.split() for line in sections["Grid"]]
    bulbs = {
        (row, col)
        for row in range(size)
        for col in range(size)
        if solution.get(f"r{row + 1}c{col + 1}", False)
    }
    walls = [
        (row, col)
        for row in range(size)
        for col in range(size)
        if grid[row][col] == "W" and rng.random() < fraction
    ]
    if not walls:
        return None
    for row, col in walls:
        grid[row][col] = str(
            sum(
                (near_row, near_col) in bulbs
                for near_row, near_col in (
                    (row - 1, col),
                    (row + 1, col),
                    (row, col - 1),
                    (row, col + 1),
                )
                if 0 <= near_row < size and 0 <= near_col < size
            )
        )
    return _replace_or_append_section(text, "Grid", [" ".join(row) for row in grid])


def _regenerate_tents(text: str, solution: Mapping[str, Any], rng: random.Random) -> str | None:
    sections = read_sections(text)
    size = int(sections["Size"][0])
    tents = {
        (row, col)
        for row in range(size)
        for col in range(size)
        if solution.get(f"r{row + 1}c{col + 1}", False)
    }
    if not tents:
        return None
    candidate_trees = {}
    for tent in tents:
        row, col = tent
        options = [
            cell
            for cell in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
            if 0 <= cell[0] < size
            and 0 <= cell[1] < size
            and cell not in tents
            and sum(
                (cell[0] + dr, cell[1] + dc) in tents
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                if 0 <= cell[0] + dr < size and 0 <= cell[1] + dc < size
            )
            == 1
        ]
        rng.shuffle(options)
        candidate_trees[tent] = options

    ordered = sorted(tents, key=lambda cell: len(candidate_trees[cell]))

    def match(index: int, chosen: set[tuple[int, int]]) -> set[tuple[int, int]] | None:
        if index == len(ordered):
            return chosen
        for tree in candidate_trees[ordered[index]]:
            if tree in chosen or any(
                abs(tree[0] - other[0]) + abs(tree[1] - other[1]) == 1 for other in chosen
            ):
                continue
            result = match(index + 1, chosen | {tree})
            if result is not None:
                return result
        return None

    trees = match(0, set())
    if trees is None:
        return None
    board = [["." for _ in range(size)] for _ in range(size)]
    for row, col in trees:
        board[row][col] = "T"
    generated = _replace_or_append_section(text, "Trees", [" ".join(row) for row in board])
    if generated == text:
        return None
    return generated


def _regenerate_count_grid(
    text: str, family: str, solution: Mapping[str, Any], rng: random.Random
) -> str | None:
    size = int(read_sections(text)["Size"][0])
    row_order = rng.sample(range(size), size)
    column_order = rng.sample(range(size), size)
    cells = [
        [
            bool(solution.get(f"r{row_order[row] + 1}c{column_order[col] + 1}", False))
            for col in range(size)
        ]
        for row in range(size)
    ]
    if family == "battleships":
        row_counts = [sum(row) for row in cells]
        column_counts = [sum(cells[row][col] for row in range(size)) for col in range(size)]
        return (
            f"Family: battleships\nSize: {size}\nRowCounts:\n{' '.join(map(str, row_counts))}"
            f"\nColumnCounts:\n{' '.join(map(str, column_counts))}\n"
        )
    row_sums = [sum((col + 1) * cells[row][col] for col in range(size)) for row in range(size)]
    column_sums = [sum((row + 1) * cells[row][col] for row in range(size)) for col in range(size)]
    return (
        f"Family: kakurasu\nSize: {size}\nRowSums:\n{' '.join(map(str, row_sums))}"
        f"\nColumnSums:\n{' '.join(map(str, column_sums))}\n"
    )


def _display_value(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _append_section(text: str, section: str, lines: list[str]) -> str:
    if not lines:
        return text
    source = text.splitlines()
    output: list[str] = []
    active = False
    found = False
    for line in source:
        stripped = line.strip()
        if stripped.endswith(":") and " " not in stripped[:-1]:
            if active:
                output.extend(lines)
                active = False
            active = stripped[:-1] == section
            found |= active
        output.append(line)
    if active:
        output.extend(lines)
    elif not found:
        output.extend(["", f"{section}:", *lines])
    return "\n".join(output) + "\n"


def _replace_or_append_section(text: str, section: str, lines: list[str]) -> str:
    source = text.splitlines()
    output: list[str] = []
    active = False
    found = False
    for line in source:
        stripped = line.strip()
        if stripped.endswith(":") and " " not in stripped[:-1]:
            active = stripped[:-1] == section
            if active:
                found = True
                output.append(line)
                output.extend(lines)
                continue
        if active:
            continue
        output.append(line)
    return "\n".join(output) + "\n" if found else _append_section(text, section, lines)


def _existing_given_cells(text: str, size: int, section: str) -> set[str]:
    lines = read_sections(text).get(section, [])
    cells: set[str] = set()
    for row, line in enumerate(lines[:size], 1):
        tokens = line.split()
        if len(tokens) != size:
            continue
        for col, token in enumerate(tokens, 1):
            if token not in {".", "?"}:
                cells.add(f"r{row}c{col}")
    return cells


def _paths(patterns: Sequence[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        path = Path(pattern)
        if path.is_file():
            found.add(path)
        elif path.is_dir():
            found.update(path.rglob("*.txt"))
        else:
            found.update(Path(item) for item in glob(pattern, recursive=True))
    return sorted(found)


def _rate_command(args: argparse.Namespace) -> int:
    path = Path(args.puzzle)
    try:
        result = rate(path.read_text(), str(path))
    except (ValueError, KeyError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 2
    output = asdict(result)
    print(
        json.dumps(output, sort_keys=True)
        if args.json
        else (
            f"{result.family}: {result.tier} ({result.grade}); "
            f"{result.solutions} solution; {result.placements} placements, "
            f"{result.eliminations} eliminations"
        )
    )
    return 0 if result.tier != "invalid" else 1


def _search_command(args: argparse.Namespace) -> int:
    accepted = []
    for path in _paths(args.paths):
        try:
            text = path.read_text()
            if args.family and family_of(text) != args.family.casefold():
                continue
            result = rate(text, str(path))
        except (ValueError, KeyError):
            continue
        if result.tier == args.tier:
            accepted.append(result)
    accepted.sort(key=lambda item: (item.grade, item.placements, item.path))
    if args.json:
        print(json.dumps([asdict(item) for item in accepted], indent=2))
    else:
        for item in accepted:
            print(f"{item.path}: {item.family} {item.tier} ({item.grade})")
        print(f"{len(accepted)} matching puzzle(s)")
    return 0 if accepted else 1


def _generate_command(args: argparse.Namespace) -> int:
    source = Path(args.source)
    source_text = source.read_text()
    original = source_text
    if family_of(original) == "murdoku":
        print("Murdoku has its own puzzle tools and is out of scope here", file=sys.stderr)
        return 2
    if args.as_family:
        aliases = {
            "queens": "queens",
            "dogdoku": "queens",
            "binairo": "binairo",
            "tango": "binairo",
        }
        try:
            target_kind = detect(f"Family: {args.as_family}\n")
        except ValueError as error:
            print(f"{source}: {error}", file=sys.stderr)
            return 2
        if target_kind != detect(original) or args.as_family not in aliases:
            print(
                f"{args.as_family} is not a compatible display family for {source}", file=sys.stderr
            )
            return 2
        family_line = re.compile(r"(?m)^Family:\s*\S+\s*$")
        replacement = f"Family: {args.as_family}"
        original = (
            family_line.sub(replacement, original)
            if family_line.search(original)
            else f"{replacement}\n{original}"
        )
    kind = detect(original)
    try:
        solutions = bruteforce.solutions(original, kind, limit=1)
    except (ValueError, KeyError) as error:
        print(f"{source}: could not get a source solution: {error}", file=sys.stderr)
        return 2
    if not solutions:
        print(f"{source}: has no solution to use as a generation seed", file=sys.stderr)
        return 2
    rng = random.Random(args.seed)
    for attempt in range(args.attempts):
        family = family_of(original)
        fraction = {
            "easy": rng.uniform(0.02, 0.12),
            "medium": rng.uniform(0.12, 0.38),
            "hard": rng.uniform(0.28, 0.72),
        }[args.tier]
        candidate: str | None
        if args.as_family and attempt == 0:
            candidate = original
        elif family == "calcudoku" and args.tier == "easy":
            candidate = _generate_calcudoku(original, solutions[0], rng)
        elif family == "minesweeper":
            candidate = _generate_minesweeper(original, rng, args.tier)
        elif family in {"suguru", "tectonic"}:
            candidate = _generate_suguru(original, solutions[0], rng, args.tier)
        elif args.tier == "hard" or attempt % 2 == 0:
            candidate = _mutate(original, rng, fraction)
        else:
            candidate = _add_givens(original, family, solutions[0], rng, rng.uniform(0.15, 0.7))
        if candidate is None or (candidate == original and not (args.as_family and attempt == 0)):
            candidate = _mutate(original, rng, fraction)
        if candidate is None or (candidate == original and not (args.as_family and attempt == 0)):
            candidate = _add_givens(original, family, solutions[0], rng, rng.uniform(0.15, 0.7))
        if candidate is None:
            print(f"{source}: no clue-removal strategy is available", file=sys.stderr)
            return 2
        if candidate == original and (not args.as_family or original == source_text):
            continue
        try:
            result = rate(candidate, f"{source} (candidate {attempt + 1})")
        except (ValueError, KeyError):
            continue
        if result.tier != args.tier:
            continue
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(candidate)
        print(f"wrote {output}: {result.family} {result.tier} ({result.grade}), unique")
        return 0
    print(
        f"no unique {args.tier} candidate found in {args.attempts} attempts "
        f"(seed {args.seed}); source was not changed",
        file=sys.stderr,
    )
    return 1


def _audit_command(args: argparse.Namespace) -> int:
    from csp import audit

    items = audit.profiles(audit.puzzle_files(args.paths))
    found = audit.audit(items)
    if args.json:
        print(
            json.dumps(
                {
                    "shared_solutions": [[str(p) for p in g] for g in found.shared_solutions],
                    "shared_layouts": [[str(p) for p in g] for g in found.shared_layouts],
                    "out_of_order": {
                        name: [{"path": str(m.path), "level": m.label} for m in members]
                        for name, members in found.out_of_order.items()
                    },
                },
                indent=2,
            )
        )
        return 0 if found.clean else 1
    for title, groups in (
        ("Shared solution", found.shared_solutions),
        ("Shared layout", found.shared_layouts),
    ):
        for group in groups:
            print(f"{title}: {', '.join(path.name for path in group)}")
    for name, members in found.out_of_order.items():
        listed = ", ".join(f"{m.path.name} {m.label}" for m in members)
        print(f"Not easy to hard: {name}: {listed}")
    if found.clean:
        print(f"{len(items)} puzzles: distinct solutions and layouts, each section easy to hard")
    return 0 if found.clean else 1


def _fresh_command(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    for attempt in range(args.attempts):
        candidate = fresh.fresh(
            args.family, args.size, rng, args.open_share, args.comment, args.tier
        )
        if candidate is None:
            continue
        result = rate(candidate, f"fresh {args.family} (candidate {attempt + 1})")
        if result.tier != args.tier:
            continue
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(candidate)
        print(f"wrote {output}: {result.family} {result.tier} ({result.grade}), unique")
        return 0
    print(
        f"no unique {args.tier} {args.family} found in {args.attempts} attempts (seed {args.seed})",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rate_parser = commands.add_parser("rate", help="rate one puzzle and verify uniqueness")
    rate_parser.add_argument("puzzle")
    rate_parser.add_argument("--json", action="store_true")
    rate_parser.set_defaults(run=_rate_command)

    search_parser = commands.add_parser("search", help="find rated puzzles in files or globs")
    search_parser.add_argument("paths", nargs="+")
    search_parser.add_argument("--family")
    search_parser.add_argument("--tier", choices=tuple(TIERS), required=True)
    search_parser.add_argument("--json", action="store_true")
    search_parser.set_defaults(run=_search_command)

    generate_parser = commands.add_parser(
        "generate", help="generate or search for rated variants of a seed"
    )
    generate_parser.add_argument("source")
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--tier", choices=tuple(TIERS), required=True)
    generate_parser.add_argument("--as-family", choices=("queens", "dogdoku", "binairo", "tango"))
    generate_parser.add_argument("--seed", type=int, default=0)
    generate_parser.add_argument("--attempts", type=int, default=100)
    generate_parser.set_defaults(run=_generate_command)

    fresh_parser = commands.add_parser(
        "fresh", help="build an original board with its own solution and rate it"
    )
    fresh_parser.add_argument("family", choices=fresh.FAMILIES)
    fresh_parser.add_argument("--size", type=int, required=True)
    fresh_parser.add_argument("--output", required=True)
    fresh_parser.add_argument("--tier", choices=tuple(TIERS), required=True)
    fresh_parser.add_argument(
        "--open-share",
        type=float,
        default=0.5,
        help="empty-cell share for Binairo/Tango or unknown-cell share for Minesweeper",
    )
    fresh_parser.add_argument("--comment", default="")
    fresh_parser.add_argument("--seed", type=int, default=0)
    fresh_parser.add_argument("--attempts", type=int, default=10)
    fresh_parser.set_defaults(run=_fresh_command)

    audit_parser = commands.add_parser(
        "audit",
        help="find shared solutions or layouts and sections not ordered easy to hard",
    )
    audit_parser.add_argument("paths", nargs="+", help="puzzle files or folders, e.g. examples")
    audit_parser.add_argument("--json", action="store_true")
    audit_parser.set_defaults(run=_audit_command)

    args = parser.parse_args(argv)
    return cast(Callable[[argparse.Namespace], int], args.run)(args)


if __name__ == "__main__":
    raise SystemExit(main())
