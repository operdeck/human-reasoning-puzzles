"""Zebra-style logic grids expressed as item-to-position variables and relations."""

from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections


@dataclass(frozen=True)
class Clue:
    kind: str
    first: str
    second: str

    @property
    def label(self) -> str:
        return f"{self.kind} {self.first} {self.second}"

    def holds(self, first: int, second: int) -> bool:
        if self.kind == "same":
            return first == second
        if self.kind == "different":
            return first != second
        if self.kind in ("left_of", "before"):
            return first < second
        return abs(first - second) == 1


@dataclass(frozen=True)
class Puzzle:
    size: int
    categories: dict[str, tuple[str, ...]]
    category_of: dict[str, str]
    clues: tuple[Clue, ...]


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size", "Categories"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "logicgrid":
        raise ValueError("Family must be 'logicgrid'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Logic grids need at least two positions")
    categories: dict[str, tuple[str, ...]] = {}
    category_of: dict[str, str] = {}
    for line in sections["Categories"]:
        name, separator, items = line.partition(":")
        category, members = name.strip(), tuple(items.split())
        if not separator or not category or not members:
            raise ValueError(f"bad category {line!r}, expected 'category: item ...'")
        if category in categories:
            raise ValueError(f"category {category!r} is defined more than once")
        if len(members) != size:
            raise ValueError(f"category {category!r} needs {size} items, got {len(members)}")
        if len(set(members)) != len(members):
            raise ValueError(f"category {category!r} repeats an item")
        for item in members:
            if item in category_of:
                raise ValueError(f"item {item!r} appears in more than one category")
            category_of[item] = category
        categories[category] = members
    if len(categories) < 2:
        raise ValueError("Logic grids need at least two categories")

    allowed = {"same", "different", "left_of", "before", "next_to"}
    clues: list[Clue] = []
    for line in sections.get("Clues", []):
        parts = line.split()
        if len(parts) != 3 or parts[0] not in allowed:
            raise ValueError(f"bad logic-grid clue {line!r}")
        if parts[1] not in category_of or parts[2] not in category_of:
            raise ValueError(f"logic-grid clue {line!r} names an unknown item")
        clues.append(Clue(parts[0], parts[1], parts[2]))
    if not clues:
        raise ValueError("Clues: must contain at least one relation")
    return Puzzle(size, categories, category_of, tuple(clues))


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    model = Model()
    positions = range(1, puzzle.size + 1)
    for category, items in puzzle.categories.items():
        for item in items:
            model.constrain(
                f"{item} has one position",
                Kind.EXACTLY_ONE,
                [model.literal(item, position) for position in positions],
                defines=item,
                family="each item has one position",
            )
        for position in positions:
            model.constrain(
                f"one {category} at position {position}",
                Kind.EXACTLY_ONE,
                [model.literal(item, position) for item in items],
                family="one item per category and position",
            )
    for clue in puzzle.clues:
        model.relate(
            clue.label,
            (clue.first, clue.second),
            clue.holds,
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {(step.var, step.value) for step in steps if step.asserted}
    widths = {
        category: max(len(category), *(len(item) for item in items))
        for category, items in puzzle.categories.items()
    }
    out = [
        f"\n{title}",
        "Position " + " ".join(str(position) for position in range(1, puzzle.size + 1)),
    ]
    for category, items in puzzle.categories.items():
        out.append(f"{category}: ")
        for item in items:
            chosen = model.chosen(item)
            if chosen is None:
                options = "/".join(str(model.value_of(literal)) for literal in model.options(item))
                mark = options or "-"
            else:
                mark = str(chosen)
            display = f"  {item:<{widths[category]}} {mark}"
            if (item, chosen) in changed:
                display = f"\033[38;5;21m{display}\033[0m"
            out.append(display)
    return "\n".join(out)
