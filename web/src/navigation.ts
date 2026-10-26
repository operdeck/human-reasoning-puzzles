export interface PuzzleNavigationEntry {
  id: string;
  title: string;
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
