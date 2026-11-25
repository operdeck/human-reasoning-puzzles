// Player-facing names for the solver's internal deduction grades.
//
// `index.json` keeps the ladder's own rule names (`core.DEFAULT_RULES`) so the
// export, the solver and tooling stay stable; the index and the prerendered
// pages translate them here. The order is the solver's ladder order, cheapest
// first, and a new rung needs an entry here or it falls back to its raw name.
//
// This file is plain ESM so `scripts/prerender.mjs` can share it with the app
// without a dependency or a build step.

/**
 * @typedef {{ grade: string, label: string, meaning: string }} Grade
 */

/** @type {readonly Grade[]} */
export const GRADES = Object.freeze([
  {
    grade: "single",
    label: "Forced moves",
    meaning:
      "A choice is forced because only one option is left, or because a required total leaves only one possible count.",
  },
  {
    grade: "count",
    label: "Count deductions",
    meaning:
      "Deductions from how many items are required: which totals are allowed, their bounds, and the capacity that groups share.",
  },
  {
    grade: "reach",
    label: "Reachability",
    meaning:
      "An option cannot belong to the connected network when it cannot reach the required nodes; present edges require both endpoints.",
  },
  {
    grade: "cut",
    label: "Connectivity cuts",
    meaning:
      "An edge or node is forced because every possible connection between required nodes passes through it.",
  },
  {
    grade: "relations",
    label: "Relationship checks",
    meaning:
      "An option is removed when it cannot satisfy a clue or relation with the other variables involved.",
  },
  {
    grade: "subsumption",
    label: "Constraint overlap",
    meaning:
      "One constraint's remaining options use up another constraint's available capacity, ruling out that constraint's other options.",
  },
  {
    grade: "cover2",
    label: "Two-set pattern",
    meaning:
      "Two separate required choices together use up another constraint's remaining capacity.",
  },
  {
    grade: "cover3",
    label: "Three-set pattern",
    meaning:
      "Three separate required choices together use up another constraint's remaining capacity.",
  },
  {
    grade: "chains",
    label: "Reasoning chains",
    meaning:
      "Following a chain of alternating implications and exclusions rules an option out.",
  },
  {
    grade: "wing",
    label: "Three-option pattern",
    meaning:
      "A three-option pivot and two two-option helpers force their shared value into one of them, so an option excluded alongside all three is impossible.",
  },
  {
    grade: "closure",
    label: "Component closure",
    meaning:
      "An edge-related choice is ruled out when its local consequences close off a required component from the rest of the network.",
  },
  {
    grade: "what_if",
    label: "Case analysis",
    meaning:
      "The solver tries an option and follows only the cheaper rules; if that reaches a contradiction, the option is impossible.",
  },
]);

/** The paragraph above the glossary, true for every grade above. */
export const GLOSSARY_INTRO =
  "A puzzle's label names the hardest deduction this solver needed to finish it. " +
  "The solver always tries the cheaper rules first, so the label is the most demanding step it could not avoid. " +
  "It measures this solver's reasoning, not how difficult a person will find the puzzle.";

/** The glossary's note about the `what_if` frontier badge. */
export const BEYOND_DEDUCTION_NOTE =
  "The \u201cbeyond deduction\u201d badge marks a puzzle labelled Case analysis: " +
  "only this solver's trial of a guess closes it, so it sits at the edge of what pure deduction can prove.";

/**
 * Whether the index's internal grade has a player-facing label.
 * @param {string} grade
 * @returns {boolean}
 */
export function isKnownGrade(grade) {
  return GRADES.some((entry) => entry.grade === grade);
}

/**
 * The player-facing label for an internal grade, or the grade itself when this
 * app does not know it yet, so an unfamiliar value stays visible.
 * @param {string} grade
 * @returns {string}
 */
export function gradeLabel(grade) {
  return GRADES.find((entry) => entry.grade === grade)?.label ?? grade;
}
