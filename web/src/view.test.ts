// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";
import { conflictText, footerParagraphs, mineCounter, PuzzleView, verdictText } from "./view";
import type { Bundle } from "./game";

describe("footerParagraphs", () => {
  it("credits Murdoku's inventor under a Murdoku board", () => {
    const paragraphs = footerParagraphs("All rights reserved.", "murdoku");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0].textContent).toContain("All rights reserved.");
    expect(paragraphs[0].querySelector("a")?.textContent).toBe("Licence");
    expect(paragraphs[1].className).toBe("credit");
    expect(paragraphs[1].querySelector("a")?.getAttribute("href")).toBe("https://murdoku.com");
  });

  it("keeps other families to the licence alone", () => {
    const paragraphs = footerParagraphs("All rights reserved.", "sudoku");
    expect(paragraphs).toHaveLength(1);
    expect(paragraphs[0].querySelector(".credit")).toBeNull();
  });
});

describe("conflictText", () => {
  it("identifies the conflicting cell and the exported rule", () => {
    expect(conflictText("1", "r1c1", "en", "anti-knight rule")).toBe(
      "1 conflicts with the same value at r1c1 (anti-knight rule).",
    );
    expect(conflictText("1", "r1c1", "nl", "anti-paardregel")).toBe(
      "1 botst met dezelfde waarde op r1c1 (anti-paardregel).",
    );
  });
});

describe("verdictText", () => {
  it("tells the puzzle's own story when solved", () => {
    expect(verdictText({ status: "solved" }, "nl", "Wouter doet het met Sanne.")).toBe(
      "Opgelost! Wouter doet het met Sanne.",
    );
    expect(verdictText({ status: "solved" }, "en", "")).toBe("Solved! Everything is in the right place.");
  });

  it("speaks the puzzle's language", () => {
    expect(verdictText({ status: "wrong", wrong: 1 }, "nl")).toBe("Nog niet goed: 1 stuk staat op de verkeerde plek.");
    expect(verdictText({ status: "wrong", wrong: 2 }, "en")).toBe("Not right: 2 pieces are in the wrong place.");
    expect(verdictText({ status: "incomplete", missing: 3 }, "nl")).toBe("Nog geen fouten; nog 3 te plaatsen.");
  });

  it("names the missing mine in English and Dutch", () => {
    const mine = { singular: "mine", plural: "mines" };
    const mijn = { singular: "mijn", plural: "mijnen" };
    expect(verdictText({ status: "incomplete", missing: 1 }, "en", undefined, mine)).toBe(
      "No mistakes so far; 1 mine still to place.",
    );
    expect(verdictText({ status: "incomplete", missing: 1 }, "nl", undefined, mijn)).toBe(
      "Nog geen fouten; nog 1 mijn te plaatsen.",
    );
    expect(verdictText({ status: "incomplete", missing: 2 }, "nl", undefined, mijn)).toBe(
      "Nog geen fouten; nog 2 mijnen te plaatsen.",
    );
  });
});

describe("palette", () => {
  const BOARD = `<svg viewBox="0 0 100 100"><g class="cells">
    <rect class="cell" id="r1c1" x="0" y="0" width="50" height="50"/>
    <rect class="cell" id="r1c2" x="50" y="0" width="50" height="50"/>
    <rect class="cell" id="r2c1" x="0" y="50" width="50" height="50"/>
    <rect class="cell" id="r2c2" x="50" y="50" width="50" height="50"/>
  </g></svg>`;

  function bundle(overrides: Partial<Bundle> = {}): Bundle {
    return {
      schema: 3,
      id: "crossed-people",
      family: "murdoku",
      title: "Two people",
      grade: "single",
      deductive: true,
      static: "two-people.svg",
      license: "",
      language: "en",
      size: [2, 2],
      playable: true,
      palette: [
        { id: "Ada", label: "Ada", symbol: "Ad" },
        { id: "Bo", label: "Bo", symbol: "Bo" },
      ],
      placement: { perItem: 1, blocked: [] },
      autoMark: { default: true, mark: "cross", onPlace: [{ scope: "row" }, { scope: "col" }] },
      givens: {},
      solution: { r1c1: "Ada", r2c2: "Bo" },
      rules: [],
      clues: [],
      key: [],
      question: "",
      ...overrides,
    };
  }

  function mount(overrides: Partial<Bundle> = {}): HTMLElement {
    const root = document.createElement("main");
    document.body.append(root);
    new PuzzleView(bundle(overrides), BOARD).render(root);
    return root;
  }

  function press(root: HTMLElement, key: string): void {
    const board = root.querySelector<HTMLElement>(".board");
    if (!board) throw new Error("no board");
    board.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  }

  beforeEach(() => {
    localStorage.clear();
    document.body.replaceChildren();
  });

  it("selects a clue card independently of its checkbox and restores saved progress", () => {
    const overrides: Partial<Bundle> = {
      clues: ["Bo's old clue"],
      clueEntries: [{ id: "clue:1", item: "Bo", text: "Bo is here.", sources: ["clue:1"] }],
      legacyClueSources: [["clue:1"]],
    };
    localStorage.setItem("hrp:v1:crossed-people", JSON.stringify({
      placed: { r1c1: "Ada" }, crosses: ["r1c2"], usedClues: [0],
    }));
    const root = mount(overrides);
    expect(root.querySelectorAll(".figure-entry")).toHaveLength(2);
    const cards = root.querySelectorAll<HTMLElement>(".figure-entry");
    expect(cards[0].querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c1");
    expect(cards[0].querySelector("input")).toBeNull();
    const checkbox = cards[1].querySelector<HTMLInputElement>("input")!;
    expect(checkbox.checked).toBe(true);
    checkbox.click();
    expect(root.querySelector('.palette [aria-checked="true"]')?.textContent).toContain("Ada");
    const button = cards[1].querySelector<HTMLButtonElement>(".entry-select")!;
    button.click();
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(checkbox.checked).toBe(false);
    press(root, "ArrowRight");
    press(root, "ArrowRight");
    press(root, "Enter");
    expect(cards[1].querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c2");
    const again = mount(overrides);
    expect(again.querySelectorAll<HTMLInputElement>(".entry-clues input")[0].checked).toBe(false);
    expect(again.querySelectorAll(".placement-status")[1].textContent).toBe("✓ Placed: r1c2");
  });

  it("uses shared checked sources for multiple references and keeps loose clues separate", () => {
    const root = mount({
      clueEntries: [
        { id: "a", item: "Ada", text: "Ada and Bo.", sources: ["clue:1"] },
        { id: "b", text: "Another reference.", sources: ["clue:1"] },
      ],
      headings: { other_clues: "Overige aanwijzingen" },
    });
    const boxes = root.querySelectorAll<HTMLInputElement>(".entry-clues input");
    boxes[0].click();
    expect(boxes[1].checked).toBe(true);
    expect(root.querySelector(".figure-entries h3")?.textContent).toBe("Overige aanwijzingen");
    expect(root.querySelector('.panel-section[data-tab="rules"]')?.textContent).not.toContain("The figures");
  });

  it("moves focus between clue and rule tabs with the keyboard", () => {
    const root = mount({ clueEntries: [] });
    const tabs = root.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    expect(tabs[0].tabIndex).toBe(0);
    tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(document.activeElement).toBe(tabs[1]);
    expect(tabs[1].getAttribute("aria-selected")).toBe("true");
    expect(tabs[0].tabIndex).toBe(-1);
    expect(root.querySelector(`#${tabs[1].getAttribute("aria-controls")}`)?.getAttribute("role")).toBe("tabpanel");
    tabs[1].dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("crosses the person that is on the board", () => {
    const root = mount();
    expect(root.querySelectorAll(".tool.used")).toHaveLength(0);
    press(root, "ArrowRight");
    press(root, "Enter");
    const used = [...root.querySelectorAll(".palette .tool.used")];
    expect(used).toHaveLength(1);
    expect(used[0].textContent).toContain("Ada");
    expect(used[0].querySelectorAll(".used-cross line")).toHaveLength(2);
  });

  it("crosses a person already placed as a given", () => {
    const root = mount({ givens: { r1c1: "Bo" } });
    const used = [...root.querySelectorAll(".palette .tool.used")];
    expect(used).toHaveLength(1);
    expect(used[0].textContent).toContain("Bo");
  });

  it("draws the symbols supplied with the board key", () => {
    const root = mount({
      key: [{ name: "Point", text: "fountain", svg: '<svg viewBox="0 0 1 1"><circle r="1"/></svg>' }],
    });
    const key = root.querySelector('.panel-section[data-tab="key"]');
    expect(key?.querySelector("dt .icon svg circle")).not.toBeNull();
    expect(key?.textContent).toContain("fountain");
  });

  it("drops the cross when auto-mark is switched off", () => {
    const root = mount();
    press(root, "ArrowRight");
    press(root, "Enter");
    const auto = root.querySelector<HTMLInputElement>(".assist-controls .auto input");
    if (!auto) throw new Error("no auto-mark switch");
    auto.checked = false;
    auto.dispatchEvent(new Event("change"));
    expect(root.querySelectorAll(".tool.used")).toHaveLength(0);
    expect(auto.checked).toBe(false);
  });

  it("never crosses an item the board may hold more than once", () => {
    const root = mount({ placement: { perCell: 1, blocked: [] } });
    press(root, "ArrowRight");
    press(root, "Enter");
    expect(root.querySelectorAll(".tool.used")).toHaveLength(0);
  });
});

describe("mineCounter", () => {
  it("counts placed mines, ignores crosses, and flags an over-total count", () => {
    const bundle = { language: "en", totals: { mine: 2 } };
    expect(mineCounter(bundle, { placed: { r1c1: "mine" } })).toEqual({
      text: "Mines: 1 / 2",
      overLimit: false,
    });
    expect(mineCounter(bundle, { placed: { r1c1: "mine", r1c2: "mine" } })).toEqual({
      text: "Mines: 2 / 2",
      overLimit: false,
    });
    expect(mineCounter(bundle, { placed: { r1c1: "mine", r1c2: "mine", r1c3: "mine" } })).toEqual({
      text: "Mines: 3 / 2",
      overLimit: true,
    });
    expect(mineCounter({ language: "nl", totals: { mine: 1 } }, { placed: {} })).toEqual({
      text: "Mijnen: 0 / 1",
      overLimit: false,
    });
    expect(mineCounter({ language: "en" }, { placed: {} })).toBeNull();
  });
});
