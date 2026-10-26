import { describe, expect, it } from "vitest";
import { adjacentPuzzles } from "./navigation";

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
