export interface PuzzleNavigationEntry {
  id: string;
  title: string;
}

/** A crawlable link to the puzzle's canonical page. */
export function puzzleLink(id: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.href = new URL(`p/${encodeURIComponent(id)}/`, document.baseURI).href;
  // The dev server has no prerendered puzzle pages; keep its player usable.
  if (import.meta.env.DEV) {
    link.addEventListener("click", (event) => {
      if (event.defaultPrevented || event.button !== 0 ||
          event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      window.location.hash = encodeURIComponent(id);
    });
  }
  return link;
}

export function adjacentPuzzles(
  puzzles: readonly PuzzleNavigationEntry[],
  id: string,
): { previous?: PuzzleNavigationEntry; next?: PuzzleNavigationEntry } {
  const index = puzzles.findIndex((puzzle) => puzzle.id === id);
  return {
    previous: index > 0 ? puzzles[index - 1] : undefined,
    next: index >= 0 && index < puzzles.length - 1 ? puzzles[index + 1] : undefined,
  };
}
