"""Cluedo-style room puzzles: every person takes one room, rooms have capacities.

The board is a plan of rooms rather than a grid of squares. Several people may
share a room, a room may stay empty, and a room's capacity caps how many fit.
Clues talk about rooms through their properties ("a room with a mirror"), about
company ("was not alone"), about counts ("exactly one person in the garden")
and about direction ("directly behind"). The people are the variables and a
room is a value, so every clue becomes a count or a relation over a handful of
variables: a small model that still asks real questions.

A puzzle file:

    Family: rooms
    Language: en
    Plan:
    a a b
    c d e
    Rooms:
    a: 3 #CBE6B9 living room
    b: 1 #FADFB5 hall
    c: 2 #C4DCF2 kitchen
    d: 1 #F4CBC3 study
    e: 2 #E8D5F2 attic
    Tags:
    window: a d e
    People:
    Ada
    Ben
    Cleo
    Dirk
    Clues:
    Ada in area:c
    not (Ben in area:window)
    count (people in area:a) = 2
    Cleo alone
    Ada together Cleo
    Ben dir:up Ada
    Dirk beside Cleo
    exactly 1 of (Ben in area:e; Dirk in area:e)

`Plan:` positions the rooms on a grid for direction clues; a room may cover
several plan cells. A clue may end in `| wording` to replace the generated
sentence, and `Words:` renames a room or a group in the text the solver writes
("a: the living room").
"""

import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .core import Kind, Model, Step
from .puzzlefile import read_sections

STEPS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
STEP_WORDS = {
    "en": {
        "up": "directly behind",
        "down": "directly in front of",
        "left": "directly to the left of",
        "right": "directly to the right of",
    },
    "nl": {
        "up": "direct achter",
        "down": "direct voor",
        "left": "direct links van",
        "right": "direct rechts van",
    },
}
COUNT_WORDS = {
    "en": {"=": "exactly", "<": "fewer than", ">": "more than", "<=": "at most", ">=": "at least"},
    "nl": {"=": "precies", "<": "minder dan", ">": "meer dan", "<=": "hoogstens", ">=": "minstens"},
}
NUMBERS = {
    "en": ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"),
    "nl": ("geen", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien"),
}
# The names the model gives its constraints and relations, in the puzzle's language,
# so `--show-model`, `--step` and the worked solution read in the same language.
LABELS = {
    "en": {
        "room": "{person}'s room",
        "capacity": "{room} holds at most {capacity}",
        "one_room": "each person is in one room",
        "capacities": "room capacity",
        "clue": "a clue",
        "sharing": "sharing a room",
        "shared": "{first} and {second} share a room",
        "state": "{name} state",
        "together_rule": "people who are together are in the same room",
        "not": "it is not the case that {sentence}",
    },
    "nl": {
        "room": "de kamer van {person}",
        "capacity": "{room} heeft plaats voor hoogstens {capacity}",
        "one_room": "iedereen staat in één kamer",
        "capacities": "capaciteit per kamer",
        "clue": "een aanwijzing",
        "sharing": "samen in een kamer",
        "shared": "{first} en {second} delen een kamer",
        "state": "{name}: toestand",
        "together_rule": "wie samen zit, zit in dezelfde kamer",
        "not": "het is niet zo dat {sentence}",
    },
}


def labels(language: str) -> dict[str, str]:
    """The solver's own names for this family, in the puzzle's language."""
    return LABELS.get(language, LABELS["en"])


_COUNT = re.compile(r"^count\s*\(\s*people in area:(\S+?)\s*\)\s*(<=|>=|=|<|>)\s*(\d+)$")
_IN = re.compile(r"^(\S+)\s+in\s+area:(\S+)$")
_ALONE = re.compile(r"^(\S+)\s+alone$")
_PAIR = re.compile(r"^(\S+)\s+(together|apart)\s+(\S+)$")
_BESIDE = re.compile(r"^(\S+)\s+beside\s+(\S+)$")
_DIRECTION = re.compile(r"^(\S+)\s+dir:(up|down|left|right)\s+(\S+)$")
_CHOICE = re.compile(r"^exactly\s+(\d+)\s+of\s*\((.*)\)$")
_ROOM_LINE = re.compile(r"^(\S+)\s*:\s*(\d+)\s+(#[0-9A-Fa-f]{6})\s*(.*)$")


@dataclass(frozen=True)
class Room:
    """One room: its capacity, its colour and the plan cells it covers."""

    key: str
    label: str
    capacity: int
    colour: str
    cells: tuple[tuple[int, int], ...] = ()

    @property
    def title(self) -> str:
        return self.label[:1].upper() + self.label[1:]


class Clue(Protocol):
    """What a clue says: a test on a full placement, and a sentence for it."""

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        """Whether a placement (person -> room key) satisfies the clue."""

    def describe(self, puzzle: "Puzzle") -> str:
        """The clue as one sentence in the puzzle's language."""


@dataclass(frozen=True)
class InRoom:
    """A person stands in one of these areas, or in none of them."""

    person: str
    area: str
    negated: bool = False

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        inside = where[self.person] in puzzle.areas(self.area)
        return not inside if self.negated else inside

    def describe(self, puzzle: "Puzzle") -> str:
        place = puzzle.phrase(self.area)
        if puzzle.language == "nl":
            return f"{self.person} zit {'niet ' if self.negated else ''}in {place}."
        return f"{self.person} is {'not ' if self.negated else ''}in {place}."


@dataclass(frozen=True)
class Population:
    """How many people stand in an area."""

    area: str
    operator: str
    number: int

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        rooms = puzzle.areas(self.area)
        return compare(sum(room in rooms for room in where.values()), self.operator, self.number)

    def describe(self, puzzle: "Puzzle") -> str:
        group = len(puzzle.areas(self.area)) > 1
        place = puzzle.group_phrase(self.area) if group else puzzle.phrase(self.area)
        place = place[:1].upper() + place[1:]
        if self.operator == "=" and self.number == 0:
            if puzzle.language == "nl":
                return f"{place} zijn leeg." if group else f"{place} is leeg."
            return f"{place} are empty." if group else f"{place} is empty."
        word = number_word(puzzle.language, self.number)
        count = COUNT_WORDS[puzzle.language][self.operator]
        if self.operator == ">=" and self.number == 1:
            if puzzle.language == "nl":
                return f"{place} {'zijn niet leeg.' if group else 'is niet leeg.'}"
            return f"{place} {'are not empty.' if group else 'is not empty.'}"
        if puzzle.language == "nl":
            people = "persoon" if self.number == 1 else "personen"
            verb = "bevatten samen" if group else "bevat"
            return f"{place} {verb} {count} {word} {people}."
        people = "person" if self.number == 1 else "people"
        if group:
            return f"{place} hold {count} {word} {people} together."
        return f"{place} holds {count} {word} {people}."


@dataclass(frozen=True)
class Alone:
    """A person shares a room with nobody, or with at least one other person."""

    person: str
    negated: bool = False

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        room = where[self.person]
        alone = sum(other == room for other in where.values()) == 1
        return not alone if self.negated else alone

    def describe(self, puzzle: "Puzzle") -> str:
        if puzzle.language == "nl":
            return f"{self.person} zit {'niet ' if self.negated else ''}alleen."
        return f"{self.person} is {'not ' if self.negated else ''}alone."


@dataclass(frozen=True)
class Company:
    """Two people share a room, or they do not."""

    first: str
    second: str
    together: bool

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        together = where[self.first] == where[self.second]
        return together if self.together else not together

    def describe(self, puzzle: "Puzzle") -> str:
        if puzzle.language == "nl":
            return f"{self.first} en {self.second} zaten {'' if self.together else 'niet '}samen."
        return f"{self.first} and {self.second} are {'' if self.together else 'not '}together."


@dataclass(frozen=True)
class Beside:
    """Two people share a room or stand in rooms that touch along a side."""

    first: str
    second: str
    negated: bool = False

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        first, second = where[self.first], where[self.second]
        if first == second:
            return not self.negated
        touching = any(
            (row + dr, col + dc) in puzzle.room(second).cells
            for row, col in puzzle.room(first).cells
            for dr, dc in STEPS.values()
        )
        return touching != self.negated

    def describe(self, puzzle: "Puzzle") -> str:
        if puzzle.language == "nl":
            return f"{self.first} zat {'niet ' if self.negated else ''}naast {self.second}."
        return f"{self.first} is {'not ' if self.negated else ''}next to {self.second}."


@dataclass(frozen=True)
class Direction:
    """One person's room touches the other's in that direction."""

    first: str
    step: str
    second: str

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        first, second = where[self.first], where[self.second]
        if first == second:
            return False
        dr, dc = STEPS[self.step]
        behind = {(row + dr, col + dc) for row, col in puzzle.room(second).cells}
        return bool(set(puzzle.room(first).cells) & behind)

    def describe(self, puzzle: "Puzzle") -> str:
        words = STEP_WORDS[puzzle.language][self.step]
        if puzzle.language == "nl":
            return f"{self.first} zit {words} {self.second}."
        return f"{self.first} is {words} {self.second}."


@dataclass(frozen=True)
class Choice:
    """Exactly `number` of these room clauses hold."""

    number: int
    atoms: tuple["Simple", ...]

    def holds(self, where: Mapping[str, str], puzzle: "Puzzle") -> bool:
        return sum(atom.holds(where, puzzle) for atom in self.atoms) == self.number

    def describe(self, puzzle: "Puzzle") -> str:
        body = "; ".join(atom.describe(puzzle).removesuffix(".") for atom in self.atoms)
        word = number_word(puzzle.language, self.number)
        how_many = number_word(puzzle.language, len(self.atoms))
        if puzzle.language == "nl":
            return f"Precies {word} van deze {how_many} geldt: {body}."
        return f"Exactly {word} of these {how_many} holds: {body}."


Simple = InRoom | Population | Alone
ClueType = Simple | Company | Beside | Choice | Direction


def number_word(language: str, number: int) -> str:
    """A small number as a word, so clues read like sentences; digits beyond ten."""
    words = NUMBERS[language]
    return words[number] if 0 <= number < len(words) else str(number)


@dataclass(frozen=True)
class Puzzle:
    """A parsed room puzzle: the plan, the rooms, the groups, the people and the clues."""

    rooms: tuple[Room, ...]
    plan: tuple[tuple[str, ...], ...]
    tags: dict[str, tuple[str, ...]]
    people: tuple[str, ...]
    clues: tuple[ClueType, ...]
    words: dict[str, str] = field(default_factory=dict)
    wording: dict[int, str] = field(default_factory=dict)
    language: str = "en"
    group_words: dict[str, str] = field(default_factory=dict)

    def room(self, key: str) -> Room:
        """The room with that key."""
        return next(room for room in self.rooms if room.key == key)

    def areas(self, selector: str) -> tuple[str, ...]:
        """The rooms an area names: one room key, or a group of rooms."""
        if selector in self.tags:
            return self.tags[selector]
        if any(room.key == selector for room in self.rooms):
            return (selector,)
        raise ValueError(f"unknown area {selector!r}")

    def phrase(self, selector: str) -> str:
        """How a room or group reads inside a sentence about one person."""
        if selector in self.words:
            return self.words[selector]
        if selector in self.tags:
            return selector.replace("_", " ")
        article = "de " if self.language == "nl" else "the "
        return article + self.room(selector).label

    def group_phrase(self, selector: str) -> str:
        """How a group reads in a count, which speaks for several rooms at once."""
        if selector in self.group_words:
            return self.group_words[selector]
        if selector in self.tags:
            name = selector.replace("_", " ")
            return f"de {name}kamers" if self.language == "nl" else f"the {name} rooms"
        return self.phrase(selector)

    def sentence(self, number: int) -> str:
        """The clue's own sentence, with the file's `| wording` if it has one."""
        if number in self.wording:
            return self.wording[number]
        return self.clues[number - 1].describe(self)

    @property
    def clue_lines(self) -> list[str]:
        """Every clue as a sentence, numbered from one."""
        return [self.sentence(number) for number in range(1, len(self.clues) + 1)]

    @property
    def width(self) -> int:
        return len(self.plan[0])

    @property
    def height(self) -> int:
        return len(self.plan)


def read_plan(lines: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """The plan grid: one line per row, room keys or `.` for no room."""
    plan = tuple(tuple(line.split()) for line in lines)
    if not plan or not plan[0]:
        raise ValueError("Plan: needs at least one row of room keys")
    width = len(plan[0])
    if any(len(row) != width for row in plan):
        raise ValueError("every Plan: row needs the same number of cells")
    return plan


def read_rooms(lines: Sequence[str], plan: tuple[tuple[str, ...], ...]) -> tuple[Room, ...]:
    """The `Rooms:` declarations, with the plan cells each room covers."""
    cells: dict[str, list[tuple[int, int]]] = {}
    for row, plan_row in enumerate(plan):
        for col, key in enumerate(plan_row):
            if key != ".":
                cells.setdefault(key, []).append((row, col))
    rooms: list[Room] = []
    for line in lines:
        match = _ROOM_LINE.match(line.strip())
        if not match:
            raise ValueError(f"bad room {line!r}, expected 'key: capacity #RRGGBB [label]'")
        key, capacity, colour, label = match.groups()
        if key not in cells:
            raise ValueError(f"room {key!r} is not on the plan")
        rooms.append(
            Room(
                key,
                label.strip() or key.replace("_", " "),
                int(capacity),
                colour,
                tuple(cells[key]),
            )
        )
    if not rooms:
        raise ValueError("Rooms: needs at least one room")
    missing = set(cells) - {room.key for room in rooms}
    if missing:
        raise ValueError(f"rooms on the plan without a Rooms: line: {sorted(missing)}")
    if len({room.label for room in rooms}) != len(rooms):
        raise ValueError("two rooms share a label; clues would not tell them apart")
    return tuple(rooms)


def read_tags(lines: Sequence[str], rooms: Sequence[Room]) -> dict[str, tuple[str, ...]]:
    """`Tags:` lines name groups of rooms; a clue may use a tag as its area."""
    keys = {room.key for room in rooms}
    tags: dict[str, tuple[str, ...]] = {}
    for line in lines:
        name, separator, rest = line.partition(":")
        name, members = name.strip(), tuple(rest.split())
        if not separator or not name or not members:
            raise ValueError(f"bad tag {line!r}, expected 'name: room room ...'")
        if name in keys:
            raise ValueError(f"tag {name!r} has the same name as a room")
        if name in tags:
            raise ValueError(f"tag {name!r} is defined more than once")
        unknown = set(members) - keys
        if unknown:
            raise ValueError(f"tag {name!r} names unknown rooms {sorted(unknown)}")
        tags[name] = members
    return tags


def compare(count: int, operator: str, number: int) -> bool:
    """Whether `count` satisfies `count operator number`."""
    if operator == "=":
        return count == number
    if operator == "<":
        return count < number
    if operator == ">":
        return count > number
    if operator == "<=":
        return count <= number
    return count >= number


def parse(text: str) -> Puzzle:
    """Read a room puzzle, checking that every name it uses is declared."""
    sections = read_sections(text)
    for required in ("Family", "Plan", "Rooms", "People"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "rooms":
        raise ValueError("Family must be 'rooms'")
    plan = read_plan(sections["Plan"])
    rooms = read_rooms(sections["Rooms"], plan)
    tags = read_tags(sections.get("Tags", []), rooms)
    people = tuple(sections["People"])
    if len(set(people)) != len(people):
        raise ValueError("People: repeats a name")
    if any(len(name.split()) != 1 for name in people):
        raise ValueError("every person needs a single-word name")
    for room in rooms:
        if room.capacity > len(people):
            raise ValueError(
                f"{room.label} holds {room.capacity} but there are only {len(people)} people"
            )
    if sum(room.capacity for room in rooms) < len(people):
        raise ValueError("the rooms have less room than the number of people")
    words: dict[str, str] = {}
    group_words: dict[str, str] = {}
    for line in sections.get("Words", []):
        name, separator, phrase = line.partition(":")
        single, _, group = phrase.partition("|")
        if not separator or not name.strip() or not single.strip():
            raise ValueError(f"bad word {line!r}, expected 'name: words [| words for a group]'")
        words[name.strip()] = single.strip()
        if group.strip():
            group_words[name.strip()] = group.strip()
    language = (sections.get("Language") or ["en"])[0].casefold()
    if language not in NUMBERS:
        raise ValueError(f"unknown Language {language!r}")
    empty = Puzzle(rooms, plan, tags, people, (), words, {}, language, group_words)
    clues: list[ClueType] = []
    wording: dict[int, str] = {}
    for number, line in enumerate(sections.get("Clues", []), 1):
        written, _, text = line.partition("|")
        clue = parse_clue(written.strip(), empty)
        _check_names(clue, empty)
        clues.append(clue)
        if text.strip():
            wording[number] = text.strip()
    if not clues:
        raise ValueError("Clues: needs at least one clue")
    return Puzzle(rooms, plan, tags, people, tuple(clues), words, wording, language, group_words)


def parse_clue(line: str, puzzle: Puzzle) -> ClueType:
    """Read one clue: a room clause, two people, or `exactly n of (...)`."""
    if match := _CHOICE.match(line):
        atoms = tuple(parse_clause(part.strip(), puzzle) for part in match[2].split(";"))
        return Choice(int(match[1]), atoms)
    if line.startswith("not (") and line.endswith(")"):
        return negate(parse_clue(line[5:-1].strip(), puzzle))
    if match := _COUNT.match(line):
        return Population(match[1], match[2], int(match[3]))
    if match := _IN.match(line):
        return InRoom(match[1], match[2])
    if match := _ALONE.match(line):
        return Alone(match[1])
    if match := _PAIR.match(line):
        return Company(match[1], match[3], match[2] == "together")
    if match := _BESIDE.match(line):
        return Beside(match[1], match[2])
    if match := _DIRECTION.match(line):
        return Direction(match[1], match[2], match[3])
    raise ValueError(f"bad room clue {line!r}")


def parse_clause(line: str, puzzle: Puzzle) -> Simple:
    """Read a clause that fits inside `exactly n of (...)`."""
    clue = parse_clue(line, puzzle)
    if not isinstance(clue, (InRoom, Population, Alone)):
        raise ValueError(f"only room clauses belong inside a choice: {line!r}")
    return clue


def negate(clue: ClueType) -> ClueType:
    """The opposite of a clue that can be negated."""
    if isinstance(clue, InRoom):
        return InRoom(clue.person, clue.area, True)
    if isinstance(clue, Alone):
        return Alone(clue.person, True)
    if isinstance(clue, Beside):
        return Beside(clue.first, clue.second, not clue.negated)
    if isinstance(clue, Company):
        return Company(clue.first, clue.second, not clue.together)
    raise ValueError("only a room clause, a pair or 'alone' can be negated")


def format_clue(clue: ClueType) -> str:
    """A clue as it is written in a puzzle file, so `parse` can read it back."""
    if isinstance(clue, InRoom):
        text = f"{clue.person} in area:{clue.area}"
        return f"not ({text})" if clue.negated else text
    if isinstance(clue, Population):
        return f"count (people in area:{clue.area}) {clue.operator} {clue.number}"
    if isinstance(clue, Alone):
        text = f"{clue.person} alone"
        return f"not ({text})" if clue.negated else text
    if isinstance(clue, Company):
        return f"{clue.first} {'together' if clue.together else 'apart'} {clue.second}"
    if isinstance(clue, Beside):
        text = f"{clue.first} beside {clue.second}"
        return f"not ({text})" if clue.negated else text
    if isinstance(clue, Choice):
        return f"exactly {clue.number} of ({'; '.join(format_clue(atom) for atom in clue.atoms)})"
    assert isinstance(clue, Direction)
    return f"{clue.first} dir:{clue.step} {clue.second}"


def _check_names(clue: ClueType, puzzle: Puzzle) -> None:
    """Every person and area a clue names must be declared."""
    for name in (
        getattr(clue, "person", None),
        getattr(clue, "first", None),
        getattr(clue, "second", None),
    ):
        if name is not None and name not in puzzle.people:
            raise ValueError(f"unknown person {name!r}")
    if (area := getattr(clue, "area", None)) is not None:
        puzzle.areas(area)
    for atom in getattr(clue, "atoms", ()):
        _check_names(atom, puzzle)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Compile a room puzzle: one variable per person, a count per room capacity.

    A variable's values are the rooms' labels, so the solver's own output,
    `--step` and the worked solution all read as rooms rather than as codes.
    """
    model, puzzle, _ = _compile(text)
    return model, puzzle


@dataclass
class StoryWords:
    """How a worked solution reads what the model keeps hidden.

    `hidden` maps a hidden yes/no value to its sentence ("Dirk and Ada are
    together"); `sources` maps a helper constraint's name to the clue or rule
    a player knows it by.
    """

    hidden: dict[tuple[str, Any], str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)


def story_words(text: str) -> StoryWords:
    """The sentences a worked solution uses for this puzzle's hidden helpers."""
    return _compile(text)[2]


def _compile(text: str) -> tuple[Model, Puzzle, StoryWords]:
    puzzle = parse(text)
    say = labels(puzzle.language)
    words = StoryWords()
    model = Model()
    for person in puzzle.people:
        model.constrain(
            say["room"].format(person=person),
            Kind.EXACTLY_ONE,
            [model.literal(person, room.label) for room in puzzle.rooms],
            defines=person,
            family=say["one_room"],
        )
    for room in puzzle.rooms:
        model.constrain(
            say["capacity"].format(room=room.title, capacity=room.capacity),
            Kind.COUNT,
            [model.literal(person, room.label) for person in puzzle.people],
            allowed_counts=range(room.capacity + 1),
            family=say["capacities"],
        )
    shares = _Shares(model, puzzle, say, words)
    seen: set[str] = set()
    for number, clue in enumerate(puzzle.clues, 1):
        name = puzzle.sentence(number).removesuffix(".")
        if name in seen:
            raise ValueError(f"two clues read the same: {name!r}")
        seen.add(name)
        _compile_clue(model, puzzle, clue, shares, name, say, words)
    return model, puzzle, words


class _Shares:
    """One hidden Boolean per pair of people: whether they share a room.

    "Was not alone" then becomes a count over those Booleans, which keeps the
    clue a small `COUNT` instead of a relation over every person at once.
    """

    def __init__(
        self, model: Model, puzzle: Puzzle, say: dict[str, str], words: StoryWords
    ) -> None:
        self._model = model
        self._puzzle = puzzle
        self._say = say
        self._words = words
        self._literals: dict[frozenset[str], int] = {}

    def literal(self, first: str, second: str) -> int:
        """The literal that is true exactly when both stand in one room."""
        pair = frozenset((first, second))
        if pair in self._literals:
            return self._literals[pair]
        name = self._say["shared"].format(first=first, second=second)
        variable, yes, _ = _hidden_boolean(
            self._model, "rooms", name, self._say["sharing"], self._say
        )
        self._model.relate(name, (first, second, variable), lambda a, b, shared: shared == (a == b))
        for together in (True, False):
            sentence = Company(first, second, together).describe(self._puzzle)
            self._words.hidden[variable, together] = sentence.removesuffix(".")
        self._words.sources[name] = self._say["together_rule"]
        self._literals[pair] = yes
        return yes


def _hidden_boolean(
    model: Model, prefix: str, name: str, family: str, say: dict[str, str]
) -> tuple[str, int, int]:
    """A hidden true/false variable, with the constraint that defines it."""
    number = 1
    while f"{prefix} {number}" in model.all_variables:
        number += 1
    variable = f"{prefix} {number}"
    yes, no = model.literal(variable, True), model.literal(variable, False)
    model.constrain(
        say["state"].format(name=name),
        Kind.EXACTLY_ONE,
        [yes, no],
        defines=variable,
        hidden=True,
        family=family,
    )
    return variable, yes, no


def _compile_clue(
    model: Model,
    puzzle: Puzzle,
    clue: ClueType,
    shares: _Shares,
    name: str,
    say: dict[str, str],
    words: StoryWords,
) -> None:
    """Add the constraint a clue states, named after the sentence it reads as."""
    if isinstance(clue, InRoom):
        literals = _room_literals(model, puzzle, clue.area, clue.person)
        _count(model, name, literals, {0} if clue.negated else {1}, say)
    elif isinstance(clue, Population):
        _population(model, name, puzzle, clue, say)
    elif isinstance(clue, Company):
        model.relate(name, (clue.first, clue.second), lambda a, b: (a == b) == clue.together)
    elif isinstance(clue, Direction):
        labels = {room.label: room.key for room in puzzle.rooms}
        placed: dict[str, str] = {}

        def holding(first: str, second: str) -> bool:
            placed[clue.first], placed[clue.second] = labels[first], labels[second]
            return clue.holds(placed, puzzle)

        model.relate(name, (clue.first, clue.second), holding)
    elif isinstance(clue, Beside):
        labels = {room.label: room.key for room in puzzle.rooms}
        side: dict[str, str] = {}

        def touching(first: str, second: str) -> bool:
            side[clue.first], side[clue.second] = labels[first], labels[second]
            return clue.holds(side, puzzle)

        model.relate(name, (clue.first, clue.second), touching)
    elif isinstance(clue, Alone):
        others = [other for other in puzzle.people if other != clue.person]
        literals = [shares.literal(clue.person, other) for other in others]
        allowed = set(range(1, len(literals) + 1)) if clue.negated else {0}
        _count(model, name, literals, allowed, say)
    else:
        assert isinstance(clue, Choice)
        truths = [
            _reify(
                model,
                puzzle,
                atom,
                f"{name}: {atom.describe(puzzle).removesuffix('.')}",
                shares,
                say,
                words,
                clue=name,
            )
            for atom in clue.atoms
        ]
        _count(model, name, truths, {clue.number}, say)


def _room_literals(model: Model, puzzle: Puzzle, area: str, person: str) -> list[int]:
    """One person's literals for every room an area names, as the solver's values."""
    return [model.literal(person, puzzle.room(key).label) for key in puzzle.areas(area)]


def _population(
    model: Model, name: str, puzzle: Puzzle, clue: Population, say: dict[str, str]
) -> None:
    """The count of people in an area, as one `COUNT` over its room literals."""
    rooms = puzzle.areas(clue.area)
    literals = [
        model.literal(person, puzzle.room(room).label) for person in puzzle.people for room in rooms
    ]
    _count(model, name, literals, _allowed(literals, clue.operator, clue.number, name), say)


def _allowed(literals: Sequence[int], operator: str, number: int, name: str) -> set[int]:
    """The counts a comparison allows, or an error when it allows none."""
    allowed = {count for count in range(len(literals) + 1) if compare(count, operator, number)}
    if not allowed:
        raise ValueError(f"clue {name!r} can never hold")
    return allowed


def _count(
    model: Model, name: str, literals: Sequence[int], allowed: set[int], say: dict[str, str]
) -> None:
    model.constrain(name, Kind.COUNT, literals, allowed_counts=allowed, family=say["clue"])


def _reify(
    model: Model,
    puzzle: Puzzle,
    atom: Simple,
    name: str,
    shares: _Shares,
    say: dict[str, str],
    words: StoryWords,
    clue: str,
) -> int:
    """A hidden literal that is true exactly when the clause holds."""
    variable, yes, _ = _hidden_boolean(model, "clue", name, say["clue"], say)
    sentence = atom.describe(puzzle).removesuffix(".")
    if isinstance(atom, Population):
        opposite = say["not"].format(sentence=sentence[:1].lower() + sentence[1:])
    else:
        opposite = negate(atom).describe(puzzle).removesuffix(".")
    words.hidden[variable, True] = sentence
    words.hidden[variable, False] = opposite
    words.sources[f"{name} count"] = clue
    if isinstance(atom, InRoom):
        literals = _room_literals(model, puzzle, atom.area, atom.person)
        allowed = {0} if atom.negated else {1}
    elif isinstance(atom, Population):
        rooms = puzzle.areas(atom.area)
        literals = [
            model.literal(person, puzzle.room(room).label)
            for person in puzzle.people
            for room in rooms
        ]
        allowed = _allowed(literals, atom.operator, atom.number, name)
    else:
        assert isinstance(atom, Alone)
        others = [other for other in puzzle.people if other != atom.person]
        literals = [shares.literal(atom.person, other) for other in others]
        allowed = set(range(1, len(literals) + 1)) if atom.negated else {0}
    model.constrain(
        f"{name} count",
        Kind.COUNT,
        literals,
        allowed_counts=allowed,
        reified_by=yes,
        family="a clue",
    )
    return yes


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The plan, with each room's certain and possible people."""
    changed = {(step.var, step.value) for step in steps if step.asserted}
    width = max(len(room.title) for room in puzzle.rooms)
    out = [f"\n{title}"]
    for room in puzzle.rooms:
        placed = [person for person in puzzle.people if model.chosen(person) == room.label]
        if placed:
            mark = ", ".join(placed)
        else:
            possible = [
                person
                for person in puzzle.people
                if model.chosen(person) is None
                and model.literal(person, room.label) in model.options(person)
            ]
            mark = " ".join(f"{person}?" for person in possible) or "-"
        line = f"  {room.title:<{width}} ({room.capacity})  {mark}"
        if any((person, room.label) in changed for person in puzzle.people):
            line = f"\033[38;5;21m{line}\033[0m"
        out.append(line)
    return "\n".join(out)


def people_of(clue: ClueType) -> frozenset[str]:
    """Every person a clue talks about, so a search knows when it can judge the clue."""
    names = {
        name
        for name in (
            getattr(clue, "person", None),
            getattr(clue, "first", None),
            getattr(clue, "second", None),
        )
        if name is not None
    }
    for atom in getattr(clue, "atoms", ()):
        names |= people_of(atom)
    return frozenset(names)


def needs_everyone(clue: ClueType) -> bool:
    """Whether a clue's truth depends on people it does not name.

    A count in an area and "alone" both speak for every person, so a search may
    only judge them once the whole placement is known; a membership, a pair or a
    direction mentions everyone it depends on.
    """
    if isinstance(clue, (Population, Alone)):
        return True
    return any(needs_everyone(atom) for atom in getattr(clue, "atoms", ()))


def candidate_clues(puzzle: Puzzle, where: Mapping[str, str]) -> list[tuple[int, str]]:
    """Every clue that is true of a placement, with a rank: 0 is the sharpest.

    The rank is the difficulty dial an author turns. A clue that names one
    person's room comes first, then a group's, then a count, a pair or being
    alone; the weakest comparisons and the direction clues, which much of any
    plan satisfies, come last. Ties keep the puzzle file's own order.
    """
    keys = [room.key for room in puzzle.rooms]
    found: set[tuple[int, str]] = set()

    def add(rank: int, clue: ClueType) -> None:
        if clue.holds(where, puzzle):
            found.add((rank, format_clue(clue)))

    def add_either(rank: int, clue: InRoom | Alone) -> None:
        add(rank, clue if clue.holds(where, puzzle) else negate(clue))

    for person in puzzle.people:
        for room in keys:
            add_either(0 if where[person] == room else 1, InRoom(person, room))
        for tag in puzzle.tags:
            add_either(2 if where[person] in puzzle.tags[tag] else 3, InRoom(person, tag))
        alone = sum(other == where[person] for other in where.values()) == 1
        add_either(5 if alone else 7, Alone(person))
        for other in puzzle.people:
            if other > person:
                same = where[other] == where[person]
                found.add((4 if same else 6, format_clue(Company(person, other, same))))
                add(6, Beside(person, other))
        for step in STEPS:
            for other in puzzle.people:
                if other != person:
                    add(9, Direction(person, step, other))
    for area in (*keys, *puzzle.tags):
        total = sum(room in puzzle.areas(area) for room in where.values())
        add(3, Population(area, "=", total))
        if total:
            add(8, Population(area, ">=", total))
            add(8, Population(area, "<=", total))
    for first, second in itertools.combinations(puzzle.tags, 2):
        for one, two in itertools.permutations(puzzle.people, 2):
            clause = (InRoom(one, first), InRoom(two, second))
            if sum(atom.holds(where, puzzle) for atom in clause) == 1:
                found.add((7, format_clue(Choice(1, clause))))
    return sorted(found)
