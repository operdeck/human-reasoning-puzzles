// The post-build step is a build script, but every page it writes is a string, so the
// pages are checked here by rendering them from a small fixture index and comparing the
// text, without running vite or a Python export.
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildDate,
  DEFAULT_SITE,
  MURDOKU_CREDIT,
  prerender,
  puzzleId,
  renderPages,
  REPO,
  siteAddress,
  SITE_NAME,
  sitemapDate,
  verificationTags,
} from "./prerender.mjs";

const murdoku = {
  id: "first-case",
  title: "The first case",
  family: "murdoku",
  familyLabel: "Murdoku",
  section: "Murdoku · Demo",
  size: [4, 4],
  grade: "single",
};

const sudoku = {
  id: "sudoku_1",
  title: "Sudoku 1 & friends",
  family: "sudoku",
  familyLabel: "Sudoku",
  section: "Sudoku",
  size: [9, 9],
  grade: "relations",
};

const index = { license: "All rights reserved.", puzzles: [murdoku, sudoku] };

// A fixed build date keeps the sitemap assertions (and diffs) stable.
const TODAY = "2026-11-08";

const shell = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Human reasoning puzzles</title>
    <link rel="stylesheet" href="./assets/index-abc.css" />
    <script type="module" crossorigin src="./assets/index-abc.js"></script>
  </head>
  <body><main id="app"></main></body>
</html>
`;

const render = (site = DEFAULT_SITE, built = shell, lastmod = TODAY) =>
  renderPages({ index, built, site, lastmod });
const pageFor = (files: { path: string; contents: string }[], wanted: string) =>
  files.find((file) => file.path === wanted)?.contents ?? "";

describe("renderPages", () => {
  it("writes the home page, the Murdoku landing page, one page per puzzle, a sitemap and robots", () => {
    expect(render().map((file) => file.path)).toEqual([
      "index.html",
      "murdoku/index.html",
      "p/first-case/index.html",
      "p/sudoku_1/index.html",
      "sitemap.xml",
      "robots.txt",
    ]);
  });

  it("keeps the built app's own tags on the home page and lists every puzzle", () => {
    const home = pageFor(render(), "index.html");
    expect(home).toContain('src="./assets/index-abc.js"');
    expect(home).toContain('href="./assets/index-abc.css"');
    expect(home).toContain("<title>Human reasoning puzzles – play Murdoku, Sudoku, Queens and more online</title>");
    expect(home).toContain(`Play 2 free logic puzzles online`);
    expect(home).toContain('<main id="app">');
    expect(home).toContain('<a href="p/first-case/">The first case</a>');
    expect(home).toContain('<a href="p/sudoku_1/">Sudoku 1 &amp; friends</a>');
    expect(home).toContain('<meta property="og:url" content="https://operdeck.github.io/human-reasoning-puzzles/" />');
    expect(home).toContain('"@type":"WebSite"');
  });

  it("lists only Murdoku cases on the Murdoku landing page", () => {
    const landing = pageFor(render(), "murdoku/index.html");
    expect(landing).toContain(`Play free Murdoku online: 1 original murder-mystery logic puzzle`);
    expect(landing).toContain('<a href="../p/first-case/">The first case</a>');
    expect(landing).not.toContain("sudoku_1");
  });

  it("gives each puzzle its own page with a picture and a link into the player", () => {
    const page = pageFor(render(), "p/first-case/index.html");
    expect(page).toContain("<title>The first case – Murdoku murder mystery (4×4) | Human reasoning puzzles</title>");
    expect(page).toContain('<link rel="canonical" href="https://operdeck.github.io/human-reasoning-puzzles/p/first-case/" />');
    expect(page).toContain('<img src="../../puzzles/first-case.svg"');
    expect(page).toContain('<a class="cta" href="../../#first-case">Play this puzzle</a>');
    expect(page).toContain(`<a href="${REPO}">human reasoning puzzles</a>`);
  });

  it("credits Murdoku's inventor wherever a Murdoku appears, and nowhere else", () => {
    const files = render();
    expect(MURDOKU_CREDIT).toBe(
      'Murdoku was invented by <a href="https://murdoku.com" ' +
      'title="Murdoku books and free puzzles by their inventor">Manuel Garand</a>.',
    );
    for (const file of ["index.html", "murdoku/index.html", "p/first-case/index.html"]) {
      expect(pageFor(files, file)).toContain(`<p class="credit">${MURDOKU_CREDIT}</p>`);
    }
    expect(pageFor(files, "p/sudoku_1/index.html")).not.toContain("Manuel Garand");
  });

  it("escapes titles in HTML but still links them into the player", () => {
    const page = pageFor(render(), "p/sudoku_1/index.html");
    expect(page).toContain("<h1>Sudoku 1 &amp; friends</h1>");
    expect(page).toContain('alt="Sudoku 1 &amp; friends, Sudoku puzzle"');
  });

  it("lists the home page, the Murdoku page and every puzzle once in the sitemap", () => {
    const sitemap = pageFor(render(), "sitemap.xml");
    const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
    expect(urls).toEqual([
      `${DEFAULT_SITE}/`,
      `${DEFAULT_SITE}/murdoku/`,
      `${DEFAULT_SITE}/p/first-case/`,
      `${DEFAULT_SITE}/p/sudoku_1/`,
    ]);
    expect(pageFor(render(), "robots.txt")).toContain(`Sitemap: ${DEFAULT_SITE}/sitemap.xml`);
  });

  it("dates every sitemap entry, and lets a puzzle date itself", () => {
    const dates = pageFor(render(), "sitemap.xml").match(/<lastmod>[^<]+<\/lastmod>/g);
    expect(dates).toEqual(Array(4).fill(`<lastmod>${TODAY}</lastmod>`));
    const dated = renderPages({
      index: { ...index, puzzles: [{ ...murdoku, updated: "2025-01-02" }, sudoku] },
      built: shell,
      site: DEFAULT_SITE,
      lastmod: TODAY,
    });
    expect(pageFor(dated, "sitemap.xml")).toContain(
      `<url><loc>${DEFAULT_SITE}/p/first-case/</loc><lastmod>2025-01-02</lastmod></url>`,
    );
  });

  it("follows SITE_URL for previews on another host", () => {
    const files = render("https://example.test/preview/");
    expect(pageFor(files, "index.html")).toContain('<link rel="canonical" href="https://example.test/preview/" />');
    expect(pageFor(files, "sitemap.xml")).toContain("<loc>https://example.test/preview/p/sudoku_1/</loc>");
  });

  it("names the site in the home page title and the Murdoku page in its own", () => {
    const files = render();
    expect(pageFor(files, "index.html")).toContain(SITE_NAME);
    expect(pageFor(files, "murdoku/index.html")).toContain(
      `<title>Murdoku online – free murder mystery logic puzzles | ${SITE_NAME}</title>`,
    );
  });
});

describe("hostile input", () => {
  it("refuses puzzle ids that could leave the dist directory", () => {
    for (const id of ["../../escaped", "a/b", "..", ".", "", "a\\b", null, 42]) {
      expect(() =>
        renderPages({
          index: { puzzles: [{ ...murdoku, id }] },
          built: shell,
          site: DEFAULT_SITE,
          lastmod: TODAY,
        }),
      ).toThrow(/unsafe puzzle id/);
    }
    expect(puzzleId({ id: "murdoku_1_first_case" }, 0)).toBe("murdoku_1_first_case");
    expect(puzzleId({ id: "food-murdoku-2" }, 3)).toBe("food-murdoku-2");
  });

  it("writes nothing outside the directory being built", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "prerender-hostile-"));
    const dist = path.join(root, "dist");
    await mkdir(path.join(dist, "puzzles"), { recursive: true });
    await writeFile(path.join(dist, "index.html"), shell);
    await writeFile(
      path.join(dist, "puzzles", "index.json"),
      JSON.stringify({ puzzles: [{ ...murdoku, id: "../../escaped" }] }),
    );
    await expect(prerender({ distDir: dist })).rejects.toThrow(/unsafe puzzle id/);
    expect(existsSync(path.join(root, "escaped"))).toBe(false);
    await rm(root, { recursive: true, force: true });
  });

  it("refuses a SITE_URL that is not a plain http(s) origin", () => {
    for (const site of ["not a url", "javascript:alert(1)", "file:///etc/passwd",
      "https://user:pass@example.test", "data:text/html,<script>"]) {
      expect(() =>
        renderPages({ index, built: shell, site, lastmod: TODAY }),
      ).toThrow(/SITE_URL/);
    }
    expect(siteAddress("https://example.test/preview/")).toBe("https://example.test/preview");
    expect(siteAddress("https://example.test/preview///?x=1#y")).toBe("https://example.test/preview");
  });

  it("refuses a SITE_URL that carries whitespace or control characters", () => {
    for (const site of ["https://evil.test/\nUser-agent: *\nDisallow: /", "https://evil.test/ ", "https://evil.test/\u0000"]) {
      expect(() =>
        renderPages({ index, built: shell, site, lastmod: TODAY }),
      ).toThrow(/whitespace or control characters/);
    }
  });

  it("ignores dates the export cannot promise", () => {
    const files = renderPages({
      index: { puzzles: [{ ...murdoku, updated: "not-a-date</lastmod><x>" }] },
      built: shell,
      site: DEFAULT_SITE,
      lastmod: TODAY,
    });
    expect(pageFor(files, "sitemap.xml")).not.toContain("not-a-date");
    expect(pageFor(files, "sitemap.xml")).toContain(`<lastmod>${TODAY}</lastmod>`);
    expect(sitemapDate("2025-01-02", TODAY)).toBe("2025-01-02");
    expect(sitemapDate(undefined, TODAY)).toBe(TODAY);
  });

  it("escapes a hostile title out of the HTML and the JSON-LD block", () => {
    const files = renderPages({
      index: { puzzles: [{ ...sudoku, id: "ok", title: '</script><script>alert(1)</script>' }] },
      built: shell,
      site: DEFAULT_SITE,
      lastmod: TODAY,
    });
    const page = pageFor(files, "p/ok/index.html");
    expect(page).not.toContain("<script>alert");
    expect(page.match(/<script/g)).toHaveLength(1); // the ld+json block, nothing else
    expect(page).toContain("&lt;/script&gt;");
    expect(page).toContain("\\u003c/script>");
  });

  it("fails loudly on an index without puzzles instead of writing junk", () => {
    for (const bad of [{}, { puzzles: "nope" }, null]) {
      expect(() =>
        renderPages({ index: bad as never, built: shell, site: DEFAULT_SITE, lastmod: TODAY }),
      ).toThrow(/no puzzles array/);
    }
  });
});

describe("verificationTags", () => {
  it("carries a Google or Bing verification tag from the built shell into every page", () => {
    const tagged = shell.replace(
      "<title>",
      '<meta name="google-site-verification" content="TEST" />\n    <title>',
    );
    expect(verificationTags(tagged)).toHaveLength(1);
    expect(verificationTags(shell)).toHaveLength(0);
    for (const file of render(DEFAULT_SITE, tagged).filter((page) => page.path.endsWith(".html"))) {
      expect(file.contents).toContain('<meta name="google-site-verification" content="TEST" />');
    }
  });
});

describe("prerender", () => {
  it("writes the pages next to the built app and reports the puzzle count", async () => {
    const dist = await mkdtemp(path.join(tmpdir(), "prerender-"));
    await mkdir(path.join(dist, "puzzles"), { recursive: true });
    await writeFile(path.join(dist, "index.html"), shell);
    await writeFile(path.join(dist, "puzzles", "index.json"), JSON.stringify(index));
    const { puzzles, files } = await prerender({ distDir: dist });
    expect(puzzles).toBe(2);
    expect(files).toHaveLength(6);
    expect(await readFile(path.join(dist, "p", "first-case", "index.html"), "utf8")).toContain(
      "The first case",
    );
    expect(await readFile(path.join(dist, "robots.txt"), "utf8")).toContain("Sitemap:");
    await rm(dist, { recursive: true, force: true });
  });
});

describe("buildDate", () => {
  it("uses today in UTC, or SOURCE_DATE_EPOCH for a reproducible build", () => {
    expect(buildDate(new Date("2026-11-08T23:30:00Z"))).toBe("2026-11-08");
    const saved = process.env.SOURCE_DATE_EPOCH;
    process.env.SOURCE_DATE_EPOCH = "1700000000";
    try {
      expect(buildDate(new Date("2026-11-08T23:30:00Z"))).toBe("2023-11-14");
    } finally {
      if (saved === undefined) delete process.env.SOURCE_DATE_EPOCH;
      else process.env.SOURCE_DATE_EPOCH = saved;
    }
  });
});
