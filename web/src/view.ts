import {
  autoMarks,
  check,
  clearCell,
  emptyState,
  History,
  locked,
  occupied,
  parseCell,
  place,
  placementConflict,
  restore,
  setCross,
  struckNotes,
  toggleClue,
  toggleNote,
  cellId,
  usedItems,
  type Bundle,
  type CellId,
  type ClueEntry,
  type Named,
  type PaletteItem,
  type State,
  type Verdict,
} from "./game";
import type { PuzzleNavigationEntry } from "./navigation";
import { creditLine } from "./credit";

const SVG_NS = "http://www.w3.org/2000/svg";
const CROSS = "__cross__";
const LONG_PRESS_MS = 450;
let nextTooltipId = 0;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

/** What stands under the board: the licence, plus the credit when the board is a Murdoku. */
export function footerParagraphs(license: string, family: string): HTMLElement[] {
  const paragraphs = [
    el(
      "p",
      {},
      license + " ",
      el("a", {
        href: "https://github.com/operdeck/human-reasoning-puzzles/blob/main/examples/LICENSE.md",
        textContent: "Licence",
      }),
    ),
  ];
  // The puzzle family is Manuel Garand's invention; say so wherever one of his boards stands.
  if (family === "murdoku") paragraphs.push(creditLine());
  return paragraphs;
}

function svgEl(tag: string, attrs: Record<string, string | number> = {}): SVGElement {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function storageKey(id: string): string {
  return `hrp:v1:${id}`;
}

function load(bundle: Bundle): State {
  try {
    const raw = localStorage.getItem(storageKey(bundle.id));
    return raw ? restore(bundle, JSON.parse(raw)) : emptyState(bundle);
  } catch {
    return emptyState(bundle);
  }
}

function save(bundle: Bundle, state: State): void {
  try {
    localStorage.setItem(storageKey(bundle.id), JSON.stringify(state));
  } catch {
    // Private mode or full storage: progress just isn't kept.
  }
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface CellTooltip {
  cell: CellId;
  x: number;
  y: number;
  keyboard: boolean;
}

/** One puzzle: the board from the export, an overlay for the player's moves, and the panel. */
export function verdictText(
  verdict: Verdict,
  language: string,
  reveal?: string,
  missingItem?: { singular: string; plural: string },
): string {
  const nl = language === "nl";
  if (verdict.status === "solved") {
    const story = reveal?.trim() || (nl ? "Alles staat op de goede plek." : "Everything is in the right place.");
    return `${nl ? "Opgelost!" : "Solved!"} ${story}`;
  }
  if (verdict.status === "wrong") {
    const n = verdict.wrong;
    if (nl) return `Nog niet goed: ${n} ${n === 1 ? "stuk staat" : "stukken staan"} op de verkeerde plek.`;
    return `Not right: ${n} piece${n === 1 ? " is" : "s are"} in the wrong place.`;
  }
  const m = verdict.missing;
  if (missingItem) {
    const item = m === 1 ? missingItem.singular : missingItem.plural;
    return nl
      ? `Nog geen fouten; nog ${m} ${item} te plaatsen.`
      : `No mistakes so far; ${m} ${item} still to place.`;
  }
  return nl ? `Nog geen fouten; nog ${m} te plaatsen.` : `No mistakes so far; ${m} still to place.`;
}

export function mineCounter(
  bundle: Pick<Bundle, "language" | "totals">,
  state: Pick<State, "placed">,
): { text: string; overLimit: boolean } | null {
  const total = bundle.totals?.mine;
  if (total === undefined) return null;
  const placed = Object.values(state.placed).filter((item) => item === "mine").length;
  return {
    text: `${bundle.language === "nl" ? "Mijnen" : "Mines"}: ${placed} / ${total}`,
    overLimit: placed > total,
  };
}

export function conflictText(item: string, cell: CellId, language: string, description?: string): string {
  const reason = description ? ` (${description})` : "";
  return language === "nl"
    ? `${item} botst met dezelfde waarde op ${cell}${reason}.`
    : `${item} conflicts with the same value at ${cell}${reason}.`;
}

const BALLOON_COLOURS = ["#e74c3c", "#f39c12", "#f1c40f", "#2ecc71", "#3498db", "#9b59b6", "#e84393"];

/** Let a handful of balloons float up over the page; skipped when the user prefers less motion. */
export function celebrate(count = 18): void {
  if (typeof window === "undefined" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  document.querySelector(".balloons")?.remove();
  const layer = el("div", { className: "balloons" });
  layer.setAttribute("aria-hidden", "true");
  let longest = 0;
  for (let i = 0; i < count; i++) {
    const balloon = el("span", { className: "balloon" });
    const duration = 4 + Math.random() * 3;
    const delay = Math.random() * 1.5;
    longest = Math.max(longest, duration + delay);
    balloon.style.left = `${Math.random() * 92}%`;
    balloon.style.setProperty("--colour", BALLOON_COLOURS[i % BALLOON_COLOURS.length]);
    balloon.style.setProperty("--sway", `${Math.round(Math.random() * 60 - 30)}px`);
    balloon.style.animationDuration = `${duration}s`;
    balloon.style.animationDelay = `${delay}s`;
    balloon.style.transform = `scale(${0.7 + Math.random() * 0.6})`;
    layer.append(balloon);
  }
  document.body.append(layer);
  window.setTimeout(() => layer.remove(), longest * 1000 + 200);
}

export class PuzzleView {
  private history: History;
  private working: State | null = null;
  private tool: string;
  private cursor: CellId | null = null;
  private boxes = new Map<CellId, Box>();
  private cells = new Map<CellId, SVGRectElement>();
  private tooltip = el("div", { className: "cell-tooltip", hidden: true });
  private cellStatus = el("span", { className: "visually-hidden" });
  private currentTooltip: CellTooltip | null = null;
  private overlay!: SVGGElement;
  private icons = new Map<string, SVGSVGElement>();
  private paletteButtons = new Map<string, HTMLButtonElement>();
  private mineCount = el("p", { className: "mine-counter" });
  private verdict = el("p", { className: "verdict" });
  private undoButton = el("button", { type: "button", textContent: "Undo" });
  private redoButton = el("button", { type: "button", textContent: "Redo" });
  private autoBox = el("input", { type: "checkbox" });
  private warningsBox = el("input", { type: "checkbox" });
  private notesMode = false;
  private notesButton = el("button", { type: "button", className: "tool notes-toggle" });
  private clueBoxes: { box: HTMLInputElement; index: number }[] = [];
  private entryButtons = new Map<string, HTMLButtonElement>();
  private placementLabels = new Map<string, HTMLElement>();

  constructor(
    private bundle: Bundle,
    private boardSvg: string,
    private navigation: { previous?: PuzzleNavigationEntry; next?: PuzzleNavigationEntry } = {},
  ) {
    this.history = new History(load(bundle));
    this.tool = bundle.palette?.[0]?.id ?? CROSS;
    this.verdict.setAttribute("aria-live", "polite");
    this.mineCount.setAttribute("aria-live", "polite");
  }

  private get state(): State {
    return this.working ?? this.history.current;
  }

  render(root: HTMLElement): void {
    const b = this.bundle;
    document.title = `${b.title} · Human reasoning puzzles`;
    const puzzleLink = (
      entry: PuzzleNavigationEntry,
      direction: "Previous" | "Next",
      text: string,
    ): HTMLAnchorElement => {
      const link = el("a", {
        href: `#${encodeURIComponent(entry.id)}`,
        textContent: text,
        title: entry.title,
      });
      link.setAttribute("aria-label", `${direction} puzzle: ${entry.title}`);
      return link;
    };
    const puzzleNav = el(
      "nav",
      { className: "puzzle-nav" },
      el("a", { href: "#", className: "back", textContent: "← All puzzles" }),
      ...(this.navigation.previous
        ? [puzzleLink(this.navigation.previous, "Previous", "← Previous")]
        : []),
      ...(this.navigation.next
        ? [puzzleLink(this.navigation.next, "Next", "Next →")]
        : []),
      el("a", {
        href: "https://github.com/operdeck/human-reasoning-puzzles",
        textContent: "GitHub",
        target: "_blank",
        rel: "noreferrer",
        title: "View the source repository on GitHub",
      }),
    );
    puzzleNav.setAttribute("aria-label", "Puzzle navigation");
    const header = el(
      "header",
      { className: "puzzle-header" },
      puzzleNav,
      ...(b.section ? [el("p", { className: "meta", textContent: b.section })] : []),
      ...(b.deductive === false
        ? [el("p", {
            className: "meta",
            textContent: "beyond deduction: only this solver's what_if case analysis closes it",
          })]
        : []),
      el("h1", { textContent: b.number ? `${b.number}. ${b.title}` : b.title }),
    );
    const assists = el("div", { className: "assist-controls" });
    if (b.playable && b.autoMark && (b.autoMark.onPlace.length > 0 || (b.notes && b.peers?.length))) {
      this.autoBox.checked = this.state.auto;
      this.autoBox.addEventListener("change", () =>
        this.commit({ ...this.state, auto: this.autoBox.checked }),
      );
      assists.append(el("label", { className: "auto" }, this.autoBox, " Auto-mark"));
    }
    if (b.playable && b.peers?.length) {
      this.warningsBox.checked = this.state.warnings;
      this.warningsBox.addEventListener("change", () =>
        this.commit({ ...this.state, warnings: this.warningsBox.checked }),
      );
      assists.append(el("label", { className: "auto" }, this.warningsBox,
        b.language === "nl" ? " Waarschuwingen" : " Warnings"));
    }
    if (assists.childElementCount > 0) header.append(assists);

    const board = el("div", { className: "board", tabIndex: 0 });
    board.setAttribute("role", "application");
    board.setAttribute("aria-label", "Puzzle board; arrow keys move, space places");
    board.innerHTML = this.boardSvg;
    if (b.cellDetails) {
      this.tooltip.id = `cell-tooltip-${++nextTooltipId}`;
      this.tooltip.setAttribute("role", "tooltip");
      this.cellStatus.setAttribute("role", "status");
      board.setAttribute("aria-describedby", this.tooltip.id);
      board.append(this.tooltip, this.cellStatus);
    }
    const play = el("section", { className: "play" }, board);
    if (b.playable && b.clueEntries) {
      // Figure cards select figures, so only the cross joins the controls.
      const controls = this.controls();
      controls.prepend(this.paletteBar());
      play.append(controls, this.verdict);
    } else if (b.playable) {
      play.append(this.paletteBar(), this.mineCount, this.controls(), this.verdict);
    } else {
      play.append(el("p", { className: "note", textContent: b.unsupported ?? "Not playable yet." }));
    }

    root.replaceChildren(
      header,
      el("div", { className: `layout${b.clueEntries ? " with-clue-entries" : ""}` }, play, this.panel()),
      el("footer", {}, ...footerParagraphs(this.bundle.license, this.bundle.family)),
    );
    this.setUpBoard(board);
    this.redraw();
  }

  // --- panel: clues, rules and details ------------------------------------

  private heading(key: string, fallback: string): string {
    return this.bundle.headings?.[key] ?? fallback;
  }

  private panel(): HTMLElement {
    const b = this.bundle;
    const sections: [string, string, HTMLElement][] = [];
    if (b.clueEntries || b.clues.length > 0 || b.question) {
      const list = el("ol", { className: "clues" });
      let section: HTMLElement;
      if (b.clueEntries) {
        section = this.figureEntries(b.clueEntries);
      } else {
        b.clues.forEach((clue, index) => {
          const box = this.clueBox();
          box.addEventListener("change", () => this.commit(toggleClue(this.state, index)));
          this.clueBoxes.push({ box, index });
          list.append(el("li", {}, el("label", {}, el("span", { textContent: clue }), box)));
        });
        section = el("div", {}, list);
      }
      if (b.question) {
        section.append(
          el(
            "div",
            { className: "question" },
            el("strong", { textContent: this.heading("question", "Question") }),
            el("p", { textContent: b.question }),
          ),
        );
      }
      sections.push(["clues", this.heading(b.clueEntries ? "figure_clues" : "clues", "Clues"), section]);
    }
    const rules = el("div", {}, el("ul", {}, ...b.rules.map((rule) => el("li", { textContent: rule }))));
    const figures = !b.clueEntries && b.family === "murdoku" ? (b.palette ?? []) : [];
    if (figures.length > 0) rules.append(this.namedList(this.heading("figures", "The figures"),
      figures.map((item) => ({ name: item.label, text: item.description ?? "", svg: item.svg }))));
    if (!b.combineExtras) {
      if (b.attributes?.length) rules.append(this.namedList(this.heading("attributes", "Attributes"), b.attributes));
      if (b.roles?.length) rules.append(this.namedList(this.heading("roles", "Roles"), b.roles));
    }
    sections.push(["rules", this.heading("rules_title", "Rules"), rules]);
    const extras = [...(b.attributes ?? []), ...(b.roles ?? []), ...b.key, ...(b.objects ?? [])];
    if (b.combineExtras) {
      if (extras.length) sections.push(["extras", this.heading("extras", "Case details"), this.namedList(null, extras)]);
    } else {
      if (b.objects?.length) {
        sections.push(["objects", this.heading("objects", "Objects"), this.namedList(null, b.objects)]);
      }
      if (b.key.length > 0) {
        sections.push(["key", this.heading("key", "Key"), this.namedList(null, b.key)]);
      }
    }

    const tabs = el("div", { className: "tabs" });
    tabs.setAttribute("role", "tablist");
    const tabbed = b.combineExtras ? extras.length > 0 : Boolean(b.objects?.length);
    const aside = el("aside", { className: `panel${tabbed ? " with-details" : ""}` }, tabs);
    const select = (name: string) => {
      for (const node of aside.querySelectorAll<HTMLElement>("[data-tab]")) {
        node.classList.toggle("active", node.dataset.tab === name);
        if (node instanceof HTMLButtonElement) {
          node.setAttribute("aria-selected", String(node.dataset.tab === name));
          node.tabIndex = node.dataset.tab === name ? 0 : -1;
        }
      }
    };
    for (const [name, title, body] of sections) {
      const tab = el("button", { type: "button", textContent: title });
      tab.dataset.tab = name;
      tab.id = `tab-${name}`;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", `section-${name}`);
      tab.addEventListener("click", () => select(name));
      tab.addEventListener("keydown", (event) => {
        const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
        if (!keys.includes(event.key)) return;
        event.preventDefault();
        const index = sections.findIndex(([key]) => key === name);
        const next = event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : sections.length - 1)) % sections.length;
        select(sections[next][0]);
        tabs.querySelector<HTMLButtonElement>(`[data-tab="${sections[next][0]}"]`)?.focus();
      });
      tabs.append(tab);
      const section = el("section", { className: "panel-section" }, el("h2", { textContent: title }), body);
      section.dataset.tab = name;
      section.id = `section-${name}`;
      section.setAttribute("role", "tabpanel");
      section.setAttribute("aria-labelledby", tab.id);
      aside.append(section);
    }
    select(sections[0][0]);
    return aside;
  }

  private clueBox(): HTMLInputElement {
    const title = this.bundle.language === "nl" ? "Aanwijzing afvinken" : "Mark this clue as used";
    return el("input", { type: "checkbox", title });
  }

  private entryClues(entries: ClueEntry[]): HTMLElement {
    const list = el("ul", { className: "clues entry-clues" });
    for (const entry of entries) list.append(el("li", { textContent: entry.text }));
    return list;
  }

  private figureEntries(entries: ClueEntry[]): HTMLElement {
    const section = el("div", { className: "figure-entries" });
    for (const item of this.bundle.palette ?? []) {
      const portrait = el("span", { className: item.svg ? "entry-portrait" : "entry-mark" });
      portrait.setAttribute("aria-hidden", "true");
      if (item.svg) portrait.innerHTML = item.svg;
      portrait.append(this.usedCross());
      const status = el("span", { className: "placement-status" });
      this.placementLabels.set(item.id, status);
      const heading = el("span", { className: "entry-label" },
        el("strong", { textContent: item.label }), ...(!item.svg ? [portrait] : []));
      const name = el("span", { className: "entry-name" },
        heading, status);
      const select = el("button", { type: "button", className: "entry-select" },
        ...(item.svg ? [portrait] : []), name);
      select.setAttribute("aria-pressed", String(this.tool === item.id));
      select.addEventListener("click", () => this.selectTool(item.id));
      this.entryButtons.set(item.id, select);
      const card = el("article", { className: "figure-entry" }, select);
      if (item.description) card.append(el("p", { className: "entry-description", textContent: item.description }));
      const clues = entries.filter((entry) => entry.item === item.id);
      if (clues.length) card.append(this.entryClues(clues));
      section.append(card);
    }
    const other = entries.filter((entry) => !entry.item);
    if (other.length) section.append(
      el("h3", { textContent: this.heading("other_clues", "Other clues") }),
      this.entryClues(other),
    );
    return section;
  }

  private namedList(title: string | null, items: Named[]): HTMLElement {
    const list = el("dl", {});
    for (const { name, text, svg } of items) {
      const term = el("dt", {});
      if (svg) {
        const icon = el("span", { className: "icon" });
        icon.innerHTML = svg;
        term.append(icon);
      }
      term.append(name);
      if (text) list.append(term, el("dd", { textContent: text }));
      else list.append(term);
    }
    return title ? el("div", {}, el("h3", { textContent: title }), list) : list;
  }

  // --- palette and controls ------------------------------------------------

  private paletteBar(): HTMLElement {
    const bar = el("div", { className: "palette" });
    bar.setAttribute("role", "radiogroup");
    bar.setAttribute("aria-label", "Palette");
    const figures = this.bundle.clueEntries ? [] : this.bundle.palette ?? [];
    const items: (PaletteItem | null)[] = [...figures, null];
    for (const item of items) {
      const id = item?.id ?? CROSS;
      const button = el("button", { type: "button", className: "tool" });
      button.setAttribute("role", "radio");
      if (item) {
        const swatch = el("span", { className: "swatch" });
        if (item.svg) swatch.innerHTML = item.svg;
        else swatch.textContent = item.symbol;
        button.append(swatch);
        if (item.svg || item.label !== item.symbol) button.append(el("span", { textContent: item.label }));
        button.title = item.description ? `${item.label}: ${item.description}` : item.label;
        swatch.append(this.usedCross());
      } else {
        button.append(el("span", { className: "swatch cross", textContent: "✕" }), el("span", { textContent: "Cross" }));
        button.title = "Cross tool (also right-click or long-press)";
      }
      button.dataset.baseTitle = button.title;
      button.addEventListener("click", () => this.selectTool(id));
      this.paletteButtons.set(id, button);
      bar.append(button);
    }
    if (this.bundle.notes) {
      this.notesButton.append(el("span", { className: "swatch", textContent: "✎" }), el("span", { textContent: "Notes" }));
      this.notesButton.title = "Pencil marks: digits go in as small notes (key N)";
      this.notesButton.addEventListener("click", () => this.setNotesMode(!this.notesMode));
      this.setNotesMode(false);
      bar.append(this.notesButton);
    }
    return bar;
  }

  /**
   * The grey cross over a palette button whose item is already on the board.
   * `preserveAspectRatio="none"` keeps the two lines corner to corner whatever
   * the button's width, so it reads like the auto-mark on a cell.
   */
  private usedCross(): SVGElement {
    const svg = svgEl("svg", {
      class: "used-cross",
      viewBox: "0 0 100 100",
      preserveAspectRatio: "none",
      "aria-hidden": "true",
    });
    const pad = 18;
    svg.append(
      svgEl("line", { x1: pad, y1: pad, x2: 100 - pad, y2: 100 - pad }),
      svgEl("line", { x1: 100 - pad, y1: pad, x2: pad, y2: 100 - pad }),
    );
    return svg;
  }

  private selectTool(id: string): void {
    this.tool = id;
    for (const [key, button] of this.paletteButtons) button.setAttribute("aria-checked", String(key === id));
    for (const [key, button] of this.entryButtons) {
      button.setAttribute("aria-pressed", String(key === id));
      button.closest(".figure-entry")?.classList.toggle("selected", key === id);
    }
  }

  private setNotesMode(on: boolean): void {
    this.notesMode = on;
    this.notesButton.setAttribute("aria-pressed", String(on));
  }

  private controls(): HTMLElement {
    this.undoButton.addEventListener("click", () => this.undo());
    this.redoButton.addEventListener("click", () => this.redo());
    const clear = el("button", { type: "button", textContent: "Clear" });
    clear.addEventListener("click", () => this.clearBoard());
    const checkButton = el("button", { type: "button", textContent: "Check", className: "primary" });
    checkButton.addEventListener("click", () => this.showVerdict());
    return el("div", { className: "controls" }, this.undoButton, this.redoButton, clear, checkButton);
  }

  private clearBoard(): void {
    this.commit({ ...emptyState(this.bundle), auto: this.state.auto, warnings: this.state.warnings });
    this.verdict.textContent = "";
    this.verdict.className = "verdict";
  }

  private showVerdict(): void {
    const verdict = check(this.bundle, this.state);
    this.verdict.className = `verdict ${verdict.status}`;
    const missingItem = this.bundle.totals?.mine === undefined
      ? undefined
      : {
          singular: this.bundle.language === "nl" ? "mijn" : "mine",
          plural: this.bundle.language === "nl" ? "mijnen" : "mines",
        };
    this.verdict.textContent = verdictText(
      verdict, this.bundle.language, this.bundle.reveal, missingItem,
    );
    if (verdict.status === "solved") celebrate();
  }

  // --- state changes -------------------------------------------------------

  private commit(next: State): void {
    this.working = null;
    if (this.history.push(next)) this.changed();
    else this.redraw();
  }

  private undo(): void {
    if (this.history.undo()) this.changed();
  }

  private redo(): void {
    if (this.history.redo()) this.changed();
  }

  private changed(): void {
    save(this.bundle, this.history.current);
    this.verdict.textContent = "";
    this.verdict.className = "verdict";
    this.redraw();
  }

  // --- board ---------------------------------------------------------------

  private setUpBoard(board: HTMLElement): void {
    const svg = board.querySelector("svg");
    if (!svg) return;
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    for (const rect of svg.querySelectorAll<SVGRectElement>("rect.cell")) {
      const box = {
        x: Number(rect.getAttribute("x")),
        y: Number(rect.getAttribute("y")),
        w: Number(rect.getAttribute("width")),
        h: Number(rect.getAttribute("height")),
      };
      this.boxes.set(rect.id, box);
      this.cells.set(rect.id, rect);
      rect.setAttribute("aria-label", rect.id);
    }
    this.overlay = svgEl("g", { class: "overlay", "pointer-events": "none" }) as SVGGElement;
    const cells = svg.querySelector("g.cells");
    svg.insertBefore(this.overlay, cells);
    for (const item of this.bundle.palette ?? []) {
      if (!item.svg) continue;
      const parsed = new DOMParser().parseFromString(item.svg, "image/svg+xml").documentElement;
      if (parsed instanceof SVGSVGElement) this.icons.set(item.id, parsed);
    }
    if (!this.bundle.playable) return;
    this.selectTool(this.tool);
    this.listen(board, svg);
  }

  private cellForTarget(target: EventTarget | null): CellId | null {
    return target instanceof SVGRectElement && target.classList.contains("cell") && this.boxes.has(target.id)
      ? target.id
      : null;
  }

  private cellAt(x: number, y: number): CellId | null {
    return this.cellForTarget(document.elementFromPoint(x, y));
  }

  private cellLines(cell: CellId, occupants = occupied(this.bundle, this.state)): string[] {
    const details = this.bundle.cellDetails?.[cell];
    if (!details) return [];
    const lines = [`${this.heading("cell", "Cell")}: ${cell}`, ...details];
    const item = occupants[cell];
    if (item) {
      const label = this.bundle.palette?.find((candidate) => candidate.id === item)?.label ?? item;
      lines.push(`${this.heading("cell_figure", "Figure")}: ${label}`);
    }
    return lines;
  }

  private showCellTooltip(cell: CellId, x: number, y: number, keyboard = false): void {
    if (!this.bundle.cellDetails?.[cell]) {
      this.hideCellTooltip();
      return;
    }
    this.currentTooltip = { cell, x, y, keyboard };
    this.refreshCellTooltip();
  }

  private showKeyboardTooltip(cell: CellId): void {
    const rect = this.cells.get(cell);
    if (!rect) return;
    const box = rect.getBoundingClientRect();
    this.showCellTooltip(cell, box.left + box.width / 2, box.top + box.height / 2, true);
  }

  private refreshCellTooltip(): void {
    if (!this.currentTooltip) return;
    const { cell, x, y, keyboard } = this.currentTooltip;
    const lines = this.cellLines(cell);
    const text = lines.join("\n");
    if (this.tooltip.textContent !== text) this.tooltip.textContent = text;
    this.tooltip.hidden = false;
    const pad = 8;
    this.tooltip.style.left = `${Math.max(pad, Math.min(x + 14, window.innerWidth - this.tooltip.offsetWidth - pad))}px`;
    this.tooltip.style.top = `${Math.max(pad, Math.min(y + 18, window.innerHeight - this.tooltip.offsetHeight - pad))}px`;
    const announcement = keyboard ? lines.join("; ") : "";
    if (this.cellStatus.textContent !== announcement) this.cellStatus.textContent = announcement;
  }

  private hideCellTooltip(): void {
    this.currentTooltip = null;
    this.tooltip.hidden = true;
    this.tooltip.textContent = "";
    this.cellStatus.textContent = "";
  }

  private listen(board: HTMLElement, svg: SVGSVGElement): void {
    let press: { cell: CellId; timer: number | null; cross: boolean | null; pointer: number } | null = null;
    const startCross = (cell: CellId) => {
      const value = !this.state.crosses.includes(cell);
      this.working = setCross(this.bundle, this.history.current, cell, value);
      this.redraw();
      return value;
    };
    svg.addEventListener("contextmenu", (event) => event.preventDefault());
    svg.addEventListener("pointerdown", (event) => {
      const cell = this.cellAt(event.clientX, event.clientY);
      if (!cell || press || (event.button !== 0 && event.button !== 2)) return;
      this.hideCellTooltip();
      // Keep the pointer's events even if it leaves the board, so a press always ends.
      try {
        svg.setPointerCapture(event.pointerId);
      } catch {
        // Synthetic or already-released pointers cannot be captured; nothing to keep.
      }
      this.cursor = cell;
      const crossNow = event.button === 2 || this.tool === CROSS;
      press = { cell, timer: null, cross: null, pointer: event.pointerId };
      if (crossNow) {
        press.cross = startCross(cell);
        event.preventDefault();
      } else if (event.pointerType !== "mouse") {
        const current = press;
        current.timer = window.setTimeout(() => {
          current.timer = null;
          current.cross = startCross(current.cell);
          navigator.vibrate?.(15);
        }, LONG_PRESS_MS);
      }
      this.redraw();
    });
    svg.addEventListener("pointermove", (event) => {
      if (press) {
        if (event.pointerId === press.pointer && press.cross !== null) {
          const cell = this.cellAt(event.clientX, event.clientY);
          if (cell && this.working) {
            this.working = setCross(this.bundle, this.working, cell, press.cross);
            this.redraw();
          }
        }
      } else if (event.pointerType !== "touch") {
        const cell = this.cellForTarget(event.target);
        if (cell) this.showCellTooltip(cell, event.clientX, event.clientY);
        else this.hideCellTooltip();
      }
    });
    svg.addEventListener("pointerleave", () => {
      if (!press && !this.currentTooltip?.keyboard) this.hideCellTooltip();
    });
    const finish = (event: PointerEvent, cancelled: boolean) => {
      if (!press || event.pointerId !== press.pointer) return;
      const current = press;
      press = null;
      if (current.timer !== null) window.clearTimeout(current.timer);
      if (current.cross !== null) {
        this.commit(this.working ?? this.history.current);
      } else if (!cancelled) {
        this.apply(current.cell);
      }
      if (!cancelled && event.pointerType !== "touch") {
        const cell = this.cellAt(event.clientX, event.clientY);
        if (cell) this.showCellTooltip(cell, event.clientX, event.clientY);
      }
    };
    svg.addEventListener("pointerup", (event) => finish(event, false));
    svg.addEventListener("pointercancel", (event) => finish(event, true));
    svg.addEventListener("lostpointercapture", (event) => finish(event, true));
    svg.style.touchAction = "none";

    board.addEventListener("keydown", (event) => this.key(event));
    board.addEventListener("focus", () => {
      if (!press && this.cursor && board.matches(":focus-visible")) this.showKeyboardTooltip(this.cursor);
    });
    board.addEventListener("blur", () => {
      if (this.currentTooltip?.keyboard) this.hideCellTooltip();
    });
  }

  private apply(cell: CellId): void {
    const next = this.tool === CROSS ? setCross(this.bundle, this.state, cell)
      : this.notesMode ? toggleNote(this.bundle, this.state, cell, this.tool)
      : place(this.bundle, this.state, cell, this.tool);
    const conflict = next !== this.state && this.tool !== CROSS
      && (this.notesMode ? next.notes[cell]?.includes(this.tool) : next.placed[cell] === this.tool)
      ? placementConflict(this.bundle, next, cell, this.tool) : null;
    this.commit(next);
    if (conflict) {
      this.verdict.className = "verdict wrong";
      this.verdict.textContent = conflictText(this.tool, conflict.cell, this.bundle.language, conflict.description);
    }
  }

  private key(event: KeyboardEvent): void {
    const [rows, cols] = this.bundle.size;
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "z") {
      event.shiftKey ? this.redo() : this.undo();
    } else if (mod && event.key.toLowerCase() === "y") {
      this.redo();
    } else if (event.key.startsWith("Arrow")) {
      const [r, c] = this.cursor ? parseCell(this.cursor) : [1, 1];
      const [dr, dc] = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[
        event.key
      ] ?? [0, 0];
      const next = this.cursor ? [r + dr, c + dc] : [1, 1];
      this.cursor = cellId(Math.min(rows, Math.max(1, next[0])), Math.min(cols, Math.max(1, next[1])));
      this.redraw();
      this.showKeyboardTooltip(this.cursor);
    } else if ((event.key === " " || event.key === "Enter") && this.cursor) {
      this.apply(this.cursor);
    } else if ((event.key === "Delete" || event.key === "Backspace") && this.cursor) {
      this.commit(clearCell(this.bundle, this.state, this.cursor));
    } else if (event.key.toLowerCase() === "n" && !mod && this.bundle.notes) {
      this.setNotesMode(!this.notesMode);
    } else if (event.key.toLowerCase() === "x" && !mod) {
      if (this.cursor) this.commit(setCross(this.bundle, this.state, this.cursor));
      else this.selectTool(CROSS);
    } else if (!mod && this.paletteButtons.has(event.key)) {
      this.selectTool(event.key);
      if (this.cursor) this.apply(this.cursor);
    } else if (!mod && /^[1-9]$/.test(event.key)) {
      const item = this.bundle.palette?.[Number(event.key) - 1];
      if (item) this.selectTool(item.id);
    } else if (event.key === "Escape" && this.currentTooltip) {
      this.hideCellTooltip();
    } else {
      return;
    }
    event.preventDefault();
  }

  private redraw(): void {
    const state = this.state;
    const mineCount = mineCounter(this.bundle, state);
    this.mineCount.hidden = mineCount === null;
    this.mineCount.textContent = mineCount?.text ?? "";
    this.mineCount.className = `mine-counter${mineCount?.overLimit ? " wrong" : ""}`;
    this.undoButton.disabled = !this.history.canUndo;
    this.redoButton.disabled = !this.history.canRedo;
    this.autoBox.checked = state.auto;
    this.warningsBox.checked = state.warnings;
    const used = usedItems(this.bundle, state);
    for (const [id, button] of this.paletteButtons) {
      const crossed = used.has(id);
      button.classList.toggle("used", crossed);
      button.title = crossed
        ? `${button.dataset.baseTitle ?? ""} — ${this.bundle.language === "nl" ? "al geplaatst" : "already placed"}`
        : button.dataset.baseTitle ?? "";
    }
    for (const [id, button] of this.entryButtons) button.classList.toggle("used", used.has(id));
    this.clueBoxes.forEach(({ box, index }) => {
      box.checked = state.usedClues.includes(index);
      box.closest("li")?.classList.toggle("used", box.checked);
    });
    const occupants = occupied(this.bundle, state);
    const placements = Object.entries(occupants);
    for (const [id, label] of this.placementLabels) {
      const cells = placements.filter(([, item]) => item === id).map(([cell]) => cell);
      label.closest(".figure-entry")?.classList.toggle("placed", cells.length > 0);
      label.textContent = cells.length
        ? `✓ ${this.bundle.language === "nl" ? "Geplaatst" : "Placed"}: ${cells.join(", ")}`
        : this.bundle.language === "nl" ? "Nog te plaatsen" : "Not placed yet";
    }
    if (this.bundle.cellDetails) {
      for (const [cell, rect] of this.cells) {
        rect.setAttribute("aria-label", this.cellLines(cell, occupants).join("; ") || cell);
      }
      this.refreshCellTooltip();
    }
    if (!this.overlay) return;
    const marks = autoMarks(this.bundle, state);
    const parts: SVGElement[] = [];
    if (this.bundle.autoMark?.mark === "light") {
      const lit = state.auto ? new Set([...marks, ...Object.keys(occupied(this.bundle, state))]) : [];
      for (const cell of lit) parts.push(this.light(cell));
    } else {
      for (const cell of marks) {
        if (!state.crosses.includes(cell) && !(cell in state.placed)) parts.push(this.cross(cell, "auto"));
      }
    }
    const struck = struckNotes(this.bundle, state);
    for (const [cell, items] of Object.entries(state.notes)) {
      if (!(cell in state.placed)) parts.push(this.notes(cell, items, struck.get(cell)));
    }
    for (const cell of state.crosses) parts.push(this.cross(cell, "manual"));
    for (const [cell, item] of Object.entries(state.placed)) parts.push(this.piece(cell, item));
    if (this.cursor && this.boxes.has(this.cursor)) {
      const { x, y, w, h } = this.boxes.get(this.cursor)!;
      const inset = Math.max(2, w * 0.04);
      parts.push(
        svgEl("rect", {
          class: `cursor${locked(this.bundle, this.cursor) ? " locked" : ""}`,
          x: x + inset / 2,
          y: y + inset / 2,
          width: w - inset,
          height: h - inset,
        }),
      );
    }
    this.overlay.replaceChildren(...parts);
  }

  private light(cell: CellId): SVGElement {
    const { x, y, w, h } = this.boxes.get(cell)!;
    return svgEl("rect", { class: "lit", x, y, width: w, height: h });
  }

  /** Pencil marks in a small grid, each digit in its own spot; ruled-out ones are hidden. */
  private notes(cell: CellId, items: string[], struck: Set<string> | undefined): SVGElement {
    const { x, y, w, h } = this.boxes.get(cell)!;
    const palette = this.bundle.palette ?? [];
    const side = Math.max(3, Math.ceil(Math.sqrt(palette.length)));
    const group = svgEl("g", { class: "notes", "font-size": (Math.min(w, h) / side) * 0.8 });
    for (const item of items) {
      if (struck?.has(item)) continue;
      const index = palette.findIndex((entry) => entry.id === item);
      if (index < 0) continue;
      const text = svgEl("text", {
        x: x + (w * ((index % side) + 0.5)) / side,
        y: y + (h * (Math.floor(index / side) + 0.78)) / side,
      });
      text.textContent = palette[index].symbol;
      group.append(text);
    }
    return group;
  }

  private cross(cell: CellId, kind: "auto" | "manual"): SVGElement {
    const { x, y, w, h } = this.boxes.get(cell)!;
    const pad = Math.min(w, h) * 0.3;
    const group = svgEl("g", { class: `mark ${kind}`, "stroke-width": Math.min(w, h) * 0.06 });
    group.append(
      svgEl("line", { x1: x + pad, y1: y + pad, x2: x + w - pad, y2: y + h - pad }),
      svgEl("line", { x1: x + w - pad, y1: y + pad, x2: x + pad, y2: y + h - pad }),
    );
    return group;
  }

  private piece(cell: CellId, itemId: string): SVGElement {
    const { x, y, w, h } = this.boxes.get(cell)!;
    const item = this.bundle.palette?.find((candidate) => candidate.id === itemId);
    const group = svgEl("g", { class: "piece" });
    const icon = this.icons.get(itemId);
    const labelled = this.bundle.placement?.perItem === 1;
    if (icon) {
      const size = Math.min(w, h) * (labelled ? 0.6 : 0.92);
      const copy = icon.cloneNode(true) as SVGSVGElement;
      copy.setAttribute("x", String(x + (w - size) / 2));
      copy.setAttribute("y", String(labelled ? y + h * 0.06 : y + (h - size) / 2));
      copy.setAttribute("width", String(size));
      copy.setAttribute("height", String(size));
      group.append(copy);
    }
    if (labelled) {
      const name = item?.label ?? itemId;
      const fontSize = Math.min(h * (icon ? 0.2 : 0.26), (w * 0.9) / Math.max(3, name.length * 0.58));
      const tagWidth = Math.min(w * 0.94, name.length * fontSize * 0.62 + fontSize);
      const tagY = icon ? y + h * 0.7 : y + (h - fontSize * 1.5) / 2;
      group.append(
        svgEl("rect", {
          class: "tag",
          x: x + (w - tagWidth) / 2,
          y: tagY,
          width: tagWidth,
          height: fontSize * 1.5,
          rx: fontSize * 0.4,
        }),
      );
      const text = svgEl("text", { x: x + w / 2, y: tagY + fontSize * 1.08, "font-size": fontSize });
      text.textContent = name;
      group.append(text);
    } else if (!icon) {
      const text = svgEl("text", { class: "symbol", x: x + w / 2, y: y + h * 0.68, "font-size": h * 0.55 });
      text.textContent = item?.symbol ?? itemId;
      group.append(text);
    }
    return group;
  }
}
