import { describe, expect, it } from "vitest";
import { conflictText, verdictText } from "./view";

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
});
