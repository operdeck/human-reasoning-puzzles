// Game state and rules that know nothing of puzzle families: everything
// family-specific comes from the bundle that `csp --export` writes.

export type CellId = string;

export interface PaletteItem {
  id: string;
  label: string;
  symbol: string;
  svg?: string;
  description?: string;
}

export interface Scope {
  scope: "row" | "col" | "region" | "neighbors4" | "neighbors8" | "king" | "knight" | "peers";
  whenFull?: number;
}

/** Cells that may hold each of `items` (default: every palette item) at most once. */
export interface PeerGroup {
  cells: CellId[];
  items?: string[];
  description?: string;
}

export interface Named {
  name: string;
  text: string;
  svg?: string;
}

export interface Bundle {
  schema: number;
  id: string;
  family: string;
  section?: string;
  number?: number;
  title: string;
  grade: string;
  static: string;
  license: string;
  language: string;
  size: [number, number];
  playable: boolean;
  unsupported?: string;
  palette?: PaletteItem[];
  placement?: { perItem?: number; perCell?: number; blocked: CellId[] };
  autoMark?: { default: boolean; mark: "cross" | "light"; onPlace: Scope[] };
  peers?: PeerGroup[];
  notes?: boolean;
  givens?: Record<CellId, string>;
  solution?: Record<CellId, string>;
  regions?: Record<CellId, string>;
  headings?: Record<string, string>;
  rules: string[];
  clues: string[];
  conditions: Named[];
  question: string;
  reveal?: string;
  attributes?: Named[];
  roles?: Named[];
  objects?: Named[];
}

export interface State {
  placed: Record<CellId, string>;
  crosses: CellId[];
  notes: Record<CellId, string[]>;
  usedClues: number[];
  auto: boolean;
}

export function emptyState(bundle: Bundle): State {
  return { placed: {}, crosses: [], notes: {}, usedClues: [], auto: bundle.autoMark?.default ?? false };
}

export function cellId(row: number, col: number): CellId {
  return `r${row}c${col}`;
}

export function parseCell(id: CellId): [number, number] {
  const match = /^r(\d+)c(\d+)$/.exec(id);
  if (!match) throw new Error(`not a cell id: ${id}`);
  return [Number(match[1]), Number(match[2])];
}

export function allCells(bundle: Bundle): CellId[] {
  const [rows, cols] = bundle.size;
  const out: CellId[] = [];
  for (let r = 1; r <= rows; r++) for (let c = 1; c <= cols; c++) out.push(cellId(r, c));
  return out;
}

/** Cells the player can never change: blocked squares and givens. */
export function locked(bundle: Bundle, cell: CellId): boolean {
  return (bundle.placement?.blocked ?? []).includes(cell) || cell in (bundle.givens ?? {});
}

const KNIGHT = [[1, 2], [2, 1], [-1, 2], [-2, 1], [1, -2], [2, -1], [-1, -2], [-2, -1]];

const peerIndex = new WeakMap<Bundle, Map<CellId, PeerGroup[]>>();

/** The cells that may not hold `item` too once `cell` holds it, by the bundle's peer groups. */
export function peerCells(bundle: Bundle, cell: CellId, item: string): CellId[] {
  let index = peerIndex.get(bundle);
  if (!index) {
    index = new Map();
    for (const group of bundle.peers ?? []) {
      for (const member of group.cells) index.set(member, [...(index.get(member) ?? []), group]);
    }
    peerIndex.set(bundle, index);
  }
  const out = new Set<CellId>();
  for (const group of index.get(cell) ?? []) {
    if (group.items && !group.items.includes(item)) continue;
    for (const other of group.cells) if (other !== cell) out.add(other);
  }
  return [...out];
}

/** Explain an equal-item conflict without consulting the hidden solution. */
export function placementConflict(bundle: Bundle, state: State, cell: CellId, item: string):
  { cell: CellId; description?: string } | null {
  const pieces = occupied(bundle, state);
  for (const group of bundle.peers ?? []) {
    if (!group.cells.includes(cell) || (group.items && !group.items.includes(item))) continue;
    const other = group.cells.find((peer) => peer !== cell && pieces[peer] === item);
    if (other) return { cell: other, description: group.description };
  }
  return null;
}

/** The cells of `scope` that contain `cell`, without `cell` itself; `item` is what `cell` holds. */
export function scopeCells(bundle: Bundle, scope: Scope["scope"], cell: CellId, item = ""): CellId[] {
  const [row, col] = parseCell(cell);
  const [rows, cols] = bundle.size;
  const inside = ([r, c]: number[]) => r >= 1 && r <= rows && c >= 1 && c <= cols;
  const offsets = (list: number[][]) =>
    list.map(([dr, dc]) => [row + dr, col + dc]).filter(inside).map(([r, c]) => cellId(r, c));
  switch (scope) {
    case "row":
      return Array.from({ length: cols }, (_, c) => cellId(row, c + 1)).filter((other) => other !== cell);
    case "col":
      return Array.from({ length: rows }, (_, r) => cellId(r + 1, col)).filter((other) => other !== cell);
    case "region": {
      const region = bundle.regions?.[cell];
      if (region === undefined) return [];
      return allCells(bundle).filter((other) => other !== cell && bundle.regions?.[other] === region);
    }
    case "neighbors4":
      return offsets([[1, 0], [-1, 0], [0, 1], [0, -1]]);
    case "neighbors8":
    case "king":
      return offsets([[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]);
    case "knight":
      return offsets(KNIGHT);
    case "peers":
      return peerCells(bundle, cell, item);
  }
}

/** Every placement on the board: the puzzle's givens and the player's pieces. */
export function occupied(bundle: Bundle, state: State): Record<CellId, string> {
  return { ...state.placed, ...(bundle.givens ?? {}) };
}

/**
 * The cells auto-marked with a cross: derived from the placements, never stored,
 * so removing a piece or undoing a move cleans up its crosses by itself.
 */
export function autoMarks(bundle: Bundle, state: State): Set<CellId> {
  const marks = new Set<CellId>();
  if (!state.auto || !bundle.autoMark) return marks;
  const pieces = occupied(bundle, state);
  for (const [cell, item] of Object.entries(pieces)) {
    for (const rule of bundle.autoMark.onPlace) {
      const others = scopeCells(bundle, rule.scope, cell, item);
      if (rule.whenFull !== undefined) {
        const count = 1 + others.filter((other) => other in pieces).length;
        if (count < rule.whenFull) continue;
      }
      for (const other of others) marks.add(other);
    }
  }
  for (const cell of Object.keys(pieces)) marks.delete(cell);
  for (const cell of bundle.placement?.blocked ?? []) marks.delete(cell);
  return marks;
}

/**
 * Pencil marks ruled out by a placement: `cell` maps to the noted items that a
 * peer already holds. Derived like the auto marks, so they come back on undo.
 */
export function struckNotes(bundle: Bundle, state: State): Map<CellId, Set<string>> {
  const struck = new Map<CellId, Set<string>>();
  if (!state.auto) return struck;
  const pieces = occupied(bundle, state);
  for (const [cell, items] of Object.entries(state.notes)) {
    if (cell in pieces) continue;
    for (const item of items) {
      if (peerCells(bundle, cell, item).some((other) => pieces[other] === item)) {
        if (!struck.has(cell)) struck.set(cell, new Set());
        struck.get(cell)!.add(item);
      }
    }
  }
  return struck;
}

/** Add or remove the pencil mark `item` on an empty `cell`. */
export function toggleNote(bundle: Bundle, state: State, cell: CellId, item: string): State {
  if (!bundle.notes || locked(bundle, cell) || cell in state.placed) return state;
  const current = state.notes[cell] ?? [];
  const order = (bundle.palette ?? []).map((entry) => entry.id);
  const next = current.includes(item)
    ? current.filter((other) => other !== item)
    : [...current, item].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const notes = { ...state.notes };
  if (next.length > 0) notes[cell] = next;
  else delete notes[cell];
  return { ...state, notes };
}

/** Place `item` on `cell`, or take it off if it is already there. */
export function place(bundle: Bundle, state: State, cell: CellId, item: string): State {
  if (locked(bundle, cell)) return state;
  const placed = { ...state.placed };
  if (placed[cell] === item) {
    delete placed[cell];
  } else {
    if (bundle.placement?.perItem === 1) {
      for (const [other, there] of Object.entries(placed)) if (there === item) delete placed[other];
    }
    placed[cell] = item;
  }
  return { ...state, placed, crosses: state.crosses.filter((other) => other !== cell) };
}

/** Empty `cell`: no piece, no manual cross and no pencil marks. */
export function clearCell(bundle: Bundle, state: State, cell: CellId): State {
  if (locked(bundle, cell)) return state;
  const placed = { ...state.placed };
  delete placed[cell];
  const notes = { ...state.notes };
  delete notes[cell];
  return { ...state, placed, notes, crosses: state.crosses.filter((other) => other !== cell) };
}

/** Set or remove a manual cross; `on` undefined toggles it. Pieces are left alone. */
export function setCross(bundle: Bundle, state: State, cell: CellId, on?: boolean): State {
  if (locked(bundle, cell) || cell in state.placed) return state;
  const has = state.crosses.includes(cell);
  const want = on ?? !has;
  if (want === has) return state;
  const crosses = want ? [...state.crosses, cell] : state.crosses.filter((other) => other !== cell);
  return { ...state, crosses };
}

export function toggleClue(state: State, index: number): State {
  const usedClues = state.usedClues.includes(index)
    ? state.usedClues.filter((other) => other !== index)
    : [...state.usedClues, index].sort((a, b) => a - b);
  return { ...state, usedClues };
}

export type Verdict =
  | { status: "solved" }
  | { status: "incomplete"; missing: number }
  | { status: "wrong"; wrong: number };

/** Compare the player's pieces with the solution; crosses count as empty. */
export function check(bundle: Bundle, state: State): Verdict {
  const solution = bundle.solution ?? {};
  const givens = bundle.givens ?? {};
  let wrong = 0;
  let missing = 0;
  for (const [cell, item] of Object.entries(state.placed)) {
    if (cell in givens) continue;
    if (solution[cell] !== item) wrong++;
  }
  for (const [cell, item] of Object.entries(solution)) {
    if (cell in givens) continue;
    if (state.placed[cell] === undefined && item !== undefined) missing++;
  }
  if (wrong > 0) return { status: "wrong", wrong };
  if (missing > 0) return { status: "incomplete", missing };
  return { status: "solved" };
}

/** Undo and redo over whole states. */
export class History {
  private past: State[] = [];
  private future: State[] = [];

  constructor(public current: State) {}

  push(next: State): boolean {
    if (JSON.stringify(next) === JSON.stringify(this.current)) return false;
    this.past.push(this.current);
    this.future = [];
    this.current = next;
    return true;
  }

  undo(): boolean {
    const previous = this.past.pop();
    if (!previous) return false;
    this.future.push(this.current);
    this.current = previous;
    return true;
  }

  redo(): boolean {
    const next = this.future.pop();
    if (!next) return false;
    this.past.push(this.current);
    this.current = next;
    return true;
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }

  get canRedo(): boolean {
    return this.future.length > 0;
  }
}

/** Read a saved state, ignoring anything that no longer fits the puzzle. */
export function restore(bundle: Bundle, saved: unknown): State {
  const state = emptyState(bundle);
  if (typeof saved !== "object" || saved === null) return state;
  const raw = saved as Record<keyof State, unknown>;
  const cells = new Set(allCells(bundle));
  const items = new Set((bundle.palette ?? []).map((item) => item.id));
  const free = (cell: unknown): cell is CellId =>
    typeof cell === "string" && cells.has(cell) && !locked(bundle, cell);
  if (typeof raw.placed === "object" && raw.placed !== null) {
    for (const [cell, item] of Object.entries(raw.placed)) {
      if (free(cell) && typeof item === "string" && items.has(item)) state.placed[cell] = item;
    }
  }
  if (Array.isArray(raw.crosses)) {
    state.crosses = [...new Set(raw.crosses)].filter((cell) => free(cell) && !(cell in state.placed));
  }
  if (bundle.notes && typeof raw.notes === "object" && raw.notes !== null) {
    for (const [cell, noted] of Object.entries(raw.notes)) {
      if (!cells.has(cell) || locked(bundle, cell) || !Array.isArray(noted)) continue;
      const kept = [...items].filter((item) => noted.includes(item));
      if (kept.length > 0) state.notes[cell] = kept;
    }
  }
  if (Array.isArray(raw.usedClues)) {
    state.usedClues = [...new Set(raw.usedClues)]
      .filter((n): n is number => Number.isInteger(n) && n >= 0 && n < bundle.clues.length)
      .sort((a, b) => a - b);
  }
  if (typeof raw.auto === "boolean") state.auto = raw.auto;
  return state;
}
