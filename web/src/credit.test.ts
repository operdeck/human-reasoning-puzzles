// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { creditLine, INVENTOR, INVENTOR_URL } from "./credit";

describe("creditLine", () => {
  it("names Murdoku's inventor and links to his own site", () => {
    const credit = creditLine();
    expect(credit.className).toBe("credit");
    expect(credit.textContent).toBe(`Murdoku was invented by ${INVENTOR}.`);
    const inventor = credit.querySelector("a")!;
    expect(inventor.textContent).toBe(INVENTOR);
    expect(inventor.getAttribute("href")).toBe(INVENTOR_URL);
    expect(inventor.title).toBe("Murdoku books and free puzzles by their inventor");
    expect(inventor.target).toBe("_blank");
    expect(inventor.rel).toBe("noreferrer");
  });
});
