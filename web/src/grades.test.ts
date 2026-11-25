import { describe, expect, it } from "vitest";

import {
  BEYOND_DEDUCTION_NOTE,
  GLOSSARY_INTRO,
  GRADES,
  gradeLabel,
  isKnownGrade,
} from "./grades.mjs";

// The solver's ladder (`core.DEFAULT_RULES`), cheapest first. The export keeps
// these internal names; only the display changes.
const LADDER = [
  "single",
  "count",
  "reach",
  "cut",
  "relations",
  "subsumption",
  "cover2",
  "cover3",
  "chains",
  "wing",
  "closure",
  "what_if",
];

describe("grade labels", () => {
  it("covers the solver's ladder in its own order", () => {
    expect(GRADES.map((entry) => entry.grade)).toEqual(LADDER);
  });

  it("turns each internal rule name into a player-facing label", () => {
    expect(gradeLabel("single")).toBe("Forced moves");
    expect(gradeLabel("relations")).toBe("Relationship checks");
    expect(gradeLabel("reach")).toBe("Reachability");
    expect(gradeLabel("cut")).toBe("Connectivity cuts");
    expect(gradeLabel("closure")).toBe("Component closure");
    expect(gradeLabel("what_if")).toBe("Case analysis");
    expect(GRADES.every((entry) => isKnownGrade(entry.grade))).toBe(true);
  });

  it("uses one readable label per grade and no internal names", () => {
    const labels = GRADES.map((entry) => entry.label);
    expect(new Set(labels).size).toBe(labels.length);
    for (const entry of GRADES) {
      expect(entry.label).toMatch(/^[A-Z][a-z]+(?:[- ][a-z]+)*$/);
      expect(entry.label).not.toContain("_");
    }
  });

  it("defines every label in a plain sentence", () => {
    for (const entry of GRADES) {
      expect(entry.meaning.length).toBeGreaterThan(40);
      expect(entry.meaning.endsWith(".")).toBe(true);
    }
  });

  it("keeps an unknown grade visible instead of blanking it", () => {
    expect(isKnownGrade("mystery")).toBe(false);
    expect(gradeLabel("mystery")).toBe("mystery");
  });

  it("says the grades measure this solver, not human difficulty", () => {
    expect(GLOSSARY_INTRO).toContain("hardest deduction this solver needed");
    expect(GLOSSARY_INTRO).toContain("not how difficult a person will find");
  });

  it("explains the beyond-deduction badge as case analysis", () => {
    expect(BEYOND_DEDUCTION_NOTE).toContain("beyond deduction");
    expect(BEYOND_DEDUCTION_NOTE).toContain("Case analysis");
  });
});
