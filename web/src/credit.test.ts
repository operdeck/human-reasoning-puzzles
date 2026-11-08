// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { creditLine, INVENTOR, INVENTOR_URL } from "./credit";

describe("creditLine", () => {
  it("names Murdoku's inventor and links to his own site", () => {
    const credit = creditLine();
    expect(credit.className).toBe("credit");
    expect(credit.textContent).toContain(`Murdoku was invented by ${INVENTOR}`);
    expect(credit.textContent).toContain("better designed and more fun than the cases here");
    const inventor = credit.querySelector("a")!;
    expect(inventor.textContent).toBe(INVENTOR);
    expect(inventor.getAttribute("href")).toBe(INVENTOR_URL);
    expect(inventor.target).toBe("_blank");
    expect(inventor.rel).toBe("noreferrer");
  });
});
