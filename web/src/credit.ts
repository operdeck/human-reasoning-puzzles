// Credit where it is due: Murdoku is Manuel Garand's invention, not this project's.
//
// One line, shared by the puzzle index and the footer under a Murdoku board, so the
// wording cannot drift from the README or the prerendered pages (web/scripts/prerender.mjs
// carries the HTML twin of this text).
export const INVENTOR = "Manuel Garand";
export const INVENTOR_URL = "https://murdoku.com";

export function creditLine(): HTMLParagraphElement {
  const paragraph = document.createElement("p");
  paragraph.className = "credit";
  const inventor = document.createElement("a");
  inventor.href = INVENTOR_URL;
  inventor.textContent = INVENTOR;
  inventor.target = "_blank";
  inventor.rel = "noreferrer";
  inventor.title = "Murdoku books and free puzzles by their inventor";
  paragraph.append(
    "Murdoku was invented by ",
    inventor,
    ", whose books are better designed and more fun than the cases here: buy one and solve it with pen and paper.",
  );
  return paragraph;
}
