// Credit where it is due: Murdoku is Manuel Garand's invention, not this project's.
//
// One line, shared by the puzzle index and the footer under a Murdoku board.
// web/scripts/prerender.mjs carries the HTML twin for prerendered pages.
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
  paragraph.append("Murdoku was invented by ", inventor, ".");
  return paragraph;
}
