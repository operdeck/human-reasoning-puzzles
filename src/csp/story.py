"""Murdoku solutions written out the way a person would explain them.

`proof` decides *what* to say: a short replay of the solver's own
deductions. This module only decides *how*: one paragraph per placement (or
run of placements), people's options described by region, row, column or
the things on the board wherever that is exact, square numbers only when
they are few.

Wording comes from two optional sections of the puzzle file:

    Language: nl
    Words:
    water: in het water        # a region or group: where it is
    vuurtje: het vuurtje       # an object type: what it is called

Everything here reads the public `Model` API, `Step` provenance and
`murdoku`'s board and clue meaning; nothing here is needed to solve.
"""

import dataclasses
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations, groupby
from typing import Any, Literal

from .core import Kind, Solver, Step
from .murdoku import (
    COUNTING,
    FILTERS,
    Board,
    Clue,
    Condition,
    GlobalCountCondition,
    QuantifiedCondition,
    RoleCondition,
    Square,
    TargetSelector,
    board_rules,
    compile_puzzle,
    conditions,
    counted,
    global_count_conditions,
    global_count_unit_prefix,
    line_indices,
    quantified_conditions,
    role_conditions,
)
from .proof import Move, essential, replay, shortest
from .puzzlefile import load_board, read_sections

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "square": "r{row}c{col}",
        "doc.figures": "The figures",
        "doc.rules_title": "Rules",
        "doc.how": "How to get there.",
        "doc.clues": "Clues",
        "doc.question": "Question",
        "doc.solution": "Solution",
        "doc.contents": "Contents",
        "doc.solutions": "Solutions",
        "doc.answer": "Answer",
        "doc.mark": "Cells marked {abbr} are {name} cells.",
        "doc.mark_alone": (
            "Cells marked {abbr} are {name} cells: whoever stands on one is alone in their area."
        ),
        "doc.mark_not_alone": (
            "Cells marked {abbr} are {name} cells: whoever stands on one shares the area "
            "with someone else."
        ),
        "doc.area_tag": "The {tag} are {areas}.",
        "doc.attributes": "The attributes",
        "doc.attribute": "{people}",
        "doc.roles": "The roles",
        "doc.objects": "The objects",
        "doc.standable": "you can stand on it",
        "doc.blocking": "nobody can stand here",
        "doc.role": "held by {count}{extra}",
        "doc.count_one": "exactly one person",
        "doc.count_exact": "exactly {n} people",
        "doc.count_any": "any number of people",
        "doc.count_one_of": "{list} people",
        "doc.extra_regions": ", all in different areas",
        "clue.role_apart": "there is at most one {role} per area ({a}, {b})",
        "doc.extra_from": ", chosen from {people}",
        "doc.rules": (
            "Place every figure on a free square of the board. No two figures share a row or a "
            "column. Squares with an object that blocks cannot be used; squares with a standable "
            "object can."
        ),
        "and": "and",
        "or": "or",
        "region": "in the {name}",
        "the": "the {name}",
        "a": "a {name}",
        "row": "row {n}",
        "col": "column {n}",
        "rows": "rows {list}",
        "cols": "columns {list}",
        "through": "{a} to {b}",
        "in": "in {what}",
        "on": "on {what}",
        "at": "at {what}",
        "next_to": "next to {what}",
        "is": "{who} is {where}",
        "is_not": "{who} is not {where}",
        "count": "{who} has {n} squares left",
        "placed": "**{who} on {square}**",
        "so": "so",
        "takes_line": "{who} takes {line}",
        "takes_square": "{who} is already on {square}",
        "only_left": "only {square} is left for {who}",
        "only_one": "only {who} can still fill {lines}",
        "only_many": "only {who} can still fill {lines}",
        "can_only_one": "{who} can only be {where}",
        "can_only_many": "{who} can only be {where}",
        "filled_only_one": "{lines} can only be filled {where}",
        "filled_only_many": "{lines} can only be filled {where}",
        "via": "via {refs}",
        "chain_if": "If {who} is not on {square}",
        "chain_on": "then {who} is on {square}",
        "chain_off": "then {who} is not on {square}",
        "chain_so": "So {ends}; either way {outcome}.",
        "chain_either": "{ends}; either way {outcome}.",
        "nobody_else": "nobody else can be there",
        "then_on": "then {who} is on {square}",
        "nowhere": "then {who} has nowhere left",
        "nobody": "then nobody can fill {line}",
        "breaks_said": "which goes against \u2018{clue}\u2019",
        "breaks_said_first": "that goes against \u2018{clue}\u2019",
        "both": "then {who} are both {where}",
        "breaks": "which clue {n} does not allow",
        "breaks_first": "clue {n} does not allow that",
        "breaks_plain": "which the clues do not allow",
        "breaks_first_plain": "the clues do not allow that",
        "breaks_rule": "which the board does not allow",
        "breaks_rule_first": "the board does not allow that",
        "cannot": "{who} cannot be on {squares}: {chain}.",
        "nor": "Nor on {squares}: {chain}.",
        "direct": "The direct clues",
        "the_rest": "The rest",
        "squares": "{n} squares",
        "one_row": "one row",
        "n_rows": "{n} rows",
        "clue.in_region": "{a} is {where}",
        "clue.outside": "{a} is not {where}",
        "clue.at": "{a} is at {things}",
        "clue.in_tagged": "{a} is {where}",
        "clue.not_in_tagged": "{a} is not {where}",
        "clue.only_in_tagged": "{a} is only {where}",
        "clue.next_to": "{a} is next to {things}",
        "clue.not_next_to": "{a} is not next to {things}",
        "clue.knight_from": "{a} is a knight's move from {things}",
        "clue.on": "{a} is on {things}",
        "clue.not_on": "{a} is not on {things}",
        "clue.on_mark": "{a} is on {things}",
        "clue.not_on_mark": "{a} is not on {things}",
        "clue.only_on": "{a} is the only person on {things}",
        "clue.in_corner": "{a} is in a corner of the grid",
        "clue.in_row": "{a} is in {line}",
        "clue.not_in_row": "{a} is not in {line}",
        "clue.in_column": "{a} is in {line}",
        "clue.not_in_column": "{a} is not in {line}",
        "clue.in_area_corner": "{a} is in a corner, {where}",
        "clue.has_attribute": "{a} has the {attribute} attribute",
        "clue.not_attribute": "{a} does not have the {attribute} attribute",
        "clue.unique_attribute": "exactly one of {people} has the {attribute} attribute",
        "clue.adjacent_regions": "{a} and {b} are in neighboring regions",
        "clue.alone_with": (
            "{a} shares a region with exactly one other person, and that is {target}"
        ),
        "clue.alone_with_anyone": "{a} shares a region with exactly one other person",
        "clue.alone_with_n": (
            "{a} shares a region with exactly {n} others, and they are all {target}"
        ),
        "clue.alone_with_anyone_n": "{a} shares a region with exactly {n} others",
        "clue.same_region": "{a} and {b} are in the same region",
        "clue.different_region": "{a} and {b} are in different regions",
        "clue.apart": "{a} and {b} are in regions that do not touch",
        "clue.left_of": "{a} is somewhere left of {b}",
        "clue.left_of_one": "{a} is exactly one column left of {b}",
        "clue.left_of_n": "{a} is exactly {n} columns left of {b}",
        "clue.exactly": "exactly {n} of these is true: {list}",
        "clue.either": "either {first}, or {second}, but not both",
        "clue.either_same_region": "{a} is in the same region as either {b} or {c}",
        "count_reason": "the allowed counts for {name} are {counts}",
        "global_count.exact": "exactly {n}",
        "global_count.at_most": "at most {n}",
        "global_count.at_least": "at least {n}",
        "global_count.odd": "an odd number of",
        "global_count.even": "an even number of",
        "global_count.range": "between {low} and {high}",
        "global_count.people_on": "{quantity} {noun} {verb} on {target}",
        "global_count.people_in": "{quantity} {noun} {verb} {where}",
        "global_count.people_with": "{quantity} {noun} {have} {target}",
        "global_count.empty_areas": "{quantity} {noun} {verb} empty{where}",
        "global_count.no_empty_areas": "no area is empty{where}",
        "global_count.empty_cells": "{quantity} {noun} {verb} empty {where}",
        "global_count.no_empty_cells": "no free cell is empty {where}",
        "global_count.capacity": "region capacity",
        "global_count.breaks": "which the global count {clue} does not allow",
        "global_count.area_empty": "nobody is {where}",
        "global_count.area_occupied": "someone is {where}",
        "global_count.cell_empty": "{square} is empty",
        "global_count.cell_occupied": "{square} is occupied",
        "global_count.object_kind": "{kind} objects",
        "literal_true": "the literal {literal} must hold",
        "literal_false": "the literal {literal} cannot hold",
        "role_has": "{who} has the {role} role",
        "role_not": "{who} does not have the {role} role",
        "role_some": "{who} has at least one role",
        "roleless": "{who} has no roles",
        "role_at_most_one": "{who} has at most one role",
        "role_subset": "anyone matching {left} also matches {right}",
        "role_in_tagged": "{who} has role {role} only {area}",
        "role_not_in_tagged": "{who} never has role {role} {area}",
        "min_role_in_tagged": "at least {n} {role} holders are {area}",
        "role_on": "if {who} has role {role}, {subject} must be on {things}",
        "role_not_on": "if {who} has role {role}, {subject} must not be on {things}",
        "role_next_to": "if {who} has role {role}, {subject} must be next to {things}",
        "role_below": "{who} is below a {role} holder",
        "role_below_n": "{who} is {n} rows below a {role} holder",
        "sole_role_companion": "{possessive} sole region companion has role {role}",
        "role_occupant.alone": "every {role} holder is alone in their area",
        "role_occupant.not_alone": "no {role} holder is alone in their area",
        "min_role_in_tagged_one": "at least one {role} holder is {area}",
        "role_area_in": "{who} has role {role} and must be {area}",
        "role_only_one": "there is only one {role}",
        "role_area_out": "{who} cannot both have role {role} and be {area}",
        "clue.above": "{a} is somewhere above {b}",
        "clue.above_n": "{a} is exactly {rows} above {b}",
        "clue.within": "{a} is at most {n} squares from {b}",
        "clue.at_least": "{a} is at least {n} squares from {b}",
        "clue.alone": "{a} is alone in a region",
        "clue.furthest": "{a} is further from {b} than {c} is",
        "clue.furthest_all": "{a} is the furthest from {b} of all the figures",
        "target.attribute": "someone with the {name} attribute",
        "target.role": "a {name} holder",
        "target.area": "someone {where}",
        "target.on": "someone on {what}",
        "target.at": "someone at {what}",
        "target.corner": "someone in the cells around {what}",
        "target.kind": "someone on {what}",
    },
    "nl": {
        "square": "r{row}k{col}",
        "doc.figures": "De figuren",
        "doc.rules_title": "Spelregels",
        "doc.how": "Zo kom je erop.",
        "doc.clues": "Aanwijzingen",
        "doc.question": "Vraag",
        "doc.solution": "Oplossing",
        "doc.contents": "Inhoud",
        "doc.solutions": "Oplossingen",
        "doc.answer": "Antwoord",
        "doc.mark": "Vakjes met {abbr} zijn {name}-vakjes.",
        "doc.mark_alone": (
            "Vakjes met {abbr} zijn {name}-vakjes: wie daar staat, is alleen in zijn gebied."
        ),
        "doc.mark_not_alone": (
            "Vakjes met {abbr} zijn {name}-vakjes: wie daar staat, deelt het gebied met "
            "iemand anders."
        ),
        "doc.area_tag": "{Tag}: {areas}.",
        "doc.attributes": "De kenmerken",
        "doc.attribute": "{people}",
        "doc.roles": "De rollen",
        "doc.objects": "De voorwerpen",
        "doc.standable": "hier kun je op staan",
        "doc.blocking": "hier kan niemand staan",
        "doc.role": "heeft {count}{extra}",
        "doc.count_one": "precies één persoon",
        "doc.count_exact": "precies {n} mensen",
        "doc.count_any": "een willekeurig aantal mensen",
        "doc.count_one_of": "{list} mensen",
        "doc.extra_regions": ", allemaal in verschillende gebieden",
        "clue.role_apart": "er is hoogstens één {role} per gebied ({a}, {b})",
        "doc.extra_from": ", gekozen uit {people}",
        "doc.rules": (
            "Zet elke figuur op een vrij vakje van het bord. Twee figuren staan nooit in dezelfde "
            "rij of kolom. Vakjes met een blokkerend voorwerp kun je niet gebruiken; vakjes met "
            "een begaanbaar voorwerp wel."
        ),
        "and": "en",
        "or": "of",
        "region": "in de {name}",
        "the": "de {name}",
        "a": "een {name}",
        "row": "rij {n}",
        "col": "kolom {n}",
        "rows": "de rijen {list}",
        "cols": "de kolommen {list}",
        "through": "{a} t/m {b}",
        "in": "in {what}",
        "on": "op {what}",
        "at": "bij {what}",
        "next_to": "naast {what}",
        "is": "{who} zit {where}",
        "is_not": "{who} zit niet {where}",
        "count": "{who} kan nog op {n} vakjes",
        "placed": "**{who} op {square}**",
        "so": "dus",
        "takes_line": "{who} bezet {line}",
        "takes_square": "{who} zit al op {square}",
        "only_left": "voor {who} blijft alleen {square} over",
        "only_one": "{lines} kan alleen nog van {who} zijn",
        "only_many": "{lines} kunnen alleen nog van {who} zijn",
        "can_only_one": "{who} kan alleen {where}",
        "can_only_many": "{who} kunnen alleen {where}",
        "filled_only_one": "{lines} kan alleen nog gevuld worden {where}",
        "filled_only_many": "{lines} kunnen alleen nog gevuld worden {where}",
        "via": "via {refs}",
        "chain_if": "Als {who} niet op {square} zit",
        "chain_on": "dan zit {who} op {square}",
        "chain_off": "dan zit {who} niet op {square}",
        "chain_so": "Dus {ends}; hoe dan ook {outcome}.",
        "chain_either": "{ends}; hoe dan ook {outcome}.",
        "nobody_else": "daar kan verder niemand",
        "then_on": "dan zit {who} op {square}",
        "nowhere": "dan kan {who} nergens meer",
        "nobody": "dan kan niemand meer in {line}",
        "breaks_said": "en dat strookt niet met \u2018{clue}\u2019",
        "breaks_said_first": "dat strookt niet met \u2018{clue}\u2019",
        "both": "dan zitten {who} allebei {where}",
        "breaks": "en dat mag niet volgens aanwijzing {n}",
        "breaks_first": "dat mag niet volgens aanwijzing {n}",
        "breaks_plain": "en dat mag niet",
        "breaks_first_plain": "dat mag niet",
        "breaks_rule": "en dat mag niet",
        "breaks_rule_first": "dat mag niet",
        "cannot": "{who} kan niet op {squares}: {chain}.",
        "nor": "Ook niet op {squares}: {chain}.",
        "direct": "De directe aanwijzingen",
        "the_rest": "De rest",
        "squares": "{n} vakjes",
        "one_row": "één rij",
        "n_rows": "{n} rijen",
        "clue.in_region": "{a} is {where}",
        "clue.outside": "{a} is niet {where}",
        "clue.at": "{a} is bij {things}",
        "clue.in_tagged": "{a} is {where}",
        "clue.not_in_tagged": "{a} is niet {where}",
        "clue.only_in_tagged": "{a} is alleen {where}",
        "clue.next_to": "{a} zit naast {things}",
        "clue.not_next_to": "{a} zit niet naast {things}",
        "clue.knight_from": "{a} staat een paardensprong van {things}",
        "clue.on": "{a} zit op {things}",
        "clue.not_on": "{a} zit niet op {things}",
        "clue.on_mark": "{a} staat op {things}",
        "clue.not_on_mark": "{a} staat niet op {things}",
        "clue.only_on": "alleen {a} zit op {things}",
        "clue.in_corner": "{a} staat in een hoek van het raster",
        "clue.in_row": "{a} staat in {line}",
        "clue.not_in_row": "{a} staat niet in {line}",
        "clue.in_column": "{a} staat in {line}",
        "clue.not_in_column": "{a} staat niet in {line}",
        "clue.in_area_corner": "{a} staat in een hoek, {where}",
        "clue.has_attribute": "{a} heeft het kenmerk {attribute}",
        "clue.not_attribute": "{a} heeft het kenmerk {attribute} niet",
        "clue.unique_attribute": "precies één van {people} heeft het kenmerk {attribute}",
        "clue.adjacent_regions": "{a} en {b} zijn in aangrenzende gebieden",
        "clue.alone_with": "{a} deelt een gebied met precies één ander persoon, en dat is {target}",
        "clue.same_region": "{a} en {b} zijn in hetzelfde gebied",
        "clue.different_region": "{a} en {b} zijn in verschillende gebieden",
        "clue.apart": "{a} en {b} zijn in gebieden die niet aan elkaar grenzen",
        "clue.left_of": "{a} is ergens links van {b}",
        "clue.left_of_one": "{a} is precies één kolom links van {b}",
        "clue.left_of_n": "{a} is precies {n} kolommen links van {b}",
        "clue.exactly": "precies {n} hiervan klopt: {list}",
        "clue.either": "ofwel {first}, ofwel {second}, maar niet allebei",
        "clue.either_same_region": "{a} is in hetzelfde gebied als {b} of {c}",
        "clue.alone_with_anyone": "{a} deelt een gebied met precies één ander persoon",
        "clue.alone_with_n": (
            "{a} deelt een gebied met precies {n} anderen, en dat zijn allemaal {target}"
        ),
        "clue.alone_with_anyone_n": "{a} deelt een gebied met precies {n} anderen",
        "count_reason": "voor {name} zijn de toegestane aantallen {counts}",
        "global_count.exact": "precies {n}",
        "global_count.at_most": "hoogstens {n}",
        "global_count.at_least": "minstens {n}",
        "global_count.odd": "een oneven aantal",
        "global_count.even": "een even aantal",
        "global_count.range": "tussen {low} en {high}",
        "global_count.people_on": "{quantity} {noun} {verb} op {target}",
        "global_count.people_in": "{quantity} {noun} {verb} {where}",
        "global_count.people_with": "{quantity} {noun} {have} {target}",
        "global_count.empty_areas": "{quantity} {noun} {verb} leeg{where}",
        "global_count.no_empty_areas": "geen gebied is leeg{where}",
        "global_count.empty_cells": "{quantity} {noun} {verb} leeg {where}",
        "global_count.no_empty_cells": "geen vrij vakje is leeg {where}",
        "global_count.capacity": "gebiedscapaciteit",
        "global_count.breaks": "wat niet mag volgens de globale telling: {clue}",
        "global_count.area_empty": "niemand is {where}",
        "global_count.area_occupied": "iemand is {where}",
        "global_count.cell_empty": "{square} is leeg",
        "global_count.cell_occupied": "{square} is bezet",
        "global_count.object_kind": "{kind} objecten",
        "literal_true": "de letterlijke keuze {literal} moet gelden",
        "literal_false": "de letterlijke keuze {literal} kan niet gelden",
        "role_has": "{who} heeft de rol {role}",
        "role_not": "{who} heeft de rol {role} niet",
        "role_some": "{who} heeft minstens één rol",
        "roleless": "{who} heeft geen rollen",
        "role_at_most_one": "{who} heeft hoogstens één rol",
        "role_subset": "wie aan {left} voldoet, voldoet ook aan {right}",
        "role_in_tagged": "{who} heeft de rol {role} alleen {area}",
        "role_not_in_tagged": "{who} heeft de rol {role} nooit {area}",
        "min_role_in_tagged": "minstens {n} {role}-dragers zijn {area}",
        "role_on": "als {who} de rol {role} heeft, staat {subject} op {things}",
        "role_not_on": "als {who} de rol {role} heeft, staat {subject} niet op {things}",
        "role_next_to": "als {who} de rol {role} heeft, staat {subject} naast {things}",
        "role_below": "{who} staat onder een {role}-drager",
        "role_below_n": "{who} staat {n} rijen onder een {role}-drager",
        "sole_role_companion": "{possessive} enige gebiedsgenoot heeft de rol {role}",
        "role_occupant.alone": "elke {role}-drager is alleen in zijn gebied",
        "role_occupant.not_alone": "geen enkele {role}-drager is alleen in zijn gebied",
        "min_role_in_tagged_one": "minstens één {role}-drager is {area}",
        "role_area_in": "{who} heeft de rol {role} en moet {area} zijn",
        "role_only_one": "er is maar één {role}",
        "role_area_out": "{who} kan niet de rol {role} hebben en tegelijk {area} zijn",
        "clue.above": "{a} is ergens boven {b}",
        "clue.above_n": "{a} is precies {rows} boven {b}",
        "clue.within": "{a} is hooguit {n} vakjes van {b}",
        "clue.at_least": "{a} is minstens {n} vakjes van {b}",
        "clue.alone": "{a} is alleen in een gebied",
        "clue.furthest": "{a} is verder van {b} dan {c}",
        "clue.furthest_all": "{a} is van alle figuren het verst van {b}",
        "target.attribute": "iemand met het kenmerk {name}",
        "target.role": "een {name}-drager",
        "target.area": "iemand {where}",
        "target.on": "iemand op {what}",
        "target.at": "iemand bij {what}",
        "target.corner": "iemand in de vakjes rond {what}",
        "target.kind": "iemand op {what}",
    },
}

# The one-line rules of every family but Murdoku, for the booklet and the web site.
FAMILY_RULES = {
    "sudoku": "Fill the grid so every row, column and box contains each digit once.",
    "calcudoku": "Fill the grid so no digit repeats in a row or column, and each cage's "
    "digits combine to its target with its operation.",
    "futoshiki": "Fill the grid so no digit repeats in a row or column and every "
    "inequality sign between neighbouring cells holds.",
    "queens": "Place one queen in every row, column and region; queens may not touch, "
    "not even diagonally.",
    "suguru": "Fill every region of n cells with 1..n; equal digits may not touch, "
    "not even diagonally.",
    "starbattle": "Place stars so each row, column and region holds the same number; "
    "stars may not touch, not even diagonally.",
    "binairo": "Fill the grid with two symbols: no three equal in a row or column, "
    "each row and column has equally many of each, and no two rows or columns are identical.",
    "tents": "Put a tent next to each tree (horizontally or vertically), one tent per tree; "
    "tents never touch each other, and the numbers give the tents per row and column.",
    "minesweeper": "Mark the mines: each number tells how many of its eight neighbours are mines.",
    "akari": "Place lights so every white cell is lit and no two lights see each other; "
    "a number tells how many lights touch that black cell.",
    "kakurasu": "Shade cells so each row and column adds up to its target, where a "
    "shaded cell counts its position number.",
    "battleships": "Place the fleet without ships touching, even diagonally; the numbers "
    "give the ship cells per row and column.",
    "logicgrid": "Use the clues to match every item of each category with exactly one "
    "item of every other category.",
}

# Which explanation (`cond.<key>` in PHRASES) covers each Murdoku clue kind.
CONDITION_KEYS = {
    "in_region": "in_region",
    "outside": "in_region",
    "in_tagged": "in_tagged",
    "not_in_tagged": "in_tagged",
    "only_in_tagged": "in_tagged",
    "next_to": "next_to",
    "not_next_to": "next_to",
    "at": "at",
    "on_mark": "on_mark",
    "not_on_mark": "on_mark",
    "has_attribute": "attribute",
    "not_attribute": "attribute",
    "unique_attribute": "attribute",
    "has_role": "role",
    "not_role": "role",
    "some_role": "role",
    "roleless": "role",
    "at_most_one_role": "role",
    "role_subset": "role",
    "role_in_tagged": "role",
    "role_not_in_tagged": "role",
    "min_role_in_tagged": "role",
    "role_occupant": "role",
    "role_on": "role",
    "role_not_on": "role",
    "role_next_to": "role",
    "role_below": "role",
    "sole_role_companion": "role",
    "knight_from": "knight_from",
    "on": "on",
    "not_on": "on",
    "only_on": "only_on",
    "in_corner": "in_corner",
    "in_row": "in_line",
    "not_in_row": "in_line",
    "in_column": "in_line",
    "not_in_column": "in_line",
    "in_area_corner": "in_area_corner",
    "same_region": "same_region",
    "different_region": "same_region",
    "apart": "apart",
    "adjacent_regions": "adjacent_regions",
    "alone_with": "alone_with",
    "left_of": "left_of",
    "above": "above",
    "within": "distance",
    "at_least": "distance",
    "alone": "alone",
    "furthest": "furthest",
    "exactly": "exactly",
    "count": "count",
}

CONDITION_PHRASES = {
    "en": {
        "doc.conditions": "Conditions",
        "cond.in_region.name": "in an area",
        "cond.in_region": "The figure stands on a square of that area (or, with 'not', of none "
        "of them). An area may be split over several parts of the board.",
        "cond.in_tagged.name": "in a group of areas",
        "cond.in_tagged": "The figure stands in one of the areas of that group (or in none of "
        "them); the rules list which areas belong to each group.",
        "cond.next_to.name": "next to",
        "cond.next_to": "The figure's square shares a side with a square of the object, in the "
        "same area; diagonals do not count. A door, window or corner object counts across an "
        "area border.",
        "cond.at.name": "at a door or window",
        "cond.at": "The figure stands on one of the squares on either side of the door or window.",
        "cond.on_mark.name": "on a marked square",
        "cond.on_mark": "The figure stands on (or not on) a square carrying that mark.",
        "cond.attribute.name": "attributes",
        "cond.attribute": "An attribute is a fixed fact about a figure, listed beside the board; "
        "it never changes where anyone can stand.",
        "cond.role.name": "roles",
        "cond.role": "A role is held by some of the figures, as the role list says; a clue "
        "about a role only says where its holders can or cannot be.",
        "cond.knight_from.name": "a knight's move from",
        "cond.knight_from": "As a knight moves in chess: two squares one way and one square to "
        "the side. Area borders do not matter.",
        "cond.on.name": "on",
        "cond.on": "The figure stands on a square of that object (or not on one). Only "
        "standable objects, such as a chair or a bed, can be stood on.",
        "cond.only_on.name": "the only one on",
        "cond.only_on": "The figure stands on that object, and nobody else stands on any object "
        "of that kind.",
        "cond.in_corner.name": "in a corner",
        "cond.in_corner": "The figure stands on one of the four corner squares of the board.",
        "cond.in_line.name": "in a row or column",
        "cond.in_line": "The figure stands in (or not in) that numbered row or column; row 1 is "
        "at the top, column 1 at the left.",
        "cond.in_area_corner.name": "in the corner of an area",
        "cond.in_area_corner": "The figure stands on a square where two walls of its area meet "
        "at a right angle.",
        "cond.same_region.name": "same area",
        "cond.same_region": "The two figures are in the same area (or, for 'different', in "
        "different areas).",
        "cond.apart.name": "apart",
        "cond.apart": "The two figures are in different areas that do not share a side.",
        "cond.adjacent_regions.name": "neighbouring areas",
        "cond.adjacent_regions": "The two figures are in different areas that share a side.",
        "cond.alone_with.name": "alone with",
        "cond.alone_with": "The figure shares its area with exactly that many others (one if "
        "no number is given), and nobody else.",
        "cond.left_of.name": "left of",
        "cond.left_of": "Somewhere in a column further left, in any row; with a number, exactly "
        "that many columns further left.",
        "cond.above.name": "above",
        "cond.above": "Somewhere in a row higher up, in any column; with a number, exactly that "
        "many rows higher.",
        "cond.distance.name": "squares apart",
        "cond.distance": "Distance is counted in steps across sides, not diagonally: rows apart "
        "plus columns apart.",
        "cond.alone.name": "alone",
        "cond.alone": "Nobody else is in the same area.",
        "cond.furthest.name": "the furthest from",
        "cond.furthest": "Counted in steps across sides; every other figure is strictly closer.",
        "cond.exactly.name": "exactly n of",
        "cond.exactly": "Of the statements listed, exactly that many are true; the others are "
        "false.",
        "cond.count.name": "counts",
        "cond.count": "Counts the figures (or the empty areas or squares) that match; the "
        "number must be as stated.",
    },
    "nl": {
        "doc.conditions": "Voorwaarden",
        "cond.in_region.name": "in een gebied",
        "cond.in_region": "Het figuur staat op een vakje van dat gebied (of, met 'niet', van "
        "geen ervan). Een gebied kan uit meerdere delen van het bord bestaan.",
        "cond.in_tagged.name": "in een groep gebieden",
        "cond.in_tagged": "Het figuur staat in een van de gebieden van die groep (of in geen "
        "ervan); de spelregels noemen welke gebieden bij elke groep horen.",
        "cond.next_to.name": "naast",
        "cond.next_to": "Het vakje van het figuur deelt een zijde met een vakje van het object, "
        "in hetzelfde gebied; schuin telt niet. Een deur, raam of hoekobject telt ook over een "
        "gebiedsgrens heen.",
        "cond.at.name": "bij een deur of raam",
        "cond.at": "Het figuur staat op een van de vakjes aan weerszijden van de deur of het raam.",
        "cond.on_mark.name": "op een gemarkeerd vakje",
        "cond.on_mark": "Het figuur staat (niet) op een vakje met die markering.",
        "cond.attribute.name": "kenmerken",
        "cond.attribute": "Een kenmerk is een vast gegeven over een figuur, naast het bord "
        "vermeld; het verandert nooit waar iemand kan staan.",
        "cond.role.name": "rollen",
        "cond.role": "Een rol hoort bij sommige figuren, zoals de rollenlijst zegt; een "
        "aanwijzing over een rol zegt alleen waar de dragers wel of niet kunnen staan.",
        "cond.knight_from.name": "een paardensprong van",
        "cond.knight_from": "Zoals het paard in het schaakspel: twee vakjes de ene kant op en "
        "één opzij. Gebiedsgrenzen doen er niet toe.",
        "cond.on.name": "op",
        "cond.on": "Het figuur staat (niet) op een vakje van dat object. Alleen begaanbare "
        "objecten, zoals een stoel of een bed, kun je op staan.",
        "cond.only_on.name": "als enige op",
        "cond.only_on": "Het figuur staat op dat object, en niemand anders staat op een object "
        "van die soort.",
        "cond.in_corner.name": "in een hoek",
        "cond.in_corner": "Het figuur staat op een van de vier hoekvakjes van het bord.",
        "cond.in_line.name": "in een rij of kolom",
        "cond.in_line": "Het figuur staat (niet) in die genummerde rij of kolom; rij 1 is "
        "bovenaan, kolom 1 links.",
        "cond.in_area_corner.name": "in de hoek van een gebied",
        "cond.in_area_corner": "Het figuur staat op een vakje waar twee wanden van zijn gebied "
        "haaks samenkomen.",
        "cond.same_region.name": "zelfde gebied",
        "cond.same_region": "De twee figuren staan in hetzelfde gebied (of, bij 'verschillend', "
        "in verschillende gebieden).",
        "cond.apart.name": "uit elkaar",
        "cond.apart": "De twee figuren staan in verschillende gebieden die geen zijde delen.",
        "cond.adjacent_regions.name": "aangrenzende gebieden",
        "cond.adjacent_regions": "De twee figuren staan in verschillende gebieden die een zijde "
        "delen.",
        "cond.alone_with.name": "alleen met",
        "cond.alone_with": "Het figuur deelt zijn gebied met precies zoveel anderen (één als er "
        "geen getal staat), en met niemand anders.",
        "cond.left_of.name": "links van",
        "cond.left_of": "Ergens in een kolom verder naar links, in elke rij; met een getal "
        "precies zoveel kolommen verder naar links.",
        "cond.above.name": "boven",
        "cond.above": "Ergens in een hogere rij, in elke kolom; met een getal precies zoveel "
        "rijen hoger.",
        "cond.distance.name": "vakjes afstand",
        "cond.distance": "Afstand telt in stappen over zijden, niet schuin: rijen verschil plus "
        "kolommen verschil.",
        "cond.alone.name": "alleen",
        "cond.alone": "Niemand anders staat in hetzelfde gebied.",
        "cond.furthest.name": "het verst van",
        "cond.furthest": "Geteld in stappen over zijden; elk ander figuur staat echt dichterbij.",
        "cond.exactly.name": "precies n van",
        "cond.exactly": "Van de genoemde uitspraken zijn er precies zoveel waar; de rest is "
        "onwaar.",
        "cond.count.name": "aantallen",
        "cond.count": "Telt de figuren (of de lege gebieden of vakjes) die passen; het aantal "
        "moet kloppen.",
    },
}
for _language, _entries in CONDITION_PHRASES.items():
    PHRASES[_language].update(_entries)

NUMBERS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
           "ten", "eleven", "twelve"],
    "nl": ["nul", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen",
           "tien", "elf", "twaalf"],
}  # fmt: skip

MAX_LISTED = 3  # squares named outright alongside, or instead of, a description

# What a relation's other people are worth mentioning for: their rows, columns or regions.
ASPECT = {
    "above": "row",
    "left_of": "col",
    "same_region": "region",
    "different_region": "region",
    "apart": "region",
    "alone": "region",
}


@dataclass(frozen=True)
class Wording:
    """How to say things: a language from `PHRASES`, and names in it."""

    language: str = "en"
    words: dict[str, str] = field(default_factory=dict)
    phrases: dict[str, str] = field(default_factory=dict)
    numbered: bool = True
    people: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, text: str) -> "Wording":
        """The `Language:` and `Words:` sections of a puzzle file."""
        section = read_sections(text)
        language = section.get("Language", ["en"])[0]
        if language not in PHRASES:
            raise ValueError(f"no wording for language {language!r}; have {sorted(PHRASES)}")
        words = {}
        phrases = {}
        for line in section.get("Words", []):
            name, _, phrase = line.partition(":")
            if not phrase.strip():
                raise ValueError(f"Words: {line!r} is not like 'vuurtje: het vuurtje'")
            if name.strip() in PHRASES[language]:
                phrases[name.strip()] = phrase.strip()
            else:
                words[name.strip()] = phrase.strip()
        return cls(language, words, phrases)

    def unnumbered(self) -> "Wording":
        """The same wording that never points at clue numbers."""
        return dataclasses.replace(self, numbered=False)

    def __call__(self, key: str, **fields: Any) -> str:
        if not self.numbered and key in ("breaks", "breaks_first"):
            key += "_plain"
        template = self.phrases.get(key) or PHRASES[self.language][key]
        if self.people:
            fields = {
                k: self.people.get(v, v) if isinstance(v, str) else v for k, v in fields.items()
            }
        return template.format(**fields)

    def for_people(self, people: Iterable[str]) -> "Wording":
        """The same wording that calls a person by their `Words:` phrase, like "de leeuw"."""
        return dataclasses.replace(
            self, people={p: self.words[p] for p in people if p in self.words}
        )

    def number(self, n: int) -> str:
        names = NUMBERS[self.language]
        return names[n] if n < len(names) else str(n)

    def join(self, items: Sequence[str], word: str = "and") -> str:
        items = [self.people.get(item, item) for item in items]
        if len(items) <= 1:
            return "".join(items)
        return f"{', '.join(items[:-1])} {self(word)} {items[-1]}"


class Places:
    """Describes sets of squares in the board's own terms."""

    def __init__(self, board: Board, say: Wording) -> None:
        self.board = board
        self.say = say
        self.free = set(board.free)
        self.areas = self._areas()

    def square(self, sq: Square) -> str:
        return self.say("square", row=sq.row + 1, col=sq.col + 1)

    def squares(self, squares: Iterable[Square], word: str = "or") -> str:
        return self.say.join([self.square(sq) for sq in sorted(squares)], word)

    def region(self, name: str) -> str:
        return self.say.words.get(name) or self.say("region", name=name.replace("_", " "))

    def thing(self, name: str) -> str:
        if (
            name in self.board.edge_item_names
            or name in self.board.point_object_names
            or name in self.board.mark_names
        ):
            many = False
        else:
            many = len(_pieces(self.board.squares_of([name]))) > 1
        if name in self.say.words:
            said = self.say.words[name]
            article, _, noun = said.partition(" ")
            # "het perronbankje" names one of several benches as "een perronbankje";
            # a phrase with an adjective keeps its wording, as Dutch inflection may change.
            if many and article.lower() in DEFINITE and noun and " " not in noun:
                return self.say("a", name=noun)
            return said
        return self.say("a" if many else "the", name=name.replace("_", " "))

    def where_regions(self, names: Iterable[str]) -> str:
        return self.say.join([self.region(n) for n in names], "or")

    def regions(self, ids: set[str]) -> str:
        """Name candidate areas compactly, using an area tag where it fits."""
        names: list[str] = []
        left = set(ids)
        for tag in self.board.area_tags:
            inside = self.board.tagged_region_ids([tag])
            if inside <= left:
                names.append(tag)
                left -= inside
        names += [self.board.region_names[i] for i in sorted(left)]
        return self.where_regions(names)

    def line(self, kind: str, i: int) -> str:
        return self.say(kind, n=i + 1)

    def lines(self, kind: str, indices: Iterable[int], word: str = "and") -> str:
        """'row 3', or 'rows 3 and 6', 'rows 1 to 3' (with `word` 'or': 'row 3 or 6')."""
        ordered = sorted(indices)
        if len(ordered) == 1:
            return self.line(kind, ordered[0])
        if len(ordered) > 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
            listed = self.say("through", a=ordered[0] + 1, b=ordered[-1] + 1)
        else:
            listed = self.say.join([str(i + 1) for i in ordered], word)
        if word == "or":
            return self.say(kind, n=listed)
        return self.say(f"{kind}s", list=listed)

    def where(self, chosen: set[Square], within: set[Square], most: int = 2) -> str | None:
        """A short exact description of `chosen` among `within`, if there is one:
        up to `most` of region, row, column, standable object or next-to-object."""
        tests = [(name, test) for name, test in self._tests(chosen) if all(map(test, chosen))]
        found: list[str] = []
        for size in range(1, most + 1):
            for combo in combinations(tests, size):
                if {sq for sq in within if all(test(sq) for _, test in combo)} == chosen:
                    found.append(", ".join(name for name, _ in combo))
            if found:
                break
        return min(found, key=len) if found else None

    def describe(
        self, who: str, chosen: set[Square], within: set[Square], *, placing: bool = True
    ) -> str:
        """The shortest exact way to say where `who` can be, out of `within`:
        'Jos zit op de woonboot (r8k3 of r8k4)', 'Otto zit niet in rij 1'.
        One square left is a placement, in bold, unless not `placing`."""
        if len(chosen) == 1:
            if placing:
                return self.placed(who, min(chosen))
            return self.say("is", who=who, where=self.say("on", what=self.square(min(chosen))))
        ways: list[str] = []
        if (where := self.where(chosen, within)) is not None:
            listed = f" ({self.squares(chosen)})" if len(chosen) <= MAX_LISTED else ""
            ways.append(self.say("is", who=who, where=where) + listed)
        if (gone := self.where(within - chosen, within, most=1)) is not None:
            ways.append(self.say("is_not", who=who, where=gone))
        if len(chosen) <= MAX_LISTED + 1:
            ways.append(self.say("is", who=who, where=self.say("on", what=self.squares(chosen))))
        if ways:
            return min(ways, key=len)
        return self.say("count", who=who, n=self.say.number(len(chosen)))

    def roughly(self, who: str, chosen: set[Square], kind: str) -> str:
        """Where `who` can be as far as one clue cares: the rows, columns or
        regions `chosen` touches (kind 'row', 'col' or 'region')."""
        if len(chosen) < MAX_LISTED:
            return self.say("is", who=who, where=self.say("on", what=self.squares(chosen)))
        if kind == "region":
            where = self.regions({self.board.region_of(sq) for sq in chosen})
        else:
            spans = {sq.row if kind == "row" else sq.col for sq in chosen}
            where = self.say("in", what=self.lines(kind, spans, "or"))
        return self.say("is", who=who, where=where)

    def placed(self, who: str, square: Square) -> str:
        return self.say("placed", who=who, square=self.square(square))

    def _areas(self) -> list[tuple[str, Callable[[Square], bool]]]:
        board = self.board
        areas: list[tuple[str, Callable[[Square], bool]]] = []
        for name in sorted({obj.name for obj in board.standable_objects}):
            spots = board.squares_of([name])
            areas.append((self.say("on", what=self.thing(name)), spots.__contains__))
        for name in sorted(board.object_names):
            near = {
                sq
                for t in board.squares_of([name])
                for sq in self.free
                if abs(sq.row - t.row) + abs(sq.col - t.col) == 1
                and board.region_of(sq) == board.region_of(t)
            }
            areas.append((self.say("next_to", what=self.thing(name)), near.__contains__))
        for name in sorted(board.edge_item_names):
            cells = board.edge_item_cells([name])
            areas.append((self.say("at", what=self.thing(name)), cells.__contains__))
        for name in sorted(board.point_object_names):
            cells = board.point_object_cells([name])
            areas.append((self.say("next_to", what=self.thing(name)), cells.__contains__))
        for name in sorted(board.mark_names):
            cells = board.mark_cells([name])
            areas.append((self.say("on", what=self.thing(name)), cells.__contains__))
        return areas

    def _region_of(self, chosen: set[Square]) -> tuple[str, Callable[[Square], bool]]:
        """The test 'in the regions `chosen` lies in'."""
        ids = {self.board.region_of(sq) for sq in chosen}
        board = self.board
        return self.regions(ids), lambda sq: board.region_of(sq) in ids

    def _tests(self, chosen: set[Square]) -> list[tuple[str, Callable[[Square], bool]]]:
        rows = {sq.row for sq in chosen}
        cols = {sq.col for sq in chosen}
        return [
            self._region_of(chosen),
            (self.say("in", what=self.lines("row", rows, "or")), lambda sq: sq.row in rows),
            (self.say("in", what=self.lines("col", cols, "or")), lambda sq: sq.col in cols),
            *self.areas,
        ]


@dataclass
class _State:
    """Where everyone can still be, who is placed (in order), and what the
    reader has been told about the rest."""

    options: dict[str, set[Square]]
    told: dict[str, set[Square]]
    placed: dict[str, Square] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    history: list[Step] = field(default_factory=list)
    announced: list[str] = field(default_factory=list)  # placed in bold so far, in order
    role_told: dict[tuple[str, str], bool] = field(default_factory=dict)

    def announce(self, person: str) -> None:
        if person not in self.announced:
            self.announced.append(person)

    def apply(self, steps: Sequence[Step]) -> None:
        for step in steps:
            self.history.append(step)
            if step.var not in self.options:
                continue
            if step.asserted:
                self.options[step.var] = {step.value}
                self.placed[step.var] = step.value
                self.order.append(step.var)
            else:
                self.options[step.var].discard(step.value)


class Story:
    """Writes the explanation of one solved Murdoku."""

    def __init__(self, board: Board, clues: Sequence[Clue], say: Wording) -> None:
        self.board = board
        self.clues = tuple(clues)
        say = say.for_people(board.people)
        self.say = say
        self.places = Places(board, say)
        self.about = {rule.name: rule.about for rule in board_rules(board)}
        self.conditions = {c.label: c for c in conditions(board, self.clues)}
        self.role_conditions: dict[str, RoleCondition] = {
            rule.label: rule for rule in role_conditions(board, self.clues)
        }
        self.quantified_conditions: dict[str, QuantifiedCondition] = {
            condition.label: condition for condition in quantified_conditions(board, self.clues)
        }
        self.global_counts: dict[str, GlobalCountCondition] = {
            condition.label: condition for condition in global_count_conditions(board, self.clues)
        }
        self.role_variables = {
            board.role_variable(person, role.name): (person, role.name)
            for role in board.roles
            for person in board.people
        }
        self.model = compile_puzzle(board, self.clues)
        self.auxiliary_variables = (
            set(self.model.all_variables) - set(self.board.people) - set(self.role_variables)
        )
        self.global_empty_units = self._global_empty_unit_variables()

    def _global_empty_unit_variables(self) -> dict[str, tuple[str, str | Square]]:
        units: dict[str, tuple[str, str | Square]] = {}
        for condition in self.global_counts.values():
            if condition.kind == "empty_areas":
                targets: Iterable[tuple[Literal["area", "cell"], str | Square]] = (
                    ("area", region) for region in condition.regions(self.board)
                )
            elif condition.kind == "empty_cells":
                targets = (("cell", square) for square in sorted(condition.cells(self.board)))
            else:
                continue
            for kind, unit in targets:
                prefix = (
                    "__" + global_count_unit_prefix("area", str(unit))
                    if kind == "area"
                    else "__" + global_count_unit_prefix("cell", str(unit))
                )
                variable = next(
                    (
                        name
                        for name in self.model.all_variables
                        if name == prefix or name.startswith(prefix + "_")
                    ),
                    None,
                )
                if variable is not None:
                    units[variable] = (kind, unit)
        return units

    def tell(self) -> str:
        start = self.model.clone()
        compiled = list(self.model.log)
        moves: list[Move] = []
        role_moves: set[int] = set()

        def collect(rule: str, steps: Sequence[Step]) -> None:
            if (move := Move.of(rule, steps)) is not None:
                moves.append(move)
                if any(
                    step.var in self.role_variables
                    or step.var.startswith("__role_")
                    or any("role" in source for source in step.sources)
                    or self._global_count_for_sources(step.sources) is not None
                    for step in steps
                ):
                    role_moves.add(id(move))

        Solver(self.model.clone()).solve(on_step=collect)
        firings: list[tuple[str, Sequence[Step]]] = []
        necessary = {id(move) for move in shortest(start, moves)} | role_moves
        replay(
            start,
            [move for move in moves if id(move) in necessary],
            lambda rule, steps: firings.append((rule, steps)),
        )

        options = {p: {start.value_of(lit) for lit in start.options(p)} for p in self.board.people}
        state = _State(options, {p: set(s) for p, s in options.items()})
        state.history = compiled
        paragraphs = [self._opening(compiled, state)]
        sentences: list[str] = []
        placed: list[str] = []
        mark = len(state.announced)  # who the current bullet has placed starts here
        refuted: list[tuple[str, Square, str]] = []  # what_ifs waiting to be said together
        for i, (rule, steps) in enumerate(firings):
            if rule == "what_if":
                step = steps[0]
                if step.var in self.board.people:
                    refuted.append(self._what_if(step, state))
                else:
                    state.apply(steps)
                    if step.var in self.global_empty_units:
                        sentences.append(f"{self._global_empty_unit_text(step)}.")
                    elif step.var in self.role_variables and (
                        text := self._role_step_text(step, state)
                    ):
                        sentences.append(f"{_cap(text)}.")
            else:
                sentences += self._refuted(refuted)
                refuted = []
                said = self._firing(rule, steps, state)
                if said:
                    sentences.append(said)
                    if rule == "single" and steps[0].asserted and steps[0].var in self.board.people:
                        placed.append(steps[0].var)
            last = i + 1 == len(firings)
            if placed and (last or firings[i + 1][0] != "single"):
                named = state.announced[mark:]
                lead = self.say.join(named)
                if last and len(named) > 3:
                    lead = self.say("the_rest")
                paragraphs.append(f"**{lead}.** {' '.join(self._merged(sentences))}")
                sentences, placed = [], []
                mark = len(state.announced)
        sentences += self._refuted(refuted)
        if sentences:
            paragraphs.append(" ".join(self._merged(sentences)))
        return "\n\n".join(f"- {p}" for p in paragraphs)

    def _merged(self, sentences: Sequence[str]) -> list[str]:
        """Say a reason once when consecutive sentences draw several conclusions from it."""
        so = f", {self.say('so')} "
        out: list[str] = []
        premise: str | None = None
        outcomes: list[str] = []

        def flush() -> None:
            if premise is not None:
                out.append(f"{premise}{so}{self.say.join(outcomes)}.")

        for sentence in sentences:
            head, found, tail = sentence.partition(so)
            if found and tail.endswith(".") and so not in tail:
                if head == premise:
                    outcomes.append(tail[:-1])
                    continue
                flush()
                premise, outcomes = head, [tail[:-1]]
                continue
            flush()
            premise, outcomes = None, []
            out.append(sentence)
        flush()
        return out

    # --- paragraphs and sentences ------------------------------------------

    def _opening(self, compiled: Sequence[Step], state: _State) -> str:
        """Each clue about one person, with where that leaves them right after it."""
        said: list[str] = []
        seen_sources: set[str] = set()
        left = {p: set(self.places.free) for p in self.board.people}
        for label, group in groupby(compiled, key=lambda s: s.sources[0]):
            seen_sources.add(label)
            steps = list(group)
            for step in steps:
                if step.var in left:
                    left[step.var].discard(step.value)
            role_rule = self.role_conditions.get(label)
            if role_rule is not None:
                text = self._role_condition_text(role_rule)
                said.append(f"{_cap(text)}{self._role_ref(role_rule)}.")
                if role_rule.kind in ("has_role", "not_role"):
                    person, role = role_rule.args
                    state.role_told[person, role] = role_rule.kind == "has_role"
                continue
            quantified = self.quantified_conditions.get(label)
            if quantified is not None:
                said.append(
                    f"{_cap(self._quantified_text(quantified))}{self._quantified_ref(quantified)}."
                )
                continue
            condition = self.conditions.get(label)
            if condition is None:
                for step in steps:
                    if step.var in self.role_variables:
                        text = self._role_step_text(step, state)
                        if text:
                            said.append(f"{_cap(text)}.")
                continue
            if condition.number is None or condition.kind in ("in_region", "outside"):
                continue
            (person,) = condition.people
            squares = left[person]
            if len(squares) == 1:
                where = self.places.placed(person, min(squares))
                state.announce(person)
            elif len(squares) <= MAX_LISTED + 1:
                where = self.places.squares(squares)
            else:
                where = self.say("squares", n=self.say.number(len(squares)))
            said.append(f"{_cap(self._clue(condition))} ({condition.number}): {where}.")
        for number, (kind, args) in enumerate(self.clues, 1):
            if kind not in ("has_attribute", "not_attribute", "unique_attribute"):
                continue
            label = " ".join((kind, *args))
            if label not in seen_sources:
                said.append(f"{_cap(self._clue_text(kind, args, args[:1]))} ({number}).")
        said.extend(
            f"{_cap(self._global_count_text(condition))}{self._global_count_ref(condition)}."
            for condition in self.global_counts.values()
        )
        return f"**{self.say('direct')}.** {' '.join(said)}"

    def _firing(self, rule: str, steps: Sequence[Step], state: _State) -> str:
        before = {p: set(s) for p, s in state.options.items()}
        state.apply(steps)
        if steps and all(self._fixed_role(step) for step in steps):
            return ""
        role_sentences = [
            text
            for step in steps
            if step.var in self.role_variables and step.placing is None
            if (text := self._role_step_text(step, state))
        ]
        if role_sentences:
            global_condition = self._global_count_for_sources(
                source for step in steps for source in step.sources
            )
            if global_condition is not None:
                clue = self._global_count_reason(global_condition) + self._global_count_ref(
                    global_condition
                )
                return f"{_cap(clue)}, {self.say('so')} {self.say.join(role_sentences)}."
            quantified_condition = next(
                (
                    target_condition
                    for step in steps
                    for source in step.sources
                    if (target_condition := self._quantified_condition_for_source(source))
                    is not None
                ),
                None,
            )
            if quantified_condition is not None:
                clue = _cap(self._quantified_text(quantified_condition)) + self._quantified_ref(
                    quantified_condition
                )
                return f"{clue}, {self.say('so')} {self.say.join(role_sentences)}."
            changed = [p for p in self.board.people if state.options[p] != before[p]]
            if not changed and (reason := self._role_step_reason(steps)):
                return f"{_cap(reason)}, {self.say('so')} {self.say.join(role_sentences)}."
            if changed:
                return (
                    f"{self.say.join(role_sentences)}, {self.say('so')} "
                    + self._outcome(changed, before, state)
                    + "."
                )
            return f"{self.say.join(role_sentences)}."
        if rule == "single":
            if steps[0].var in self.auxiliary_variables:
                if (
                    global_condition := self._global_count_for_sources(steps[0].sources)
                ) is not None:
                    changed = [p for p in self.board.people if state.options[p] != before[p]]
                    return self._global_count_deduction(
                        global_condition, steps[0], changed, before, state
                    )
                if steps[0].var in self.global_empty_units:
                    return self._global_empty_unit_text(steps[0])
                return ""
            source = steps[0].sources[0] if steps[0].sources else ""
            constraint = next((c for c in self.model.constraints if c.name == source), None)
            if constraint is not None and constraint.kind is Kind.COUNT:
                changed = [p for p in self.board.people if state.options[p] != before[p]]
                return self._count(steps[0], changed, before, state)
            if steps[0].var in self.role_variables:
                return ""
            if steps[0].var not in self.board.people:
                return self._literal_text(steps[0], asserted=True)
            return self._placement(steps[0], state)
        changed = [p for p in self.board.people if state.options[p] != before[p]]
        if rule == "count":
            return self._count(steps[0], changed, before, state)
        if rule == "relations":
            outcome = self._outcome(changed, before, state)
            return self._relation(steps[0], before, changed, outcome)
        if rule == "chains":
            return self._chain(steps[0], changed, before, state)
        return self._cover(steps[0], changed, before, state)

    def _chain(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        """'If A is not on a, then B is on b, then ... so A on a or Z on z; either way ...'"""
        square = self.places.square
        (who, at), *rest = step.chain
        parts = [self.say("chain_if", who=who, square=square(at))]
        for i, (who, at) in enumerate(rest):
            key = "chain_on" if i % 2 == 0 else "chain_off"
            why = self._link_reason(step.sources[i]) if i < len(step.sources) else ""
            parts.append(self.say(key, who=who, square=square(at)) + why)
        (first, a), (last, z) = step.chain[0], step.chain[-1]
        ends = self.say.join(
            [
                self.say("is", who=first, where=self.say("on", what=square(a))),
                self.say("is", who=last, where=self.say("on", what=square(z))),
            ],
            "or",
        )
        outcome = []
        for p in changed:
            gone = self.places.squares(before[p] - state.options[p])
            outcome.append(self.say("is_not", who=p, where=self.say("on", what=gone)))
            state.told[p] -= before[p] - state.options[p]
            if len(state.options[p]) == 1 and p not in state.announced:
                state.announce(p)
                outcome.append(self.places.placed(p, min(state.options[p])))
        so = self.say("chain_so", ends=ends, outcome=self.say.join(outcome))
        if len(step.chain) == 2:
            return _cap(self.say("chain_either", ends=ends, outcome=self.say.join(outcome)))
        return f"{', '.join(parts)}. {so}"

    def _count(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        if (global_condition := self._global_count_for_sources(step.sources)) is not None:
            return self._global_count_deduction(global_condition, step, changed, before, state)
        if step.var in self.global_empty_units:
            return self._global_empty_unit_text(step)
        if step.var in self.auxiliary_variables:
            return ""
        if step.sources and (
            target_condition := self._quantified_condition_for_source(step.sources[0])
        ):
            clue = _cap(self._quantified_text(target_condition)) + self._quantified_ref(
                target_condition
            )
            outcome = self._outcome(changed, before, state) if changed else self._literal_text(step)
            return f"{clue}, {self.say('so')} {outcome}."
        constraint = next(c for c in self.model.constraints if c.name == step.sources[0])
        allowed = constraint.allowed_counts
        if constraint.reified_by is not None:
            var = self.model.var_of(constraint.reified_by)
            value = self.model.value_of(constraint.reified_by)
            known = next(
                (
                    item.asserted
                    for item in reversed(state.history)
                    if item.var == var and item.value == value
                ),
                None,
            )
            if known is None:
                if self.model.is_true(constraint.reified_by):
                    known = True
                elif self.model.is_false(constraint.reified_by):
                    known = False
            if known is False:
                allowed = frozenset(range(len(constraint.literals) + 1)) - allowed
        counts = self.say.join([self.say.number(n) for n in sorted(allowed)], "or")
        reason = self._role_area_reason(constraint, allowed) or self.say(
            "count_reason", name=constraint.name, counts=counts
        )
        outcome = self._outcome(changed, before, state) if changed else self._literal_text(step)
        return f"{_cap(reason)}, {self.say('so')} {outcome}."

    def _role_step_reason(self, steps: Sequence[Step]) -> str | None:
        """Why a role became known: the role rule or role count behind its hidden constraint."""
        by_name = {c.name: c for c in self.model.constraints}
        for step in steps:
            for source in step.sources:
                if (rule := self._role_condition_for_source(source)) is not None:
                    return self._role_condition_text(rule) + self._role_ref(rule)
                constraint = by_name.get(source)
                if constraint is None or step.var not in self.role_variables:
                    continue
                _, role = self.role_variables[step.var]
                name = self.say.words.get(role) or role.replace("_", " ")
                if constraint.family == "role cardinality" and constraint.allowed_counts == {1}:
                    return self.say("role_only_one", role=name)
                if constraint.family == "role area membership":
                    rule = next(
                        (
                            r
                            for r in self.role_conditions.values()
                            if r.kind == "min_role_in_tagged" and r.args[0] == role
                        ),
                        None,
                    )
                    if rule is not None:
                        return self._role_condition_text(rule) + self._role_ref(rule)
        return None

    def _role_area_reason(self, constraint: Any, allowed: frozenset[int]) -> str | None:
        """'Ada has role guide and is therefore in the hall', for a hidden role-and-area count.

        Such a count holds a role-membership literal followed by the squares of
        one area; the person, role and area are read from those literals.
        """
        if constraint.family != "role area membership" or len(constraint.literals) < 2:
            return None
        first, square = constraint.literals[0], self.model.value_of(constraint.literals[1])
        held = self.role_variables.get(self.model.var_of(first))
        if held is None or not isinstance(square, Square):
            return None
        person, role = held
        area = self.places.region(self.board.region_names[self.board.region_of(square)])
        role_name = self.say.words.get(role) or role.replace("_", " ")
        key = "role_area_in" if allowed == {2} else "role_area_out"
        return self.say(key, who=person, role=role_name, area=area)

    def _global_count_for_sources(self, sources: Iterable[str]) -> GlobalCountCondition | None:
        for source in sources:
            for label, condition in self.global_counts.items():
                if source == label or source.startswith(label + " "):
                    return condition
        return None

    @staticmethod
    def _global_count_ref(condition: GlobalCountCondition) -> str:
        return "" if condition.number is None else f" ({condition.number})"

    def _global_count_quantity(self, condition: GlobalCountCondition) -> str:
        comparison = condition.comparison
        if comparison == "=":
            return self.say("global_count.exact", n=self.say.number(condition.operands[0]))
        if comparison == "<=":
            return self.say("global_count.at_most", n=self.say.number(condition.operands[0]))
        if comparison == ">=":
            return self.say("global_count.at_least", n=self.say.number(condition.operands[0]))
        if comparison in ("odd", "even"):
            return self.say(f"global_count.{comparison}")
        low, high = condition.operands
        return self.say("global_count.range", low=self.say.number(low), high=self.say.number(high))

    def _global_count_where(self, condition: GlobalCountCondition) -> str:
        selector = condition.selector
        if selector is None:
            return ""
        if selector.kind in ("area", "tag"):
            return self.places.regions(condition.regions(self.board))
        if selector.kind == "rows":
            lines = self.places.lines("row", line_indices(selector.name, self.board.size), "or")
            return self.say("in", what=lines)
        if selector.kind == "columns":
            lines = self.places.lines("col", line_indices(selector.name, self.board.size), "or")
            return self.say("in", what=lines)
        return self.say("on", what=self.places.thing(selector.name))

    def _global_count_text(self, condition: GlobalCountCondition) -> str:
        quantity = self._global_count_quantity(condition)
        singular = (condition.comparison in ("=", "<=", ">=") and condition.operands == (1,)) or (
            condition.comparison == "range" and condition.operands == (1, 1)
        )
        if condition.kind.startswith("people_"):
            noun = (
                ("person" if singular else "people")
                if self.say.language == "en"
                else ("persoon" if singular else "mensen")
            )
            verb = (
                ("is" if singular else "are")
                if self.say.language == "en"
                else ("is" if singular else "zijn")
            )
        elif condition.kind == "empty_areas":
            noun = (
                ("area" if singular else "areas")
                if self.say.language == "en"
                else ("gebied" if singular else "gebieden")
            )
            verb = (
                ("is" if singular else "are")
                if self.say.language == "en"
                else ("is" if singular else "zijn")
            )
        else:
            noun = (
                ("free cell" if singular else "free cells")
                if self.say.language == "en"
                else ("vrij vakje" if singular else "vrije vakjes")
            )
            verb = (
                ("is" if singular else "are")
                if self.say.language == "en"
                else ("is" if singular else "zijn")
            )

        if condition.kind == "people_on":
            assert condition.selector is not None
            if condition.selector.kind == "object_kind":
                labels = {
                    "en": {"blocking": "blocking", "standable": "standable"},
                    "nl": {"blocking": "blokkerende", "standable": "begaanbare"},
                }
                kind_label = labels[self.say.language][condition.selector.name]
                target = self.say("global_count.object_kind", kind=kind_label)
            else:
                target = self.places.thing(condition.selector.name)
            on_verb = verb if self.say.language == "en" else ("staat" if singular else "staan")
            return self.say(
                "global_count.people_on",
                quantity=quantity,
                noun=noun,
                verb=on_verb,
                target=target,
            )
        if condition.kind == "people_in":
            return self.say(
                "global_count.people_in",
                quantity=quantity,
                noun=noun,
                verb=verb,
                where=self._global_count_where(condition),
            )
        if condition.kind == "people_with":
            assert condition.selector is not None
            name = self.say.words.get(
                condition.selector.name, condition.selector.name.replace("_", " ")
            )
            if condition.selector.kind == "role":
                target = f"the {name} role" if self.say.language == "en" else f"de rol {name}"
            else:
                target = (
                    f"the {name} attribute" if self.say.language == "en" else f"het kenmerk {name}"
                )
            return self.say(
                "global_count.people_with",
                quantity=quantity,
                noun=noun,
                have=("has" if singular else "have")
                if self.say.language == "en"
                else ("heeft" if singular else "hebben"),
                target=target,
            )
        where = self._global_count_where(condition)
        if condition.kind == "empty_areas":
            if condition.comparison == "=" and condition.operands == (0,):
                return self.say("global_count.no_empty_areas", where=f" {where}" if where else "")
            return self.say(
                "global_count.empty_areas",
                quantity=quantity,
                noun=noun,
                verb=verb,
                where=f" {where}" if where else "",
            )
        if condition.comparison == "=" and condition.operands == (0,):
            return self.say("global_count.no_empty_cells", where=where)
        return self.say(
            "global_count.empty_cells",
            quantity=quantity,
            noun=noun,
            verb=verb,
            where=where,
        )

    def _global_count_reason(self, condition: GlobalCountCondition) -> str:
        text = self._global_count_text(condition)
        area_capacity = condition.kind == "empty_areas" or (
            condition.kind == "people_in"
            and condition.selector is not None
            and condition.selector.kind in ("area", "tag")
        )
        return f"{self.say('global_count.capacity')}: {text}" if area_capacity else text

    def _global_count_deduction(
        self,
        condition: GlobalCountCondition,
        step: Step,
        changed: list[str],
        before: dict[str, set[Square]],
        state: _State,
    ) -> str:
        clue = _cap(self._global_count_reason(condition)) + self._global_count_ref(condition)
        if step.var in self.global_empty_units:
            outcome = self._global_empty_unit_text(step)
        elif changed:
            outcome = self._outcome(changed, before, state)
        else:
            outcome = self._literal_text(step)
        return f"{clue}, {self.say('so')} {outcome}."

    def _global_empty_unit_text(self, step: Step) -> str:
        kind, unit = self.global_empty_units[step.var]
        is_empty = step.value if step.asserted else not step.value
        if kind == "area":
            where = self.places.region(self.board.region_names[str(unit)])
            return self.say(
                "global_count.area_empty" if is_empty else "global_count.area_occupied",
                where=where,
            )
        assert isinstance(unit, Square)
        return self.say(
            "global_count.cell_empty" if is_empty else "global_count.cell_occupied",
            square=self.places.square(unit),
        )

    def _link_reason(self, source: str) -> str:
        """' (row 8)' or ' (7)' after a chain link; nothing when it is one person
        or one square, which the sentence already makes plain."""
        if source in self.conditions:
            return self._ref(self.conditions[source])
        if (quantified := self._quantified_condition_for_source(source)) is not None:
            return self._quantified_ref(quantified)
        kind, what = self.about.get(source, ("", None))
        if kind in ("row", "col"):
            return f" ({self.places.line(kind, what)})"
        return ""

    def _outcome(self, people: Sequence[str], before: dict[str, set[Square]], state: _State) -> str:
        """Where `people` can be now, out of where they could be `before`."""
        for p in people:
            state.told[p] = set(state.options[p])
            if len(state.options[p]) == 1:
                state.announce(p)
        return self.say.join([self.places.describe(p, state.options[p], before[p]) for p in people])

    def _relation(
        self, step: Step, before: dict[str, set[Square]], changed: list[str], outcome: str
    ) -> str:
        """The clue, where the other people involved were known to be, and the upshot."""
        source = step.sources[0]
        if (role_rule := self._role_condition_for_source(source)) is not None:
            clue = _cap(self._role_condition_text(role_rule))
            return f"{clue}, {self.say('so')} {outcome}." if outcome else f"{clue}."
        if (quantified := self._quantified_condition_for_source(source)) is not None:
            if not outcome:  # only the clue's hidden witness variables changed
                return ""
            clue = _cap(self._quantified_text(quantified)) + self._quantified_ref(quantified)
            return f"{clue}, {self.say('so')} {outcome}."
        if source not in self.conditions and (apart := self._role_apart(source)) is not None:
            return f"{_cap(apart)}, {self.say('so')} {outcome}." if outcome else f"{_cap(apart)}."
        condition = self.conditions[source]
        clue = _cap(self._clue(condition)) + self._ref(condition)
        aspect = ASPECT.get(condition.kind)
        evidence = [
            self.places.roughly(p, before[p], aspect)
            if aspect
            else self.places.describe(p, before[p], self.places.free, placing=False)
            for p in condition.people
            if p not in changed and before[p] != self.places.free
        ]
        if evidence:
            return f"{clue}. {_cap(self.say.join(evidence))}, {self.say('so')} {outcome}."
        return f"{clue}, {self.say('so')} {outcome}."

    def _cover(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        """Some people fill some rows (or columns), or some rows only fit some people."""
        if (condition := self._global_count_for_sources(step.sources)) is not None:
            return self._global_count_deduction(condition, step, changed, before, state)
        inner = [self.about.get(name, ("constraint", name)) for name in step.sources]
        outer = [self.about.get(name, ("constraint", name)) for name in step.scope]
        kinds_in = {k for k, _ in inner}
        kinds_out = {k for k, _ in outer}
        if len(kinds_in) == 1 and len(kinds_out) == 1 and kinds_out <= {"row", "col"}:
            ((kind_in,), (kind,)) = (kinds_in, kinds_out)
            where = self.say("in", what=self.places.lines(kind, [i for _, i in outer], "or"))
            many = "_many" if len(inner) > 1 else "_one"
            if kind_in == "person":
                text = self.say(
                    "can_only" + many, who=self.say.join([p for _, p in inner]), where=where
                )
            else:
                lines = self.places.lines(kind_in, [i for _, i in inner])
                text = self.say("filled_only" + many, lines=lines, where=where)
            text = f"{_cap(text)}, {self.say('nobody_else')}"
            # Being shut out of those lines goes without saying; only news is worth a word.
            news = [p for p in changed if len(state.options[p]) <= MAX_LISTED]
            if news:
                return f"{text}: {self._outcome(news, before, state)}."
            return f"{text}."
        outcome = self._outcome(changed, before, state)
        if kinds_out == {"person"} and len(kinds_in) == 1 and kinds_in <= {"row", "col"}:
            (kind,) = kinds_in
            lines = self.places.lines(kind, [i for _, i in inner])
            key = "only_one" if len(inner) == 1 else "only_many"
            text = self.say(key, lines=lines, who=self.say.join([p for _, p in outer]))
            return f"{_cap(text)}, {self.say('so')} {outcome}."
        return f"{_cap(outcome)}."

    def _placement(self, step: Step, state: _State) -> str:
        who, square = step.var, step.value
        if who in state.announced:
            return ""
        state.announce(who)
        placed = self.places.placed(who, square)
        kind, what = self.about[step.sources[0]]
        gone = state.told[who] - {square}
        state.told[who] = {square}
        if kind in ("row", "col"):
            text = self.say("only_one", lines=self.places.line(kind, what), who=who)
            return f"{_cap(text)}: {placed}."
        reasons = self._blockers(who, gone, state)
        if reasons is None:
            text = self.say("only_left", who=who, square=self.places.square(square))
            return f"{_cap(text)}: {placed}."
        if reasons:
            return f"{_cap(self.say.join(reasons))}, {self.say('so')} {placed}."
        return f"{placed}."

    def _blockers(self, who: str, gone: set[Square], state: _State) -> list[str] | None:
        """Who took the squares the reader still had for `who`, fewest people
        first; None if that takes more than two."""
        takers: dict[str, set[Square]] = {}
        for sq in gone:
            for other, there in state.placed.items():
                if other != who and (there.row == sq.row or there.col == sq.col):
                    takers.setdefault(other, set()).add(sq)
        chosen: list[str] = []
        left = set(gone)
        while left:
            best = max(
                takers, key=lambda p: (len(takers[p] & left), state.order.index(p)), default=None
            )
            if best is None or not takers[best] & left:
                return None
            chosen.append(best)
            left -= takers[best]
        if len(chosen) > 2:
            return None
        said = []
        for other in chosen:
            there = state.placed[other]
            covered = takers[other] & gone
            if all(sq.row == there.row for sq in covered):
                line = self.places.line("row", there.row)
            elif all(sq.col == there.col for sq in covered):
                line = self.places.line("col", there.col)
            else:
                line = self.say.join(
                    [self.places.line("row", there.row), self.places.line("col", there.col)]
                )
            said.append(self.say("takes_line", who=other, line=line))
        return said

    def _what_if(self, step: Step, state: _State) -> tuple[str, Square, str]:
        """Who could not be where, and the chain of events that rules it out."""
        who, square = step.var, step.value
        needed = essential(self.model, state.history, step)
        state.apply([step])
        state.told[who].discard(square)
        parts: list[str] = []
        refs: list[int] = []
        for j in needed:
            inner = step.trail[j]
            if inner.asserted and j > 0 and inner.var in self.board.people:
                parts.append(
                    self.say("then_on", who=inner.var, square=self.places.square(inner.value))
                )
            for name in inner.sources:
                condition = self.conditions.get(name)
                if condition is not None and condition.number is not None:
                    refs.append(condition.number)
                global_count = self.global_counts.get(name)
                if global_count is not None and global_count.number is not None:
                    refs.append(global_count.number)
        parts.append(self._broken(step, first=not parts))
        source = step.sources[0] if step.sources else None
        broken = self.conditions.get(source) if source else None
        broken_global = self._global_count_for_sources(step.sources)
        other = None
        if source is not None and broken is None and broken_global is None:
            other = self._quantified_condition_for_source(
                source
            ) or self._role_condition_for_source(source)
        broken_number = (
            broken.number
            if broken is not None
            else broken_global.number
            if broken_global is not None
            else other.number
            if other is not None
            else None
        )
        cited = sorted(set(refs) - {broken_number})
        if not cited or not self.say.numbered:
            return who, square, ", ".join(parts)
        listed = self.say.join([str(n) for n in cited])
        explained = (
            broken is not None
            or other is not None
            or (broken_global is None and source not in self.about)
        )
        ref = self.say("via", refs=listed) if explained else listed
        return who, square, f"{', '.join(parts)} ({ref})"

    def _refuted(self, refuted: Sequence[tuple[str, Square, str]]) -> list[str]:
        """Consecutive what_ifs, one sentence per person and reason."""
        sentences: list[str] = []
        previous = None
        for (who, chain), group in groupby(refuted, key=lambda r: (r[0], r[2])):
            squares = self.places.squares([sq for _, sq, _ in group])
            key = "nor" if who == previous else "cannot"
            sentences.append(self.say(key, who=who, squares=squares, chain=chain))
            previous = who
        return sentences

    def _broken(self, step: Step, first: bool) -> str:
        """The contradiction a what_if ran into."""
        source = step.sources[0] if step.sources else None
        if (global_count := self._global_count_for_sources(step.sources)) is not None:
            return self.say("global_count.breaks", clue=self._global_count_text(global_count))
        if source in self.conditions:
            condition = self.conditions[source]
            suffix = "_first" if first else ""
            if condition.number is not None and self.say.numbered:
                return self.say(f"breaks{suffix}", n=condition.number)
            if quoted := self._clue(condition):
                return self.say(f"breaks_said{suffix}", clue=_cap(quoted))
            if condition.number is None:
                return self.say(f"breaks_rule{suffix}")
            return self.say(f"breaks{suffix}", n=condition.number)
        if source in self.about:
            kind, what = self.about[source]
            if kind == "person":
                return self.say("nowhere", who=what)
            placed = [s for s in step.trail if s.asserted and not isinstance(s.value, bool)]
            inside = [s.var for s in placed if self._in(kind, what, s.value)]
            if kind == "square":
                where = self.say("on", what=self.places.square(what))
                return self.say("both", who=self.say.join(inside), where=where)
            if len(inside) > 1:
                where = self.say("in", what=self.places.line(kind, what))
                return self.say("both", who=self.say.join(inside), where=where)
            return self.say("nobody", line=self.places.line(kind, what))
        suffix = "_first" if first else ""
        rule = None
        if source is not None:
            rule = self._quantified_condition_for_source(source) or self._role_condition_for_source(
                source
            )
        if rule is not None and rule.number is not None and self.say.numbered:
            return self.say(f"breaks{suffix}", n=rule.number)
        said: str | None = None
        if isinstance(rule, QuantifiedCondition):
            said = self._quantified_text(rule)
        elif rule is not None:
            said = self._role_condition_text(rule)
        elif source is not None:
            said = self._role_apart(source)
        if said:
            return self.say(f"breaks_said{suffix}", clue=_cap(said))
        if rule is not None and rule.number is None:
            return self.say(f"breaks_rule{suffix}")
        return self.say("breaks_first_plain" if first else "breaks_plain")

    @staticmethod
    def _in(kind: str, what: Any, sq: Square) -> bool:
        return bool({"row": sq.row, "col": sq.col, "square": sq}[kind] == what)

    # --- clues ---------------------------------------------------------------

    def clue_texts(self) -> list[str]:
        """Every numbered clue as one human-readable sentence, in clue order."""
        said: dict[int, str] = {}
        for condition in conditions(self.board, self.clues):
            if condition.number is not None:
                said.setdefault(condition.number, self._clue(condition))
        for quantified in self.quantified_conditions.values():
            if quantified.number is not None:
                said.setdefault(quantified.number, self._quantified_text(quantified))
        for rule in self.role_conditions.values():
            if rule.number is not None:
                said.setdefault(rule.number, self._role_condition_text(rule))
        for count in self.global_counts.values():
            if count.number is not None:
                said.setdefault(count.number, self._global_count_text(count))
        out = []
        for number, (kind, args) in enumerate(self.clues, 1):
            text = said.get(number) or self._clue_text(kind, args, args[:1])
            out.append(f"{_cap(text)}.")
        return out

    def _clue(self, condition: Condition) -> str:
        return self._clue_text(condition.kind, condition.args, condition.people)

    def _fixed_role(self, step: Step) -> bool:
        """A role fact the booklet figure list gives: ineligible, or all eligible hold it."""
        if self.say.numbered or step.var not in self.role_variables:
            return False
        person, role = self.role_variables[step.var]
        present = step.value if step.asserted else not step.value
        spec = next((r for r in self.board.roles if r.name == role), None)
        if spec is None or spec.eligible_people is None:
            return False
        eligible = person in spec.eligible_people
        if not present:
            return not eligible
        return eligible and spec.allowed_counts == {len(spec.eligible_people)}

    def _literal_text(self, step: Step, asserted: bool | None = None) -> str:
        """A fixed literal in words; role memberships read as "X is (not) the role"."""
        holds = step.asserted if asserted is None else asserted
        if step.var in self.role_variables:
            person, role = self.role_variables[step.var]
            present = step.value if holds else not step.value
            name = self.say.words.get(role) or role.replace("_", " ")
            return self.say("role_has" if present else "role_not", who=person, role=name)
        return self.say("literal_true" if holds else "literal_false", literal=step.literal)

    def _role_step_text(self, step: Step, state: _State) -> str:
        person, role = self.role_variables[step.var]
        present = step.value if step.asserted else not step.value
        key = (person, role)
        if state.role_told.get(key) == present:
            return ""
        state.role_told[key] = present
        if self._fixed_role(step):
            return ""
        name = self.say.words.get(role) or role.replace("_", " ")
        return self.say("role_has" if present else "role_not", who=person, role=name)

    def _role_apart(self, source: str) -> str | None:
        """The text for a different_regions role step, labelled "A and B role in ..."."""
        for role in self.board.roles:
            if role.different_regions and source.endswith(f" {role.name} in different regions"):
                a, _, b = source.removesuffix(f" {role.name} in different regions").partition(
                    " and "
                )
                name = self.say.words.get(role.name) or role.name.replace("_", " ")
                return self.say("clue.role_apart", role=name, a=a, b=b)
        return None

    def _role_condition_for_source(self, source: str) -> RoleCondition | None:
        if source in self.role_conditions:
            return self.role_conditions[source]
        return next(
            (
                rule
                for label, rule in sorted(
                    self.role_conditions.items(), key=lambda pair: len(pair[0]), reverse=True
                )
                if source.startswith(label + " ")
            ),
            None,
        )

    def _pronoun(self, person: str, form: str) -> str:
        pronouns = self.board.pronouns.get(person)
        if pronouns is None:
            return {"subject": "they", "object": "them", "possessive": "their"}[form]
        return {
            "subject": pronouns.subject,
            "object": pronouns.object,
            "possessive": pronouns.possessive,
        }[form]

    def _membership_text(self, token: str) -> str:
        kind, separator, name = token.partition(":")
        if not separator:
            kind, name = "role", token
        if kind == "role":
            return self.say("target.role", name=self.say.words.get(name, name.replace("_", " ")))
        if kind == "attribute":
            return self.say(
                "target.attribute", name=self.say.words.get(name, name.replace("_", " "))
            )
        return name

    def _role_condition_text(self, rule: RoleCondition) -> str:
        kind, args = rule.kind, rule.args

        def role(name: str) -> str:
            return self.say.words.get(name) or name.replace("_", " ")

        if kind in ("has_role", "not_role"):
            return self.say(
                "role_has" if kind == "has_role" else "role_not",
                who=args[0],
                role=role(args[1]),
            )
        if kind in ("some_role", "roleless", "at_most_one_role"):
            key = {
                "some_role": "role_some",
                "roleless": "roleless",
                "at_most_one_role": "role_at_most_one",
            }[kind]
            return self.say(key, who=args[0])
        if kind == "role_subset":
            return self.say(
                "role_subset",
                left=self._membership_text(args[0]),
                right=self._membership_text(args[1]),
            )
        if kind in ("role_in_tagged", "role_not_in_tagged"):
            area = self.places.regions(self.board.tagged_region_ids([args[2]]))
            return self.say(kind, who=args[0], role=role(args[1]), area=area)
        if kind == "min_role_in_tagged":
            area = self.places.regions(self.board.tagged_region_ids([args[1]]))
            return self.say(
                "min_role_in_tagged_one" if args[2] == "1" else "min_role_in_tagged",
                n=self.say.number(int(args[2])),
                role=role(args[0]),
                area=area,
            )
        if kind in ("role_on", "role_not_on", "role_next_to"):
            what = self.say.join([self._role_target_name(name) for name in args[2:]], "or")
            return self.say(
                kind,
                who=args[0],
                role=role(args[1]),
                things=what,
                subject=self._pronoun(args[0], "subject"),
            )
        if kind == "role_below":
            if len(args) == 4:
                key = "role_below_n"
                return self.say(
                    key,
                    who=args[0],
                    role=role(args[1]),
                    n=self.say.number(int(args[3])),
                )
            return self.say("role_below", who=args[0], role=role(args[1]))
        if kind == "sole_role_companion":
            return self.say(
                kind,
                who=args[0],
                role=role(args[1]),
                possessive=self._pronoun(args[0], "possessive"),
            )
        return self.say(f"role_occupant.{args[1]}", role=role(args[0]))

    def _role_target_name(self, name: str) -> str:
        if name in ("blocking", "standable"):
            labels = {
                "en": {"blocking": "blocking objects", "standable": "standable objects"},
                "nl": {"blocking": "blokkerende objecten", "standable": "begaanbare objecten"},
            }
            return labels[self.say.language][name]
        return self.places.thing(name)

    @staticmethod
    def _role_ref(rule: RoleCondition) -> str:
        return "" if rule.number is None else f" ({rule.number})"

    def _clue_text(self, kind: str, args: Sequence[str], people: Sequence[str]) -> str:
        if kind == COUNTING:
            n, parts = counted(args)
            if n == 1 and len(parts) == 2:
                (k1, a1), (k2, a2) = parts
                if k1 == k2 == "same_region" and a1[0] == a2[0]:
                    return self.say("clue.either_same_region", a=a1[0], b=a1[1], c=a2[1])
                first = self._clue_text(k1, a1, a1[: 1 if k1 in FILTERS else 2])
                second = self._clue_text(k2, a2, a2[: 1 if k2 in FILTERS else 2])
                return self.say("clue.either", first=first, second=second)
            listed = "; ".join(
                self._clue_text(k, rest, rest[: 1 if k in FILTERS else 2]) for k, rest in parts
            )
            return self.say("clue.exactly", n=self.say.number(n), list=listed)
        if kind == "furthest":
            return self.say("clue.furthest_all", a=args[0], b=args[1])
        fields: dict[str, Any] = dict(zip("abc", people, strict=False))
        line_clues = ("in_row", "not_in_row", "in_column", "not_in_column")
        has_filter_args = kind in FILTERS or kind == "only_on" or kind in line_clues
        rest = args[1:] if has_filter_args else ()
        if kind in ("in_region", "outside"):
            fields["where"] = self.places.where_regions(rest)
        elif kind in ("in_tagged", "not_in_tagged", "only_in_tagged"):
            fields["where"] = self.places.regions(self.board.tagged_region_ids(rest))
        elif kind in ("in_row", "not_in_row"):
            fields["line"] = self.places.line("row", int(args[1]) - 1)
        elif kind in ("in_column", "not_in_column"):
            fields["line"] = self.places.line("col", int(args[1]) - 1)
        elif kind == "in_area_corner":
            fields["where"] = (
                self.places.regions(self.board.area_ids(rest))
                if rest
                else ("within an area" if self.say.language == "en" else "binnen een gebied")
            )
        elif kind in ("has_attribute", "not_attribute"):
            fields["attribute"] = self.say.words.get(args[1], args[1].replace("_", " "))
        elif kind == "unique_attribute":
            fields["people"] = self.say.join(list(args[1:]))
            fields["attribute"] = self.say.words.get(args[0], args[0].replace("_", " "))
        elif rest:
            fields["things"] = self.say.join([self.places.thing(t) for t in rest], "or")
        if kind == "only_on":
            fields["a"] = args[0]
        if kind == "left_of" and len(args) > 2:
            distance = int(args[2])
            fields["n"] = self.say.number(distance)
            kind = "left_of_one" if distance == 1 else "left_of_n"
        if kind == "above" and len(args) > 2:
            n = int(args[2])
            kind = "above_n"
            fields["rows"] = (
                self.say("one_row") if n == 1 else self.say("n_rows", n=self.say.number(n))
            )
        elif kind in ("within", "at_least"):
            fields["n"] = self.say.number(int(args[2]))
        return self.say(f"clue.{kind}", **fields)

    def _target_text(self, selector: TargetSelector) -> str:
        if selector.kind == "person":
            return selector.name
        if selector.kind == "attribute":
            name = self.say.words.get(selector.name, selector.name.replace("_", " "))
            return self.say("target.attribute", name=name)
        if selector.kind == "role":
            name = self.say.words.get(selector.name, selector.name.replace("_", " "))
            return self.say("target.role", name=name)
        if selector.kind in ("area", "tag"):
            ids = (
                self.board.area_ids([selector.name])
                if selector.kind == "area"
                else self.board.tagged_region_ids([selector.name])
            )
            return self.say("target.area", where=self.places.regions(ids))
        if selector.kind == "object_kind":
            names = {
                "en": {"blocking": "blocking objects", "standable": "standable objects"},
                "nl": {"blocking": "blokkerende objecten", "standable": "begaanbare objecten"},
            }
            return self.say("target.kind", what=names[self.say.language][selector.name])
        what = self.places.thing(selector.name)
        if selector.kind in ("object", "mark"):
            return self.say("target.on", what=what)
        if selector.kind == "edge_item":
            return self.say("target.at", what=what)
        return self.say("target.corner", what=what)

    def _quantified_text(self, condition: QuantifiedCondition) -> str:
        target = (
            "" if condition.selector.kind == "anyone" else self._target_text(condition.selector)
        )
        if condition.kind == "alone_with":
            selector = condition.selector
            others = set(self.board.people) - {condition.subject}
            n = condition.companions
            anyone = selector.kind == "anyone" or (
                selector.kind == "attribute"
                and others <= self.board.attributes.get(selector.name, frozenset())
            )
            if n != 1:
                count = self.say.number(n)
                if anyone:
                    return self.say("clue.alone_with_anyone_n", a=condition.subject, n=count)
                return self.say("clue.alone_with_n", a=condition.subject, n=count, target=target)
            if anyone:
                return self.say("clue.alone_with_anyone", a=condition.subject)
            return self.say("clue.alone_with", a=condition.subject, target=target)
        fields: dict[str, Any] = {"a": condition.subject, "b": target}
        if condition.kind == "above" and condition.rest:
            rows = int(condition.rest[0])
            fields["rows"] = self.say("one_row") if rows == 1 else self.say("n_rows", n=rows)
            return self.say("clue.above_n", **fields)
        if condition.kind == "left_of" and condition.rest:
            distance = int(condition.rest[0])
            fields["n"] = self.say.number(distance)
            return self.say("clue.left_of_one" if distance == 1 else "clue.left_of_n", **fields)
        if condition.kind in ("within", "at_least") and condition.rest:
            fields["n"] = self.say.number(int(condition.rest[0]))
        if condition.kind in ("same_region", "different_region", "apart", "adjacent_regions"):
            return self.say(f"clue.{condition.kind}_target", a=condition.subject, target=target)
        return self.say(f"clue.{condition.kind}", **fields)

    def _quantified_condition_for_source(self, source: str) -> QuantifiedCondition | None:
        return next(
            (
                condition
                for label, condition in sorted(
                    self.quantified_conditions.items(), key=lambda pair: len(pair[0]), reverse=True
                )
                if source == label or source.startswith(label + " ")
            ),
            None,
        )

    @staticmethod
    def _quantified_ref(condition: QuantifiedCondition) -> str:
        return "" if condition.number is None else f" ({condition.number})"

    def _ref(self, condition: Condition) -> str:
        return "" if condition.number is None else f" ({condition.number})"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _pieces(squares: set[Square]) -> list[set[Square]]:
    """`squares` split into side-by-side pieces, such as the separate benches."""
    left, pieces = set(squares), []
    while left:
        piece, todo = set(), [left.pop()]
        while todo:
            sq = todo.pop()
            piece.add(sq)
            near = {s for s in left if abs(s.row - sq.row) + abs(s.col - sq.col) == 1}
            left -= near
            todo += near
        pieces.append(piece)
    return pieces


ARTICLES = frozenset({"the", "a", "an", "de", "het", "een"})
DEFINITE = frozenset({"the", "de", "het"})
NEGATIONS = frozenset({"not", "niet"})
LINE_WORDS = frozenset({"row", "column", "rij", "kolom"})


def _merge_predicates(predicates: Sequence[str], say: Wording) -> str:
    """Join the predicates of one subject, folding those that share their opening words:
    'is not next to the plant', 'is not next to the bench' -> 'is not next to the plant or
    the bench'."""
    groups: dict[tuple[str, ...], list[list[str]]] = {}
    for predicate in predicates:
        words = predicate.split()
        width = 3 if len(words) > 3 and words[1] in NEGATIONS else 2
        groups.setdefault(tuple(words[:width]), []).append(words)
    segments: list[str] = []
    for members in groups.values():
        shared = list(members[0])
        for words in members[1:]:
            keep = 0
            while keep < min(len(shared), len(words)) and shared[keep] == words[keep]:
                keep += 1
            shared = shared[:keep]
        while shared and shared[-1] in ARTICLES:
            shared.pop()
        tails = [" ".join(words[len(shared) :]) for words in members]
        lines_only = all(tail.split(" ", 1)[0] in LINE_WORDS for tail in tails)
        if len(members) == 1 or not all(tails) or len(shared) < (2 if lines_only else 3):
            segments.extend(" ".join(words) for words in members)
            continue
        joiner = "or" if shared[1] in NEGATIONS else "and"
        segments.append(f"{' '.join(shared)} {say.join(tails, joiner)}")
    return say.join(segments, "and")


def clue_paragraphs(text: str, overrides: dict[int, str] | None = None) -> list[str]:
    """The clues grouped per person, one paragraph each, in the order of the people.

    What a clue says about its first person is folded into that person's sentence;
    clues that are not about one person come last, one paragraph each.
    `overrides` replaces the generated wording of clue numbers.
    """
    board, clues = load_board(text)
    story = Story(board, clues, Wording.read(text))
    texts = story.clue_texts()
    shown = {p: _cap(story.say.people.get(p, p)) for p in board.people}
    owners = sorted(board.people, key=lambda p: len(shown[p]), reverse=True)
    predicates: dict[str, list[str]] = {person: [] for person in board.people}
    extra: dict[str, list[str]] = {person: [] for person in board.people}
    loose: list[str] = []
    for number, generated in enumerate(texts, 1):
        sentence = (overrides or {}).get(number, generated)
        owner = next((p for p in owners if sentence.startswith(f"{shown[p]} ")), None)
        if owner is None:
            loose.append(sentence)
            continue
        rest = sentence[len(shown[owner]) + 1 :].rstrip(".")
        if rest.split(" ", 1)[0] in (story.say("and"),):
            extra[owner].append(sentence)
        else:
            predicates[owner].append(rest)
    out = []
    for person in board.people:
        parts = []
        if predicates[person]:
            parts.append(f"{shown[person]} {_merge_predicates(predicates[person], story.say)}.")
        parts.extend(extra[person])
        if parts:
            out.append(" ".join(parts))
    return out + loose


def clue_texts(text: str) -> list[str]:
    """The numbered clues of a Murdoku puzzle file in plain language."""
    board, clues = load_board(text)
    return Story(board, clues, Wording.read(text)).clue_texts()


def board_notes(text: str) -> list[str]:
    """Plain sentences for what the board picture only abbreviates: marks, attributes, roles."""
    board, _ = load_board(text)
    say = Wording.read(text)

    def name(raw: str) -> str:
        return say.words.get(raw, raw.replace("_", " "))

    notes = []
    for tag, members in board.area_tags.items():
        areas = [
            board.region_names[r].replace("_", " ").capitalize()
            for r in sorted(board.region_ids(members))
        ]
        label = re.sub(r"^((in|op|the|a|an|een|de|het) )+", "", name(tag))
        tagged = say.join(areas)
        notes.append(
            say("doc.area_tag", tag=label, Tag=label[:1].upper() + label[1:], areas=tagged)
        )
    for mark in board.marks:
        key = f"doc.mark_{mark.occupant_condition}" if mark.occupant_condition else "doc.mark"
        notes.append(say(key, abbr=mark.name[:2].upper(), name=name(mark.name)))
    return notes


def role_list(text: str) -> list[tuple[str, str]]:
    """(role name, plain description) for each role, for a list beside the board."""
    board, _ = load_board(text)
    say = Wording.read(text)
    if "role_has" in say.phrases:
        return []
    out = []
    for role in board.roles:
        counts = sorted(role.allowed_counts)
        if counts == [1]:
            count = say("doc.count_one")
        elif len(counts) == 1:
            count = say("doc.count_exact", n=say.number(counts[0]))
        elif counts == list(range(counts[0], len(board.people) + 1)):
            count = say("doc.count_any")
        else:
            count = say("doc.count_one_of", list=say.join([say.number(n) for n in counts], "or"))
        extra = say("doc.extra_regions") if role.different_regions and counts != [1] else ""
        if role.eligible_people is not None:
            chosen = [person for person in board.people if person in role.eligible_people]
            extra += say("doc.extra_from", people=say.join(chosen))
        name = say.words.get(role.name, role.name.replace("_", " "))
        out.append((name, say("doc.role", count=count, extra=extra)))
    return out


def attribute_list(text: str) -> list[tuple[str, str]]:
    """(attribute name, the people who have it) for a list beside the board."""
    board, _ = load_board(text)
    say = Wording.read(text)
    if "target.attribute" in say.phrases:
        return []
    out = []
    for attribute, holders in board.attributes.items():
        people = [person for person in board.people if person in holders]
        name = say.words.get(attribute, attribute.replace("_", " "))
        out.append((name, say("doc.attribute", people=say.join(people))))
    return out


def object_list(text: str) -> list[tuple[str, str, bool]]:
    """(object type, name to show, standable) for each kind of object on the board.

    `boom1` and `boom2` are one type, `boom`; the type is what `icons.object_icon` finds.
    """
    board, _ = load_board(text)
    words = Wording.read(text).words
    out: dict[str, tuple[str, str, bool]] = {}
    for obj in board.objects:
        kind = obj.name.lower().rstrip("0123456789").rstrip("_")
        said = words.get(obj.name) or words.get(kind)
        bare = re.sub(r"^(the|a|an|de|het|een) ", "", said) if said else ""
        # Keep the article before an adjective: "het zachte tapijt", not "zachte tapijt".
        label = (bare if " " not in bare else said) if said else kind.replace("_", " ")
        out.setdefault(kind, (kind, label[:1].upper() + label[1:], obj.kind == "standable"))
    return list(out.values())


def phrase(text: str, key: str) -> str:
    """A fixed phrase such as `doc.clues` in the puzzle's language."""
    return Wording.read(text)(key)


def condition_list(text: str) -> list[tuple[str, str]]:
    """(name, plain meaning) of each kind of condition the puzzle's clues and rules use.

    Only the kinds used appear, in the order they are first used; clues inside
    `exactly` count too.
    """
    board, clues = load_board(text)
    say = Wording.read(text)
    keys: list[str] = []

    def visit(kind: str, args: Sequence[str]) -> None:
        key = CONDITION_KEYS.get(kind)
        if key is not None and key not in keys:
            keys.append(key)
        if kind == COUNTING:
            for inner_kind, inner_args in counted(args)[1]:
                visit(inner_kind, inner_args)

    for kind, args in [*board.rules, *clues]:
        visit(kind, args)
    return [(say(f"cond.{key}.name"), say(f"cond.{key}")) for key in keys]


def explain(text: str, numbered: bool = True) -> str:
    """The worked solution of a Murdoku puzzle file, as Markdown bullets.

    Without `numbered` it never points at clue numbers, for clues that are not numbered.
    """
    board, clues = load_board(text)
    say = Wording.read(text)
    story = Story(board, clues, say if numbered else say.unnumbered()).tell()
    story = re.sub(
        r"((?:^- |\. |^- \*\*|\. \*\*))([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        story,
        flags=re.MULTILINE,
    )
    return story if numbered else re.sub(r" \(\d+\)", "", story)
