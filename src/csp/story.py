"""Shared Murdoku wording, clue presentation and worked-solution entry point.

`murdoku_story` narrates the expression compiler's structured proof origins.
This module provides its phrasebook and spatial wording, and presents the
same typed clues to booklet and player consumers.

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
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from . import battleships, minesweeper, murdoku_lang, starbattle, sudoku
from .murdoku import (
    Board,
    CellMark,
    Square,
    next_to_covers_own_squares,
    target_name,
)
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import NUMBERS, ExpressionWords, alone_person, feature_name, only_on
from .puzzlefile import load_board_layout, load_presentation, read_sections

LEGACY_WORD_KEYS = {
    "doc.clue_next_to_object": "doc.clue_beside_object",
    "doc.clue_next_to_border": "doc.clue_on_door or doc.clue_on_point, depending on the target",
    "doc.clue_next_to_door": "doc.clue_on_door",
    "doc.clue_next_to_point": "doc.clue_on_point",
    "doc.clue_next_to_window": "doc.clue_on_window",
    "doc.clue_next_to_mark": "doc.clue_touches_mark",
    "doc.clue_at": "doc.clue_on_door or doc.clue_on_window, depending on the target",
    "clue.alone_with": "clue.with_same_area",
    "clue.alone_with_anyone": "clue.with_same_area_anyone",
    "clue.alone_with_n": "clue.with_same_area_n",
    "clue.alone_with_anyone_n": "clue.with_same_area_anyone_n",
    "role_occupant.alone": "rule.role_occupancy.alone",
    "role_occupant.not_alone": "rule.role_occupancy.not_alone",
}

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
        "web.cell_door": "{name}",
        "web.cell_window": "{name}",
        "web.cell_figure": "Figure",
        "web.extras": "Case details",
        "web.solution_steps": "Solution steps",
        "web.spoiler": "Spoiler: the steps below reveal the solution.",
        "web.steps_incomplete": (
            "These steps do not reach the whole solution; the rest is not explained here."
        ),
        "web.steps_unavailable": "No solution steps are available for this puzzle.",
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
        "doc.clue_beside_object": (
            "Beside an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count."
        ),
        "doc.clue_on_door": (
            "On a door means standing on either square it touches, even across an area boundary."
        ),
        "doc.clue_on_point": (
            "On a point object means standing on any square it touches, even in another area."
        ),
        "doc.clue_on_window": "On a window means standing on its one inside square.",
        "doc.clue_touches_mark": (
            "A square touches a marked square when they share a side, even across an area "
            "boundary; diagonals do not count."
        ),
        "doc.clue_distance": "Distance counts steps across sides, not diagonals.",
        "doc.clue_euclidean_distance": (
            "As-the-crow-flies distance is measured in a straight line between square centers."
        ),
        "doc.clue_neighboring_areas": (
            "Areas are neighbors when they share a side, not just a corner."
        ),
        "doc.clue_away_from": (
            "Away from an object means not on it and sharing neither a side nor a corner with "
            "it, in any area."
        ),
        "doc.standable": "you can stand on it",
        "doc.stand_under": "you can stand under it",
        "doc.sit_on": "you can sit on it",
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
        "count": "{who} has {n} candidate squares left",
        "placed": "**{who} on {square}**",
        "so": "so",
        "cross_out.one": "cross out the other open square in that {line}",
        "cross_out.many": "cross out the other {n} open squares in that {line}: {squares}",
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
        "clue_reference.one": "see clue {refs}",
        "clue_reference.many": "see clues {refs}",
        "chain_if": "If {who} is not on {square}",
        "chain_on": "then {who} is on {square}",
        "chain_off": "then {who} is not on {square}",
        "chain_so": "So {ends}; either way {outcome}.",
        "chain_either": "{ends}; either way {outcome}.",
        "chain_hidden": "The clues together show: {outcome}.",
        "nobody_else": "nobody else can be there",
        "then_on": "then {who} would be on {square}",
        "also_on": "{who} on {square}",
        "then_in": "then {who} would be {where}",
        "mark_case.alone": (
            "the square is marked {mark}, so {who} would be alone {where} "
            "and its other squares would be empty"
        ),
        "mark_case.not_alone": "the square is marked {mark}, so {who} would have company {where}",
        "mark_placed.alone": "{who} is on a {mark} square, so **{who} is alone {where}**",
        "mark_placed.not_alone": "{who} is on a {mark} square, so **{who} has company {where}**",
        "mark_count_filled": (
            "That is the only occupied {mark} square, so **all other {mark} squares are empty**"
        ),
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
        "clue.adjacent_regions": "{a} and {b} are in neighboring areas",
        "clue.with_same_area": (
            "{a} shares an area with exactly one other person, and that is {target}"
        ),
        "clue.with_same_area_anyone": "{a} shares an area with exactly one other person",
        "clue.with_same_area_n": (
            "{a} shares an area with exactly {n} others, and they are all {target}"
        ),
        "clue.with_same_area_anyone_n": "{a} shares an area with exactly {n} others",
        "clue.same_region": "{a} and {b} are in the same area",
        "clue.different_region": "{a} and {b} are in different areas",
        "clue.apart": "{a} and {b} are in areas that do not touch",
        "clue.same_region_target": "{a} is in the same area as {target}",
        "clue.different_region_target": "{a} is in a different area from {target}",
        "clue.adjacent_regions_target": "{a} is in an area that touches the area of {target}",
        "clue.apart_target": "{a} is in an area that does not touch the area of {target}",
        "clue.left_of": "{a} is somewhere left of {b}",
        "clue.left_of_one": "{a} is exactly one column left of {b}",
        "clue.left_of_n": "{a} is exactly {n} columns left of {b}",
        "clue.exactly": "exactly {n} of these is true: {list}",
        "clue.either": "either {first}, or {second}, but not both",
        "clue.either_same_region": "{a} is in the same area as either {b} or {c}",
        "clue.busiest_area": "the area with the most people is {areas}",
        "clue.quietest_area": "the area with the fewest people is {areas}",
        "clue.busiest_area_tie": "the areas with the most people are {areas}",
        "clue.quietest_area_tie": "the areas with the fewest people are {areas}",
        "count_reason": "the allowed counts for {name} are {counts}",
        "count.mark_occupant.alone": ("someone on a square marked {mark} {where} must be alone"),
        "count.mark_occupant.not_alone": (
            "someone on a square marked {mark} {where} must have company"
        ),
        "count.mark_occupant.name": "the number of people in {where} for the {mark} square rule",
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
        "sudoku.row": "row {number}",
        "sudoku.column": "column {number}",
        "sudoku.box": "the box containing {cell}",
        "sudoku.extra": "the extra house {name}",
        "sudoku.singles": "**Singles.**",
        "sudoku.last_digit": "{placements} (the only digit left there)",
        "sudoku.last_digits": "{placements} (in order, each is the only digit left in its cell)",
        "sudoku.only_place": "{placements} (the only place for {digits} in {house})",
        "sudoku.only_places": "{placements} (in order, the only places for {digits} in {house})",
        "sudoku.locked": (
            "**Locked candidate.** Every remaining place for {digit} in {source} is inside "
            "{target}, so **{conclusion}**."
        ),
        "sudoku.cross_one": "cross {digit} out at {cell}",
        "sudoku.cross_many": "cross {digit} out at {cells}",
        "sudoku.naked_set": (
            "**Naked set.** In {house}, {cells} can only contain {digits} between them. "
            "They use those digits, so **remove {digits} from the other cells in {house}**."
        ),
        "sudoku.hidden_set": (
            "**Hidden set.** In {house}, {digits} can only go in {cells}. "
            "Those digits fill the cells, so **remove the other candidates from them**."
        ),
        "sudoku.fish": (
            "**Line pattern.** In {sources}, every remaining place for {digit} is in {targets}. "
            "The {digit}s in those lines fill {targets}, so **remove {digit} from {targets} "
            "outside {sources}**."
        ),
        "sudoku.unavailable": (
            "**The next step needs {rule}.** A pattern-first explanation is not available for "
            "that deduction yet; use --verbose for its detailed trace."
        ),
        "sudoku.stalled": (
            "**Stopped.** The current deduction rules do not finish this grid; "
            "use --verbose for the technical trace."
        ),
        "generic.trace_fallback": (
            "A pattern-first explanation is not available for every deduction; "
            "the following is the technical placement trace."
        ),
        "sudoku.givens_complete": "The givens already fill the grid.",
        "sudoku.rule.single": "a single",
        "sudoku.rule.subsumption": "a constraint interaction",
        "sudoku.rule.cover2": "a two-set deduction",
        "sudoku.rule.cover3": "a three-set deduction",
        "sudoku.rule.chains": "a chain",
        "sudoku.rule.wing": "a wing",
        "sudoku.rule.what_if": "case analysis",
        "sudoku.rule.relations": "a variant clue",
        "sudoku.rule.count": "a counting deduction",
        "generic.placed": "{var} = {value}",
        "generic.not_placed": "{var} ≠ {value}",
        "generic.yes": "{var} yes",
        "generic.no": "{var} no",
        "generic.true.akari": "bulb",
        "generic.false.akari": "no bulb",
        "generic.true.battleships": "ship",
        "generic.false.battleships": "water",
        "generic.true.binairo": "black",
        "generic.false.binairo": "white",
        "generic.true.kakurasu": "shaded",
        "generic.false.kakurasu": "empty",
        "generic.true.minesweeper": "mine",
        "generic.false.minesweeper": "safe",
        "generic.true.mosaic": "black",
        "generic.false.mosaic": "white",
        "generic.true.pattern": "filled",
        "generic.false.pattern": "empty",
        "generic.true.starbattle": "star",
        "generic.false.starbattle": "no star",
        "generic.true.tents": "tent",
        "generic.false.tents": "no tent",
        "generic.true.thermometers": "mercury",
        "generic.false.thermometers": "empty",
        "generic.cannot_be": "{where} cannot be {values}",
        "generic.internal": "an intermediate step",
        "generic.singles_by": "**Only option.** {parts}.",
        "generic.by_rule": "{placements} by {rules}",
        "generic.singles_plain": "**Only option.** Then: {parts}.",
        "generic.singles_more": "**Only option, continued.** {parts}.",
        "generic.last_left": "{placements}, the only option left",
        "generic.last_left_each": "{placements}, each the only option left",
        "generic.left_after": "{placements}, the only option left once {causes}",
        "generic.left_after_each": "{placements}, each the only option left once {causes}",
        "generic.left_after_prior": "{placements}, the only option left after the earlier "
        "exclusions, once {causes}",
        "generic.left_after_previous": "{placements}, the only option left after the earlier "
        "exclusions",
        "generic.constraint_left_after": "{placements}, the only option left in {source} "
        "once {causes}",
        "generic.constraint_left_after_prior": "{placements}, the only option left in {source} "
        "after the earlier exclusions, once {causes}",
        "generic.rules_out": "{source} rules out {values}",
        "generic.calcudoku_cages": "**Cages.** Each row and column contains the numbers 1 to "
        "{size} exactly once. Whenever a cage is cited below, use its arithmetic together "
        "with those row and column rules; cage cells not sharing a row or column may repeat.",
        "generic.exclusion_by_placements": "{placements} {verb} {values} under {source}",
        "generic.compared_equal": "{pairs}; the corresponding cells match",
        "generic.placed_elsewhere": "{variables} are already assigned values other than {value}",
        "generic.binairo_legend": "Here 1 is black and 0 is white.",
        "generic.different_rows": "the rule that rows {first} and {second} must differ",
        "generic.different_columns": "the rule that columns {first} and {second} must differ",
        "generic.rule_out": "rule out",
        "generic.rules_out_verb": "rules out",
        "generic.opposite_ruled_out_by": "{placements}, because {cause} rules out {alternatives}",
        "generic.opposite_ruled_out_by_support": "{placements}, because {cause} and {source} "
        "rule out {alternatives}",
        "generic.count_single_support": "{placements}: {facts}; with {source}, that leaves "
        "no alternative",
        "generic.count_single_again": "{placements}, using the same count from {source}",
        "generic.given_single_ship": "{cell} is a given single-cell ship",
        "generic.ships_do_not_touch": "ships do not touch, even diagonally",
        "generic.akari_lighting": "the requirement to light {cell}",
        "generic.clues": "**Clues.** {items}.",
        "generic.clue": "{sources} gives {conclusion}",
        "generic.clue_count_again": "{sources} gives {conclusion}, using the same count as before",
        "generic.clue_with_candidates": "With {candidates}, {sources} gives {conclusion}",
        "generic.subsumption": "**Overlap.** Every remaining option of {sources} lies within "
        "{scope}, so {conclusion}.",
        "generic.subsumption_count": "**Overlap.** With {placed} already counted, every remaining "
        "option of {sources} lies within {scope}, so {conclusion}.",
        "generic.subsumption_count_options": "**Overlap.** With {placed} already counted, the "
        "remaining options of {sources} are {options}; each lies within {scope}, so {conclusion}.",
        "generic.cover": "**Combined rules.** {sources} use the remaining capacity of {scope}, "
        "so {conclusion}.",
        "generic.cover_counted": "**Combined rules.** With {counted} already counted, {sources} "
        "use the remaining capacity of {scope}, so {conclusion}.",
        "generic.cover_count_option": "under {source}, one of {options} must hold",
        "generic.cover_count_options": "**Combined rules.** With {counted} already counted, "
        "{options}. These separate options fill the remaining capacity of {scope}, "
        "so {conclusion}.",
        "generic.cover_naked": "**Combined rules.** {cells} can only be {values}. By {rules}, "
        "those values must go in those cells, so {conclusion}.",
        "generic.cover_hidden": "**Combined rules.** By {rules}, {values} can only go in {cells}, "
        "so {conclusion}.",
        "generic.chain": "**Chain.** If {start}, then {links}. So {first} or {last}, "
        "and either way {conclusion}.",
        "generic.chain_continuation": "Continuing the same chain, still assuming {assumption}, "
        "{links}. It also shows that {conclusion}.",
        "generic.chain_also": "The same chain also shows that {conclusion}.",
        "generic.chain_reused": "**Chain.** {start}, then {prefix}. The earlier chain from "
        "{shared_start} shows {shared_end}; continuing, {continuation}. So {first} or {last}. "
        "{reason}",
        "generic.chain_if": "If {assumption}",
        "generic.chain_explained": "**Chain.** {start}, then {links}. So {first} or {last}. "
        "{reason}",
        "generic.chain_either_explained": "**Chain.** {ends}. {reason}",
        "generic.chain_eliminates": "{target} is ruled out: {first} conflicts with it by "
        "{first_source}, and {last} by {last_source}.",
        "generic.chain_domain_reason": "; it is the only value left after {excluded} is ruled out",
        "generic.chain_link": ", so ",
        "generic.chain_reason": " by {source}",
        "generic.chain_supported": "under {source}, {options} were the only options; with "
        "{excluded} ruled out, {placement}",
        "generic.chain_supported_either": "only {options} remain under {source}",
        "generic.wing": "**Wing.** One of {options} must hold, so {conclusion}.",
        "generic.other": "**{rule}.** {conclusion}.",
        "generic.what_if": "**Suppose {assumed}.** Then {trail}; but {breaks}; so {refuted}.",
        "generic.what_if_segmented": "**Suppose {assumed}.** {trail} But {breaks}, so {refuted}.",
        "generic.what_if_direct": "**Suppose {assumed}.** Then {breaks}; so {refuted}.",
        "generic.trail_start": "Then {items}.",
        "generic.trail_continue": "Next {items}.",
        "generic.trail_place": "{placement} by {sources}",
        "generic.trail_only": "{placement} is the only option",
        "generic.breaks": "{source} fails",
        "generic.remaining_values": "{variable} = {values}",
        "generic.breaks_relation": "{options} break {source}",
        "generic.breaks_unknown": "the puzzle gets stuck",
        "generic.breaks_empty": "{cells} would have no value left that fits {source}",
        "generic.stalled": "**Stalled.** The current rules do not finish this puzzle; "
        "use --verbose for the detailed trace.",
        "generic.givens_complete": "The givens already solve the puzzle.",
        "generic.doc_how": "How to solve it",
        "expression.by": "By {sources}, {conclusion}.",
        "expression.clue": "clue {number}",
        "expression.rule": "rule {number}",
        "expression.person": "{person} stands on one free square",
        "expression.square": "{square} holds at most one person",
        "expression.row": "at most one person per row",
        "expression.column": "at most one person per column",
        "expression.row_exact": "exactly one person per row",
        "expression.column_exact": "exactly one person per column",
        "expression.role_count": "the allowed number of people with the {role} role is {counts}",
        "expression.role_eligibility": "the declared role candidates",
        "rule.role_separation": "there is at most one {role} per area ({a}, {b})",
        "expression.role_state": "{person} either has the {role} role or does not",
        "literal_true": "the literal {literal} must hold",
        "literal_false": "the literal {literal} cannot hold",
        "role_has": "{who} has the {role} role",
        "role_not": "{who} does not have the {role} role",
        "role_others": "nobody else has the {role} role",
        "role_not_many": "{people} cannot have the {role} role",
        "role_eligible_only_one": "only {people} is eligible for the {role} role",
        "role_eligible_only_many": "only {people} are eligible for the {role} role",
        "role_eligible_statements": "{role}: the only possible assignments are: {statements}",
        "role_eligible_true": "{role}: only these assignments are true: {statements}",
        "murdoku.chain_domain_reason": "; it is the only square left after {excluded} is ruled out",
        "murdoku.relation_pair": "Of the remaining squares, only {pair} satisfy {source}.",
        "murdoku.area_pair_square": "{square} ({area})",
        "murdoku.area_pair_candidates": "{who} can only be on {squares}",
        "murdoku.area_pair_reason": "{candidates}. For {pair}, the areas do not share a border; "
        "a route crossing two borders is {route}. All other possible area pairs are the same "
        "area or share a border, so their distance is at most one.",
        "murdoku.relation_pair_with_known": "Given {known}, only {pair} among the remaining "
        "squares satisfies {source}.",
        "murdoku.direction_boundaries": "{clue}, so **{first}** and **{second}**.",
        "murdoku.with_prior": "Taking the earlier restrictions into account, {conclusion}",
        "murdoku.given_relation": "With {known} already established: {reason}",
        "murdoku.relation_occupied_lines": "If {who} were on {rejected}, {other} would have to "
        "be on {squares} by {source}. Each square is in an already occupied row or column "
        "({lines}), so none is available. Therefore {placement}; {other} can only "
        "be on {remaining}.",
        "line_single": "In {line}, only {placement} remains; since the line requires one person, "
        "that person must be there.",
        "murdoku.line_single_excluded": "{clue} rules out {squares} for {who}",
        "murdoku.region_candidates": "Possible areas: {candidates}",
        "murdoku.line_single_with_clues": "{clues}; in {line} only {placement} remains, and the "
        "line requires one person, so that person must be there.",
        "murdoku.line_single_consequences": "{line} must be occupied; only {who} can fill it, "
        "at {square}. That row and column are then unavailable to others. The placements are "
        "{placements}.",
        "murdoku.line_overlap": "The only remaining place for {source_line} is {square}, in "
        "{scope_line}; since {source_line} must be occupied, {scope_line} is already occupied, "
        "so {conclusion}",
        "murdoku.line_overlap_with_exclusion": "The only remaining place for {source_line} "
        "is {square}, in {scope_line}; it must be occupied there. Only one person can be in "
        "{scope_line}, so {removed} is unavailable to {who}; hence {conclusion}",
        "murdoku.line_overlap_with_exclusions": "The only remaining place for {source_line} "
        "is {square}, in {scope_line}; it must be occupied there. Only one person can be in "
        "{scope_line}, so {removed} are unavailable to {who}; hence {conclusion}",
        "murdoku.line_overlap_only": "The only remaining place for {source_line} is {square}, "
        "in {scope_line}; since {source_line} must be occupied, {scope_line} is already occupied",
        "murdoku.area_confined": "{who}'s remaining squares are all {area}",
        "murdoku.area_no_candidate": "{who} has no remaining square {area}",
        "murdoku.area_excluded_by_clue": "{clue} rules {who} out of {squares}",
        "murdoku.area_excluded_by_occupant": "{blocker} occupies {line}, so {who} cannot use "
        "{squares}",
        "murdoku.area_excluded_by_reservation": "{blocker}'s remaining squares are all in {line}, "
        "so {who} cannot use {squares}",
        "murdoku.role_area_unique": "{reasons}. That leaves {who} as the only eligible person who "
        "can still be {area}. {rule}; since only one {role} is allowed, "
        "**{who} is the {role}**",
        "person_single": "Only {placement} is possible now.",
        "murdoku.person_single_explained": "Given {support}, {placement} is the only remaining "
        "place for {who}",
        "murdoku.person_single_evidence": "{support}; therefore {placement} is the only "
        "remaining place",
        "murdoku.use_sources": "We use {sources}",
        "murdoku.established_placements": "the placements already established",
        "murdoku.group_excluded_squares": "{people} cannot be on {squares}",
        "murdoku.final_answer": "**Answer.** {reveal}",
        "murdoku.final_placements": "Final placements not yet named: {placements}.",
        "murdoku.rule_context": "**Rules.** {rules}.",
        "murdoku.role_exclusion": "{rule} rules out {who} as the {role}",
        "murdoku.role_exclusion_candidates": "{rule} says {statement}.{detail} {who}'s remaining "
        "squares are {squares}; none satisfies it, so {who} cannot be the {role}",
        "murdoku.role_exclusion_candidates_unnumbered": "{statement}.{detail} {who}'s remaining "
        "squares are {squares}; none satisfies it, so {who} cannot be the {role}",
        "murdoku.role_exclusion_candidates_many": "{rule} says {statement}.{detail} "
        "{who} each have only {squares} left; none satisfies it, so none of them "
        "can be the {role}",
        "murdoku.role_exclusion_candidates_many_unnumbered": "{statement}.{detail} "
        "{who} each have only {squares} left; none satisfies it, so none of them "
        "can be the {role}",
        "murdoku.beside_different_area": "An area boundary separates {squares} from {thing}; "
        "beside requires the same area",
        "line_takes": "{who} occupies {lines}",
        "murdoku.line_takes_known": "{who} occupies {lines}",
        "murdoku.shared_rule_exclusions_some": "By {source}, only {people} can use {squares}",
        "murdoku.shared_rule_exclusions_one": "By {source}, only {people} can use {squares}",
        "murdoku.shared_rule_exclusions_none": "By {source}, nobody can use {squares}",
        "line_exclusions": "{blockers}; at most one person can use each row or column, so no one "
        "else can use those lines",
        "line_exclusions_exact": "{blockers}; exactly one person occupies each row and column, "
        "so no one else can use those lines",
        "line_exclusions_followup": "{blockers}; the one-person-per-line rule excludes everyone "
        "else",
        "must_occupy_line": "{who} must occupy {line}",
        "nobody_else_line": "the one-person-per-line rule excludes everyone else",
        "line_reservation": "{person}'s remaining squares are all in {line}, so {person} must be "
        "there; {rule} leaves no other person in that line, so {conclusion}",
        "line_reservation_only": "{person}'s remaining squares are all in {line}, so {rule} "
        "reserves that line for {person}",
        "candidate_bound": "Only {lines} are available to {people}",
        "murdoku.relation_candidate_bound": "{people} can only be in {lines}",
        "murdoku.relation_area_bound": "{who} can only be {areas}",
        "murdoku.line_person": "Only {who} can occupy {line} ({squares}); that line must be "
        "occupied, so {conclusion}",
        "murdoku.count_square_reservation": "According to {source}, {count} people must be "
        "counted, and only {squares} can count. At most one person can occupy each square, so "
        "all of them are occupied.",
        "murdoku.reserved_line_excludes_squares": "{who} must be in {line} but cannot use "
        "{squares}; the one-person-per-line rule means nobody can stand there.",
        "murdoku.occupied_square_line": "{square} is occupied, and only one person can be in "
        "{line}, so {conclusion}.",
        "murdoku.relation_with_candidates": ("Given {candidates}, {sources} gives {conclusion}"),
        "murdoku.relation_exact_candidates": "{who} can only be on {squares}",
        "murdoku.furthest_exclusion": "{clue} rules out {subject} at {candidate}: each remaining "
        "square for {rival} ({rival_squares}) is at least as far from every remaining {target} "
        "square ({target_squares}) as {subject} would be. The clue requires {subject} to be "
        "uniquely farthest, so {conclusion}",
        "row_reservation": "{people} are each confined to {rows}; they must occupy different rows, "
        "so those rows are reserved",
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
        "rule.role_occupancy.alone": "every {role} holder is alone in their area",
        "rule.role_occupancy.not_alone": "no {role} holder is alone in their area",
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
        "clue.in": "{a} is {where}",
        "clue.not_in": "{a} is not {where}",
        "clue.beside": "{a} is beside {things}",
        "clue.not_beside": "{a} is not beside {things}",
        "clue.touches": "{a} shares a side with {things}",
        "clue.not_touches": "{a} does not share a side with {things}",
        "clue.dir_same_area": "{a} and {b} are in the same area",
        "clue.dir_different_areas": "{a} and {b} are in different areas",
        "clue.dir_not": "It is not the case that {relation}",
        "clue.dir_distance": "{a} and {b} are {comparison} {n} {unit} apart",
        "clue.dir_exact": "{a} is exactly {n} {unit} {direction} {b}",
        "clue.dir_direction": "{a} is {direction} {b}",
        "clue.dir_knight": "{a} is a knight's move from {b}",
        "clue.dir_near_cell": (
            "{a} is on or directly next to {b} (including diagonally and across area borders)"
        ),
        "clue.dir_not_near_cell": (
            "{a} is not on or directly next to {b} (not even diagonally or across area borders)"
        ),
        "clue.area_isolation": ("No two side-adjacent areas{scope} are both occupied"),
        "clue.conditional": "If {a} holds role {role}, then {predicate}",
        "clue.alone_area": "{a} is the only person in {where}",
        "clue.alone_area_any": "exactly one person is in {where}",
        "clue.with_area": "In {where}, at least two people are present, including {membership}",
        "clue.with_area_person": (
            "{a} is in {where}; exactly {n} other occupants match {membership}"
        ),
        "location.touched_by": "a square touching {thing}",
        "target.attribute": "someone with the {name} attribute",
        "target.role": "a {name} holder",
        "target.unique_role": "the {name}",
        "target.area": "someone {where}",
        "target.on": "someone on {what}",
        "target.at": "someone at {what}",
        "target.corner": "someone in the cells around {what}",
        "target.kind": "someone on {what}",
        "cell_target.area": "a square {where}",
        "cell_target.on": "a square of {what}",
        "cell_target.at": "a square touching {what}",
        "cell_target.corner": "a square around {what}",
        "cell_target.kind": "a square of {what}",
        "target.people_on": "someone on {what}",
        "target.people": "one of {people}",
        "target.anyone": "anyone",
        "location.in_line": "in {line}",
        "area.name": "the {name} area",
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
        "web.cell_door": "een deur",
        "web.cell_window": "een raam",
        "web.cell_figure": "Figuur",
        "web.extras": "Bijzonderheden",
        "web.solution_steps": "Oplossingsstappen",
        "web.spoiler": "Spoiler: de stappen hieronder verklappen de oplossing.",
        "web.steps_incomplete": (
            "Deze stappen leiden niet tot de hele oplossing; de rest wordt hier niet uitgelegd."
        ),
        "web.steps_unavailable": "Voor deze puzzel zijn geen oplossingsstappen beschikbaar.",
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
        "doc.clue_beside_object": (
            "Naast een voorwerp in een vakje betekent een zijde delen met een vakje van het "
            "voorwerp in hetzelfde gebied; schuin telt niet."
        ),
        "doc.clue_on_door": (
            "Op een deur betekent dat je op een van de twee vakjes staat die eraan raken, "
            "ook over een gebiedsgrens heen."
        ),
        "doc.clue_on_point": (
            "Op een puntobject betekent dat je op een vakje staat dat het raakt, ook in een "
            "ander gebied."
        ),
        "doc.clue_on_window": (
            "Op een raam betekent dat je op het ene vakje aan de binnenkant staat."
        ),
        "doc.clue_touches_mark": (
            "Een vakje raakt een gemarkeerd vakje als het er een zijde mee deelt, ook over "
            "een gebiedsgrens heen; schuin telt niet."
        ),
        "doc.clue_distance": "Afstand telt stappen over zijden, niet schuin.",
        "doc.clue_euclidean_distance": (
            "De afstand in vogelvlucht is de rechte lijn tussen de middelpunten van de vakjes."
        ),
        "doc.clue_neighboring_areas": (
            "Gebieden grenzen aan elkaar als ze een zijde delen, niet alleen een hoek."
        ),
        "doc.clue_away_from": (
            "Uit de buurt van een voorwerp betekent er niet op staan en er geen zijde of hoek "
            "mee delen, in welk gebied dan ook."
        ),
        "doc.standable": "hier kun je op staan",
        "doc.stand_under": "hier kun je onder staan",
        "doc.sit_on": "hier kun je op zitten",
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
        "count": "{who} kan nog op {n} vakjes staan",
        "placed": "**{who} op {square}**",
        "so": "dus",
        "cross_out.one": "streep het andere nog open vakje in die {line} weg",
        "cross_out.many": "streep de {n} andere nog open vakjes in die {line} weg: {squares}",
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
        "clue_reference.one": "zie aanwijzing {refs}",
        "clue_reference.many": "zie aanwijzingen {refs}",
        "chain_if": "Als {who} niet op {square} zit",
        "chain_on": "dan zit {who} op {square}",
        "chain_off": "dan zit {who} niet op {square}",
        "chain_so": "Dus {ends}; hoe dan ook {outcome}.",
        "chain_either": "{ends}; hoe dan ook {outcome}.",
        "chain_hidden": "De aanwijzingen samen laten zien: {outcome}.",
        "nobody_else": "daar kan verder niemand",
        "then_on": "dan zou {who} op {square} zitten",
        "also_on": "{who} op {square}",
        "then_in": "dan zou {who} {where} zijn",
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
        "mark_count_filled": (
            "Dat is het enige bezette vakje met markering {mark}, "
            "dus **alle andere vakjes met die markering zijn leeg**"
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
        "clue.with_same_area": (
            "{a} deelt een gebied met precies één ander persoon, en dat is {target}"
        ),
        "clue.same_region": "{a} en {b} zijn in hetzelfde gebied",
        "clue.different_region": "{a} en {b} zijn in verschillende gebieden",
        "clue.apart": "{a} en {b} zijn in gebieden die niet aan elkaar grenzen",
        "clue.same_region_target": "{a} is in hetzelfde gebied als {target}",
        "clue.different_region_target": "{a} is in een ander gebied dan {target}",
        "clue.adjacent_regions_target": "{a} is in een gebied dat aan dat van {target} grenst",
        "clue.apart_target": "{a} is in een gebied dat niet aan dat van {target} grenst",
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
        "clue.with_same_area_anyone": "{a} deelt een gebied met precies één ander persoon",
        "clue.with_same_area_n": (
            "{a} deelt een gebied met precies {n} anderen, en dat zijn allemaal {target}"
        ),
        "clue.with_same_area_anyone_n": "{a} deelt een gebied met precies {n} anderen",
        "count_reason": "voor {name} zijn de toegestane aantallen {counts}",
        "count.mark_occupant.alone": (
            "wie op een vakje met markering {mark} {where} staat, moet alleen zijn"
        ),
        "count.mark_occupant.not_alone": (
            "wie op een vakje met markering {mark} {where} staat, moet gezelschap hebben"
        ),
        "count.mark_occupant.name": "het aantal mensen {where} voor de regel over {mark}-vakjes",
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
        "sudoku.row": "rij {number}",
        "sudoku.column": "kolom {number}",
        "sudoku.box": "het blok met {cell}",
        "sudoku.extra": "het extra gebied {name}",
        "sudoku.singles": "**Enkele kandidaten.**",
        "sudoku.last_digit": "{placements} (het enige cijfer dat daar nog kan)",
        "sudoku.last_digits": "{placements} (in deze volgorde telkens het enige cijfer dat "
        "in dat vakje nog kan)",
        "sudoku.only_place": "{placements} (de enige plek voor {digits} in {house})",
        "sudoku.only_places": "{placements} (in deze volgorde de enige plekken voor {digits} "
        "in {house})",
        "sudoku.locked": (
            "**Gebonden kandidaat.** Alle overgebleven plekken voor {digit} in {source} liggen "
            "binnen {target}, dus **{conclusion}**."
        ),
        "sudoku.cross_one": "streep {digit} weg op {cell}",
        "sudoku.cross_many": "streep {digit} weg op {cells}",
        "sudoku.naked_set": (
            "**Naked set.** In {house} kunnen {cells} samen alleen {digits} bevatten. "
            "Daarmee zijn die cijfers gebruikt, dus **streep {digits} weg uit de andere vakjes "
            "in {house}**."
        ),
        "sudoku.hidden_set": (
            "**Hidden set.** In {house} kunnen {digits} alleen in {cells} staan. "
            "Die cijfers vullen de vakjes, dus **streep de andere kandidaten daar weg**."
        ),
        "sudoku.fish": (
            "**Lijnenpatroon.** In {sources} liggen alle plekken voor {digit} in {targets}. "
            "De {digit}'s van die lijnen vullen {targets}, dus **streep {digit} in {targets} "
            "buiten {sources} weg**."
        ),
        "sudoku.unavailable": (
            "**De volgende stap gebruikt {rule}.** Hiervoor is nog geen patroonverklaring "
            "beschikbaar; met --verbose zie je het technische spoor."
        ),
        "sudoku.stalled": (
            "**Gestopt.** De huidige regels lossen dit rooster niet helemaal op; "
            "met --verbose zie je het technische spoor."
        ),
        "generic.trace_fallback": (
            "Niet elke stap heeft al een patroonverklaring; hieronder staat het technische "
            "spoor van de plaatsingen."
        ),
        "sudoku.givens_complete": "Het rooster is al gevuld met de gegeven cijfers.",
        "sudoku.rule.single": "een enkele kandidaat",
        "sudoku.rule.subsumption": "een combinatie van regels",
        "sudoku.rule.cover2": "een combinatie van twee verzamelingen",
        "sudoku.rule.cover3": "een combinatie van drie verzamelingen",
        "sudoku.rule.chains": "een keten",
        "sudoku.rule.wing": "een wing",
        "sudoku.rule.what_if": "een gevalsonderscheid",
        "sudoku.rule.relations": "een variantregel",
        "sudoku.rule.count": "een telredenering",
        "generic.placed": "{var} = {value}",
        "generic.not_placed": "{var} ≠ {value}",
        "generic.yes": "{var} wel",
        "generic.no": "{var} niet",
        "generic.true.akari": "lamp",
        "generic.false.akari": "geen lamp",
        "generic.true.battleships": "schip",
        "generic.false.battleships": "water",
        "generic.true.binairo": "zwart",
        "generic.false.binairo": "wit",
        "generic.true.kakurasu": "gekleurd",
        "generic.false.kakurasu": "leeg",
        "generic.true.minesweeper": "mijn",
        "generic.false.minesweeper": "veilig",
        "generic.true.mosaic": "zwart",
        "generic.false.mosaic": "wit",
        "generic.true.pattern": "gevuld",
        "generic.false.pattern": "leeg",
        "generic.true.starbattle": "ster",
        "generic.false.starbattle": "geen ster",
        "generic.true.tents": "tent",
        "generic.false.tents": "geen tent",
        "generic.true.thermometers": "kwik",
        "generic.false.thermometers": "leeg",
        "generic.cannot_be": "{where}: geen {values}",
        "generic.internal": "een tussenstap",
        "generic.singles_by": "**Enige mogelijkheid.** {parts}.",
        "generic.by_rule": "{placements} door {rules}",
        "generic.singles_plain": "**Enige mogelijkheid.** Dan: {parts}.",
        "generic.singles_more": "**Enige mogelijkheid, vervolg.** {parts}.",
        "generic.last_left": "{placements}, de enige mogelijkheid die overblijft",
        "generic.last_left_each": "{placements}, telkens de enige mogelijkheid die overblijft",
        "generic.left_after": "{placements}, de enige mogelijkheid die overblijft nu {causes}",
        "generic.left_after_each": (
            "{placements}, telkens de enige mogelijkheid die overblijft nu {causes}"
        ),
        "generic.left_after_prior": "{placements}, de enige mogelijkheid na de eerdere "
        "uitsluitingen, nu {causes}",
        "generic.left_after_previous": "{placements}, de enige mogelijkheid na de eerdere "
        "uitsluitingen",
        "generic.constraint_left_after": "{placements}, de enige mogelijkheid in {source} "
        "die overblijft nu {causes}",
        "generic.constraint_left_after_prior": "{placements}, de enige mogelijkheid in {source} "
        "na de eerdere uitsluitingen, nu {causes}",
        "generic.rules_out": "{source} {values} uitsluit",
        "generic.calcudoku_cages": "**Kooien.** In elke rij en kolom staan de getallen 1 tot en "
        "met {size} precies één keer. Gebruik bij elke kooi hieronder zowel de berekening als "
        "deze rij- en kolomregels; kooivakjes die geen rij of kolom delen mogen gelijk zijn.",
        "generic.exclusion_by_placements": "{placements} volgens {source} {values} {verb}",
        "generic.compared_equal": "{pairs}; de overeenkomstige vakjes zijn gelijk",
        "generic.placed_elsewhere": "{variables} hebben al een andere waarde dan {value}",
        "generic.binairo_legend": "Hier is 1 zwart en 0 wit.",
        "generic.different_rows": "de regel dat rij {first} en rij {second} moeten verschillen",
        "generic.different_columns": (
            "de regel dat kolom {first} en kolom {second} moeten verschillen"
        ),
        "generic.rule_out": "uitsluiten",
        "generic.rules_out_verb": "uitsluit",
        "generic.opposite_ruled_out_by": "{placements}, omdat {cause} {alternatives} uitsluit",
        "generic.opposite_ruled_out_by_support": "{placements}, omdat {cause} en {source} "
        "{alternatives} uitsluiten",
        "generic.count_single_support": "{placements}: {facts}; met {source} blijft er geen "
        "andere mogelijkheid over",
        "generic.count_single_again": "{placements}, met dezelfde telling uit {source}",
        "generic.given_single_ship": "{cell} is een gegeven schip van één vakje",
        "generic.ships_do_not_touch": "schepen raken elkaar niet, ook niet diagonaal",
        "generic.akari_lighting": "de regel dat {cell} verlicht moet zijn",
        "generic.clues": "**Aanwijzingen.** {items}.",
        "generic.clue": "{sources} geeft {conclusion}",
        "generic.clue_count_again": "{sources} geeft {conclusion}, met dezelfde telling als eerder",
        "generic.clue_with_candidates": "Met {candidates} over geeft {sources} {conclusion}",
        "generic.subsumption": "**Overlap.** Alle resterende opties van {sources} liggen binnen "
        "{scope}, dus {conclusion}.",
        "generic.subsumption_count": "**Overlap.** Nu {placed} al meetelt, liggen alle resterende "
        "opties van {sources} binnen {scope}, dus {conclusion}.",
        "generic.subsumption_count_options": "**Overlap.** Nu {placed} al meetelt, zijn de "
        "resterende opties van {sources} {options}; ze liggen binnen {scope}, dus {conclusion}.",
        "generic.cover": "**Combinatie.** {sources} gebruiken de resterende ruimte van {scope}, "
        "dus {conclusion}.",
        "generic.cover_counted": "**Combinatie.** Met {counted} al meegeteld, gebruiken "
        "{sources} de resterende ruimte van {scope}, dus {conclusion}.",
        "generic.cover_count_option": "onder {source} moet {options} gelden",
        "generic.cover_count_options": "**Combinatie.** Met {counted} al meegeteld, "
        "{options}. Deze afzonderlijke mogelijkheden vullen de resterende ruimte van "
        "{scope}, dus {conclusion}.",
        "generic.cover_naked": "**Gecombineerde regels.** {cells} kunnen alleen {values} zijn. "
        "Volgens {rules} moeten die waarden dus in die vakjes staan, dus {conclusion}.",
        "generic.cover_hidden": "**Gecombineerde regels.** Volgens {rules} kunnen {values} alleen "
        "in {cells} staan, dus {conclusion}.",
        "generic.chain": "**Keten.** Als {start}, dan {links}. Dus {first} of {last}, "
        "en hoe dan ook {conclusion}.",
        "generic.chain_continuation": "Als we dezelfde keten voortzetten met nog steeds "
        "{assumption} als aanname, {links}. De keten laat ook zien dat {conclusion}.",
        "generic.chain_also": "Dezelfde keten laat ook zien dat {conclusion}.",
        "generic.chain_reused": "**Keten.** {start}, dan {prefix}. De eerdere keten laat vanaf "
        "{shared_start} {shared_end} zien; daarna {continuation}. Dus {first} of {last}. "
        "{reason}",
        "generic.chain_if": "Als {assumption}",
        "generic.chain_explained": "**Keten.** {start}, dan {links}. Dus {first} of {last}. "
        "{reason}",
        "generic.chain_either_explained": "**Keten.** {ends}. {reason}",
        "generic.chain_eliminates": "{target} valt af: {first} botst ermee door {first_source}, "
        "en {last} door {last_source}.",
        "generic.chain_domain_reason": "; dat is het enige cijfer dat overblijft nadat "
        "{excluded} is uitgesloten",
        "generic.chain_link": ", dus ",
        "generic.chain_reason": " door {source}",
        "generic.chain_supported": "onder {source} waren alleen {options} mogelijk; nu {excluded} "
        "afvalt, geldt {placement}",
        "generic.chain_supported_either": "onder {source} blijven alleen {options} over",
        "generic.wing": "**Wing.** Een van {options} moet gelden, dus {conclusion}.",
        "generic.other": "**{rule}.** {conclusion}.",
        "generic.what_if": "**Stel {assumed}.** Daaruit volgt: {trail}; maar dan {breaks}; "
        "dus {refuted}.",
        "generic.what_if_segmented": "**Stel {assumed}.** {trail} Maar dan {breaks}, "
        "dus {refuted}.",
        "generic.what_if_direct": "**Stel {assumed}.** Dan {breaks}; dus {refuted}.",
        "generic.trail_start": "Daaruit volgt: {items}.",
        "generic.trail_continue": "Verder: {items}.",
        "generic.trail_place": "{placement} door {sources}",
        "generic.trail_only": "{placement} is de enige mogelijkheid",
        "generic.breaks": "klopt {source} niet meer",
        "generic.remaining_values": "{variable} = {values}",
        "generic.breaks_relation": "botsen {options} met {source}",
        "generic.breaks_unknown": "loopt het vast",
        "generic.breaks_empty": "blijft er voor {cells} geen waarde over die past bij {source}",
        "generic.stalled": "**Gestopt.** De huidige regels lossen deze puzzel niet helemaal op; "
        "met --verbose zie je het technische spoor.",
        "generic.givens_complete": "De puzzel is al opgelost door wat gegeven is.",
        "generic.doc_how": "Zo los je het op",
        "expression.by": "Door {sources} geldt: {conclusion}.",
        "expression.clue": "aanwijzing {number}",
        "expression.rule": "regel {number}",
        "expression.person": "{person} staat op één vrij vakje",
        "expression.square": "op {square} staat hoogstens één persoon",
        "expression.row": "hoogstens één persoon per rij",
        "expression.column": "hoogstens één persoon per kolom",
        "expression.row_exact": "precies één persoon per rij",
        "expression.column_exact": "precies één persoon per kolom",
        "expression.role_count": "het toegestane aantal personen met de rol {role} is {counts}",
        "expression.role_eligibility": "de opgegeven kandidaten voor de rollen",
        "rule.role_separation": "er is hoogstens één {role} per gebied ({a}, {b})",
        "expression.role_state": "{person} heeft de rol {role} wel of niet",
        "literal_true": "de letterlijke keuze {literal} moet gelden",
        "literal_false": "de letterlijke keuze {literal} kan niet gelden",
        "role_has": "{who} heeft de rol {role}",
        "role_not": "{who} heeft de rol {role} niet",
        "role_others": "niemand anders heeft de rol {role}",
        "role_not_many": "{people} kunnen de rol {role} niet hebben",
        "role_eligible_only_one": "alleen {people} komt in aanmerking voor de rol {role}",
        "role_eligible_only_many": "alleen {people} komen in aanmerking voor de rol {role}",
        "role_eligible_statements": "{role}: dit zijn de enige mogelijke toewijzingen: "
        "{statements}",
        "role_eligible_true": "{role}: alleen deze toewijzingen zijn waar: {statements}",
        "murdoku.chain_domain_reason": "; dat is het enige vakje dat overblijft nadat "
        "{excluded} is uitgesloten",
        "murdoku.relation_pair": "Van de overgebleven vakjes voldoen alleen {pair} aan {source}.",
        "murdoku.area_pair_square": "{square} ({area})",
        "murdoku.area_pair_candidates": "{who} kan alleen nog op {squares} staan",
        "murdoku.area_pair_reason": "{candidates}. Bij {pair} grenzen de gebieden niet aan "
        "elkaar; een route langs twee grenzen is {route}. Alle andere mogelijke gebiedsparen "
        "zijn gelijk of grenzen aan elkaar; hun afstand is dus hoogstens één.",
        "murdoku.relation_pair_with_known": "Met {known} voldoet van de overgebleven vakjes "
        "alleen {pair} aan {source}.",
        "murdoku.direction_boundaries": "{clue}, dus **{first}** en **{second}**.",
        "murdoku.with_prior": "Met de eerdere beperkingen geldt: {conclusion}",
        "murdoku.given_relation": "Nu is bekend: {known}. {reason}",
        "murdoku.relation_occupied_lines": "Als {who} op {rejected} stond, moest {other} "
        "volgens {source} op {squares} staan. Elk vakje ligt in een al bezette rij of kolom "
        "({lines}) en valt dus af. Daarom {placement}; {other} kan alleen nog "
        "op {remaining} staan.",
        "line_single": "In {line} is alleen {placement} over; omdat daar precies één persoon moet "
        "staan, moet die persoon daar staan.",
        "murdoku.line_single_excluded": "{clue} sluit {squares} voor {who} uit",
        "murdoku.region_candidates": "Mogelijke gebieden: {candidates}",
        "murdoku.line_single_with_clues": "{clues}; daardoor is in {line} alleen {placement} "
        "over, want daar moet precies één persoon staan.",
        "murdoku.line_single_consequences": "{line} moet bezet zijn; alleen {who} kan daar "
        "staan, op {square}. Die rij en kolom zijn daarmee voor anderen bezet. "
        "Daardoor liggen de plaatsen vast: "
        "{placements}.",
        "murdoku.line_overlap": "De enige overgebleven plaats in {source_line} is {square}, in "
        "{scope_line}; omdat {source_line} bezet moet zijn, is {scope_line} al bezet, dus "
        "{conclusion}",
        "murdoku.line_overlap_with_exclusion": "De enige overgebleven plaats in {source_line} "
        "is {square}, in {scope_line}; dat vakje moet bezet zijn. In {scope_line} past maar "
        "één persoon, dus voor {who} valt {removed} af; daarom {conclusion}",
        "murdoku.line_overlap_with_exclusions": "De enige overgebleven plaats in {source_line} "
        "is {square}, in {scope_line}; dat vakje moet bezet zijn. In {scope_line} past maar "
        "één persoon, dus voor {who} vallen {removed} af; daarom {conclusion}",
        "murdoku.line_overlap_only": "De enige overgebleven plaats in {source_line} is {square}, "
        "in {scope_line}; omdat {source_line} bezet moet zijn, is {scope_line} al bezet",
        "murdoku.area_confined": "{who} kan alleen nog op vakjes {area}",
        "murdoku.area_no_candidate": "{who} heeft geen overgebleven vakje {area}",
        "murdoku.area_excluded_by_clue": "{clue} sluit {who} uit op {squares}",
        "murdoku.area_excluded_by_occupant": "{blocker} bezet {line}, dus {who} kan niet op "
        "{squares}",
        "murdoku.area_excluded_by_reservation": "{blocker} kan alleen nog in {line} staan, dus "
        "{who} kan niet op {squares}",
        "murdoku.role_area_unique": "{reasons}. Daardoor is {who} de enige geschikte persoon die "
        "nog {area} kan zijn. {rule}; omdat er maar één {role} mag zijn, "
        "**{who} is de {role}**",
        "person_single": "Alleen {placement} is nog mogelijk.",
        "murdoku.person_single_explained": "Met {support} blijft alleen {placement} over "
        "voor {who}",
        "murdoku.person_single_evidence": "{support}; daardoor blijft alleen {placement} over",
        "murdoku.use_sources": "We gebruiken {sources}",
        "murdoku.established_placements": "de plaatsingen die al vaststaan",
        "murdoku.group_excluded_squares": "{people} kunnen niet op {squares} staan",
        "murdoku.final_answer": "**Antwoord.** {reveal}",
        "murdoku.final_placements": "Nog niet expliciet genoemde plaatsingen: {placements}.",
        "murdoku.rule_context": "**Regels.** {rules}.",
        "murdoku.role_exclusion": "{rule} sluit {who} uit als {role}",
        "murdoku.role_exclusion_candidates": "{rule} zegt: {statement}.{detail} {who} kan alleen "
        "nog op {squares} staan; geen daarvan voldoet, dus {who} kan niet de {role} zijn",
        "murdoku.role_exclusion_candidates_unnumbered": "{statement}.{detail} {who} kan alleen "
        "nog op {squares} staan; geen daarvan voldoet, dus {who} kan niet de {role} zijn",
        "murdoku.role_exclusion_candidates_many": "{rule} zegt: {statement}.{detail} "
        "{who} kunnen ieder alleen nog op {squares} staan; geen daarvan voldoet, dus "
        "geen van hen kan de {role} zijn",
        "murdoku.role_exclusion_candidates_many_unnumbered": "{statement}.{detail} "
        "{who} kunnen ieder alleen nog op {squares} staan; geen daarvan voldoet, dus "
        "geen van hen kan de {role} zijn",
        "murdoku.beside_different_area": "Tussen {squares} en {thing} ligt een gebiedsgrens; "
        "naast vereist hetzelfde gebied",
        "line_takes": "{who} bezet {lines}",
        "murdoku.line_takes_known": "{who} bezet {lines}",
        "murdoku.shared_rule_exclusions_some": (
            "Door {source} kunnen alleen {people} op {squares} staan"
        ),
        "murdoku.shared_rule_exclusions_one": (
            "Door {source} kan alleen {people} op {squares} staan"
        ),
        "murdoku.shared_rule_exclusions_none": "Door {source} kan niemand op {squares} staan",
        "line_exclusions": "{blockers}; per rij en kolom kan hoogstens één persoon staan, dus "
        "niemand anders kan die lijnen gebruiken",
        "line_exclusions_exact": "{blockers}; elke rij en kolom heeft precies één persoon, dus "
        "niemand anders kan die lijnen gebruiken",
        "line_exclusions_followup": "{blockers}; de regel van één persoon per rij of kolom "
        "sluit iedereen anders uit",
        "must_occupy_line": "{who} moet in {line} staan",
        "nobody_else_line": "de regel van één persoon per rij of kolom sluit iedereen anders uit",
        "line_reservation": "de resterende vakjes van {person} liggen allemaal in {line}, dus "
        "{person} moet daar staan; {rule} sluit iedereen anders in die lijn uit: {conclusion}",
        "line_reservation_only": "de resterende vakjes van {person} liggen allemaal in {line}, "
        "dus {rule} reserveert die lijn voor {person}",
        "candidate_bound": "Voor {people} blijven alleen {lines} over",
        "murdoku.relation_candidate_bound": "{people} alleen nog in {lines} kunnen staan",
        "murdoku.relation_area_bound": "{who} alleen nog {areas} kan staan",
        "murdoku.line_person": "Alleen {who} kan in {line} staan ({squares}); die lijn moet "
        "bezet zijn, dus {conclusion}",
        "murdoku.count_square_reservation": "Volgens {source} moeten {count} mensen meetellen, "
        "en alleen {squares} tellen mee. Op elk vakje past hoogstens één persoon, dus alle vakjes "
        "zijn bezet.",
        "murdoku.reserved_line_excludes_squares": "{who} moet in {line} staan maar kan niet op "
        "{squares} staan; volgens de regel van één persoon per rij of kolom kan daar dus niemand "
        "staan.",
        "murdoku.occupied_square_line": "{square} is bezet en in {line} past maar één persoon, "
        "dus {conclusion}.",
        "murdoku.relation_with_candidates": (
            "Omdat {candidates}, leidt {sources} tot {conclusion}"
        ),
        "murdoku.relation_exact_candidates": "{who} alleen nog op {squares} kan staan",
        "murdoku.furthest_exclusion": "{clue} sluit {subject} op {candidate} uit: ieder "
        "overgebleven vakje voor {rival} ({rival_squares}) ligt minstens zo ver van elk "
        "overgebleven vakje voor {target} ({target_squares}) als {subject} zou liggen. De "
        "aanwijzing vereist dat {subject} als enige het verst staat, dus {conclusion}",
        "row_reservation": (
            "{people} kunnen alleen in {rows} staan; ze moeten verschillende rijen bezetten, "
            "dus die rijen zijn gereserveerd"
        ),
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
        "rule.role_occupancy.alone": "elke {role}-drager is alleen in zijn gebied",
        "rule.role_occupancy.not_alone": "geen enkele {role}-drager is alleen in zijn gebied",
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
        "clue.in": "{a} is {where}",
        "clue.not_in": "{a} is niet {where}",
        "clue.beside": "{a} staat naast {things}",
        "clue.not_beside": "{a} staat niet naast {things}",
        "clue.touches": "{a} deelt een zijde met {things}",
        "clue.not_touches": "{a} deelt geen zijde met {things}",
        "clue.dir_same_area": "{a} en {b} staan in hetzelfde gebied",
        "clue.dir_different_areas": "{a} en {b} staan in verschillende gebieden",
        "clue.dir_not": "Het is niet zo dat {relation}",
        "clue.dir_distance": "{a} en {b} zijn {comparison} {n} {unit} van elkaar verwijderd",
        "clue.dir_exact": "{a} staat precies {n} {unit} {direction} {b}",
        "clue.dir_direction": "{a} staat {direction} {b}",
        "clue.dir_knight": "{a} staat een paardensprong van {b}",
        "clue.dir_near_cell": (
            "{a} staat op of direct naast {b} (ook schuin en over gebiedsgrenzen)"
        ),
        "clue.dir_not_near_cell": (
            "{a} staat niet op of direct naast {b} "
            "(ook niet schuin, en dit geldt zelfs over gebiedsgrenzen heen)"
        ),
        "clue.area_isolation": (
            "Twee gebieden die aan een zijde grenzen{scope} mogen niet allebei bezet zijn"
        ),
        "clue.conditional": "Als {a} de rol {role} heeft, dan geldt dat {predicate}",
        "clue.alone_area": "{a} is de enige persoon in {where}",
        "clue.alone_area_any": "precies één persoon is in {where}",
        "clue.with_area": "In {where} zijn minstens twee mensen aanwezig, waaronder {membership}",
        "clue.with_area_person": (
            "{a} is in {where}; precies {n} andere aanwezigen voldoen aan {membership}"
        ),
        "location.touched_by": "een vakje dat {thing} raakt",
        "target.attribute": "iemand met het kenmerk {name}",
        "target.role": "een {name}-drager",
        "target.unique_role": "de {name}",
        "target.area": "iemand {where}",
        "target.on": "iemand op {what}",
        "target.at": "iemand bij {what}",
        "target.corner": "iemand in de vakjes rond {what}",
        "target.kind": "iemand op {what}",
        "cell_target.area": "een vakje {where}",
        "cell_target.on": "een vakje van {what}",
        "cell_target.at": "een vakje dat {what} raakt",
        "cell_target.corner": "een vakje rond {what}",
        "cell_target.kind": "een vakje van {what}",
        "target.people_on": "iemand op {what}",
        "target.people": "een van {people}",
        "target.anyone": "iedereen",
        "location.in_line": "in {line}",
        "area.name": "het gebied {name}",
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
    "rooms": "Give every person one room. Several people may share a room, a room may stay "
    "empty, and a room never holds more than its capacity; the clues name rooms by their "
    "properties and say who is together, apart, alone or where.",
}

# Which explanation (`cond.<key>` in PHRASES) covers each Murdoku clue kind.

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

        A rule line may end in `| wording`, like a clue. Keep that sentence with
        its rule so renderers can preserve the author's wording.
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
            key = name.strip()
            replacement = LEGACY_WORD_KEYS.get(key)
            if replacement is None and key.startswith("doc.clue_next_to_"):
                replacement = (
                    "predicate-specific keys such as doc.clue_beside_object, "
                    "doc.clue_touches_mark, or doc.clue_on_<target>"
                )
            if replacement is not None:
                raise ValueError(f"Words: key {key!r} is legacy; use {replacement}")
            if key in PHRASES[language]:
                phrases[key] = phrase.strip()
            else:
                words[key] = phrase.strip()
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

    def has(self, key: str) -> bool:
        """Whether this language has a phrase for `key`."""
        return key in self.phrases or key in PHRASES[self.language]

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
        ids = [region for region, label in self.board.region_names.items() if label == name]
        words = self.say.words.get(name) or next(
            (self.say.words[region] for region in ids if region in self.say.words), None
        )
        return words or self.say("region", name=name.replace("_", " "))

    def thing(self, name: str, *, as_label: bool = False) -> str:
        """Name a feature; a cell label names the kind, not one of its instances."""
        name = target_name(name)
        if as_label or name in self.board.mark_names:
            many = False
        elif name in self.board.edge_item_names:
            many = sum(item.name == name for item in self.board.edge_items) > 1
        elif name in self.board.point_object_names:
            many = sum(point.name == name for point in self.board.point_objects) > 1
        else:
            many = sum(obj.name == name for obj in self.board.objects) > 1
        return feature_name(
            name,
            many,
            self.say.words,
            lambda noun, indefinite: (
                self._indefinite(noun) if indefinite else self.say("the", name=noun)
            ),
        )

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

    def blockers(
        self, gone: set[Square], placed: dict[str, Square], *, max_people: int = 2
    ) -> list[str] | None:
        """Name announced row/column occupiers that cover every excluded square."""
        takers: dict[str, set[Square]] = {}
        order = {person: index for index, person in enumerate(placed)}
        for square in gone:
            for person, there in placed.items():
                if there.row == square.row or there.col == square.col:
                    takers.setdefault(person, set()).add(square)
        chosen: list[str] = []
        left = set(gone)
        while left:
            best = max(
                takers, key=lambda person: (len(takers[person] & left), order[person]), default=None
            )
            if best is None or not takers[best] & left:
                return None
            chosen.append(best)
            left -= takers[best]
        if len(chosen) > max_people:
            return None
        said = []
        for person in chosen:
            there = placed[person]
            covered = takers[person] & gone
            if all(square.row == there.row for square in covered):
                line = self.line("row", there.row)
            elif all(square.col == there.col for square in covered):
                line = self.line("col", there.col)
            else:
                line = self.say.join([self.line("row", there.row), self.line("col", there.col)])
            said.append(self.say("takes_line", who=person, line=line))
        return said

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
            what = self.say.words.get(name) or self.say(
                "global_count.mark", name=name.replace("_", " ")
            )
            areas.append((self.say("on", what=what), cells.__contains__))
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


def _cap(text: str) -> str:
    if text.startswith("**"):
        return "**" + _cap(text[2:])
    return text[:1].upper() + text[1:]


ARTICLES = frozenset({"the", "a", "an", "de", "het", "een"})
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
    """A player-facing paragraph with clue or rule source numbers and semantic owner."""

    text: str
    sources: tuple[int, ...]
    person: str | None
    rule_sources: tuple[int, ...] = ()

    @property
    def id(self) -> str:
        if self.rule_sources:
            return "rule:" + ",".join(map(str, self.rule_sources))
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


def figure_clues(
    text: str,
    *,
    expressions: Sequence[murdoku_lang.Statement] | None = None,
    expression_rules: Sequence[murdoku_lang.Statement] | None = None,
) -> CluePresentation:
    """Shared booklet/player entries for all puzzle-specific clues and rules."""
    if expressions is None or expression_rules is None:
        _, rules, clues = load_expression_board(text)
        expressions = clues if expressions is None else expressions
        expression_rules = rules if expression_rules is None else expression_rules
    return _expression_figure_clues(text, expressions, expression_rules)


def _expression_sentence(words: ExpressionWords, statement: murdoku_lang.Statement) -> str:
    sentence = _cap(words.statement(statement).strip())
    return sentence if sentence.endswith((".", "!", "?")) else sentence + "."


def _expression_figure_clues(
    text: str,
    clues: Sequence[murdoku_lang.Statement],
    rules: Sequence[murdoku_lang.Statement],
) -> CluePresentation:
    board = load_board_layout(text)
    presentation = load_presentation(text)
    say = ExpressionWords.read(board, text)
    by_person: dict[str, list[ClueParagraph]] = {person: [] for person in board.people}
    other: list[ClueParagraph] = []
    for number, clue in enumerate(clues, 1):
        formula = clue.formula
        while isinstance(formula, murdoku_lang.Negation):
            formula = formula.formula
        owner = _expression_clue_owner(formula, by_person)
        sentence = _expression_sentence(say, clue)
        paragraph = ClueParagraph(sentence, (number,), owner)
        (by_person[owner] if owner is not None else other).append(paragraph)
    wording = Wording.read(text)
    for person, paragraphs in by_person.items():
        if len(paragraphs) < 2:
            continue
        shown = _cap(say.names.get(person, person))
        predicates = []
        extra = []
        for paragraph in paragraphs:
            source = clues[paragraph.sources[0] - 1]
            if source.wording is not None or not paragraph.text.startswith(f"{shown} "):
                extra.append(paragraph.text)
                continue
            rest = paragraph.text[len(shown) + 1 :].rstrip(".")
            if rest.split(" ", 1)[0] == wording("and"):
                extra.append(paragraph.text)
            else:
                predicates.append(rest)
        parts = [f"{shown} {_merge_predicates(predicates, wording)}."] if predicates else []
        parts.extend(extra)
        by_person[person] = [
            ClueParagraph(
                " ".join(parts),
                tuple(number for paragraph in paragraphs for number in paragraph.sources),
                person,
            )
        ]
    for number, rule in enumerate(rules, 1):
        owner = _expression_rule_owner(rule.formula, board.people)
        paragraph = ClueParagraph(_expression_sentence(say, rule), (), owner, (number,))
        (by_person[owner] if owner is not None else other).append(paragraph)
    figures = tuple(
        FigureClues(
            person,
            _cap(say.names.get(person, person)),
            _figure_description(
                presentation.figures[person].description if person in presentation.figures else "",
                bool(by_person[person]),
            ),
            tuple(by_person[person]),
        )
        for person in board.people
    )
    return CluePresentation(figures, tuple(other))


def _figure_description(description: str, has_clues: bool) -> str:
    if not has_clues:
        return description
    return re.sub(
        r"(?:, )?(?:(?:with |has )?no clues of (?:their|his|her) own"
        r"|(?:zonder eigen|geen eigen) aanwijzingen)$",
        "",
        description,
    ).rstrip(", ")


def _expression_rule_owner(formula: murdoku_lang.Formula, people: Collection[str]) -> str | None:
    """Use a semantic subject, or the sole named figure anchoring a compound rule."""
    if isinstance(formula, murdoku_lang.Negation):
        return _expression_rule_owner(formula.formula, people)
    if owner := _expression_clue_owner(formula, people):
        return owner
    return _sole_named_person(formula, people)


def _sole_named_person(formula: murdoku_lang.Formula, people: Collection[str]) -> str | None:
    """The only figure named anywhere in a compound formula, if there is exactly one."""
    known = set(people)

    def named_people(value: object) -> set[str]:
        if isinstance(value, murdoku_lang.Name):
            return {value.token.text} & known
        if isinstance(value, tuple):
            return set().union(*(named_people(item) for item in value))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return set().union(
                *(named_people(getattr(value, item.name)) for item in dataclasses.fields(value))
            )
        return set()

    names = named_people(formula)
    return next(iter(names)) if len(names) == 1 else None


def _anchored_person(formula: murdoku_lang.Formula, people: Collection[str]) -> str | None:
    """The sole person anchoring a compound clue, in tiers: subject, projection, direction target.

    A bare mention such as the right side of `(people on object:chair) != Ada` is not
    an anchor: that clue compares an occupancy set with a person and stays global.
    """
    known = set(people)
    subjects: set[str] = set()
    projections: set[str] = set()
    direction_targets: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, (murdoku_lang.Atom, murdoku_lang.AdjectiveAtom)):
            if isinstance(value.subject, murdoku_lang.Name):
                name = value.subject.token.text
                if name in known:
                    subjects.add(name)
            if (
                isinstance(value, murdoku_lang.Atom)
                and value.operator.text.startswith("dir:")
                and isinstance(value.target, murdoku_lang.Name)
            ):
                name = value.target.token.text
                if name in known:
                    direction_targets.add(name)
        if isinstance(value, murdoku_lang.Projection) and isinstance(
            value.operand, murdoku_lang.Name
        ):
            name = value.operand.token.text
            if name in known:
                projections.add(name)
        if isinstance(value, tuple):
            for item in value:
                walk(item)
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for item in dataclasses.fields(value):
                walk(getattr(value, item.name))

    walk(formula)
    for names in (subjects, projections, direction_targets):
        if len(names) == 1:
            return next(iter(names))
        if len(names) > 1:
            return None
    return None


def _expression_clue_owner(formula: murdoku_lang.Formula, people: Collection[str]) -> str | None:
    if isinstance(formula, murdoku_lang.Negation):
        return _expression_clue_owner(formula.formula, people)
    if isinstance(formula, (murdoku_lang.Atom, murdoku_lang.AdjectiveAtom)) and isinstance(
        formula.subject, murdoku_lang.Name
    ):
        name = formula.subject.token.text
        if name in people:
            return name
    if person := alone_person(formula, people):
        return person.token.text
    if only := only_on(formula, people):
        return only[0].token.text
    return _anchored_person(formula, people)


def clue_paragraphs(
    text: str,
    overrides: dict[int, str] | None = None,
    *,
    expressions: Sequence[murdoku_lang.Statement] | None = None,
) -> list[str]:
    """The clues grouped per person, one paragraph each, in the order of the people.

    What a clue says about its first person is folded into that person's sentence;
    clues that are not about one person come last, one paragraph each.
    `overrides` replaces the generated wording of clue numbers.
    """
    if expressions is None:
        expressions = load_expression_board(text)[2]
    clues = [
        dataclasses.replace(clue, wording=overrides[number])
        if overrides is not None and number in overrides
        else clue
        for number, clue in enumerate(expressions, 1)
    ]
    entries = figure_clues(text, expressions=clues, expression_rules=())
    return [clue.text for figure in entries.figures for clue in figure.clues] + [
        clue.text for clue in entries.other
    ]


def clue_texts(text: str) -> list[str]:
    """The numbered clues of a Murdoku puzzle file in plain language."""
    board, _, statements = load_expression_board(text)
    words = ExpressionWords.read(board, text)
    return [_expression_sentence(words, clue) for clue in statements]


def global_count_statements(text: str) -> list[tuple[murdoku_lang.Statement, str]]:
    """Each count-bearing Murdoku statement and its player-facing sentence, in file order."""
    board, rules, statements = load_expression_board(text)
    words = ExpressionWords.read(board, text)

    def contains_count(value: object) -> bool:
        if isinstance(value, murdoku_lang.Count):
            return True
        if isinstance(value, tuple):
            return any(contains_count(item) for item in value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return any(
                contains_count(getattr(value, item.name)) for item in dataclasses.fields(value)
            )
        return False

    return [
        (statement, _expression_sentence(words, statement))
        for statement in (*rules, *statements)
        if contains_count(statement.formula)
    ]


def global_count_texts(text: str) -> list[str]:
    """Each global count of a Murdoku puzzle file as one plain sentence, in file order."""
    return [sentence for _, sentence in global_count_statements(text)]


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


def board_notes(
    text: str, *, expression_rules: Sequence[murdoku_lang.Statement] | None = None
) -> list[str]:
    """Plain sentences for what the board picture only abbreviates: area tags, marks, and
    board rules with author wording or global counts."""
    if expression_rules is None:
        expression_rules = load_expression_board(text)[1]
    board = load_board_layout(text)
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
    words = ExpressionWords.read(board, text)
    notes.extend(_expression_sentence(words, rule) for rule in expression_rules)
    return notes


def murdoku_key_items(text: str) -> list[tuple[str, str, str]]:
    """(target, label, name) for each symbol the rules do not otherwise name.

    Doors, windows and point objects are symbols whose meaning is not in the
    text; regions are labelled on the board, and marks, roles and attributes are
    stated in the rules or listed beside it.
    """
    board = load_board_layout(text)
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


def _expression_rule_notes(
    board: Board, statements: Sequence[murdoku_lang.Statement], say: Wording
) -> list[str]:
    notes: list[str] = []

    def target_names(value: object) -> set[str]:
        if isinstance(value, murdoku_lang.Name):
            return {value.token.text}
        if isinstance(value, tuple):
            return {name for item in value for name in target_names(item)}
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                name
                for item in dataclasses.fields(value)
                for name in target_names(getattr(value, item.name))
            }
        return set()

    def visit(value: object) -> None:
        if isinstance(value, (murdoku_lang.Atom, murdoku_lang.Filter)):
            operator = value.operator.text
            names = target_names(value.target)
            kinds = {name.partition(":")[0] for name in names}
            features = {name.rsplit(":", 1)[-1] for name in names} & board.edge_item_names
            if operator == "beside" and (
                "objects" in names or bool(kinds & {"object", "object_kind"})
            ):
                notes.append(say("doc.clue_beside_object"))
            if operator == "touches" and "mark" in kinds:
                notes.append(say("doc.clue_touches_mark"))
            if operator == "on":
                if "point_object" in kinds:
                    notes.append(say("doc.clue_on_point"))
                if "edge_item" in kinds:
                    edge_kinds = {board.edge_item_kind(name) for name in features}
                    if "door" in edge_kinds:
                        notes.append(say("doc.clue_on_door"))
                    if "window" in edge_kinds:
                        notes.append(say("doc.clue_on_window"))
            if operator.startswith("dir:"):
                modes = operator.split(":")[1:]
                if "manhattan" in modes:
                    notes.append(say("doc.clue_distance"))
                if "euclidean" in modes:
                    notes.append(say("doc.clue_euclidean_distance"))
                if "areas" in modes:
                    notes.append(say("doc.clue_neighboring_areas"))
        if isinstance(value, tuple):
            for item in value:
                visit(item)
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for item in dataclasses.fields(value):
                visit(getattr(value, item.name))

    for statement in statements:
        visit(statement.formula)
    return list(dict.fromkeys(notes))


def murdoku_rules(
    text: str,
    *,
    expression_rules: Sequence[murdoku_lang.Statement] | None = None,
    expression_clues: Sequence[murdoku_lang.Statement] = (),
) -> list[str]:
    """The rules a Murdoku player reads before starting, in the author's order.

    The `Intro:` paragraphs (or the standard rules when a file has none), what
    the board picture only abbreviates, the clue semantics the short clue text
    leaves implicit, and the note that a figure's story detail is not a clue.
    Puzzle-specific `Rules:` statements belong in `figure_clues`, not here.

    Preserve the intro and deduplicate matching semantic clarifications rather
    than repeating them as separate bullets.
    """
    if expression_rules is None:
        _, expression_rules, expression_clues = load_expression_board(text)
    presentation = load_presentation(text)
    board = load_board_layout(text)
    say = Wording.read(text)
    return _unique_player_rules(
        presentation.intro or [say("doc.rules")],
        [
            *board_notes(text, expression_rules=()),
            *_expression_rule_notes(board, [*expression_rules, *expression_clues], say),
            say("doc.murdoku_note"),
        ],
    )


def murdoku_reference_rules(
    text: str,
    *,
    expression_rules: Sequence[murdoku_lang.Statement] | None = None,
    expression_clues: Sequence[murdoku_lang.Statement] = (),
) -> list[str]:
    """The rules reference, excluding introductory paragraphs shown separately."""
    intro = set(load_presentation(text).intro)
    rules = murdoku_rules(
        text, expression_rules=expression_rules, expression_clues=expression_clues
    )
    return [rule for rule in rules if rule not in intro]


def _unique_player_rules(intro_items: list[str], notes: list[str]) -> list[str]:
    # An intro paragraph may already contain a board rule or mark note; do not
    # print that same sentence again as a separate bullet.
    kept = intro_items + [
        item for item in notes if not any(item in paragraph for paragraph in intro_items)
    ]
    return list(dict.fromkeys(kept))


def role_list(text: str) -> list[tuple[str, str]]:
    """(role name, plain description) for each role, for a list beside the board."""
    board = load_board_layout(text)
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
    board = load_board_layout(text)
    say = Wording.read(text)
    if any(line.startswith("name.attribute:") for line in read_sections(text).get("Words", [])):
        return []
    out = []
    for attribute, holders in board.attributes.items():
        people = [person for person in board.people if person in holders]
        name = say.words.get(attribute, attribute.replace("_", " "))
        out.append((name, say("doc.attribute", people=say.join(people))))
    return out


def object_kind(name: str) -> str:
    return name.lower().rstrip("0123456789").rstrip("_")


def object_position_text(say: Wording, name: str, standable: bool) -> str:
    if not standable:
        return say("doc.blocking")
    kind = object_kind(name)
    if kind in {"buitendouche", "douche", "shower"}:
        return say("doc.stand_under")
    if kind in {"bank", "terrasbank"}:
        return say("doc.sit_on")
    return say("doc.standable")


def object_list(text: str) -> list[tuple[str, str, bool]]:
    """(object type, name to show, standable) for each kind of object on the board.

    `boom1` and `boom2` are one type, `boom`; the type is what `icons.object_icon` finds.
    """
    board = load_board_layout(text)
    words = Wording.read(text).words
    out: dict[str, tuple[str, str, bool]] = {}
    for obj in board.objects:
        kind = object_kind(obj.name)
        said = words.get(obj.name) or words.get(kind)
        bare = re.sub(r"^(the|a|an|de|het|een) ", "", said) if said else ""
        # Keep the article before an adjective: "het zachte tapijt", not "zachte tapijt".
        label = (bare if " " not in bare else said) if said else kind.replace("_", " ")
        out.setdefault(kind, (kind, label[:1].upper() + label[1:], obj.kind == "standable"))
    return list(out.values())


def phrase(text: str, key: str) -> str:
    """A fixed phrase such as `doc.clues` in the puzzle's language."""
    return Wording.read(text)(key)


def presentation_reveal(text: str) -> str:
    return " ".join(load_presentation(text).reveal)


def explain(text: str, numbered: bool = True) -> str:
    """The worked solution of a Murdoku puzzle file, as Markdown bullets.

    Without `numbered` it never points at clue numbers, for clues that are not numbered.
    """
    # Import lazily: narrators share this module's phrasebook.
    from .murdoku_story import explain as expression_explain

    return expression_explain(text, numbered=numbered).markdown()
