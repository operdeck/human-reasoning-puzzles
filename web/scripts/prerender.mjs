// Post-build step: turns the client-side player into something search engines can index.
//
// Reads dist/puzzles/index.json (written by `csp --export`) and writes, next to the built app:
//   - dist/index.html      the home page with a static puzzle list inside #app (the player replaces it)
//   - dist/murdoku/        a landing page for online Murdoku puzzles
//   - dist/p/<id>/         one static page per puzzle, linking into the player
//   - dist/sitemap.xml and dist/robots.txt
//
// No dependencies. Usage: node scripts/prerender.mjs [distDir]
// SITE_URL overrides the public address (default: the GitHub Pages URL).
//
// Site-verification meta tags (Google, Bing, Yandex) in web/index.html are copied into
// every prerendered <head>: the build's own head is replaced below, so a tag added there
// would otherwise vanish in dist/. robots.txt is written for completeness, but on a
// GitHub Pages project site it is not served from the domain root, so crawlers ignore it:
// submit sitemap.xml by hand instead. See docs/discoverability.md.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const SITE = (process.env.SITE_URL ?? "https://operdeck.github.io/human-reasoning-puzzles").replace(/\/$/, "");
const REPO = "https://github.com/operdeck/human-reasoning-puzzles";
const SITE_NAME = "Human reasoning puzzles";
const dist = path.resolve(process.argv[2] ?? "dist");

// The shell vite just built: it keeps the CSS/JS tags for the home page below, and carries
// whatever site-verification meta tags web/index.html had (head() below rebuilds the rest).
const built = await readFile(path.join(dist, "index.html"), "utf8");
const verificationTags = [
  ...built.matchAll(/<meta name="(?:google-site-verification|msvalidate\.01|yandex-verification)"[^>]*>/g),
].map((match) => match[0]);

const esc = (text) =>
  String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const isMurdoku = (entry) => entry.family === "murdoku";
const sizeText = (entry) => `${entry.size[0]}×${entry.size[1]}`;

function head({ title, description, canonical, image, jsonLd }) {
  return `<meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    ${verificationTags.map((tag) => `${tag}\n    `).join("")}<title>${esc(title)}</title>
    <meta name="description" content="${esc(description)}" />
    <link rel="canonical" href="${esc(canonical)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="${SITE_NAME}" />
    <meta property="og:title" content="${esc(title)}" />
    <meta property="og:description" content="${esc(description)}" />
    <meta property="og:url" content="${esc(canonical)}" />
    ${image ? `<meta property="og:image" content="${esc(image)}" />\n    <meta name="twitter:card" content="summary_large_image" />` : '<meta name="twitter:card" content="summary" />'}
    <script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, "\\u003c")}</script>`;
}

function groupBySection(puzzles) {
  const groups = new Map();
  for (const entry of puzzles) {
    const list = groups.get(entry.section) ?? [];
    list.push(entry);
    groups.set(entry.section, list);
  }
  return groups;
}

function puzzleList(entries, prefix) {
  return `<ul>${entries
    .map(
      (e) =>
        `<li><a href="${prefix}p/${encodeURIComponent(e.id)}/">${esc(e.title)}</a> <span class="meta">${sizeText(e)} · ${esc(e.grade)}</span></li>`,
    )
    .join("")}</ul>`;
}

function sectionsHtml(puzzles, prefix) {
  return [...groupBySection(puzzles)]
    .map(([label, entries]) => `<section><h2>${esc(label)}</h2>${puzzleList(entries, prefix)}</section>`)
    .join("\n");
}

const pageStyle = `<style>body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:0 auto;padding:1rem 16px}
img{max-width:100%;height:auto}.meta{color:#666;font-size:.9em}.cta{display:inline-block;padding:.5rem 1rem;background:#2ea44f;color:#fff;border-radius:6px;text-decoration:none;font-weight:600}</style>`;

const index = JSON.parse(await readFile(path.join(dist, "puzzles", "index.json"), "utf8"));
const puzzles = index.puzzles;
const murdoku = puzzles.filter(isMurdoku);
const families = [...new Set(puzzles.map((p) => p.familyLabel))];

// 1. Home page: keep the built shell (script/CSS tags) but put real content in #app and real metadata in <head>.
const homeDescription =
  `Play ${puzzles.length} free logic puzzles online: Murdoku murder mysteries, Sudoku, Queens, Star Battle, ` +
  `Kakuro, Zebra grids and more. Every puzzle can be solved by reasoning alone, with an open-source explainable solver.`;
const builtAssets = [...built.matchAll(/<(?:link rel="stylesheet"|script type="module")[^>]*>(?:<\/script>)?/g)].map(
  (m) => m[0],
);
const homeHead = head({
  title: `${SITE_NAME} – play Murdoku, Sudoku, Queens and more online`,
  description: homeDescription,
  canonical: `${SITE}/`,
  jsonLd: {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebSite", name: SITE_NAME, url: `${SITE}/`, description: homeDescription },
      {
        "@type": "SoftwareSourceCode",
        name: SITE_NAME,
        codeRepository: REPO,
        programmingLanguage: ["Python", "TypeScript"],
        license: "https://www.apache.org/licenses/LICENSE-2.0",
        description: "An explainable constraint solver and puzzle generator that solves logic puzzles the way a person would.",
      },
    ],
  },
});
const homeBody = `<main id="app">
      <header><h1>${SITE_NAME}</h1>
      <p>Logic puzzles that can be solved by reasoning alone, as a person would: ${esc(families.slice(0, 12).join(", "))} and more.
      Start with the <a href="murdoku/">Murdoku murder mysteries</a>, or browse the full list below.
      The solver behind them is <a href="${REPO}">open source</a>.</p></header>
      ${sectionsHtml(puzzles, "")}
    </main>`;
await writeFile(
  path.join(dist, "index.html"),
  `<!doctype html>\n<html lang="en">\n  <head>\n    ${homeHead}\n    ${builtAssets.join("\n    ")}\n  </head>\n  <body>\n    ${homeBody}\n  </body>\n</html>\n`,
);

// 2. Murdoku landing page.
const murdokuDescription =
  `Play free Murdoku online: ${murdoku.length} original murder-mystery logic puzzles. Place every suspect using the clues, ` +
  `find the murderer, and see a step-by-step explanation of the solution.`;
await mkdir(path.join(dist, "murdoku"), { recursive: true });
await writeFile(
  path.join(dist, "murdoku", "index.html"),
  `<!doctype html>\n<html lang="en">\n  <head>\n    ${head({
    title: `Murdoku online – free murder mystery logic puzzles | ${SITE_NAME}`,
    description: murdokuDescription,
    canonical: `${SITE}/murdoku/`,
    jsonLd: { "@context": "https://schema.org", "@type": "CollectionPage", name: "Murdoku puzzles", url: `${SITE}/murdoku/`, description: murdokuDescription },
  })}\n    ${pageStyle}\n  </head>\n  <body>
    <p><a href="../">← All puzzles</a></p>
    <h1>Murdoku online</h1>
    <p>Murdoku is a murder-mystery logic puzzle: place each suspect on the floor plan so that nobody shares a row or column,
    use the clues to work out who stood where, and find the murderer, who is alone with the victim.
    These original cases play in your browser, with notes, auto-marking and explanations. Every one can be solved by deduction, with no guessing.</p>
    ${sectionsHtml(murdoku, "../")}
    <p>Curious how it works? The explainable solver and puzzle generator are <a href="${REPO}">open source on GitHub</a>.</p>
  </body>\n</html>\n`,
);

// 3. One static page per puzzle.
for (const entry of puzzles) {
  const url = `${SITE}/p/${encodeURIComponent(entry.id)}/`;
  const image = `${SITE}/puzzles/${encodeURIComponent(entry.id)}.svg`;
  const what = isMurdoku(entry) ? "Murdoku murder mystery" : `${entry.familyLabel} puzzle`;
  const description =
    `Play "${entry.title}" online, a ${sizeText(entry)} ${what} (difficulty: ${entry.grade}). ` +
    `Free, in your browser, solvable by logic alone.`;
  const dir = path.join(dist, "p", entry.id);
  await mkdir(dir, { recursive: true });
  await writeFile(
    path.join(dir, "index.html"),
    `<!doctype html>\n<html lang="en">\n  <head>\n    ${head({
      title: `${entry.title} – ${what} (${sizeText(entry)}) | ${SITE_NAME}`,
      description,
      canonical: url,
      jsonLd: { "@context": "https://schema.org", "@type": "WebPage", name: entry.title, url, description, isPartOf: { "@type": "WebSite", name: SITE_NAME, url: `${SITE}/` } },
    })}\n    ${pageStyle}\n  </head>\n  <body>
    <p><a href="../../">← All puzzles</a>${isMurdoku(entry) ? ' · <a href="../../murdoku/">Murdoku</a>' : ""}</p>
    <h1>${esc(entry.title)}</h1>
    <p>${esc(entry.section)} · ${sizeText(entry)} · ${esc(entry.grade)}</p>
    <p><img src="../../puzzles/${encodeURIComponent(entry.id)}.svg" alt="${esc(`${entry.title}, ${what}`)}" width="480" height="480"></p>
    <p><a class="cta" href="../../#${encodeURIComponent(entry.id)}">Play this puzzle</a></p>
    <p>Part of the open-source <a href="${REPO}">human reasoning puzzles</a> collection.</p>
  </body>\n</html>\n`,
  );
}

// 4. Sitemap and robots.txt.
const urls = [`${SITE}/`, `${SITE}/murdoku/`, ...puzzles.map((p) => `${SITE}/p/${encodeURIComponent(p.id)}/`)];
await writeFile(
  path.join(dist, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${esc(u)}</loc></url>`).join("\n")}\n</urlset>\n`,
);
await writeFile(path.join(dist, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`);

console.log(`prerendered ${puzzles.length} puzzle pages, the Murdoku page, sitemap.xml and robots.txt in ${dist}`);
