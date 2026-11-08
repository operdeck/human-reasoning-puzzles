// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { conflictText, footerParagraphs, mineCounter, verdictText } from "./view";

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
