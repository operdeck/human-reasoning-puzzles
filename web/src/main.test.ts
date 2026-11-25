// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { renderPuzzle, destroyPuzzle } = vi.hoisted(() => ({
  renderPuzzle: vi.fn(),
  destroyPuzzle: vi.fn(),
}));
vi.mock("./view", () => ({
  PuzzleView: class {
    render = renderPuzzle;
    destroy = destroyPuzzle;
  },
}));

const puzzles = [
  {
    id: "first-case",
    number: 1,
    section: "Murdoku · Demo",
    title: "First case",
    family: "murdoku",
    familyLabel: "Murdoku",
    size: [4, 4],
    grade: "relations",
    static: "first-case.svg",
    playable: true,
  },
  {
    id: "logicgrid_1",
    number: 2,
    section: "Logic grid",
    title: "Logic grid",
    family: "logicgrid",
    familyLabel: "Logic grid",
    size: [3, 3],
    grade: "single",
    static: "logicgrid_1.svg",
    playable: false,
    unsupported: "This puzzle is not playable yet.",
  },
];

let listeners: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.resetModules();
  renderPuzzle.mockReset();
  destroyPuzzle.mockReset();
  renderPuzzle.mockImplementation((app: HTMLElement) => app.replaceChildren());
  document.body.innerHTML = '<main id="app"></main>';
  window.history.replaceState(null, "", "/human-reasoning-puzzles/");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  listeners = vi.spyOn(window, "addEventListener");
  vi.stubGlobal("fetch", vi.fn(async (url: URL) => {
    if (url.pathname.endsWith("/index.json")) {
      return new Response(JSON.stringify({ license: "All rights reserved.", puzzles }));
    }
    if (url.pathname.endsWith(".svg")) return new Response("<svg></svg>");
    return new Response("{}");
  }));
});

afterEach(() => {
  for (const [type, listener] of listeners.mock.calls) {
    window.removeEventListener(type, listener);
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function openIndex(): Promise<void> {
  await import("./main");
  await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(2));
}

describe("puzzle index", () => {
  it("renders group previews and ordered puzzle links under the Pages base path", async () => {
    await openIndex();
    expect([...document.querySelectorAll(".family h2")].map((node) => node.textContent))
      .toEqual(["Murdoku · Demo", "Logic grid"]);
    const links = [...document.querySelectorAll<HTMLAnchorElement>(".puzzle-list a")];
    expect(links.map((link) => link.pathname)).toEqual([
      "/human-reasoning-puzzles/p/first-case/",
      "/human-reasoning-puzzles/p/logicgrid_1/",
    ]);
    expect(links.every((link) => link.hash === "")).toBe(true);
    expect(links[0].textContent).toBe("1. First case");
    expect(links[0].parentElement?.textContent).toContain("4×4 · Relationship checks");
    expect(
      [...document.querySelectorAll(".puzzle-list .meta")].map((node) => node.textContent),
    ).toEqual(["4×4 · Relationship checks", "3×3 · Forced moves"]);
    const images = [...document.querySelectorAll<HTMLImageElement>(".family-thumbnail")];
    expect(images.map((image) => new URL(image.src).pathname)).toEqual([
      "/human-reasoning-puzzles/puzzles/first-case.svg",
      "/human-reasoning-puzzles/puzzles/logicgrid_1.svg",
    ]);
    expect(images.every((image) => image.loading === "lazy" && image.alt.endsWith("puzzle preview"))).toBe(true);
    expect(links[1].parentElement?.querySelector(".badge")?.getAttribute("title")).toBe(puzzles[1].unsupported);
    expect(document.querySelector("footer")?.textContent).toContain("All rights reserved.");
  });

  it("links back to the source repository from the landing page header", async () => {
    await openIndex();
    const github = document.querySelector<HTMLAnchorElement>(".site-header .repo-link a");
    expect(github?.textContent).toBe("GitHub");
    expect(github?.getAttribute("href")).toBe("https://github.com/operdeck/human-reasoning-puzzles");
    expect(github?.target).toBe("_blank");
    expect(github?.rel).toBe("noreferrer");
  });

  it("credits the inventor of Murdoku in the landing page header", async () => {
    await openIndex();
    const credit = document.querySelector(".site-header .credit");
    expect(credit?.textContent).toBe("Murdoku was invented by Manuel Garand.");
    const inventor = credit?.querySelector<HTMLAnchorElement>("a");
    expect(inventor?.textContent).toBe("Manuel Garand");
    expect(inventor?.getAttribute("href")).toBe("https://murdoku.com");
    expect(inventor?.target).toBe("_blank");
    expect(inventor?.rel).toBe("noreferrer");
  });

  it("flags a puzzle the deduction ladder cannot close on its own", async () => {
    const collection = [
      { ...puzzles[0], id: "frontier", grade: "what_if", static: "frontier.svg", deductive: false },
      { ...puzzles[0], id: "deduced", static: "deduced.svg", deductive: true },
    ];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      license: "All rights reserved.",
      puzzles: collection,
    }))));
    await import("./main");
    await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(2));
    const items = [...document.querySelectorAll(".puzzle-list li")];
    expect(items[0].querySelector(".badge")?.textContent).toBe("beyond deduction");
    expect(items[0].querySelector(".badge")?.getAttribute("title")).toContain("What if trials");
    expect(items[1].querySelector(".badge")).toBeNull();
  });

  it("anchors each family section and opens the index at a #family- link", async () => {
    window.history.replaceState(null, "", "/human-reasoning-puzzles/#family-logic-grid");
    const scrolled = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrolled;
    await openIndex();
    expect([...document.querySelectorAll(".family")].map((node) => node.id))
      .toEqual(["family-murdoku-demo", "family-logic-grid"]);
    await vi.waitFor(() => expect(scrolled).toHaveBeenCalled());
    expect(scrolled.mock.contexts[0]).toBe(document.getElementById("family-logic-grid"));
    expect(renderPuzzle).not.toHaveBeenCalled();
  });

  it("opens a glossary of the grade labels above the puzzle list", async () => {
    await openIndex();
    const glossary = document.querySelector<HTMLDetailsElement>("details.glossary")!;
    expect(glossary.open).toBe(false);
    expect(glossary.querySelector("summary")?.textContent).toBe("Difficulty ratings");
    expect(glossary.textContent).toContain("hardest deduction this solver needed");
    expect(glossary.textContent).toContain("not how difficult a person will find the puzzle");
    const terms = [...glossary.querySelectorAll("dt")].map((node) => node.textContent);
    expect(terms).toContain("Relationship checks");
    expect(terms).toContain("What if");
    expect(glossary.querySelectorAll("dd")).toHaveLength(terms.length);
    expect(glossary.textContent).toContain("beyond deduction");
    // The app routes puzzles through the hash, so the glossary must stay unlinked.
    expect(glossary.querySelector("a")).toBeNull();
    const firstGroup = document.querySelector(".family")!;
    expect(
      glossary.compareDocumentPosition(firstGroup) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps an unknown grade visible under its raw name", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      license: "All rights reserved.",
      puzzles: [{ ...puzzles[0], id: "odd", static: "odd.svg", grade: "mystery" }],
    }))));
    await import("./main");
    await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(1));
    const meta = document.querySelector(".puzzle-list .meta")!;
    expect(meta.textContent).toContain("4×4 · mystery");
    expect(meta.getAttribute("title")).toBe("This solver grade has no player-facing name yet.");
  });

  it("uses one preview per group, including each Murdoku series and Binairo/Tango", async () => {
    const collection = [
      puzzles[0],
      { ...puzzles[0], id: "another-demo", static: "another-demo.svg" },
      { ...puzzles[0], id: "museum", section: "Murdoku · Museum", static: "museum.svg" },
      { ...puzzles[1], id: "binairo", family: "binairo", familyLabel: "Binairo", section: "Binairo" },
      { ...puzzles[1], id: "tango", family: "binairo", familyLabel: "Tango", section: "Tango" },
    ];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      license: "All rights reserved.",
      puzzles: collection,
    }))));
    await import("./main");
    await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(5));
    expect(document.querySelectorAll("img")).toHaveLength(4);
    expect([...document.querySelectorAll(".family h2")].map((node) => node.textContent))
      .toEqual(["Murdoku · Demo", "Murdoku · Museum", "Binairo", "Tango"]);
    expect(document.querySelectorAll(".family")[0].querySelectorAll("img")).toHaveLength(1);
    expect(document.querySelectorAll(".family")[0].querySelectorAll(".puzzle-list a")).toHaveLength(2);
  });

  it("keeps puzzle links usable and reports a failed group preview", async () => {
    await openIndex();
    document.querySelector("img")!.dispatchEvent(new Event("error"));
    expect(document.querySelector(".preview-unavailable")?.textContent).toBe("Preview unavailable");
    expect(document.querySelector<HTMLAnchorElement>(".puzzle-list a")?.pathname)
      .toBe("/human-reasoning-puzzles/p/first-case/");
  });

  it("opens a puzzle's player and returns to the same index", async () => {
    await openIndex();
    document.querySelector<HTMLAnchorElement>(".puzzle-list a")!.click();
    await vi.waitFor(() => expect(renderPuzzle).toHaveBeenCalledOnce());
    const requested = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(requested.some((url) => url.endsWith("/first-case.json"))).toBe(true);
    expect(requested.some((url) => url.endsWith("/first-case.svg"))).toBe(true);
    window.location.hash = "";
    await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(2));
    expect(requested.filter((url) => url.endsWith("/index.json"))).toHaveLength(1);
    expect(destroyPuzzle).toHaveBeenCalledOnce();
  });

  it("opens a prerendered puzzle immediately using the site's base URL", async () => {
    window.history.replaceState(null, "", "/human-reasoning-puzzles/p/first-case/?source=search");
    const base = document.createElement("base");
    base.href = "/human-reasoning-puzzles/";
    document.head.append(base);
    document.getElementById("app")!.dataset.puzzleId = "first-case";
    try {
      await import("./main");
      await vi.waitFor(() => expect(renderPuzzle).toHaveBeenCalledOnce());
      expect(window.location.hash).toBe("");
      expect(window.location.pathname).toBe("/human-reasoning-puzzles/p/first-case/");
      expect(window.location.search).toBe("?source=search");
      const requested = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
      expect(requested.some((url) => url.endsWith("/human-reasoning-puzzles/puzzles/first-case.json"))).toBe(true);
      expect(document.querySelector(".puzzle-list")).toBeNull();
    } finally {
      base.remove();
    }
  });

  it("lets an explicit hash override a prerendered puzzle's initial id", async () => {
    document.getElementById("app")!.dataset.puzzleId = "first-case";
    window.history.replaceState(null, "", "/human-reasoning-puzzles/p/first-case/#logicgrid_1");
    await import("./main");
    await vi.waitFor(() => expect(renderPuzzle).toHaveBeenCalledOnce());
    expect(window.location.hash).toBe("#logicgrid_1");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/logicgrid_1.json"))).toBe(true);
  });
});
