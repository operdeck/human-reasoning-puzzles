import { describe, expect, it } from "vitest";
import { adjacentPuzzles, puzzleIdFromPath } from "./navigation";

const puzzles = [
  { id: "first", title: "First" },
  { id: "second", title: "Second" },
  { id: "third", title: "Third" },
];

describe("adjacentPuzzles", () => {
  it("returns neighbors in reading order", () => {
    expect(adjacentPuzzles(puzzles, "second")).toEqual({
      previous: puzzles[0],
      next: puzzles[2],
    });
  });

  it("omits the previous puzzle at the beginning and next puzzle at the end", () => {
    expect(adjacentPuzzles(puzzles, "first")).toEqual({ previous: undefined, next: puzzles[1] });
    expect(adjacentPuzzles(puzzles, "third")).toEqual({ previous: puzzles[1], next: undefined });
  });
});
describe("puzzleIdFromPath", () => {
  it("reads the id from a canonical puzzle path under the site root", () => {
    expect(puzzleIdFromPath("/human-reasoning-puzzles/p/first-case/", "/human-reasoning-puzzles/"))
      .toBe("first-case");
    expect(puzzleIdFromPath("/human-reasoning-puzzles/p/first-case", "/human-reasoning-puzzles"))
      .toBe("first-case");
    expect(puzzleIdFromPath("/p/a%20b/", "/")).toBe("a b");
  });

  it("ignores pages that are not a puzzle page", () => {
    expect(puzzleIdFromPath("/human-reasoning-puzzles/", "/human-reasoning-puzzles/"))
      .toBeUndefined();
    expect(puzzleIdFromPath("/human-reasoning-puzzles/murdoku/", "/human-reasoning-puzzles/"))
      .toBeUndefined();
    expect(puzzleIdFromPath("/human-reasoning-puzzles/p/", "/human-reasoning-puzzles/"))
      .toBeUndefined();
  });
});

