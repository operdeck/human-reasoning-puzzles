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

from . import battleships, minesweeper, starbattle, sudoku
from .core import Constraint, Kind, Model, Solver, Step
from .murdoku import (
    AREA_POPULATION,
    COUNTING,
    FILTERS,
    POPULATION_FAMILY,
    AreaPopulationCondition,
    Board,
    CellMark,
    Clue,
    Condition,
    GlobalCountCondition,
    QuantifiedCondition,
    RoleCondition,
    Square,
    TargetSelector,
    area_population_conditions,
    board_rules,
    compile_puzzle,
    conditions,
    counted,
    global_count_conditions,
    global_count_unit_prefix,
    line_indices,
    mark_occupant_name,
    next_to_covers_own_squares,
    quantified_conditions,
    role_conditions,
    role_statuses,
    target_name,
)
from .proof import Move, essential, replay, shortest
from .puzzlefile import load_board, load_presentation, read_sections

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "square": "r{row}c{col}",
        "doc.figures": "The figures",
        "doc.figure_clues": "The figures and their clues",
        "doc.other_clues": "Other clues",
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
        "web.cell": "Cell",
        "web.cell_area": "Area: {name}",
        "web.cell_tag": "Area tag: {name}",
        "web.cell_object": "Object: {name} ({condition})",
        "web.cell_touch": "Touches: {name}",
        "web.cell_figure": "Figure",
        "web.extras": "Case details",
        "doc.area_tag": "The {tag} are {areas}.",
        "doc.area_tag_one": "The {tag} is {areas}.",
        "doc.attributes": "The attributes",
        "doc.attribute": "{people}",
        "doc.roles": "The roles",
        "doc.objects": "The objects",
        "doc.key": "Key",
        "doc.key_door": "Door",
        "doc.key_window": "Window",
        "doc.key_point": "Point",
        "doc.clue_next_to_object": (
            "Next to an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count."
        ),
        "doc.clue_next_to_border": (
            "A door or point object is next to every square it touches, even across an area "
            "boundary."
        ),
        "doc.clue_next_to_door": (
            "A door is next to both squares it touches, even across an area boundary."
        ),
        "doc.clue_next_to_point": (
            "A point object is next to every square it touches, even if the square lies in "
            "another area."
        ),
        "doc.clue_next_to_window": "A window is next to its one inside square.",
        "doc.clue_next_to_mark": (
            "A marked square is next to a square that shares a side with it, even across an "
            "area boundary."
        ),
        "doc.clue_at": "At a door or window means standing on a square it touches.",
        "doc.clue_distance": "Distance counts steps across sides, not diagonals.",
        "doc.clue_away_from": (
            "Away from an object means not on it and sharing neither a side nor a corner with "
            "it, in any area."
        ),
        "doc.standable": "you can stand on it",
        "doc.blocking": "nobody can stand here",
        "doc.standable_group": "Standable",
        "doc.blocking_group": "Blocking",
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
        "doc.murdoku_note": (
            "Only the puzzle's stated rules and clues determine what is possible; a kind "
            "or trait matters only when a rule or clue explicitly uses it."
        ),
        "and": "and",
        "or": "or",
        "region": "in the {name}",
        "the": "the {name}",
        "a": "a {name}",
        "an": "an {name}",
        "row": "row {n}",
        "col": "column {n}",
        "rows": "rows {list}",
        "cols": "columns {list}",
        "through": "{a} to {b}",
        "in": "in {what}",
        "on": "on {what}",
        "at": "at {what}",
        "next_to": "next to {what}",
        "on_or_next_to": "on or next to {what}",
        "is": "{who} is {where}",
        "is_not": "{who} is not {where}",
        "count": "{who} has {n} squares left",
        "placed": "**{who} on {square}**",
        "so": "so",
        "cross_out.one": "cross out the other open square in that {line}",
        "cross_out.many": "cross out the other {n} open squares in that {line}",
        "cross_out.row": "row",
        "cross_out.col": "column",
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
        "mark_case.alone": (
            "the square is marked {mark}, so {who} would be alone {where} "
            "and its other squares would be empty"
        ),
        "mark_case.not_alone": "the square is marked {mark}, so {who} would have company {where}",
        "mark_placed.alone": "{who} is on a {mark} square, so **{who} is alone {where}**",
        "mark_placed.not_alone": "{who} is on a {mark} square, so **{who} has company {where}**",
        "mark_blocked.alone": (
            "{who} is {where} but cannot stand on a {mark} square there. "
            "Anyone on a {mark} square would be alone, so **nobody can use those squares {where}**"
        ),
        "mark_breaks.not_alone": (
            "but a {mark} square needs company, and nobody else can be {where}"
        ),
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
        "cannot": "**{who} cannot be on {squares}**: {chain}.",
        "nor": "**Nor on {squares}**: {chain}.",
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
        "clue.away_from": "{a} is not on or beside {things}, not even diagonally",
        "clue.on_or_next_to": "{a} is on or next to {things}",
        "clue.not_on_or_next_to": "{a} is neither on nor next to {things}",
        "clue.beside_but_not_on": "{a} is beside {things}, but not on {things}",
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
        "clue.busiest_area": "the area with the most people is {areas}",
        "clue.quietest_area": "the area with the fewest people is {areas}",
        "clue.busiest_area_tie": "the areas with the most people are {areas}",
        "clue.quietest_area_tie": "the areas with the fewest people are {areas}",
        "count_reason": "the allowed counts for {name} are {counts}",
        "count.population_reason": "the {area} area holding at least {count} people",
        "count.population_reason_one": "the {area} area holding at least one person",
        "count.population_full": "{areas} already hold all {n} people",
        "count.population_person": "{people} is {where}, so **at least one person is there**",
        "count.population_people": (
            "{people} are {where}, so **at least {count} people are there**"
        ),
        "count.population_minimum": "at least {count} people are {where}",
        "count.population_all": "together that accounts for all {n} people",
        "count.population_blocked": "{blockers}: all other free squares {where} are unavailable",
        "count.population_only": "only {who} is {where}",
        "count.population_at_most_zero": "the area counts leave {where} empty",
        "count.population_at_most_one": "the area counts allow at most one person {where}",
        "count.population_at_most": "the area counts allow at most {count} people {where}",
        "global_count.exact": "exactly {n}",
        "global_count.at_most": "at most {n}",
        "global_count.at_least": "at least {n}",
        "global_count.odd": "an odd number of",
        "global_count.even": "an even number of",
        "global_count.range": "between {low} and {high}",
        "global_count.people_on": "{quantity} {noun} {verb} on {target}",
        "global_count.mark": "the squares marked {name}",
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
        "role_on_or_next_to": "if {who} has role {role}, {subject} must be on or next to {things}",
        "role_below": "{who} is below a {role} holder",
        "role_below_n": "{who} is {n} rows below a {role} holder",
        "sole_role_companion": "{possessive} sole region companion has role {role}",
        "role_occupant.alone": "every {role} holder is alone in their area",
        "role_occupant.not_alone": "no {role} holder is alone in their area",
        "min_role_in_tagged_one": "at least one {role} holder is {area}",
        "min_role_in_tagged_one_unique": "the {role} is {area}",
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
        "target.unique_role": "the {name}",
        "target.area": "someone {where}",
        "target.on": "someone on {what}",
        "target.at": "someone at {what}",
        "target.corner": "someone in the cells around {what}",
        "target.kind": "someone on {what}",
    },
    "nl": {
        "square": "r{row}k{col}",
        "doc.figures": "De figuren",
        "doc.figure_clues": "De figuren en hun aanwijzingen",
        "doc.other_clues": "Overige aanwijzingen",
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
        "web.cell": "Vakje",
        "web.cell_area": "Gebied: {name}",
        "web.cell_tag": "Gebiedsgroep: {name}",
        "web.cell_object": "Voorwerp: {name} ({condition})",
        "web.cell_touch": "Raakt: {name}",
        "web.cell_figure": "Figuur",
        "web.extras": "Bijzonderheden",
        "doc.area_tag": "{Tag}: {areas}.",
        "doc.area_tag_one": "{Tag}: {areas}.",
        "doc.attributes": "De kenmerken",
        "doc.attribute": "{people}",
        "doc.roles": "De rollen",
        "doc.objects": "De voorwerpen",
        "doc.key": "Legenda",
        "doc.key_door": "Deur",
        "doc.key_window": "Raam",
        "doc.key_point": "Punt",
        "doc.clue_next_to_object": (
            "Naast een voorwerp in een vakje betekent een zijde delen met een vakje van het "
            "voorwerp in hetzelfde gebied; schuin telt niet."
        ),
        "doc.clue_next_to_border": (
            "Een deur of puntobject is naast elk vakje dat het raakt, ook over een "
            "gebiedsgrens heen."
        ),
        "doc.clue_next_to_door": (
            "Een deur is naast beide vakjes die eraan raken, ook over een gebiedsgrens heen."
        ),
        "doc.clue_next_to_point": (
            "Een puntobject is naast elk vakje dat het raakt, ook als het vakje in een ander "
            "gebied ligt."
        ),
        "doc.clue_next_to_window": "Een raam is naast het ene vakje aan de binnenkant.",
        "doc.clue_next_to_mark": (
            "Een gemarkeerd vakje is naast elk vakje dat er een zijde mee deelt, ook over "
            "een gebiedsgrens heen."
        ),
        "doc.clue_at": "Bij een deur of raam betekent op een vakje staan dat eraan raakt.",
        "doc.clue_distance": "Afstand telt stappen over zijden, niet schuin.",
        "doc.clue_away_from": (
            "Uit de buurt van een voorwerp betekent er niet op staan en er geen zijde of hoek "
            "mee delen, in welk gebied dan ook."
        ),
        "doc.standable": "hier kun je op staan",
        "doc.blocking": "hier kan niemand staan",
        "doc.standable_group": "Begaanbaar",
        "doc.blocking_group": "Blokkerend",
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
        "doc.murdoku_note": (
            "Alleen de expliciete regels en aanwijzingen bepalen "
            "wat mogelijk is; een soort of eigenschap telt alleen mee als een regel of aanwijzing "
            "die uitdrukkelijk gebruikt."
        ),
        "and": "en",
        "or": "of",
        "region": "in de {name}",
        "the": "de {name}",
        "a": "een {name}",
        "an": "een {name}",
        "row": "rij {n}",
        "col": "kolom {n}",
        "rows": "de rijen {list}",
        "cols": "de kolommen {list}",
        "through": "{a} t/m {b}",
        "in": "in {what}",
        "on": "op {what}",
        "at": "bij {what}",
        "next_to": "naast {what}",
        "on_or_next_to": "op of naast {what}",
        "is": "{who} zit {where}",
        "is_not": "{who} zit niet {where}",
        "count": "{who} kan nog op {n} vakjes",
        "placed": "**{who} op {square}**",
        "so": "dus",
        "cross_out.one": "streep het andere nog open vakje in die {line} weg",
        "cross_out.many": "streep de {n} andere nog open vakjes in die {line} weg",
        "cross_out.row": "rij",
        "cross_out.col": "kolom",
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
        "mark_case.alone": (
            "het vakje heeft markering {mark}, dus {who} zou alleen zijn {where} "
            "en de andere vakjes daar zouden leeg zijn"
        ),
        "mark_case.not_alone": (
            "het vakje heeft markering {mark}, dus {who} zou samen met iemand zijn {where}"
        ),
        "mark_placed.alone": (
            "{who} staat op een vakje met markering {mark}, dus **{who} is alleen {where}**"
        ),
        "mark_placed.not_alone": (
            "{who} staat op een vakje met markering {mark}, dus **{who} heeft gezelschap {where}**"
        ),
        "mark_blocked.alone": (
            "{who} is {where} maar kan daar niet op een vakje met markering {mark} staan. "
            "Wie op zo'n vakje staat is alleen, dus **niemand kan die vakjes {where} gebruiken**"
        ),
        "mark_breaks.not_alone": (
            "maar op een vakje met markering {mark} moet iemand gezelschap hebben "
            "en verder kan niemand {where} zijn"
        ),
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
        "cannot": "**{who} kan niet op {squares}**: {chain}.",
        "nor": "**Ook niet op {squares}**: {chain}.",
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
        "clue.away_from": "{a} zit niet op of naast {things}, ook niet schuin",
        "clue.on_or_next_to": "{a} zit op of naast {things}",
        "clue.not_on_or_next_to": "{a} zit niet op of naast {things}",
        "clue.beside_but_not_on": "{a} zit naast {things}, maar niet op {things}",
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
        "clue.busiest_area": "het gebied met de meeste mensen is {areas}",
        "clue.quietest_area": "het gebied met de minste mensen is {areas}",
        "clue.busiest_area_tie": "de gebieden met de meeste mensen zijn {areas}",
        "clue.quietest_area_tie": "de gebieden met de minste mensen zijn {areas}",
        "clue.alone_with_anyone": "{a} deelt een gebied met precies één ander persoon",
        "clue.alone_with_n": (
            "{a} deelt een gebied met precies {n} anderen, en dat zijn allemaal {target}"
        ),
        "clue.alone_with_anyone_n": "{a} deelt een gebied met precies {n} anderen",
        "count_reason": "voor {name} zijn de toegestane aantallen {counts}",
        "count.population_reason": "het gebied {area} met minstens {count} mensen",
        "count.population_reason_one": "het gebied {area} met minstens één mens",
        "count.population_full": "{areas} bevatten samen al alle {n} mensen",
        "count.population_person": "{people} is {where}, dus **daar is minstens één persoon**",
        "count.population_people": (
            "{people} zijn {where}, dus **daar zijn minstens {count} mensen**"
        ),
        "count.population_minimum": "zijn er {where} minstens {count} mensen",
        "count.population_all": "samen zijn dat alle {n} mensen",
        "count.population_blocked": "{blockers}: alle andere vrije vakjes {where} vallen af",
        "count.population_only": "alleen {who} zit {where}",
        "count.population_at_most_zero": "de gebiedstellingen laten {where} niemand toe",
        "count.population_at_most_one": "de gebiedstellingen geven {where} hoogstens één persoon",
        "count.population_at_most": "de gebiedstellingen geven {where} hoogstens {count} mensen",
        "global_count.exact": "precies {n}",
        "global_count.at_most": "hoogstens {n}",
        "global_count.at_least": "minstens {n}",
        "global_count.odd": "een oneven aantal",
        "global_count.even": "een even aantal",
        "global_count.range": "tussen {low} en {high}",
        "global_count.people_on": "{quantity} {noun} {verb} op {target}",
        "global_count.mark": "de vakjes met markering {name}",
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
        "role_on_or_next_to": "als {who} de rol {role} heeft, staat {subject} op of naast {things}",
        "role_below": "{who} staat onder een {role}-drager",
        "role_below_n": "{who} staat {n} rijen onder een {role}-drager",
        "sole_role_companion": "{possessive} enige gebiedsgenoot heeft de rol {role}",
        "role_occupant.alone": "elke {role}-drager is alleen in zijn gebied",
        "role_occupant.not_alone": "geen enkele {role}-drager is alleen in zijn gebied",
        "min_role_in_tagged_one": "minstens één {role}-drager is {area}",
        "min_role_in_tagged_one_unique": "de {role} is {area}",
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
        "target.unique_role": "de {name}",
        "target.area": "iemand {where}",
        "target.on": "iemand op {what}",
        "target.at": "iemand bij {what}",
        "target.corner": "iemand in de vakjes rond {what}",
        "target.kind": "iemand op {what}",
    },
}

SUDOKU_RULES = {
    "en": {
        "base": "Fill the grid so every row, column and box contains each digit once.",
        "jigsaw": (
            "The outlined regions replace the usual square boxes; each contains every digit once."
        ),
        "extra": "Each extra house marked on the grid also contains every digit once.",
        "anti_knight": (
            "Equal digits may not be a knight's move apart "
            "(two cells in one direction and one perpendicular, as in chess)."
        ),
        "anti_king": "Equal digits may not touch, not even diagonally.",
        "white": "Digits joined by a white Kropki dot differ by exactly one.",
        "black": "For a black Kropki dot, one of the joined digits is exactly twice the other.",
        "dots": "Missing dots impose no restriction; not every qualifying pair needs a dot.",
        "consecutive": "Digits joined by a consecutive-pair bar differ by exactly one.",
        "less": "Digits strictly increase along each thermometer, from the bulb towards the tip.",
        "parity": "A digit on a grey circle is odd; a digit on a grey square is even.",
        "arrow": "The digit in each circle equals the sum of the digits along its arrow.",
        "killer": (
            "Each dashed cage holds different digits that add up to the small number in its corner."
        ),
        "sandwich": (
            "A number outside the grid belongs to the row or column beside it. Add the digits "
            "between the 1 and the {top} in that line, in whichever order they appear; do not "
            "count the 1 or the {top}. A clue of 0 means the 1 and the {top} are adjacent."
        ),
        "skyscraper": (
            "A number outside the grid says how many digits are visible from that side of its "
            "row or column. Read digits as tower heights: a taller digit hides every shorter "
            "one behind it (for example, 2 4 1 3 shows two towers from the left: 2 and 4)."
        ),
    },
    "nl": {
        "base": (
            "Vul het rooster zo in dat elke rij, kolom en elk blok "
            "elk cijfer precies één keer bevat."
        ),
        "jigsaw": (
            "De omlijnde gebieden vervangen de gewone vierkante blokken; "
            "elk gebied bevat elk cijfer precies één keer."
        ),
        "extra": (
            "Elk extra gemarkeerd gebied op het rooster bevat ook elk cijfer precies één keer."
        ),
        "anti_knight": (
            "Gelijke cijfers mogen niet op een paardensprong van elkaar staan "
            "(twee vakjes in één richting en één loodrecht daarop, zoals bij schaken)."
        ),
        "anti_king": "Gelijke cijfers mogen elkaar niet raken, ook niet diagonaal.",
        "white": "Cijfers verbonden door een witte Kropki-stip verschillen precies één.",
        "black": (
            "Bij een zwarte Kropki-stip is het ene verbonden cijfer precies tweemaal het andere."
        ),
        "dots": (
            "Ontbrekende stippen leggen geen beperking op; "
            "niet elk passend paar hoeft een stip te hebben."
        ),
        "consecutive": "Cijfers verbonden door een streepje verschillen precies één.",
        "less": "De cijfers lopen op elke thermometer strikt op, van het bolletje naar de punt.",
        "parity": (
            "Een cijfer op een grijze cirkel is oneven; een cijfer op een grijs vierkant is even."
        ),
        "arrow": "Het cijfer in elke cirkel is de som van de cijfers langs de bijbehorende pijl.",
        "killer": (
            "Elke gestippelde kooi bevat verschillende cijfers die samen het kleine getal "
            "in de hoek vormen."
        ),
        "sandwich": (
            "Een getal buiten het rooster hoort bij de rij of kolom waar het naast staat. Tel "
            "de cijfers op die in die lijn tussen de 1 en de {top} staan, in welke volgorde ze "
            "ook voorkomen; de 1 en de {top} zelf tellen niet mee. Bij een getal 0 staan de 1 "
            "en de {top} direct naast elkaar."
        ),
        "skyscraper": (
            "Een getal buiten het rooster geeft aan hoeveel cijfers je vanaf die kant van de "
            "rij of kolom ziet. Lees de cijfers als torenhoogtes: een hoger cijfer verbergt elk "
            "lager cijfer erachter (bijvoorbeeld zie je in 2 4 1 3 van links twee torens: 2 en 4)."
        ),
    },
}

PEER_RULE_LABELS = {
    "en": {
        "no repeated digit on anti-knight peers": "anti-knight rule",
        "no repeated digit on anti-king peers": "anti-king rule",
        "each digit once per row": "row rule",
        "each digit once per column": "column rule",
        "each digit once per box": "box rule",
        "each digit once per extra house": "extra-house rule",
    },
    "nl": {
        "no repeated digit on anti-knight peers": "anti-paardregel",
        "no repeated digit on anti-king peers": "anti-koningregel",
        "each digit once per row": "rijregel",
        "each digit once per column": "kolomregel",
        "each digit once per box": "blokregel",
        "each digit once per extra house": "regel voor extra gebieden",
    },
}


def family_rules(text: str, kind: str) -> list[str]:
    """Player-facing rules from the same parsed variant semantics as the solver."""
    if kind == "starbattle":
        star_battle = starbattle.parse(text)
        if star_battle.stars == 1:
            return [
                "Place one queen in every row, column and region; queens may not touch, "
                "not even diagonally."
            ]
        return [
            "Place stars so each row, column and region holds the same number; "
            "stars may not touch, not even diagonally."
        ]
    if kind == "battleships":
        fleet_puzzle = battleships.parse(text)
        language = Wording.read(text).language
        if not fleet_puzzle.fleet:
            return [
                "Markeer vakjes volgens de rij- en kolomtotalen; deze variant zonder vloot "
                "legt geen scheepsvormen of aanraakregels op."
                if language == "nl"
                else FAMILY_RULES[kind]
            ]
        fleet = ", ".join(map(str, fleet_puzzle.fleet))
        if language == "nl":
            return [
                f"Plaats de volledige vloot: scheepslengten {fleet}.",
                "Elk schip is een rechte horizontale of verticale reeks vakjes.",
                "Verschillende schepen mogen elkaar niet raken, ook niet diagonaal.",
                "De getallen geven het aantal scheepsvakjes in elke rij en kolom.",
                "Golven zijn water; gegeven scheepsdelen horen bij een schip. Een rondje is "
                "een schip van één vakje, een afgeronde kant is een uiteinde, en een vierkant "
                "tussenstuk heeft aan twee tegenoverliggende kanten een scheepsdeel. "
                "Een vraagteken is een scheepsdeel waarvan de vorm niet gegeven is.",
            ]
        return [
            f"Place the complete fleet: ship lengths {fleet}.",
            "Each ship is a straight horizontal or vertical run of cells.",
            "Different ships may not touch, not even diagonally.",
            "The numbers give the occupied ship cells in each row and column.",
            "Waves mark water; given ship segments belong to a ship. A circle is a single-cell "
            "ship, a rounded side is an end, and a square middle segment has ship cells on "
            "two opposite sides. A question mark is a ship segment of unspecified shape.",
        ]
    if kind == "minesweeper":
        total_mines = minesweeper.parse(text).total_mines
        if total_mines is None:
            return [FAMILY_RULES[kind]]
        if Wording.read(text).language == "nl":
            return [
                f"Markeer de mijnen: elk getal geeft aan hoeveel van de acht buurvakjes "
                f"een mijn zijn. Er liggen in totaal {total_mines} mijnen."
            ]
        return [
            f"Mark the mines: each number tells how many of its eight neighbours are mines. "
            f"There are {total_mines} mines in total."
        ]
    if kind != "sudoku":
        display_family = (read_sections(text).get("Family") or [kind])[0].casefold()
        return [FAMILY_RULES.get(display_family, FAMILY_RULES[kind])]
    sudoku_puzzle = sudoku.parse(text)
    words = SUDOKU_RULES[Wording.read(text).language]
    rules = [words["base"]]
    if sudoku_puzzle.jigsaw:
        rules.append(words["jigsaw"])
    if sudoku_puzzle.extra_houses():
        rules.append(words["extra"])
    if sudoku_puzzle.anti_knight:
        rules.append(words["anti_knight"])
    if sudoku_puzzle.anti_king:
        rules.append(words["anti_king"])
    kinds = {link.kind for link in sudoku_puzzle.links}
    for kind in ("white", "black", "consecutive", "less"):
        if kind in kinds:
            rules.append(words[kind])
    if kinds & {"white", "black"}:
        rules.append(words["dots"])
    present = {rule.kind for rule in sudoku_puzzle.rules}
    for kind in sudoku.RULE_KINDS:
        if kind in present:
            rule = words[kind]
            if kind in {"sandwich", "skyscraper"}:
                rule = rule.format(top=sudoku_puzzle.size)
            rules.append(rule)
    return rules


# Base rules for the non-Murdoku families; Sudoku adds its active variants above.
FAMILY_RULES = {
    "sudoku": "Fill the grid so every row, column and box contains each digit once.",
    "calcudoku": "Fill the grid so no digit repeats in a row or column, and each cage's "
    "digits combine to its target with its operation.",
    "futoshiki": "Fill the grid so no digit repeats in a row or column and every "
    "inequality sign between neighbouring cells holds.",
    "suguru": "Fill every region of n cells with 1..n; equal digits may not touch, "
    "not even diagonally.",
    "binairo": "Fill the grid with two symbols: no three equal in a row or column, "
    "each row and column has equally many of each, and no two rows or columns are identical.",
    "tango": "Fill the grid with two symbols: no three equal in a row or column, each row and "
    "column has equally many of each, and no two rows or columns are identical (unlike the "
    "printed game, this engine also forbids identical lines); = signs join equal neighbouring "
    "cells and x signs join different neighbouring cells.",
    "tents": "Put a tent next to each tree (horizontally or vertically), one tent per tree; "
    "tents never touch each other, and the numbers give the tents per row and column.",
    "minesweeper": "Mark the mines: each number tells how many of its eight neighbours are mines.",
    "akari": "Place lights so every white cell is lit and no two lights see each other; "
    "a number tells how many lights touch that black cell.",
    "kakurasu": "Shade cells so each row and column adds up to its target; a shaded cell "
    "contributes its column number to the row sum and its row number to the column sum.",
    "battleships": "Mark cells to match the ship-cell counts for each row and column; "
    "this counts-only puzzle does not model ship shapes or non-touching rules.",
    "towers": "Fill the grid so every row and column holds each height once; an edge clue "
    "says how many towers are visible from there, because a tower hides every shorter one "
    "behind it.",
    "mosaic": "Colour every cell black or white; a number says how many cells in the 3x3 "
    "block around it, itself included, are black.",
    "dominosa": "Cover the whole grid with dominoes so that every pair of numbers from the "
    "full set (0-0, 0-1, ... up to the highest number) is used exactly once. Each cell "
    "shows its number as dots, the way a domino stone does; a cell without dots is a 0.",
    "rectangles": "Divide the grid into rectangles so that each contains exactly one number, "
    "equal to the number of cells in that rectangle.",
    "magnets": "Each domino is either a magnet, with one plus and one minus end, or neutral. "
    "The numbers count the plus (top, left) and minus (bottom, right) ends in each row and "
    "column, and touching cells of different dominoes never carry the same pole.",
    "undead": "Put a ghost, vampire or zombie in every empty cell so the totals are met. The "
    "border numbers count the monsters seen along that line, which bends at every mirror: "
    "zombies are always seen, vampires only directly, ghosts only in a mirror.",
    "pattern": "Fill cells so that each row and column contains the runs of filled cells "
    "listed for it, in order, with at least one empty cell between runs.",
    "thermometers": "Fill each thermometer from its bulb without gaps, so that every row and "
    "column holds the number of filled cells shown.",
    "hidato": "Write 1 up to the number of open cells so that every number touches "
    "the next one, along a side or at a corner; numbers given are fixed.",
    "numbrix": "Write 1 up to the number of open cells so that every number touches "
    "the next one along a side (corners do not count); numbers given are fixed.",
    "kakuro": "Fill the white cells with the digits 1 to 9. The number of a clue cell "
    "is the sum of the run of white cells below it (down) or to its right "
    "(across), and a run never repeats a digit.",
    "map": "Colour every region red, yellow, green or blue so that no two regions that share "
    "a border have the same colour; the dotted regions are coloured to start with.",
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
    "away_from": "away_from",
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
        "area border. On an object of several squares you are also next to it, so such clues "
        "say 'on or next to'.",
        "cond.away_from.name": "away from",
        "cond.away_from": "The figure's square shares neither a side nor a corner with a square "
        "of the object, and is not on it; this also holds across an area border.",
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
        "gebiedsgrens heen. Wie op een object van meerdere vakjes staat, staat er ook naast; "
        "zulke aanwijzingen zeggen daarom 'op of naast'.",
        "cond.away_from.name": "uit de buurt van",
        "cond.away_from": "Het vakje van het figuur deelt geen zijde en geen hoek met een vakje "
        "van het object en ligt er niet op; dat geldt ook over een gebiedsgrens heen.",
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
    rules: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, text: str) -> "Wording":
        """The `Language:` and `Words:` sections of a puzzle file, and `Rules:` wordings.

        A rule line may end in `| wording`, like a clue. That sentence is shown
        to players (booklet and web rules, picture legend) but never used in
        worked solutions, which keep the generated wording.
        """
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
        rules = {
            " ".join(rule.split()): wording.strip().rstrip(".")
            for line in section.get("Rules", [])
            for rule, _, wording in [line.partition("|")]
            if wording.strip()
        }
        return cls(language, words, phrases, rules=rules)

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
        name = target_name(name)
        if name in self.board.edge_item_names:
            many = sum(item.name == name for item in self.board.edge_items) > 1
        elif name in self.board.point_object_names:
            many = sum(point.name == name for point in self.board.point_objects) > 1
        elif name in self.board.mark_names:
            many = False
        else:
            many = len(_pieces(self.board.squares_of([name]))) > 1
        if name in self.say.words:
            said = self.say.words[name]
            article, _, noun = said.partition(" ")
            # "het perronbankje" names one of several benches as "een perronbankje";
            # a phrase with an adjective keeps its wording, as Dutch inflection may change.
            if many and article.lower() in DEFINITE and noun and " " not in noun:
                return self._indefinite(noun)
            return said
        shown = name.replace("_", " ")
        return self._indefinite(shown) if many else self.say("the", name=shown)

    def _indefinite(self, noun: str) -> str:
        """ "a bench", "an apple"; Dutch has only "een"."""
        key = "an" if noun[:1].lower() in "aeiou" else "a"
        return self.say(key, name=noun)

    def where_regions(self, names: Iterable[str]) -> str:
        return self.say.join([self.region(n) for n in names], "or")

    def common_region(self, squares: set[Square]) -> str | None:
        """The region shared by every square, if there is exactly one."""
        regions = {self.board.region_of(sq) for sq in squares}
        if len(regions) != 1:
            return None
        return self.region(self.board.region_names[next(iter(regions))])

    def common_line(self, squares: set[Square]) -> tuple[str, int] | None:
        """A row or column shared by every square, if there is one."""
        for kind, indices in (
            ("row", {sq.row for sq in squares}),
            ("col", {sq.col for sq in squares}),
        ):
            if len(indices) == 1:
                return kind, next(iter(indices))
        return None

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
            phrase = "on_or_next_to" if next_to_covers_own_squares(board, name) else "next_to"
            areas.append((self.say(phrase, what=self.thing(name)), near.__contains__))
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
        # A clue can compile to several predicates; the first names its subject.
        primary_conditions: dict[tuple[str, int | None], Condition] = {}
        for condition in conditions(board, self.clues):
            primary_conditions.setdefault((condition.label, condition.number), condition)
        self.conditions = {label: condition for (label, _), condition in primary_conditions.items()}
        self.role_conditions: dict[str, RoleCondition] = {
            rule.label: rule for rule in role_conditions(board, self.clues)
        }
        self.quantified_conditions: dict[str, QuantifiedCondition] = {
            condition.label: condition for condition in quantified_conditions(board, self.clues)
        }
        self.global_counts: dict[str, GlobalCountCondition] = {
            condition.label: condition for condition in global_count_conditions(board, self.clues)
        }
        self.population_conditions = area_population_conditions(board, self.clues)
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

        solved = self.model.clone()
        Solver(solved).solve(on_step=collect)
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
        opening = self._opening(compiled, state)
        consequences = self._mark_placement_consequences(state.announced, state)
        paragraphs = [" ".join([opening, *consequences])]
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
                previously_announced = len(state.announced)
                said = self._firing(rule, steps, state)
                if said:
                    sentences.append(said)
                    sentences.extend(
                        self._mark_placement_consequences(
                            state.announced[previously_announced:], state
                        )
                    )
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
        paragraphs.extend(self._final_role_reveals(solved, state))
        return "\n\n".join(f"- {p}" for p in paragraphs)

    def _mark_placement_consequences(self, people: Sequence[str], state: _State) -> list[str]:
        consequences = []
        for person in people:
            if len(state.options[person]) != 1:
                continue
            square = next(iter(state.options[person]))
            where = self.places.region(self.board.region_names[self.board.region_of(square)])
            for mark in self.board.marks:
                if square in mark.cells and mark.occupant_condition is not None:
                    consequences.append(
                        self.say(
                            f"mark_placed.{mark.occupant_condition}",
                            who=person,
                            mark=mark.name.replace("_", " "),
                            where=where,
                        )
                        + "."
                    )
        return consequences

    def _final_role_reveals(self, model: Model, state: _State) -> list[str]:
        """Close the explanation with a role identity inferred from solved positions."""
        statuses = role_statuses(self.board, model)
        holders = [
            (person, role.name)
            for role in self.board.roles
            for person in self.board.people
            if statuses[person, role.name] is True
            and state.role_told.get((person, role.name)) is not True
        ]
        reveals: list[str] = []
        for person, role in holders:
            condition = next(
                (
                    candidate
                    for candidate in reversed(tuple(self.quantified_conditions.values()))
                    if candidate.selector.kind == "role" and candidate.selector.name == role
                ),
                None,
            )
            name = self.say.words.get(role) or role.replace("_", " ")
            outcome = _emphasize(self.say("role_has", who=person, role=name))
            if condition is None:
                reveals.append(f"{_cap(outcome)}.")
            else:
                clue = _cap(self._quantified_text(condition)) + self._quantified_ref(condition)
                reveals.append(f"{clue}, {self.say('so')} {outcome}.")
            state.role_told[person, role] = True
        return reveals

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
        visible = {p: set(self.places.free) for p in self.board.people}
        open_squares = set(self.places.free)
        placed: set[str] = set()
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
            visible[person] = {sq for sq in visible[person] if condition.test(sq)}
            squares = left[person]
            region = self.places.common_region(squares) if squares else None
            clue = _cap(self._clue(condition))
            where: str | None
            line: tuple[str, int] | None = None
            if len(squares) == 1:
                square = min(squares)
                location = self.places.placed(person, square)
                where = f"{_emphasize(region)}: {location}" if region else location
                state.announce(person)
                placed.add(person)
                open_squares = {
                    sq for sq in open_squares if sq.row != square.row and sq.col != square.col
                }
            else:
                line = self.places.common_line(squares)
                line_where = self.say("in", what=self.places.line(*line)) if line else None
                where = region or line_where
                if (
                    condition.kind in ("in_row", "in_column")
                    and where is not None
                    and where in clue
                ):
                    where = ""
                if where is None:
                    where = self.places.where(squares, self.places.free)
                    same_edge = (
                        condition.kind == "next_to"
                        and len(condition.args) == 2
                        and target_name(condition.args[1]) in self.board.edge_item_names
                        and where == self.say("at", what=self.places.thing(condition.args[1]))
                    )
                    if where is not None and (where in clue or same_edge):
                        where = ""
                if where:
                    where = _emphasize(where)
                if where is None:
                    where = self.say("squares", n=self.say.number(len(squares)))
            suffix = f": {where}" if where else ""
            if line and person not in placed:
                kind, index = line
                explicit = (kind, condition.kind) in {("row", "in_row"), ("col", "in_column")}
                line_squares = {
                    sq for sq in open_squares if (sq.row if kind == "row" else sq.col) == index
                }
                candidates = visible[person] & open_squares
                if (region is None or explicit) and candidates and candidates <= line_squares:
                    crossed = line_squares - candidates
                    if crossed:
                        open_squares -= crossed
                        key = "cross_out.one" if len(crossed) == 1 else "cross_out.many"
                        instruction = self.say(
                            key, n=self.say.number(len(crossed)), line=self.say(f"cross_out.{kind}")
                        )
                        suffix += f", {self.say('so')} {_emphasize(instruction)}"
            said.append(f"{clue} ({condition.number}){suffix}.")
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
            role_outcome = self.say.join([_emphasize(text) for text in role_sentences])
            global_condition = self._global_count_for_sources(
                source for step in steps for source in step.sources
            )
            if global_condition is not None:
                clue = self._global_count_reason(global_condition) + self._global_count_ref(
                    global_condition
                )
                return f"{_cap(clue)}, {self.say('so')} {role_outcome}."
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
                return f"{clue}, {self.say('so')} {role_outcome}."
            changed = [p for p in self.board.people if state.options[p] != before[p]]
            if not changed and (reason := self._role_step_reason(steps)):
                return f"{_cap(reason)}, {self.say('so')} {role_outcome}."
            if changed:
                return (
                    f"{role_outcome}, {self.say('so')} "
                    + self._outcome(changed, before, state)
                    + "."
                )
            return f"{_cap(role_outcome)}."
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
        if rule == "wing":
            return self._wing(steps[0], changed, before, state)
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
            outcome.append(_emphasize(self.say("is_not", who=p, where=self.say("on", what=gone))))
            state.told[p] -= before[p] - state.options[p]
            if len(state.options[p]) == 1 and p not in state.announced:
                state.announce(p)
                outcome.append(self.places.placed(p, min(state.options[p])))
        so = self.say("chain_so", ends=ends, outcome=self.say.join(outcome))
        if len(step.chain) == 2:
            return _cap(self.say("chain_either", ends=ends, outcome=self.say.join(outcome)))
        return f"{', '.join(parts)}. {so}"

    def _wing(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        """'One of A on a, B on b or C on c; either way D is not on d.'"""
        square = self.places.square
        z = step.chain[0][1]
        parts = [
            self.say("is", who=who, where=self.say("on", what=square(z))) for who, _ in step.chain
        ]
        ends = self.say.join(parts, "or")
        outcome = self._outcome(changed, before, state) if changed else self._literal_text(step)
        return _cap(self.say("chain_so", ends=ends, outcome=outcome))

    def _population_level(self, constraint: Constraint) -> tuple[str, int] | None:
        """The region and minimum represented by a reified population count."""
        if (
            constraint.kind is not Kind.COUNT
            or constraint.family != POPULATION_FAMILY
            or constraint.reified_by is None
            or not constraint.allowed_counts
        ):
            return None
        count = min(constraint.allowed_counts)
        if count < 1 or constraint.allowed_counts != frozenset(
            range(count, len(constraint.literals) + 1)
        ):
            return None
        regions: set[str] = set()
        for literal in constraint.literals:
            square = self.model.value_of(literal)
            if self.model.var_of(literal) not in self.board.people or not isinstance(
                square, Square
            ):
                return None
            regions.add(self.board.region_of(square))
        return (next(iter(regions)), count) if len(regions) == 1 else None

    def _count_name(self, constraint: Constraint) -> str:
        """A count constraint's name as the player reads it, not as the engine spells it."""
        if (level := self._population_level(constraint)) is not None:
            region, count = level
            key = "count.population_reason_one" if count == 1 else "count.population_reason"
            return self.say(key, area=self.board.region_names[region], count=self.say.number(count))
        return constraint.name

    def _population_comparison(
        self, more: Constraint, fewer: Constraint, state: _State
    ) -> AreaPopulationCondition | None:
        """Find the clue behind an observed strict population implication."""
        higher = self._population_level(more)
        lower = self._population_level(fewer)
        if (
            higher is None
            or lower is None
            or higher[1] != lower[1] + 1
            or more.reified_by is None
            or fewer.reified_by is None
        ):
            return None
        more_var = self.model.var_of(more.reified_by)
        more_value = self.model.value_of(more.reified_by)
        fewer_choice = (self.model.var_of(fewer.reified_by), self.model.value_of(fewer.reified_by))
        for step in state.history:
            if (
                step.asserted
                or step.var != more_var
                or step.value == more_value
                or step.placing != fewer_choice
            ):
                continue
            eliminated = self.model.literal(step.var, step.value)
            if any(
                source.name in step.sources
                and source.kind is Kind.AT_MOST_ONE
                and set(source.literals) == {eliminated, fewer.reified_by}
                for source in self.model.constraints
            ):
                break
        else:
            return None
        more_region, fewer_region = higher[0], lower[0]
        return next(
            (
                condition
                for condition in self.population_conditions
                if (
                    condition.kind == "busiest_area"
                    and more_region in condition.regions
                    and fewer_region not in condition.regions
                )
                or (
                    condition.kind == "quietest_area"
                    and fewer_region in condition.regions
                    and more_region not in condition.regions
                )
            ),
            None,
        )

    def _population_evidence(
        self,
        levels: Sequence[tuple[str, int, Constraint]],
        before: dict[str, set[Square]],
        state: _State,
    ) -> list[str] | None:
        """Explain the area floors from known people and recorded comparisons."""
        sentences: list[str] = []
        known: dict[str, tuple[int, Constraint]] = {}
        pending: list[tuple[str, int, Constraint]] = []
        for region, count, constraint in levels:
            people = [
                person
                for person in self.board.people
                if before[person]
                and state.told[person]
                and all(self.board.region_of(square) == region for square in before[person])
                and all(self.board.region_of(square) == region for square in state.told[person])
            ]
            if len(people) < count:
                pending.append((region, count, constraint))
                continue
            key = "count.population_person" if count == 1 else "count.population_people"
            text = self.say(
                key,
                people=self.say.join(people[:count]),
                where=self.places.region(self.board.region_names[region]),
                count=self.say.number(count),
            )
            sentences.append(f"{_cap(text)}.")
            known[region] = (count, constraint)

        while pending:
            progress = False
            for item in pending[:]:
                region, count, constraint = item
                for lower_count, lower_constraint in known.values():
                    if count != lower_count + 1:
                        continue
                    comparison = self._population_comparison(constraint, lower_constraint, state)
                    if comparison is None:
                        continue
                    clue = self._clue_text(comparison.kind, comparison.tokens, ())
                    if comparison.number is not None and self.say.numbered:
                        clue += f" ({comparison.number})"
                    minimum = self.say(
                        "count.population_minimum",
                        count=self.say.number(count),
                        where=self.places.region(self.board.region_names[region]),
                    )
                    sentences.append(f"{_cap(clue)}, {self.say('so')} {_emphasize(minimum)}.")
                    known[region] = (count, constraint)
                    pending.remove(item)
                    progress = True
                    break
            if not progress:
                return None
        return sentences

    def _population_full(
        self,
        step: Step,
        constraint: Constraint,
        known: bool | None,
        before: dict[str, set[Square]],
        state: _State,
    ) -> str | None:
        """'Osaka and Tokyo already hold all five people' when that empties an area.

        The count step refutes "an area holds at least one person". If the
        constraints that bounded it account for everybody, say so, which is
        the argument a person makes instead of quoting allowed totals.
        """
        target = self._population_level(constraint)
        if known is not False or target is None or target[1] != 1:
            return None
        levels: list[tuple[str, int, Constraint]] = []
        for name in step.sources[1:]:
            found = [
                (other, level)
                for other in self.model.constraints
                if other.name == name and (level := self._population_level(other)) is not None
            ]
            if len(found) == 1:
                other, (region, count) = found[0]
                levels.append((region, count, other))
        regions = [region for region, _, _ in levels]
        total = sum(count for _, count, _ in levels)
        if (
            len(levels) < 2
            or len(set(regions)) != len(regions)
            or target[0] in regions
            or total != len(self.board.people)
        ):
            return None
        empty = _emphasize(
            self.say(
                "global_count.area_empty",
                where=self.places.region(self.board.region_names[target[0]]),
            )
        )
        if (evidence := self._population_evidence(levels, before, state)) is not None:
            together = self.say("count.population_all", n=self.say.number(total))
            return " ".join([*evidence, f"{_cap(together)}, {self.say('so')} {empty}."])
        parts = [
            self.say(
                "count.population_reason_one" if count == 1 else "count.population_reason",
                area=self.board.region_names[region],
                count=self.say.number(count),
            )
            for region, count, _ in levels
        ]
        reason = self.say(
            "count.population_full", areas=self.say.join(parts), n=self.say.number(total)
        )
        return f"{_cap(reason)}, {self.say('so')} {empty}."

    def _population_tied_single(
        self,
        constraint: Constraint,
        known: bool | None,
        changed: list[str],
        before: dict[str, set[Square]],
        state: _State,
    ) -> str | None:
        """Explain a tied area's sole occupant from already announced placements."""
        target = self._population_level(constraint)
        if known is not False or target is None or target[1] != 2 or not changed:
            return None
        target_region = target[0]
        target_cells = {sq for sq in self.board.free if self.board.region_of(sq) == target_region}
        if any(
            len(state.options[p]) <= 1 or not (before[p] - state.options[p]) <= target_cells
            for p in changed
        ):
            return None
        announced = {p: state.placed[p] for p in state.announced if p in state.placed}
        occupants = [p for p, sq in announced.items() if self.board.region_of(sq) == target_region]
        if len(occupants) != 1:
            return None
        (target_person,) = occupants
        for comparison in self.population_conditions:
            if target_region not in comparison.regions:
                continue
            for source_region in comparison.regions:
                if source_region == target_region:
                    continue
                people = [
                    p for p, sq in announced.items() if self.board.region_of(sq) == source_region
                ]
                if len(people) != 1:
                    continue
                (source_person,) = people
                source_cells = {
                    sq for sq in self.board.free if self.board.region_of(sq) == source_region
                }
                others = source_cells - {announced[source_person]}
                blockers = self._blockers(None, others, state, max_people=3, announced_only=True)
                if not blockers:
                    continue
                source_where = self.places.region(self.board.region_names[source_region])
                target_where = self.places.region(self.board.region_names[target_region])
                reason = self.say(
                    "count.population_blocked", blockers=self.say.join(blockers), where=source_where
                )
                source_only = self.say(
                    "count.population_only", who=source_person, where=source_where
                )
                target_only = self.say(
                    "count.population_only", who=target_person, where=target_where
                )
                clue = _cap(self._clue_text(comparison.kind, comparison.tokens, ()))
                if comparison.number is not None and self.say.numbered:
                    clue += f" ({comparison.number})"
                for person in self.board.people:
                    if person != source_person:
                        state.told[person] -= source_cells
                    if person != target_person:
                        state.told[person] -= target_cells
                return (
                    f"{_cap(reason)}, {self.say('so')} {_emphasize(source_only)}. "
                    f"{clue}, {self.say('so')} {_emphasize(target_only)}."
                )
        return None

    def _count(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str:
        if (global_condition := self._global_count_for_sources(step.sources)) is not None:
            return self._global_count_deduction(global_condition, step, changed, before, state)
        if step.var in self.global_empty_units:
            return self._global_empty_unit_text(step)
        if step.var in self.auxiliary_variables:
            return ""
        if (reason := self._mark_blocked_by_occupant(step, changed, before, state)) is not None:
            return f"{_cap(reason)}."
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
        known: bool | None = None
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
        population_full = self._population_full(step, constraint, known, before, state)
        if population_full is not None:
            return population_full
        tied_single = self._population_tied_single(constraint, known, changed, before, state)
        if tied_single is not None:
            return tied_single
        level = self._population_level(constraint)
        if level is not None and known is False:
            region, minimum = level
            maximum = minimum - 1
            key = (
                "count.population_at_most_zero"
                if maximum == 0
                else "count.population_at_most_one"
                if maximum == 1
                else "count.population_at_most"
            )
            reason = self.say(
                key,
                where=self.places.region(self.board.region_names[region]),
                count=self.say.number(maximum),
            )
        else:
            reason = self._role_area_reason(constraint, allowed) or self.say(
                "count_reason", name=self._count_name(constraint), counts=counts
            )
        outcome = self._outcome(changed, before, state) if changed else self._literal_text(step)
        return f"{_cap(reason)}, {self.say('so')} {outcome}."

    def _mark_blocked_by_occupant(
        self, step: Step, changed: list[str], before: dict[str, set[Square]], state: _State
    ) -> str | None:
        """A known occupant who cannot use an alone-mark excludes the mark in their area."""
        for mark in self.board.marks:
            if mark.occupant_condition != "alone":
                continue
            for region in {self.board.region_of(square) for square in mark.cells}:
                region_name = self.board.region_names[region]
                source = mark_occupant_name(mark, region_name) + " trigger count"
                if source not in step.sources:
                    continue
                marked = {sq for sq in mark.cells if self.board.region_of(sq) == region}
                if not changed or any(before[p] - state.options[p] - marked for p in changed):
                    continue
                occupant = next(
                    (
                        p
                        for p in self.board.people
                        if state.told[p]
                        and all(self.board.region_of(sq) == region for sq in state.told[p])
                        and not state.told[p] & marked
                    ),
                    None,
                )
                if occupant is None:
                    continue
                for person in changed:
                    state.told[person] -= before[person] - state.options[person]
                return self.say(
                    "mark_blocked.alone",
                    who=occupant,
                    where=self.places.region(region_name),
                    mark=mark.name.replace("_", " "),
                )
        return None

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
        return self.say("on", what=self._global_count_target(selector))

    def _global_count_target(self, selector: TargetSelector) -> str:
        if selector.kind == "mark" and selector.name not in self.say.words:
            return self.say("global_count.mark", name=selector.name.replace("_", " "))
        return self.places.thing(selector.name)

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
                target = self._global_count_target(condition.selector)
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
            return _emphasize(
                self.say(
                    "global_count.area_empty" if is_empty else "global_count.area_occupied",
                    where=where,
                )
            )
        assert isinstance(unit, Square)
        return _emphasize(
            self.say(
                "global_count.cell_empty" if is_empty else "global_count.cell_occupied",
                square=self.places.square(unit),
            )
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
        return self.say.join(
            [_emphasize(self.places.describe(p, state.options[p], before[p])) for p in people]
        )

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
        quantified = next(
            (
                found
                for source in step.sources
                if (found := self._quantified_condition_for_source(source)) is not None
            ),
            None,
        )
        if quantified is not None and changed:
            clue = _cap(self._quantified_text(quantified)) + self._quantified_ref(quantified)
            return f"{clue}, {self.say('so')} {self._outcome(changed, before, state)}."
        inner = [self.about.get(name, ("constraint", name)) for name in step.sources]
        outer = [self.about.get(name, ("constraint", name)) for name in step.scope]
        kinds_in = {k for k, _ in inner}
        kinds_out = {k for k, _ in outer}
        if (
            len(kinds_in) == 1
            and kinds_in <= {"person", "row", "col"}
            and len(kinds_out) == 1
            and kinds_out <= {"row", "col"}
        ):
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
            text = f"{_cap(text)}, {_emphasize(self.say('nobody_else'))}"
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

    def _blockers(
        self,
        who: str | None,
        gone: set[Square],
        state: _State,
        *,
        max_people: int = 2,
        announced_only: bool = False,
    ) -> list[str] | None:
        """Who took the squares the reader still had for `who`, fewest people
        first; None if that takes more than `max_people`."""
        takers: dict[str, set[Square]] = {}
        for sq in gone:
            for other, there in state.placed.items():
                if (
                    other != who
                    and (not announced_only or other in state.announced)
                    and (there.row == sq.row or there.col == sq.col)
                ):
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
        if len(chosen) > max_people:
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
        trial = _State({p: set(options) for p, options in state.options.items()}, {})
        trial.apply(step.trail)
        state.apply([step])
        state.told[who].discard(square)
        parts: list[str] = []
        refs: list[int] = []
        region = self.board.region_of(square)
        region_name = self.board.region_names[region]
        for mark in self.board.marks:
            if square not in mark.cells or mark.occupant_condition is None:
                continue
            mark_source = mark_occupant_name(mark, region_name) + " occupant count"
            if any(mark_source in step.trail[j].sources for j in needed):
                parts.append(
                    self.say(
                        f"mark_case.{mark.occupant_condition}",
                        mark=mark.name.replace("_", " "),
                        who=who,
                        where=self.places.region(region_name),
                    )
                )
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
        parts.append(self._broken(step, first=not parts, trial=trial))
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

    def _broken(self, step: Step, first: bool, trial: _State) -> str:
        """The contradiction a what_if ran into."""
        source = step.sources[0] if step.sources else None
        for mark in self.board.marks:
            if mark.occupant_condition != "not_alone":
                continue
            for region in {self.board.region_of(square) for square in mark.cells}:
                region_name = self.board.region_names[region]
                if source != mark_occupant_name(mark, region_name) + " occupant count":
                    continue
                occupants = [
                    item.var
                    for item in step.trail
                    if item.asserted
                    and item.var in self.board.people
                    and item.value in mark.cells
                    and self.board.region_of(item.value) == region
                ]
                if (
                    occupants
                    and all(trial.options.values())
                    and all(
                        self.board.region_of(square) != region
                        for person in self.board.people
                        if person != occupants[0]
                        for square in trial.options[person]
                    )
                ):
                    return self.say(
                        "mark_breaks.not_alone",
                        mark=mark.name.replace("_", " "),
                        where=self.places.region(region_name),
                    )
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
            return _emphasize(
                self.say("role_has" if present else "role_not", who=person, role=name)
            )
        return _emphasize(
            self.say("literal_true" if holds else "literal_false", literal=step.literal)
        )

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
            role_def = next((r for r in self.board.roles if r.name == args[0]), None)
            if args[2] == "1" and role_def is not None and role_def.allowed_counts == {1}:
                key = "min_role_in_tagged_one_unique"
            else:
                key = "min_role_in_tagged_one" if args[2] == "1" else "min_role_in_tagged"
            return self.say(
                key,
                n=self.say.number(int(args[2])),
                role=role(args[0]),
                area=area,
            )
        if kind in ("role_on", "role_not_on", "role_next_to"):
            what = self.say.join([self._role_target_name(name) for name in args[2:]], "or")
            if kind == "role_next_to" and next_to_covers_own_squares(self.board, *args[2:]):
                kind = "role_on_or_next_to"
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
        if kind in AREA_POPULATION:
            names = [token.partition(":")[2] or token for token in args]
            regions = sorted(self.board.area_ids(names))
            listed = self.say.join([self.board.region_names[region] for region in regions])
            # One named area reads as "the area with the fewest people is X"; a tie
            # names several, so the sentence has to be plural.
            key = f"clue.{kind}" if len(regions) == 1 else f"clue.{kind}_tie"
            return self.say(key, areas=listed)
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
        if kind in ("next_to", "not_next_to") and next_to_covers_own_squares(self.board, *rest):
            kind = kind.replace("next_to", "on_or_next_to")
        return self.say(f"clue.{kind}", **fields)

    def _target_text(self, selector: TargetSelector) -> str:
        if selector.kind == "person":
            return selector.name
        if selector.kind == "attribute":
            name = self.say.words.get(selector.name, selector.name.replace("_", " "))
            return self.say("target.attribute", name=name)
        if selector.kind == "role":
            name = self.say.words.get(selector.name, selector.name.replace("_", " "))
            role = next((r for r in self.board.roles if r.name == selector.name), None)
            if role is not None and role.allowed_counts == {1}:
                return self.say("target.unique_role", name=name)
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
        subject = (
            condition.subject
            if condition.subject_selector is None
            else self._target_text(condition.subject_selector)
        )
        fields: dict[str, Any] = {"a": subject, "b": target}
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
            return self.say(f"clue.{condition.kind}_target", a=subject, target=target)
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


def _emphasize(text: str) -> str:
    return f"**{text.replace('**', '')}**" if text else ""


def _cap(text: str) -> str:
    if text.startswith("**"):
        return "**" + _cap(text[2:])
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
NEGATIONS = frozenset({"not", "niet", "neither"})
CONNECTORS = frozenset({"or", "of", "nor"})
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
        split_phrase = any(tail.split(" ", 1)[0] in CONNECTORS for tail in tails)
        too_short = len(shared) < (2 if lines_only else 3)
        if len(members) == 1 or not all(tails) or split_phrase or too_short:
            segments.extend(" ".join(words) for words in members)
            continue
        joiner = "or" if shared[1] in NEGATIONS else "and"
        segments.append(f"{' '.join(shared)} {say.join(tails, joiner)}")
    return say.join(segments, "and")


@dataclass(frozen=True)
class ClueParagraph:
    """A canonical paragraph with its source clue numbers and semantic owner."""

    text: str
    sources: tuple[int, ...]
    person: str | None

    @property
    def id(self) -> str:
        return "clue:" + ",".join(map(str, self.sources))


@dataclass(frozen=True)
class FigureClues:
    """One cast member, including people who have no numbered clues."""

    person: str
    name: str
    description: str
    clues: tuple[ClueParagraph, ...]


@dataclass(frozen=True)
class CluePresentation:
    figures: tuple[FigureClues, ...]
    other: tuple[ClueParagraph, ...]


def figure_clues(text: str) -> CluePresentation:
    """Shared booklet/player entries; ownership comes from syntax, never wording."""
    board, _ = load_board(text)
    presentation = load_presentation(text)
    say = Wording.read(text).for_people(board.people)
    paragraphs = _clue_paragraphs(text, presentation.clue_text, semantic=True)
    figures = tuple(
        FigureClues(
            person,
            _cap(say.people.get(person, person)),
            presentation.figures[person].description if person in presentation.figures else "",
            tuple(clue for clue in paragraphs if clue.person == person),
        )
        for person in board.people
    )
    return CluePresentation(figures, tuple(clue for clue in paragraphs if clue.person is None))


def clue_paragraphs(text: str, overrides: dict[int, str] | None = None) -> list[str]:
    """The clues grouped per person, one paragraph each, in the order of the people.

    What a clue says about its first person is folded into that person's sentence;
    clues that are not about one person come last, one paragraph each.
    `overrides` replaces the generated wording of clue numbers.
    """
    return [paragraph.text for paragraph in _clue_paragraphs(text, overrides)]


def _clue_paragraphs(
    text: str, overrides: dict[int, str] | None = None, *, semantic: bool = False
) -> list[ClueParagraph]:
    board, clues = load_board(text)
    story = Story(board, clues, Wording.read(text))
    texts = story.clue_texts()
    combined: dict[int, str] = {}
    combined_sources: dict[int, tuple[int, ...]] = {}
    skipped: set[int] = set()
    for number, (kind, args) in enumerate(clues, 1):
        if number in skipped or number in (overrides or {}) or kind != "next_to" or len(args) != 2:
            continue
        person, thing = args
        if not next_to_covers_own_squares(board, thing):
            continue
        for other_number, (other_kind, other_args) in enumerate(clues, 1):
            if (
                other_number == number
                or other_number in skipped
                or other_number in (overrides or {})
                or other_kind != "not_on"
                or other_args != [person, thing]
            ):
                continue
            first = min(number, other_number)
            text = story.say(
                "clue.beside_but_not_on",
                a=person,
                things=story.places.thing(thing),
            )
            combined[first] = f"{_cap(text)}."
            combined_sources[first] = tuple(sorted((number, other_number)))
            skipped.update((number, other_number))
            break
    shown = {p: _cap(story.say.people.get(p, p)) for p in board.people}
    owners = sorted(board.people, key=lambda p: len(shown[p]), reverse=True)
    predicates: dict[str, list[str]] = {person: [] for person in board.people}
    extra: dict[str, list[str]] = {person: [] for person in board.people}
    sources: dict[str, list[int]] = {person: [] for person in board.people}
    loose: list[ClueParagraph] = []
    for number, generated in enumerate(texts, 1):
        if number in skipped and number not in combined:
            continue
        sentence = (overrides or {}).get(number, combined.get(number, generated))
        numbers = combined_sources.get(number, (number,))
        kind, args = clues[number - 1]
        if semantic:
            owner = args[0] if args and args[0] in board.people else None
            if kind in (
                "count",
                "busiest_area",
                "quietest_area",
                "unique_attribute",
                "role_subset",
                "role_occupant",
                "min_role_in_tagged",
            ):
                owner = None
            if kind == COUNTING:
                subjects = {a[0] for _, a in counted(args)[1] if a}
                owner = next(iter(subjects)) if len(subjects) == 1 else None
                if owner not in board.people:
                    owner = None
        else:
            owner = next((p for p in owners if sentence.startswith(f"{shown[p]} ")), None)
        if owner is None:
            loose.append(ClueParagraph(sentence, numbers, None))
            continue
        sources[owner].extend(numbers)
        if not sentence.startswith(f"{shown[owner]} "):
            extra[owner].append(sentence)
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
            out.append(ClueParagraph(" ".join(parts), tuple(sorted(sources[person])), person))
    return out + loose


def clue_texts(text: str) -> list[str]:
    """The numbered clues of a Murdoku puzzle file in plain language."""
    board, clues = load_board(text)
    return Story(board, clues, Wording.read(text)).clue_texts()


def global_count_texts(text: str) -> list[str]:
    """Each global count of a Murdoku puzzle file as one plain sentence, in file order."""
    board, clues = load_board(text)
    told = Story(board, clues, Wording.read(text))
    return [
        told.say.rules.get(condition.description) or _cap(told._global_count_text(condition))
        for condition in global_count_conditions(board, clues)
    ]


def _tagged_area(say: Wording, rid: str, name: str) -> str:
    """An area named in an area-tag note: "the Egyptian hall" from an English
    `Words:` phrase, otherwise the region name with only its first letter raised."""
    phrase = say.words.get(rid)
    if phrase and say.language == "en":
        kept = re.sub(r"^((in|at|on) )+", "", phrase)
        if re.match(r"(the|a|an) ", kept):
            return kept
    text = re.sub(r"^((in|op|the|a|an|een|de|het) )+", "", phrase or name.replace("_", " "))
    return text[:1].upper() + text[1:]


def mark_note(mark: CellMark, say: Wording) -> str:
    """The player-facing meaning of one marked set of cells."""
    key = f"doc.mark_{mark.occupant_condition}" if mark.occupant_condition else "doc.mark"
    name = say.words.get(mark.name, mark.name.replace("_", " "))
    return say(key, abbr=mark.name[:2].upper(), name=name)


def board_notes(text: str) -> list[str]:
    """Plain sentences for what the board picture only abbreviates: area tags, marks, and
    the author's `| wording` of board rules."""
    board, _ = load_board(text)
    say = Wording.read(text)

    def name(raw: str) -> str:
        return say.words.get(raw, raw.replace("_", " "))

    notes = []
    for tag, members in board.area_tags.items():
        region_ids = board.region_ids(members)
        areas = [_tagged_area(say, r, board.region_names[r]) for r in sorted(region_ids)]
        label = re.sub(r"^((in|op|the|a|an|een|de|het) )+", "", name(tag))
        tagged = say.join(areas)
        notes.append(
            say(
                "doc.area_tag_one" if len(region_ids) == 1 else "doc.area_tag",
                tag=label,
                Tag=label[:1].upper() + label[1:],
                areas=tagged,
            )
        )
    notes.extend(mark_note(mark, say) for mark in board.marks)
    notes.extend(f"{wording}." for wording in say.rules.values())
    return notes


def murdoku_key_items(text: str) -> list[tuple[str, str, str]]:
    """(target, label, name) for each symbol the rules do not otherwise name.

    Doors, windows and point objects are symbols whose meaning is not in the
    text; regions are labelled on the board, and marks, roles and attributes are
    stated in the rules or listed beside it.
    """
    board, _ = load_board(text)
    say = Wording.read(text)
    out: list[tuple[str, str, str]] = []
    for name in sorted(board.edge_item_names | board.point_object_names):
        if name in board.edge_item_names:
            kind = "door" if board.edge_item_kind(name) == "door" else "window"
        else:
            kind = "point"
        label = say(f"doc.key_{kind}")
        pretty = say.words.get(name, name.replace("_", " "))
        bare = re.sub(r"^(the|a|an|de|het|een)\s+", "", pretty, flags=re.IGNORECASE)
        out.append((name, label, "" if bare.casefold() == label.casefold() else pretty))
    return out


def murdoku_key(text: str) -> list[tuple[str, str]]:
    """(label, name) for each board symbol."""
    return [(label, name) for _, label, name in murdoku_key_items(text)]


def murdoku_rules(text: str) -> list[str]:
    """The rules a Murdoku player reads before starting, in the author's order.

    The `Intro:` paragraphs (or the standard rules when a file has none), what
    the board picture only abbreviates, the clue semantics the short clue text
    leaves implicit, and the note that a figure's story detail is not a clue.

    One constraint can be said twice: an author may write a rule's sentence in
    the intro *and* as that rule's `| wording`, and both land here. Say such a
    sentence once, where it appears first, so the rules list reads as one rule
    rather than two conditions.
    """
    board, clues = load_board(text)
    presentation = load_presentation(text)
    entries = [*board.rules, *clues]
    entries += [part for kind, args in entries if kind == COUNTING for part in counted(args)[1]]
    kinds = {kind for kind, _ in entries}
    targets: set[str] = set()
    for kind, args in entries:
        if kind in ("next_to", "not_next_to"):
            targets.update(target_name(token) for token in args[1:])
        elif kind == "role_next_to":
            targets.update(target_name(token) for token in args[2:])
    marks = targets & board.mark_names
    edges = (targets - marks) & board.edge_item_names
    points = (targets - marks - edges) & board.point_object_names
    objects = targets - marks - edges - points
    clue_notes = []
    say = Wording.read(text)
    # Intro keywords may describe a different target or omit a necessary detail.
    if objects & (board.object_names | {"blocking", "standable"}):
        clue_notes.append(phrase(text, "doc.clue_next_to_object"))
    for kind, used in (
        ("door", any(board.edge_item_kind(name) == "door" for name in edges)),
        ("point", bool(points)),
    ):
        if used:
            key = f"doc.clue_next_to_{kind}"
            if key not in say.phrases and "doc.clue_next_to_border" in say.phrases:
                key = "doc.clue_next_to_border"
            clue_notes.append(say(key))
    if any(board.edge_item_kind(name) == "window" for name in edges):
        clue_notes.append(phrase(text, "doc.clue_next_to_window"))
    if marks:
        clue_notes.append(phrase(text, "doc.clue_next_to_mark"))
    if "at" in kinds:
        clue_notes.append(phrase(text, "doc.clue_at"))
    if kinds & {"within", "at_least", "furthest"}:
        clue_notes.append(phrase(text, "doc.clue_distance"))
    if "away_from" in kinds:
        clue_notes.append(phrase(text, "doc.clue_away_from"))
    said = [
        *(presentation.intro or [phrase(text, "doc.rules")]),
        *board_notes(text),
        *clue_notes,
        phrase(text, "doc.murdoku_note"),
    ]
    intro_count = len(presentation.intro) if presentation.intro else 1
    intro_items = said[:intro_count]
    # An intro paragraph may already contain a board rule or mark note; do not
    # print that same sentence again as a separate bullet.
    kept = intro_items + [
        item
        for item in said[intro_count:]
        if not any(item in paragraph for paragraph in intro_items)
    ]
    return list(dict.fromkeys(kept))


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
