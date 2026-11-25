import { describe, expect, it } from "vitest";
import { SECTION_PREFIX, sectionAnchor } from "./sections.mjs";

describe("sectionAnchor", () => {
  it("turns section labels into prefixed, readable link targets", () => {
    expect(sectionAnchor("Bridges")).toBe("family-bridges");
    expect(sectionAnchor("Tents and Trees")).toBe("family-tents-and-trees");
    expect(sectionAnchor("Even/Odd Sudoku")).toBe("family-even-odd-sudoku");
    expect(sectionAnchor("Murdoku · Japanese food")).toBe("family-murdoku-japanese-food");
    expect(sectionAnchor("Café · Été")).toBe("family-cafe-ete");
    expect(sectionAnchor("Bridges").startsWith(SECTION_PREFIX)).toBe(true);
  });
});
