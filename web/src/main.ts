import type { Bundle } from "./game";
import { adjacentPuzzles } from "./navigation";
import { PuzzleView } from "./view";

interface IndexEntry {
  id: string;
  number: number;
  section: string;
  title: string;
  family: string;
  familyLabel: string;
  size: [number, number];
  grade: string;
  static: string;
  playable: boolean;
  unsupported?: string;
}

interface PuzzleIndex {
  license: string;
  puzzles: IndexEntry[];
}

const base = new URL("puzzles/", document.baseURI);
const app = document.getElementById("app")!;
let indexRequest: Promise<PuzzleIndex> | undefined;

async function fetchText(name: string): Promise<string> {
  const response = await fetch(new URL(name, base));
  if (!response.ok) throw new Error(`${name}: ${response.status} ${response.statusText}`);
  return response.text();
}

function fetchIndex(): Promise<PuzzleIndex> {
  if (!indexRequest) {
    indexRequest = fetchText("index.json")
      .then((text) => JSON.parse(text) as PuzzleIndex)
      .catch((error: unknown) => {
        indexRequest = undefined;
        throw error;
      });
  }
  return indexRequest;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

async function showIndex(current: () => boolean): Promise<void> {
  const index = await fetchIndex();
  if (!current()) return;
  document.title = "Human reasoning puzzles";
  // The index is already in reading order, as in the booklet.
  const groups = new Map<string, IndexEntry[]>();
  for (const entry of index.puzzles) {
    const list = groups.get(entry.familyLabel) ?? [];
    list.push(entry);
    groups.set(entry.familyLabel, list);
  }
  const sections = [...groups]
    .map(([label, entries]) => {
      const representative = entries[0];
      const preview = el("img", {
        className: "family-thumbnail",
        src: new URL(representative.static, base).href,
        alt: `${label} puzzle preview`,
        loading: "lazy",
        decoding: "async",
        width: 180,
        height: 180,
      });
      preview.addEventListener("error", () => {
        preview.replaceWith(el("span", {
          className: "family-thumbnail preview-unavailable",
          textContent: "Preview unavailable",
        }));
      }, { once: true });
      const categories = new Map<string, IndexEntry[]>();
      for (const entry of entries) {
        const category = categories.get(entry.section) ?? [];
        category.push(entry);
        categories.set(entry.section, category);
      }
      return el(
        "section",
        { className: "family" },
        el("div", { className: "family-preview" }, preview),
        el(
          "div",
          { className: "family-puzzles" },
          el("h2", { textContent: label }),
          ...[...categories].map(([category, puzzles]) => el(
            "div",
            { className: "puzzle-category" },
            ...(category === label ? [] : [el("h3", { textContent: category })]),
            el(
              "ul",
              { className: "puzzle-list" },
              ...puzzles.map((entry) => el(
                "li",
                {},
                el("a", {
                  href: `#${encodeURIComponent(entry.id)}`,
                  textContent: `${entry.number}. ${entry.title}`,
                }),
                el("span", {
                  className: "meta",
                  textContent: `${entry.size[0]}×${entry.size[1]} · ${entry.grade}`,
                }),
                ...(entry.playable
                  ? []
                  : [el("span", { className: "badge", textContent: "not yet supported", title: entry.unsupported ?? "" })]),
              )),
            ),
          )),
        ),
      );
    });
  app.replaceChildren(
    el(
      "header",
      { className: "site-header" },
      el("h1", { textContent: "Human reasoning puzzles" }),
      el("p", {
        textContent:
          "Logic puzzles that can be solved by reasoning alone, as a person would. Pick one to play in the browser.",
      }),
    ),
    ...sections,
    el(
      "footer",
      {},
      el(
        "p",
        {},
        `${index.license} `,
        el("a", {
          href: "https://github.com/operdeck/human-reasoning-puzzles/blob/main/examples/LICENSE.md",
          textContent: "Licence",
        }),
        " · ",
        el("a", { href: "https://github.com/operdeck/human-reasoning-puzzles", textContent: "Source" }),
      ),
    ),
  );
}

async function showPuzzle(id: string, current: () => boolean): Promise<void> {
  const [bundleText, svg, index] = await Promise.all([
    fetchText(`${id}.json`),
    fetchText(`${id}.svg`),
    fetchIndex(),
  ]);
  if (!current()) return;
  const bundle = JSON.parse(bundleText) as Bundle;
  new PuzzleView(bundle, svg, adjacentPuzzles(index.puzzles, id)).render(app);
}

let routing = 0;

async function route(): Promise<void> {
  const id = decodeURIComponent(location.hash.slice(1));
  const ticket = ++routing;
  // A later hash change wins, even if this page arrives after it.
  const current = () => ticket === routing;
  try {
    if (id && /^[\w.-]+$/.test(id)) await showPuzzle(id, current);
    else await showIndex(current);
  } catch (error) {
    if (!current()) return;
    app.replaceChildren(
      el("p", { className: "error", textContent: `Could not load the puzzle: ${String(error)}` }),
      el("a", { href: "#", textContent: "← All puzzles" }),
    );
  }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
void route();
