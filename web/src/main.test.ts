// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const renderPuzzle = vi.hoisted(() => vi.fn());
vi.mock("./view", () => ({
  PuzzleView: class {
    render = renderPuzzle;
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
    expect(links.map((link) => link.hash)).toEqual(["#first-case", "#logicgrid_1"]);
    expect(links[0].textContent).toBe("1. First case");
    expect(links[0].parentElement?.textContent).toContain("4×4 · relations");
    const images = [...document.querySelectorAll<HTMLImageElement>(".family-thumbnail")];
    expect(images.map((image) => new URL(image.src).pathname)).toEqual([
      "/human-reasoning-puzzles/puzzles/first-case.svg",
      "/human-reasoning-puzzles/puzzles/logicgrid_1.svg",
    ]);
    expect(images.every((image) => image.loading === "lazy" && image.alt.endsWith("puzzle preview"))).toBe(true);
    expect(links[1].parentElement?.querySelector(".badge")?.getAttribute("title")).toBe(puzzles[1].unsupported);
    expect(document.querySelector("footer")?.textContent).toContain("All rights reserved.");
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
    expect(document.querySelector(".puzzle-list a")?.getAttribute("href")).toBe("#first-case");
  });

  it("opens a puzzle's player and returns to the same index", async () => {
    await openIndex();
    window.location.hash = "#first-case";
    await vi.waitFor(() => expect(renderPuzzle).toHaveBeenCalledOnce());
    const requested = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(requested.some((url) => url.endsWith("/first-case.json"))).toBe(true);
    expect(requested.some((url) => url.endsWith("/first-case.svg"))).toBe(true);
    window.location.hash = "";
    await vi.waitFor(() => expect(document.querySelectorAll(".puzzle-list a")).toHaveLength(2));
    expect(requested.filter((url) => url.endsWith("/index.json"))).toHaveLength(1);
  });
});
