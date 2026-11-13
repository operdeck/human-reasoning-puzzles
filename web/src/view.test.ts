// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
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

  it("switches compact viewports on resize without losing moves and releases the listener", () => {
    const listeners = new Set<() => void>();
    let mobile = true;
    const media = window.matchMedia("(max-width: 760px)");
    Object.defineProperty(media, "matches", { get: () => mobile });
    vi.spyOn(media, "addEventListener").mockImplementation((_event, listener) => {
      if (typeof listener === "function") listeners.add(() => listener.call(media, new Event("change")));
    });
    vi.spyOn(media, "removeEventListener").mockImplementation(() => listeners.clear());
    const matchMedia = vi.spyOn(window, "matchMedia").mockReturnValue(media);
    const board = BOARD.replace('viewBox="0 0 100 100"', 'viewBox="-20 -40 140 180" data-compact-view-box="0 0 100 100"');
    const root = document.createElement("main");
    document.body.append(root);
    const view = new PuzzleView(bundle(), board);
    try {
      view.render(root);
      const svg = root.querySelector(".board svg")!;
      expect(svg.getAttribute("viewBox")).toBe("0 0 100 100");
      expect(root.querySelector(".board")?.classList.contains("compact-board")).toBe(true);
      press(root, "ArrowRight");
      press(root, "Enter");
      expect(root.querySelector(".overlay")?.childElementCount).toBeGreaterThan(0);
      const moves = root.querySelector(".overlay")!.innerHTML;
      mobile = false;
      listeners.forEach((listener) => listener());
      expect(svg.getAttribute("viewBox")).toBe("-20 -40 140 180");
      expect(root.querySelector(".board")?.classList.contains("compact-board")).toBe(false);
      expect(root.querySelector(".overlay")!.innerHTML).toBe(moves);
      mobile = true;
      listeners.forEach((listener) => listener());
      expect(svg.getAttribute("viewBox")).toBe("0 0 100 100");
      view.destroy();
      expect(listeners.size).toBe(0);
    } finally {
      view.destroy();
      matchMedia.mockRestore();
    }
  });

  it("selects figures from their clue cards, which replace the palette's figure buttons", () => {
    const overrides: Partial<Bundle> = {
      clues: ["Bo's old clue"],
      clueEntries: [{ id: "clue:1", item: "Bo", text: "Bo is here.", sources: ["clue:1"] }],
    };
    localStorage.setItem("hrp:v1:crossed-people", JSON.stringify({
      placed: { r1c1: "Ada" }, crosses: ["r1c2"], usedClues: [0],
    }));
    const root = mount(overrides);
    const cards = root.querySelectorAll<HTMLElement>(".figure-entry");
    expect(cards).toHaveLength(2);
    expect(root.querySelectorAll(".panel input")).toHaveLength(0);
    expect([...root.querySelectorAll(".palette .tool")].map((tool) => tool.textContent)).toEqual(["✕Cross"]);
    expect([...root.querySelectorAll(".controls button")].map((button) => button.textContent))
      .toEqual(["✕Cross", "Undo", "Redo", "Clear", "Check"]);
    expect(cards[0].querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c1");
    expect(cards[0].querySelector(".entry-select")?.classList.contains("used")).toBe(true);
    expect(cards[0].querySelectorAll(".used-cross line")).toHaveLength(2);
    const button = cards[1].querySelector<HTMLButtonElement>(".entry-select")!;
    button.click();
    expect(button.getAttribute("aria-pressed")).toBe("true");
    press(root, "ArrowRight");
    press(root, "ArrowRight");
    press(root, "Enter");
    expect(cards[1].querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c2");
    expect(button.classList.contains("used")).toBe(true);
    const again = mount(overrides);
    expect(again.querySelectorAll(".placement-status")[1].textContent).toBe("✓ Placed: r1c2");
  });

  it("shows a cross beside an iconless figure's name when auto-marked", () => {
    const root = mount({
      clueEntries: [],
      palette: [
        { id: "Ada", label: "Ada", symbol: "Ad" },
        { id: "Bo", label: "Bo", symbol: "Bo", svg: '<svg viewBox="0 0 1 1"><circle r="1"/></svg>' },
      ],
    });
    const cards = root.querySelectorAll<HTMLElement>(".figure-entry");
    const iconless = cards[0].querySelector<HTMLElement>(".entry-select")!;
    expect(iconless.querySelector(".entry-portrait")).toBeNull();
    expect(iconless.querySelector(".entry-label")?.textContent).toBe("Ada");
    expect(iconless.querySelector(".placement-status")?.textContent).toBe("Not placed yet");
    expect(iconless.querySelectorAll(".entry-mark .used-cross line")).toHaveLength(2);
    expect(iconless.classList.contains("used")).toBe(false);
    expect(cards[1].querySelector(".entry-portrait svg circle")).not.toBeNull();

    press(root, "ArrowRight");
    press(root, "Enter");
    expect(iconless.classList.contains("used")).toBe(true);
    expect(iconless.querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c1");
    const auto = root.querySelector<HTMLInputElement>(".assist-controls .auto input")!;
    auto.checked = false;
    auto.dispatchEvent(new Event("change"));
    expect(iconless.classList.contains("used")).toBe(false);
    expect(iconless.querySelector(".placement-status")?.textContent).toBe("✓ Placed: r1c1");
  });

  it("bolds complete character references throughout the puzzle prose without interpreting HTML", () => {
    const sentence = "Anna meets Ann, Dr. Éva and de leeuw; Ann's note mentions Annabelle and Annélise. <em>Ann</em>";
    const root = mount({
      textNames: ["Ann", "Anna", "Dr. Éva", "de leeuw"],
      clueEntries: [
        { id: "ada", item: "Ada", text: sentence, sources: ["clue:1"] },
        { id: "loose", text: "Ann watches Anna.", sources: ["clue:2"] },
      ],
      rules: ["Anna waits for Ann."],
      question: "Where is Dr. Éva?",
      attributes: [{ name: "Guide", text: "Ann and Anna" }],
      palette: [
        { id: "Ada", label: "Ada", symbol: "Ad", description: "Ann knows Anna." },
        { id: "Bo", label: "Bo", symbol: "Bo" },
      ],
    });
    const clue = root.querySelector(".entry-clues li")!;
    expect(clue.textContent).toBe(sentence);
    expect([...clue.querySelectorAll("strong")].map((node) => node.textContent)).toEqual([
      "Anna", "Ann", "Dr. Éva", "de leeuw", "Ann", "Ann",
    ]);
    expect(clue.querySelector("em")).toBeNull();
    expect(root.querySelector(".entry-description strong")?.textContent).toBe("Ann");
    expect(root.querySelectorAll(".figure-entries > .entry-clues strong")).toHaveLength(2);
    expect(root.querySelectorAll("#section-rules li strong")).toHaveLength(2);
    expect(root.querySelector(".question p strong")?.textContent).toBe("Dr. Éva");
    expect(root.querySelectorAll("dd strong")).toHaveLength(2);
  });

  it("leaves prose without exported character names unchanged", () => {
    const root = mount({
      clueEntries: [{ id: "ada", item: "Ada", text: "Ada meets Bo.", sources: ["clue:1"] }],
    });
    expect(root.querySelector(".entry-clues strong")).toBeNull();
    expect(root.querySelector(".entry-clues")?.textContent).toBe("Ada meets Bo.");
  });

  it("shows cell details on hover, including blocked and empty marked cells", () => {
    const root = mount({
      placement: { perItem: 1, blocked: ["r1c1"] },
      cellDetails: {
        r1c1: ["Gebied: Tuin", "Voorwerp: de boom (hier kan niemand staan)"],
        r1c2: [
          "Gebied: Atelier",
          "Wie daar staat, is alleen in zijn gebied.",
          "Precies twee mensen dragen een badjas.",
        ],
      },
      headings: { cell: "Vakje", cell_figure: "Figuur" },
    });
    const tooltip = root.querySelector<HTMLElement>(".cell-tooltip")!;
    const tree = root.querySelector<SVGRectElement>("#r1c1")!;
    tree.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true, pointerType: "mouse", clientX: 10, clientY: 10,
    }));
    expect(tooltip.hidden).toBe(false);
    expect(tooltip.textContent).toContain("Vakje: r1c1");
    expect(tooltip.textContent).toContain("Voorwerp: de boom");
    expect(tooltip.textContent).not.toContain("Ada");
    expect(tree.getAttribute("aria-label")).toContain("Gebied: Tuin");

    root.querySelector<SVGRectElement>("#r1c2")!.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true, pointerType: "mouse", clientX: 60, clientY: 10,
    }));
    expect(tooltip.textContent).toContain("Wie daar staat, is alleen");
    expect(tooltip.textContent).toContain("Precies twee mensen dragen een badjas.");
    expect(root.querySelector("#r1c2")?.getAttribute("aria-label")).toContain("Precies twee mensen");
    expect(tooltip.textContent).not.toContain("de boom");
    root.querySelector("svg")!.dispatchEvent(new PointerEvent("pointerleave"));
    expect(tooltip.hidden).toBe(true);

    tree.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, pointerType: "touch" }));
    expect(tooltip.hidden).toBe(true);
  });

  it("announces keyboard details and updates figures through undo, redo and clearing", () => {
    const root = mount({
      givens: { r2c2: "Bo" },
      cellDetails: {
        r1c1: ["Area: Atrium", "Cells marked QU are quiet cells."],
        r2c2: ["Area: Studio"],
      },
    });
    const board = root.querySelector<HTMLElement>(".board")!;
    const tooltip = root.querySelector<HTMLElement>(".cell-tooltip")!;
    const status = root.querySelector<HTMLElement>('[role="status"]')!;
    board.focus();
    press(root, "ArrowRight");
    expect(board.getAttribute("aria-describedby")).toBe(tooltip.id);
    expect(status.textContent).toContain("Cells marked QU");
    expect(tooltip.textContent).not.toContain("Ada");

    press(root, "Enter");
    expect(tooltip.textContent).toContain("Figure: Ada");
    expect(root.querySelector("#r1c1")?.getAttribute("aria-label")).toContain("Figure: Ada");
    board.dispatchEvent(new KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true }));
    expect(tooltip.textContent).not.toContain("Figure: Ada");
    board.dispatchEvent(new KeyboardEvent("keydown", { key: "y", ctrlKey: true, bubbles: true }));
    expect(status.textContent).toContain("Figure: Ada");
    press(root, "Delete");
    expect(tooltip.textContent).not.toContain("Figure: Ada");

    press(root, "ArrowDown");
    press(root, "ArrowRight");
    expect(tooltip.textContent).toContain("Figure: Bo");
    press(root, "Escape");
    expect(tooltip.hidden).toBe(true);
  });

  it("shows object details beyond the grid without blocking cell placement", () => {
    const root = mount({
      cellDetails: { r1c1: ["Area: Atrium"] },
      detailTargets: [
        { x: 2, y: 1, radius: 1 / 3, lines: ["Allium", "Touches the neighbouring cells."] },
        { x: 2, y: 2, radius: 1 / 3, lines: ["Sunflower"] },
        { x: 0.5, y: 0.5, radius: 1 / 3, lines: ["Fountain"] },
      ],
    });
    const svg = root.querySelector("svg")!;
    const first = root.querySelector<SVGRectElement>("#r1c1")!;
    const origin = vi.spyOn(first, "getBoundingClientRect").mockReturnValue(new DOMRect(100, 50, 50, 50));
    const hit = vi.spyOn(document, "elementFromPoint").mockReturnValue(first);
    const tooltip = root.querySelector<HTMLElement>(".cell-tooltip")!;
    const move = (x: number, y: number, pointerType = "mouse") =>
      svg.dispatchEvent(new PointerEvent("pointermove", {
        bubbles: true, pointerType, clientX: x, clientY: y,
      }));
    try {
      move(205, 100);
      expect(tooltip.hidden).toBe(false);
      expect(tooltip.textContent).toContain("Allium");
      expect(tooltip.textContent).not.toContain("Cell:");
      move(205, 155);
      expect(tooltip.textContent).toBe("Sunflower");
      move(225, 175);
      expect(tooltip.hidden).toBe(true);
      move(205, 100, "touch");
      expect(tooltip.hidden).toBe(true);

      for (const type of ["pointerdown", "pointerup"]) first.dispatchEvent(new PointerEvent(type, {
        bubbles: true, pointerId: 1, pointerType: "mouse", button: 0, clientX: 125, clientY: 75,
      }));
      expect(first.getAttribute("aria-label")).toContain("Figure: Ada");
      expect(tooltip.textContent).toBe("Fountain");
      svg.dispatchEvent(new PointerEvent("pointerleave"));
      expect(tooltip.hidden).toBe(true);
    } finally {
      origin.mockRestore();
      hit.mockRestore();
    }
  });

  it("does not leave a tooltip over the board after a touch placement", () => {
    const root = mount({ cellDetails: { r1c1: ["Area: Atrium"] } });
    const board = root.querySelector<HTMLElement>(".board")!;
    const cell = root.querySelector<SVGRectElement>("#r1c1")!;
    const hit = vi.spyOn(document, "elementFromPoint").mockReturnValue(cell);
    try {
      cell.dispatchEvent(new PointerEvent("pointerdown", {
        bubbles: true, pointerId: 1, pointerType: "touch", button: 0,
      }));
      board.focus();
      cell.dispatchEvent(new PointerEvent("pointerup", {
        bubbles: true, pointerId: 1, pointerType: "touch", button: 0,
      }));
      expect(root.querySelector<HTMLElement>(".cell-tooltip")!.hidden).toBe(true);
      expect(cell.getAttribute("aria-label")).toContain("Figure: Ada");
    } finally {
      hit.mockRestore();
    }
  });

  it("leaves boards without cell details unchanged", () => {
    const root = mount();
    expect(root.querySelector(".cell-tooltip")).toBeNull();
    press(root, "ArrowRight");
    expect(root.querySelector("#r1c1")?.getAttribute("aria-label")).toBe("r1c1");
  });

  it("keeps loose clues separate from the figure cards", () => {
    const root = mount({
      clueEntries: [
        { id: "a", item: "Ada", text: "Ada and Bo.", sources: ["clue:1"] },
        { id: "b", text: "Another reference.", sources: ["clue:2"] },
      ],
      headings: { other_clues: "Overige aanwijzingen" },
    });
    expect(root.querySelector(".figure-entries h3")?.textContent).toBe("Overige aanwijzingen");
    expect(root.querySelectorAll(".figure-entries > .entry-clues li")[0].textContent).toBe("Another reference.");
    expect(root.querySelector('.panel-section[data-tab="rules"]')?.textContent).not.toContain("The figures");
  });

  it("combines objects, board symbols, roles and attributes into one details list", () => {
    const root = mount({
      clueEntries: [],
      combineExtras: true,
      rules: ["Place each figure on a free cell."],
      headings: { rules_title: "Spelregels", extras: "Bijzonderheden" },
      attributes: [{ name: "Vrouw", text: "Ada en Bo" }],
      roles: [{ name: "Dader", text: "precies één persoon" }],
      objects: [{ name: "Boom", text: "hier kan niemand staan", svg: '<svg viewBox="0 0 1 1"><circle r="1"/></svg>' }],
      key: [{ name: "Poort", text: "een markering", svg: '<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>' }],
    });
    const rules = root.querySelector<HTMLElement>("#section-rules")!;
    const extras = root.querySelector<HTMLElement>("#section-extras")!;
    const tab = root.querySelector<HTMLButtonElement>("#tab-extras")!;
    expect(rules.textContent).toContain("Place each figure");
    expect(rules.textContent).not.toMatch(/Boom|Vrouw|Dader|Poort/);
    expect(tab.textContent).toBe("Bijzonderheden");
    expect(tab.getAttribute("aria-controls")).toBe(extras.id);
    expect(root.querySelector("#tab-objects, #tab-key")).toBeNull();
    tab.click();
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(extras.classList.contains("active")).toBe(true);
    expect(extras.querySelectorAll("dl")).toHaveLength(1);
    expect(extras.textContent).toMatch(/Vrouw.*Ada en Bo.*Dader.*precies één persoon.*Poort.*een markering.*Boom.*hier kan niemand staan/);
    expect(extras.querySelector("svg circle")).not.toBeNull();
    expect(extras.querySelector("svg path")).not.toBeNull();
    tab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(document.activeElement?.id).toBe("tab-clues");
    document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(document.activeElement?.id).toBe("tab-extras");
    tab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(document.activeElement?.id).toBe("tab-rules");
  });

  it("shows a details tab for board symbols even without objects", () => {
    const root = mount({
      combineExtras: true,
      key: [{ name: "Point", text: "fountain", svg: '<svg viewBox="0 0 1 1"><circle r="1"/></svg>' }],
    });
    expect(root.querySelector(".panel.with-details #tab-extras")).not.toBeNull();
    expect(root.querySelector("#section-extras")?.textContent).toContain("fountain");
    expect(root.querySelector("#section-extras svg circle")).not.toBeNull();
  });

  it("does not add an empty details tab", () => {
    const root = mount({ combineExtras: true });
    expect(root.querySelector("#tab-extras")).toBeNull();
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
