import type { Bundle } from "./game";
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
  playable: boolean;
  unsupported?: string;
}

const base = new URL("puzzles/", document.baseURI);
const app = document.getElementById("app")!;

async function fetchText(name: string): Promise<string> {
  const response = await fetch(new URL(name, base));
  if (!response.ok) throw new Error(`${name}: ${response.status} ${response.statusText}`);
  return response.text();
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
  const index = JSON.parse(await fetchText("index.json")) as { license: string; puzzles: IndexEntry[] };
  if (!current()) return;
  document.title = "Human reasoning puzzles";
  // The index is already in reading order, as in the booklet.
  const groups = new Map<string, IndexEntry[]>();
  for (const entry of index.puzzles) {
    const list = groups.get(entry.section) ?? [];
    list.push(entry);
    groups.set(entry.section, list);
  }
  const sections = [...groups]
    .map(([label, entries]) =>
      el(
        "section",
        { className: "family" },
        el("h2", { textContent: label }),
        el(
          "ul",
          {},
          ...entries.map((entry) =>
            el(
              "li",
              {},
              el("span", { className: "meta", textContent: `${entry.number}. ` }),
              el("a", { href: `#${encodeURIComponent(entry.id)}`, textContent: entry.title }),
              el("span", {
                className: "meta",
                textContent: ` ${entry.size[0]}×${entry.size[1]} · ${entry.grade}`,
              }),
              ...(entry.playable
                ? []
                : [el("span", { className: "badge", textContent: "not yet supported", title: entry.unsupported ?? "" })]),
            ),
          ),
        ),
      ),
    );
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
  const [bundleText, svg] = await Promise.all([fetchText(`${id}.json`), fetchText(`${id}.svg`)]);
  if (!current()) return;
  const bundle = JSON.parse(bundleText) as Bundle;
  new PuzzleView(bundle, svg).render(app);
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
