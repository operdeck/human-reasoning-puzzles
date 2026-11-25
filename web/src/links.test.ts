// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";
import {
  check, cycleSegment, emptyState, History, place, restore, segmentConflict, setSegment,
  type Bundle, type Segment,
} from "./game";
import { PuzzleView } from "./view";

const HORIZONTAL = "r3c1-r3c7";
const VERTICAL = "r1c4-r5c4";
const SIDE = "r3c7-r5c7";

function segment(id: string, endpoints: Segment["endpoints"], target: Segment["target"],
  conflicts: string[] = []): Segment {
  return {
    id, endpoints, target, conflicts, hitWidth: 20, values: ["0", "1", "2"],
    drawings: {
      "1": '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="384"><path data-decks="1" d="M64 192H448"/></svg>',
      "2": '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="384"><path data-decks="2" d="M64 185H448M64 199H448"/></svg>',
    },
  };
}

function bundle(): Bundle {
  return {
    schema: 4, id: "generic-links", family: "not-a-hardcoded-family", title: "Linked nodes",
    size: [5, 7], grade: "single", deductive: true, static: "links.svg", license: "",
    language: "en", playable: true, placement: { blocked: [] }, givens: {},
    palette: [{ id: "1", label: "Single", symbol: "─" }, { id: "2", label: "Double", symbol: "═" }],
    solution: { [HORIZONTAL]: "2", [SIDE]: "1" },
    rules: [], clues: [], key: [], question: "",
    links: {
      nodes: [
        { id: "r3c1", total: 2 }, { id: "r3c7", total: 3 },
        { id: "r1c4", total: 2 }, { id: "r5c4", total: 2 }, { id: "r5c7", total: 1 },
      ],
      segments: [
        segment(HORIZONTAL, ["r3c1", "r3c7"], [64, 192, 448, 192], [VERTICAL]),
        segment(VERTICAL, ["r1c4", "r5c4"], [256, 64, 256, 320], [HORIZONTAL]),
        segment(SIDE, ["r3c7", "r5c7"], [448, 192, 448, 320]),
      ], connected: true,
    },
  };
}

describe("generic segments", () => {
  it("cycles absence, single and double, preserving other segments", () => {
    const b = bundle();
    let state = setSegment(b, emptyState(b), SIDE, "1");
    for (const value of ["1", "2", undefined]) {
      state = cycleSegment(b, state, HORIZONTAL);
      expect(state.placed[HORIZONTAL]).toBe(value);
      expect(state.placed[SIDE]).toBe("1");
    }
    expect(place(b, state, "r3c1", "2")).toBe(state);
    expect(setSegment(b, state, HORIZONTAL, "3")).toBe(state);
  });

  it("counts the replacement only once and reports crossings without a solution", () => {
    const b = { ...bundle(), solution: undefined };
    let state = setSegment(b, emptyState(b), HORIZONTAL, "2");
    state = setSegment(b, state, SIDE, "1");
    expect(segmentConflict(b, state, SIDE)).toBeNull();
    state = setSegment(b, state, HORIZONTAL, "1");
    expect(segmentConflict(b, state, HORIZONTAL)).toBeNull();
    state = setSegment(b, state, VERTICAL, "1");
    expect(segmentConflict(b, state, VERTICAL)).toEqual({ kind: "crossing", at: HORIZONTAL });
    state = setSegment(b, state, HORIZONTAL, "0");
    expect(segmentConflict(b, state, VERTICAL)).toBeNull();
    state = setSegment(b, state, SIDE, "2");
    expect(segmentConflict(b, state, SIDE)).toEqual({ kind: "total", at: "r5c7" });
  });

  it("restores only actual segments and supports clear, check, undo and redo", () => {
    const b = bundle();
    const saved = restore(b, {
      placed: { [HORIZONTAL]: "2", r3c1: "1", invented: "2", [VERTICAL]: "0" },
      crosses: [SIDE, SIDE, "r3c1"],
    });
    expect(saved.placed).toEqual({ [HORIZONTAL]: "2" });
    expect(saved.crosses).toEqual([SIDE]);
    const history = new History(saved);
    history.push(setSegment(b, saved, SIDE, "1"));
    expect(check(b, history.current)).toEqual({ status: "solved" });
    history.undo();
    expect(check(b, history.current)).toEqual({ status: "incomplete", missing: 1 });
    history.redo();
    history.push(emptyState(b));
    history.undo();
    expect(check(b, history.current)).toEqual({ status: "solved" });
  });
});

describe("segment player", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.replaceChildren();
  });

  function mount(data = bundle()): HTMLElement {
    const root = document.createElement("main");
    document.body.append(root);
    const cells = data.links!.nodes.map(({ id }) => {
      const [, row, col] = /^r(\d+)c(\d+)$/.exec(id)!;
      return `<rect class="cell" id="${id}" x="${Number(col) * 64 - 32}" y="${Number(row) * 64 - 32}" width="64" height="64"/>`;
    }).join("");
    const board = `<svg viewBox="0 0 512 384"><g class="cells">${cells}</g><g class="above"><text>2</text></g></svg>`;
    new PuzzleView(data, board).render(root);
    return root;
  }

  function click(root: HTMLElement, selector: string): void {
    root.querySelector(selector)!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  function button(root: HTMLElement, label: string): void {
    const target = [...root.querySelectorAll("button")].find((entry) => entry.textContent === label)!;
    target.click();
  }

  it("cycles a corridor, saves it, and draws the exported decks below numbers", () => {
    const root = mount();
    const target = `[data-segment="${HORIZONTAL}"]`;
    expect(Number(root.querySelector(target)?.getAttribute("width"))).toBeGreaterThan(0);
    expect(Number(root.querySelector(target)?.getAttribute("height"))).toBeGreaterThan(0);
    click(root, target);
    expect(root.querySelector("[data-decks='1']")).not.toBeNull();
    click(root, target);
    expect(root.querySelector("[data-decks='2']")).not.toBeNull();
    expect(JSON.parse(localStorage.getItem("hrp:v1:generic-links")!).placed[HORIZONTAL]).toBe("2");
    const svg = root.querySelector(".board svg")!;
    expect([...svg.children].findIndex((node) => node.classList.contains("overlay"))).toBeLessThan(
      [...svg.children].findIndex((node) => node.classList.contains("above")));
    click(root, target);
    expect(root.querySelector(".segment-piece")).toBeNull();
    button(root, "Undo");
    expect(root.querySelector("[data-decks='2']")).not.toBeNull();
  });

  it("selects two exported endpoints, never invents a diagonal, and highlights selection", () => {
    const root = mount();
    click(root, "#r3c1");
    expect(root.querySelector(".node-selected")).not.toBeNull();
    click(root, "#r5c4");
    expect(root.querySelector(".segment-piece")).toBeNull();
    click(root, "#r3c1");
    click(root, "#r3c7");
    expect(root.querySelector("[data-decks='1']")).not.toBeNull();
    button(root, "═Double");
    click(root, "#r3c1");
    click(root, "#r3c7");
    expect(root.querySelector("[data-decks='2']")).not.toBeNull();
  });

  it("supports keyboard counts and erase, hint, solution, check and clear", () => {
    const root = mount();
    const target = root.querySelector<SVGElement>(`[data-segment="${HORIZONTAL}"]`)!;
    target.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "2", bubbles: true }));
    expect(root.querySelector("[data-decks='2']")).not.toBeNull();
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true }));
    expect(root.querySelector(".segment-piece")).toBeNull();
    button(root, "Hint");
    expect(root.querySelector("[data-decks='2']")).not.toBeNull();
    button(root, "Show solution");
    button(root, "Check");
    expect(root.querySelector(".verdict")?.textContent).toContain("Solved!");
    button(root, "Clear");
    expect(root.querySelector(".segment-piece")).toBeNull();
    button(root, "Undo");
    expect(root.querySelectorAll(".segment-piece")).toHaveLength(2);
  });

  it("reports local crossings, not an oracle disagreement", () => {
    const root = mount();
    click(root, `[data-segment="${HORIZONTAL}"]`);
    click(root, `[data-segment="${VERTICAL}"]`);
    expect(root.querySelector(".verdict")?.textContent).toBe(`Connection crosses ${HORIZONTAL}.`);
  });

  it("gets keyboard counts from exported allowed values, not a puzzle-family rule", () => {
    const data = bundle();
    data.links!.segments[0].values.push("3");
    data.palette!.push({ id: "3", label: "Three", symbol: "3" });
    const root = mount(data);
    const target = root.querySelector<SVGElement>(`[data-segment="${HORIZONTAL}"]`)!;
    target.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "3", bubbles: true }));
    expect(JSON.parse(localStorage.getItem("hrp:v1:generic-links")!).placed[HORIZONTAL]).toBe("3");
    target.dispatchEvent(new KeyboardEvent("keydown", { key: "4", bubbles: true }));
    expect(JSON.parse(localStorage.getItem("hrp:v1:generic-links")!).placed[HORIZONTAL]).toBe("3");
  });
});
