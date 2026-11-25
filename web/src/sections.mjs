// Link targets for the index's family sections, shared by the app and the
// prerendered pages so `#family-bridges` works with and without JavaScript.
//
// The app routes puzzles through the hash, so section anchors carry a prefix no
// puzzle id uses. This file is plain ESM so `scripts/prerender.mjs` can share it.

export const SECTION_PREFIX = "family-";

/**
 * The anchor id of an index section: "Murdoku · Japanese food" becomes
 * "family-murdoku-japanese-food".
 * @param {string} label
 * @returns {string}
 */
export function sectionAnchor(label) {
  const slug = label
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${SECTION_PREFIX}${slug}`;
}
