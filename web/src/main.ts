import type { Bundle } from "./game";
import { creditLine } from "./credit";
import {
  BEYOND_DEDUCTION_NOTE,
  GLOSSARY_INTRO,
  GRADES,
  gradeLabel,
  isKnownGrade,
} from "./grades.mjs";
import { adjacentPuzzles, puzzleIdFromPath, puzzleLink } from "./navigation";
import { SECTION_PREFIX, sectionAnchor } from "./sections.mjs";
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
  deductive: boolean;
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
let puzzleView: PuzzleView | undefined;

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

function glossary(): HTMLElement {
  // A <details> control needs no URL: "#glossary" would look like a puzzle id,
  // because the app routes puzzles through the hash.
  return el(
    "details",
    { className: "glossary" },
    el("summary", { textContent: "Difficulty ratings" }),
    el("p", { textContent: GLOSSARY_INTRO }),
    el(
      "dl",
      {},
      ...GRADES.flatMap(({ label, meaning }) => [
        el("dt", { textContent: label }),
        el("dd", { textContent: meaning }),
      ]),
    ),
    el("p", { className: "glossary-badge", textContent: BEYOND_DEDUCTION_NOTE }),
  );
}

async function showIndex(current: () => boolean): Promise<void> {
  const index = await fetchIndex();
  if (!current()) return;
  puzzleView?.destroy();
  puzzleView = undefined;
  document.title = "Human reasoning puzzles";
  // The index is already in reading order, as in the booklet.
  const groups = new Map<string, IndexEntry[]>();
  for (const entry of index.puzzles) {
    const list = groups.get(entry.section) ?? [];
    list.push(entry);
    groups.set(entry.section, list);
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
      return el(
        "section",
        { className: "family", id: sectionAnchor(label) },
        el("div", { className: "family-preview" }, preview),
        el(
          "div",
          { className: "family-puzzles" },
          el("h2", { textContent: label }),
          el(
            "ul",
            { className: "puzzle-list" },
            ...entries.map((entry) => {
              const link = puzzleLink(entry.id);
              link.textContent = `${entry.number}. ${entry.title}`;
              const meta = el("span", {
                className: "meta",
                textContent: `${entry.size[0]}×${entry.size[1]} · ${gradeLabel(entry.grade)}`,
              });
              if (!isKnownGrade(entry.grade)) {
                meta.title = "This solver grade has no player-facing name yet.";
              }
              return el(
                "li",
                {},
                link,
                meta,
                ...(entry.deductive === false
                  ? [el("span", {
                      className: "badge",
                      textContent: "beyond deduction",
                      title: "Only this solver's What if trials close this puzzle.",
                    })]
                  : []),
                ...(entry.playable
                  ? []
                  : [el("span", { className: "badge", textContent: "not yet supported", title: entry.unsupported ?? "" })]),
              );
            }),
          ),
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
      creditLine(),
      el(
        "p",
        { className: "repo-link" },
        el("a", {
          href: "https://github.com/operdeck/human-reasoning-puzzles",
          textContent: "GitHub",
          target: "_blank",
          rel: "noreferrer",
          title: "View the source repository on GitHub",
        }),
      ),
    ),
    glossary(),
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
  puzzleView?.destroy();
  puzzleView = new PuzzleView(bundle, svg, adjacentPuzzles(index.puzzles, id));
  puzzleView.render(app);
}

let routing = 0;

async function route(): Promise<void> {
  // The app shell served for an offline /p/<id>/ navigation has no data-puzzle-id;
  // read the id from the path then. A hash or the static page still wins.
  const fromPath = puzzleIdFromPath(location.pathname, new URL(document.baseURI).pathname);
  const id = decodeURIComponent(location.hash.slice(1) || app.dataset.puzzleId || fromPath || "");
  const ticket = ++routing;
  // A later hash change wins, even if this page arrives after it.
  const current = () => ticket === routing;
  // `#family-...` names an index section, never a puzzle.
  const section = id.startsWith(SECTION_PREFIX) ? id : "";
  try {
    if (!section && id && /^[\w.-]+$/.test(id)) await showPuzzle(id, current);
    else await showIndex(current);
  } catch (error) {
    if (!current()) return;
    puzzleView?.destroy();
    puzzleView = undefined;
    app.replaceChildren(
      el("p", { className: "error", textContent: `Could not load the puzzle: ${String(error)}` }),
      el("a", { href: "#", textContent: "← All puzzles" }),
    );
  }
  if (!current()) return;
  const target = section ? document.getElementById(section) : null;
  if (target) target.scrollIntoView();
  else window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
void route();
