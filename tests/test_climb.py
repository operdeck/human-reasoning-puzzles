import random

import pytest

from csp import climb, fresh
from csp.bruteforce import rectangles as brute

pytestmark = pytest.mark.solutions


def test_rectangles_hard_search_reaches_a_hard_grade_on_a_unique_board():
    """One slow search (about a minute): seed 4000 on 9x9 lands on a `cover3` board."""
    text = fresh.fresh("rectangles", 9, random.Random(4000), 1.0, tier="hard")

    assert text is not None
    assert len(brute.solutions(text, limit=2)) == 1
    assert climb.grade(text) in fresh.TIER_GRADES["hard"]


def test_grade_is_none_for_a_board_the_ladder_cannot_close():
    # Two 2x2-less tilings fit this board (dominoes across or down), so there is no answer to find.
    ambiguous = "Family: rectangles\nClues:\n2 .\n. 2\n"
    assert len(brute.solutions(ambiguous, limit=3)) == 2
    assert climb.grade(ambiguous) is None
