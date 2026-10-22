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
  restore,
  setCross,
  struckNotes,
  toggleClue,
  toggleNote,
  cellId,
  type Bundle,
  type CellId,
  type PaletteItem,
  type State,
} from "./game";

const SVG_NS = "http://www.w3.org/2000/svg";
const CROSS = "__cross__";
const LONG_PRESS_MS = 450;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> & { className?: string } = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
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

/** One puzzle: the board from the export, an overlay for the player's moves, and the panel. */
export class PuzzleView {
  private history: History;
  private working: State | null = null;
  private tool: string;
  private cursor: CellId | null = null;
  private boxes = new Map<CellId, Box>();
  private overlay!: SVGGElement;
  private icons = new Map<string, SVGSVGElement>();
  private paletteButtons = new Map<string, HTMLButtonElement>();
  private verdict = el("p", { className: "verdict" });
  private undoButton = el("button", { type: "button", textContent: "Undo" });
  private redoButton = el("button", { type: "button", textContent: "Redo" });
  private autoBox = el("input", { type: "checkbox" });
  private notesMode = false;
  private notesButton = el("button", { type: "button", className: "tool notes-toggle" });
  private clueBoxes: HTMLInputElement[] = [];

  constructor(
    private bundle: Bundle,
    private boardSvg: string,
  ) {
    this.history = new History(load(bundle));
    this.tool = bundle.palette?.[0]?.id ?? CROSS;
    this.verdict.setAttribute("aria-live", "polite");
  }

  private get state(): State {
    return this.working ?? this.history.current;
  }

  render(root: HTMLElement): void {
    const b = this.bundle;
    document.title = `${b.title} · Human reasoning puzzles`;
    const header = el(
      "header",
      { className: "puzzle-header" },
      el("a", { href: "#", className: "back", textContent: "← All puzzles" }),
      el("h1", { textContent: b.title }),
    );
    if (b.playable && b.autoMark && (b.autoMark.onPlace.length > 0 || (b.notes && b.peers?.length))) {
      this.autoBox.checked = this.state.auto;
      this.autoBox.addEventListener("change", () =>
        this.commit({ ...this.state, auto: this.autoBox.checked }),
      );
      header.append(el("label", { className: "auto" }, this.autoBox, " Auto-mark"));
    }

    const board = el("div", { className: "board", tabIndex: 0 });
    board.setAttribute("role", "application");
    board.setAttribute("aria-label", "Puzzle board; arrow keys move, space places");
    board.innerHTML = this.boardSvg;
    const play = el("section", { className: "play" }, board);
    if (b.playable) {
      play.append(this.paletteBar(), this.controls(), this.verdict);
    } else {
      play.append(el("p", { className: "note", textContent: b.unsupported ?? "Not playable yet." }));
    }

    root.replaceChildren(
      header,
      el("div", { className: "layout" }, play, this.panel()),
      el("footer", {}, this.licence()),
    );
    this.setUpBoard(board);
    this.redraw();
  }

  private licence(): HTMLElement {
    return el(
      "p",
      {},
      this.bundle.license + " ",
      el("a", {
        href: "https://github.com/operdeck/human-reasoning-puzzles/blob/main/examples/LICENSE.md",
        textContent: "Licence",
      }),
    );
  }

  // --- panel: clues, rules, conditions -------------------------------------

  private heading(key: string, fallback: string): string {
    return this.bundle.headings?.[key] ?? fallback;
  }

  private panel(): HTMLElement {
    const b = this.bundle;
    const sections: [string, string, HTMLElement][] = [];
    if (b.clues.length > 0 || b.question) {
      const list = el("ol", { className: "clues" });
      b.clues.forEach((clue, index) => {
        const box = el("input", { type: "checkbox", title: "Mark this clue as used" });
        box.addEventListener("change", () => this.commit(toggleClue(this.state, index)));
        this.clueBoxes.push(box);
        list.append(el("li", {}, el("label", {}, el("span", { textContent: clue }), box)));
      });
      const section = el("div", {}, list);
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
      sections.push(["clues", this.heading("clues", "Clues"), section]);
    }
    const rules = el("div", {}, el("ul", {}, ...b.rules.map((rule) => el("li", { textContent: rule }))));
    const described = (b.palette ?? []).filter((item) => item.description);
    if (described.length > 0) rules.append(this.namedList(this.heading("figures", "The figures"),
      described.map((item) => ({ name: item.label, text: item.description ?? "" }))));
    if (b.attributes?.length) rules.append(this.namedList(this.heading("attributes", "Attributes"), b.attributes));
    if (b.roles?.length) rules.append(this.namedList(this.heading("roles", "Roles"), b.roles));
    sections.push(["rules", this.heading("rules_title", "Rules"), rules]);
    if (b.conditions.length > 0) {
      sections.push(["conditions", this.heading("conditions", "Conditions"), this.namedList(null, b.conditions)]);
    }

    const tabs = el("div", { className: "tabs" });
    tabs.setAttribute("role", "tablist");
    const aside = el("aside", { className: "panel" }, tabs);
    const select = (name: string) => {
      for (const node of aside.querySelectorAll<HTMLElement>("[data-tab]")) {
        node.classList.toggle("active", node.dataset.tab === name);
        if (node instanceof HTMLButtonElement) node.setAttribute("aria-selected", String(node.dataset.tab === name));
      }
    };
    for (const [name, title, body] of sections) {
      const tab = el("button", { type: "button", textContent: title });
      tab.dataset.tab = name;
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", () => select(name));
      tabs.append(tab);
      const section = el("section", { className: "panel-section" }, el("h2", { textContent: title }), body);
      section.dataset.tab = name;
      aside.append(section);
    }
    select(sections[0][0]);
    return aside;
  }

  private namedList(title: string | null, items: { name: string; text: string }[]): HTMLElement {
    const list = el("dl", {});
    for (const { name, text } of items) list.append(el("dt", { textContent: name }), el("dd", { textContent: text }));
    return title ? el("div", {}, el("h3", { textContent: title }), list) : list;
  }

  // --- palette and controls ------------------------------------------------

  private paletteBar(): HTMLElement {
    const bar = el("div", { className: "palette" });
    bar.setAttribute("role", "radiogroup");
    bar.setAttribute("aria-label", "Palette");
    const items: (PaletteItem | null)[] = [...(this.bundle.palette ?? []), null];
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
      } else {
        button.append(el("span", { className: "swatch cross", textContent: "✕" }), el("span", { textContent: "Cross" }));
        button.title = "Cross tool (also right-click or long-press)";
      }
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

  private selectTool(id: string): void {
    this.tool = id;
    for (const [key, button] of this.paletteButtons) button.setAttribute("aria-checked", String(key === id));
  }

  private setNotesMode(on: boolean): void {
    this.notesMode = on;
    this.notesButton.setAttribute("aria-pressed", String(on));
  }

  private controls(): HTMLElement {
    this.undoButton.addEventListener("click", () => this.undo());
    this.redoButton.addEventListener("click", () => this.redo());
    const clear = el("button", { type: "button", textContent: "Clear" });
    clear.addEventListener("click", () => {
      if (confirm("Clear the board?")) this.commit({ ...emptyState(this.bundle), auto: this.state.auto });
    });
    const checkButton = el("button", { type: "button", textContent: "Check", className: "primary" });
    checkButton.addEventListener("click", () => this.showVerdict());
    return el("div", { className: "controls" }, this.undoButton, this.redoButton, clear, checkButton);
  }

  private showVerdict(): void {
    const verdict = check(this.bundle, this.state);
    this.verdict.className = `verdict ${verdict.status}`;
    if (verdict.status === "solved") this.verdict.textContent = "Solved! Everything is in the right place.";
    else if (verdict.status === "wrong")
      this.verdict.textContent = `Not right: ${verdict.wrong} piece${verdict.wrong === 1 ? " is" : "s are"} in the wrong place.`;
    else this.verdict.textContent = `No mistakes so far; ${verdict.missing} still to place.`;
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

  private cellAt(x: number, y: number): CellId | null {
    const target = document.elementFromPoint(x, y);
    return target instanceof SVGRectElement && target.classList.contains("cell") && this.boxes.has(target.id)
      ? target.id
      : null;
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
      if (!cell || press) return;
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
      if (!press || event.pointerId !== press.pointer || press.cross === null) return;
      const cell = this.cellAt(event.clientX, event.clientY);
      if (cell && this.working) {
        this.working = setCross(this.bundle, this.working, cell, press.cross);
        this.redraw();
      }
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
    };
    svg.addEventListener("pointerup", (event) => finish(event, false));
    svg.addEventListener("pointercancel", (event) => finish(event, true));
    svg.style.touchAction = "none";

    board.addEventListener("keydown", (event) => this.key(event));
  }

  private apply(cell: CellId): void {
    if (this.tool === CROSS) this.commit(setCross(this.bundle, this.state, cell));
    else if (this.notesMode) this.commit(toggleNote(this.bundle, this.state, cell, this.tool));
    else this.commit(place(this.bundle, this.state, cell, this.tool));
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
    } else {
      return;
    }
    event.preventDefault();
  }

  private redraw(): void {
    const state = this.state;
    this.undoButton.disabled = !this.history.canUndo;
    this.redoButton.disabled = !this.history.canRedo;
    this.autoBox.checked = state.auto;
    this.clueBoxes.forEach((box, index) => {
      box.checked = state.usedClues.includes(index);
      box.closest("li")?.classList.toggle("used", box.checked);
    });
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
