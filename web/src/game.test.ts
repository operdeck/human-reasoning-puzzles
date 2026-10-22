import { describe, expect, it } from "vitest";
import {
  autoMarks,
  check,
  clearCell,
  emptyState,
  History,
  place,
  restore,
  scopeCells,
  setCross,
  struckNotes,
  toggleNote,
  type Bundle,
} from "./game";

function murdoku(): Bundle {
  return {
    schema: 1,
    id: "murdoku_intro",
    family: "murdoku",
    title: "Murdoku 0",
    grade: "single",
    static: "murdoku_intro.svg",
    license: "",
    language: "en",
    size: [4, 4],
    playable: true,
    palette: [
      { id: "Ingrid", label: "Ingrid", symbol: "In" },
      { id: "Joost", label: "Joost", symbol: "Jo" },
    ],
    placement: { perItem: 1, blocked: ["r1c2", "r1c3", "r2c4", "r4c4"] },
    autoMark: { default: true, mark: "cross", onPlace: [{ scope: "row" }, { scope: "col" }] },
    givens: {},
    solution: { r1c1: "Joost", r3c4: "Ingrid" },
    rules: [],
    clues: ["a", "b"],
    conditions: [],
    question: "",
  };
}

function stars(): Bundle {
  return {
    ...murdoku(),
    family: "starbattle",
    palette: [{ id: "star", label: "Star", symbol: "*" }],
    placement: { perCell: 1, blocked: [] },
    autoMark: {
      default: true,
      mark: "cross",
      onPlace: [{ scope: "neighbors8" }, { scope: "row", whenFull: 2 }],
    },
    solution: {},
  };
}

describe("scopes", () => {
  it("finds rows, columns and neighbours inside the board", () => {
    const b = murdoku();
    expect(scopeCells(b, "row", "r2c2")).toEqual(["r2c1", "r2c3", "r2c4"]);
    expect(scopeCells(b, "col", "r1c1")).toEqual(["r2c1", "r3c1", "r4c1"]);
    expect(scopeCells(b, "neighbors8", "r1c1").sort()).toEqual(["r1c2", "r2c1", "r2c2"]);
    expect(scopeCells(b, "knight", "r1c1").sort()).toEqual(["r2c3", "r3c2"]);
  });

  it("uses the bundle's regions", () => {
    const b = { ...murdoku(), regions: { r1c1: "a", r1c2: "a", r2c1: "b" } };
    expect(scopeCells(b, "region", "r1c1")).toEqual(["r1c2"]);
  });
});

describe("auto marks", () => {
  it("are derived from placements, so removing a piece removes its crosses", () => {
    const b = murdoku();
    let state = place(b, emptyState(b), "r1c1", "Joost");
    expect(autoMarks(b, state)).toEqual(new Set(["r1c4", "r2c1", "r3c1", "r4c1"]));
    state = place(b, state, "r1c1", "Joost");
    expect(autoMarks(b, state).size).toBe(0);
  });

  it("are off when switched off", () => {
    const b = murdoku();
    const state = { ...place(b, emptyState(b), "r1c1", "Joost"), auto: false };
    expect(autoMarks(b, state).size).toBe(0);
  });

  it("mark a full line only once it holds its count", () => {
    const b = stars();
    let state = place(b, emptyState(b), "r1c1", "star");
    expect(autoMarks(b, state).has("r1c4")).toBe(false);
    state = place(b, state, "r1c3", "star");
    expect(autoMarks(b, state).has("r1c4")).toBe(true);
  });
});

describe("placing", () => {
  it("moves a piece that may appear once", () => {
    const b = murdoku();
    let state = place(b, emptyState(b), "r1c1", "Joost");
    state = place(b, state, "r3c1", "Joost");
    expect(state.placed).toEqual({ r3c1: "Joost" });
  });

  it("never touches blocked cells", () => {
    const b = murdoku();
    const state = emptyState(b);
    expect(place(b, state, "r1c2", "Joost")).toBe(state);
    expect(setCross(b, state, "r1c2")).toBe(state);
  });

  it("keeps manual crosses apart from auto marks", () => {
    const b = murdoku();
    let state = setCross(b, emptyState(b), "r1c4");
    state = place(b, state, "r1c1", "Joost");
    state = place(b, state, "r1c1", "Joost");
    expect(state.crosses).toEqual(["r1c4"]);
  });
});

describe("check", () => {
  it("tells solved, incomplete and wrong apart", () => {
    const b = murdoku();
    let state = place(b, emptyState(b), "r1c1", "Joost");
    expect(check(b, state)).toEqual({ status: "incomplete", missing: 1 });
    state = place(b, state, "r3c1", "Ingrid");
    expect(check(b, state)).toEqual({ status: "wrong", wrong: 1 });
    state = place(b, state, "r3c4", "Ingrid");
    expect(check(b, state)).toEqual({ status: "solved" });
  });
});

describe("history and storage", () => {
  it("undoes and redoes", () => {
    const b = murdoku();
    const history = new History(emptyState(b));
    history.push(place(b, history.current, "r1c1", "Joost"));
    expect(history.undo()).toBe(true);
    expect(history.current.placed).toEqual({});
    expect(history.redo()).toBe(true);
    expect(history.current.placed).toEqual({ r1c1: "Joost" });
  });

  it("drops saved moves that no longer fit the puzzle", () => {
    const b = murdoku();
    const state = restore(b, {
      placed: { r1c1: "Joost", r1c2: "Ingrid", r9c9: "Joost", r2c2: "Nobody" },
      crosses: ["r1c1", "r2c2", "r1c3"],
      usedClues: [0, 5],
      auto: false,
    });
    expect(state).toEqual({
      placed: { r1c1: "Joost" },
      crosses: ["r2c2"],
      notes: {},
      usedClues: [0],
      auto: false,
    });
  });
});

function digits(): Bundle {
  return {
    ...murdoku(),
    family: "sudoku",
    palette: ["1", "2", "3", "4"].map((d) => ({ id: d, label: d, symbol: d })),
    placement: { perCell: 1, blocked: [] },
    autoMark: { default: true, mark: "cross", onPlace: [] },
    givens: { r1c1: "1" },
    solution: { r1c2: "2" },
    notes: true,
    peers: [
      { cells: ["r1c1", "r1c2", "r1c3", "r1c4"] },
      { cells: ["r1c1", "r2c2"], items: ["3"] },
    ],
  };
}

describe("pencil marks", () => {
  it("toggle in palette order and only on free cells", () => {
    const b = digits();
    let state = toggleNote(b, emptyState(b), "r1c2", "3");
    state = toggleNote(b, state, "r1c2", "2");
    expect(state.notes).toEqual({ r1c2: ["2", "3"] });
    state = toggleNote(b, state, "r1c2", "2");
    state = toggleNote(b, state, "r1c2", "3");
    expect(state.notes).toEqual({});
    expect(toggleNote(b, state, "r1c1", "2")).toBe(state);
  });

  it("are struck by a peer holding the same digit, and come back when it goes", () => {
    const b = digits();
    let state = toggleNote(b, emptyState(b), "r1c3", "1");
    state = toggleNote(b, state, "r1c3", "2");
    state = toggleNote(b, state, "r2c2", "3");
    expect(struckNotes(b, state)).toEqual(new Map([["r1c3", new Set(["1"])]]));
    state = place(b, state, "r1c1", "3");
    expect(struckNotes(b, state).get("r2c2")).toBeUndefined();
    state = place(b, state, "r1c4", "2");
    expect(struckNotes(b, state).get("r1c3")).toEqual(new Set(["1", "2"]));
    state = place(b, state, "r1c4", "2");
    expect(struckNotes(b, state).get("r1c3")).toEqual(new Set(["1"]));
    expect(struckNotes(b, { ...state, auto: false }).size).toBe(0);
  });

  it("only strike a digit its peer group covers", () => {
    const b = { ...digits(), givens: {} };
    let state = toggleNote(b, emptyState(b), "r2c2", "3");
    state = toggleNote(b, state, "r2c2", "4");
    state = place(b, state, "r1c1", "4");
    expect(struckNotes(b, state).size).toBe(0);
    state = place(b, state, "r1c1", "3");
    expect(struckNotes(b, state).get("r2c2")).toEqual(new Set(["3"]));
  });

  it("are cleared with the cell and survive storage", () => {
    const b = digits();
    const state = toggleNote(b, emptyState(b), "r1c3", "4");
    expect(clearCell(b, state, "r1c3").notes).toEqual({});
    const saved = JSON.parse(JSON.stringify({ ...state, notes: { ...state.notes, r1c1: ["2"], r1c4: ["9", "2"] } }));
    expect(restore(b, saved).notes).toEqual({ r1c3: ["4"], r1c4: ["2"] });
  });
});

describe("peer light", () => {
  it("lights the cells a bulb sees", () => {
    const b: Bundle = {
      ...murdoku(),
      family: "akari",
      palette: [{ id: "bulb", label: "Light", symbol: "o" }],
      placement: { perCell: 1, blocked: ["r1c3"] },
      autoMark: { default: true, mark: "light", onPlace: [{ scope: "peers" }] },
      peers: [{ cells: ["r1c1", "r1c2"] }, { cells: ["r1c1", "r2c1", "r3c1"] }],
    };
    const state = place(b, emptyState(b), "r1c1", "bulb");
    expect(autoMarks(b, state)).toEqual(new Set(["r1c2", "r2c1", "r3c1"]));
  });
});

describe("restore", () => {
  it("survives storage it did not write", () => {
    const b = digits();
    for (const saved of [
      { placed: "r1c2", crosses: "r1c3", usedClues: 3, notes: [] },
      { placed: { r1c2: 7, r1c3: "2" }, crosses: ["r1c4", "r1c4", 5], notes: { r1c2: "2" } },
      null,
      42,
    ]) {
      const state = restore(b, saved);
      expect(Array.isArray(state.crosses)).toBe(true);
      expect(Array.isArray(state.usedClues)).toBe(true);
    }
    expect(restore(b, { placed: { r1c2: 7, r1c3: "2" }, crosses: ["r1c4", "r1c4", 5] })).toMatchObject({
      placed: { r1c3: "2" },
      crosses: ["r1c4"],
    });
  });
});
