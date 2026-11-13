# Discoverability

The published site is a client-side player, so the build does the mechanical half of
being findable: `npm run build` in `web/` prerenders real HTML over it
(`web/scripts/prerender.mjs`, run as the `postbuild` step). What is left is one-time
work on GitHub and with the search engines, which no pull request can do, so it is
written down here.

## What the build already produces

After `vite build`, `scripts/prerender.mjs` reads `dist/puzzles/index.json` (written by
`csp --export`, so Python stays the single source of truth) and writes:

| Output | Contents |
|---|---|
| `dist/index.html` | the built shell with a static puzzle list inside `#app`, which the player replaces on load |
| `dist/murdoku/index.html` | a landing page for online Murdoku, listing every case |
| `dist/p/<id>/index.html` | one page per puzzle: metadata and a static board fallback; JavaScript opens the player immediately |
| `dist/sitemap.xml`, `dist/robots.txt` | every prerendered URL, each dated with a `<lastmod>` |

Every page gets a specific title, a meta description, a canonical URL, Open Graph
tags and JSON-LD taken from the export. `SITE_URL` overrides the public address
(default: the GitHub Pages URL) for previews on another host. `prerender.mjs` keeps the
pages as data (`renderPages`) and only writes them in `prerender`, so
`web/scripts/prerender.test.ts` checks their HTML from a two-puzzle fixture at build time
without running vite or the export.

Puzzle pages load the same player assets as the home page, with a base URL
pointing back to the site root. Their static picture and play link remain for
crawlers and visitors without JavaScript, but players need no intermediate click.
The home page and Murdoku landing page retain illustrated previews, one per
collection section.

`robots.txt` is written for completeness but is **inert here**: this is a GitHub Pages
*project* site, so `robots.txt` is not served from the domain root and crawlers ignore
it. Submit the sitemap by hand instead.

## Repo settings

The About panel, the topics and the homepage link are what GitHub search and social
previews use:

```sh
gh repo edit operdeck/human-reasoning-puzzles \
  --description "Play free logic puzzles online (Murdoku, Sudoku, Queens, Kakuro...) and build your own with an explainable Python constraint solver" \
  --homepage "https://operdeck.github.io/human-reasoning-puzzles/" \
  --add-topic murdoku --add-topic logic-puzzles --add-topic puzzle-game \
  --add-topic sudoku --add-topic constraint-solver --add-topic constraint-programming \
  --add-topic csp --add-topic puzzle-generator --add-topic python \
  --add-topic typescript --add-topic vite --add-topic github-pages \
  --add-topic explainable-ai
```

## Social preview image

GitHub puts one image next to a link to this repository when someone pastes it into Slack,
X, LinkedIn, Discord or a pull request. It is the only picture the project has there, and
`gh` cannot set it, so it is a two-minute job by hand:

1. Open <https://github.com/operdeck/human-reasoning-puzzles> and press **Settings** in the
   repository's top bar (not your account settings).
2. On **General**, scroll down to **Social preview** and press **Edit**.
3. **Upload an image…** and pick a PNG of 1280×640 — GitHub's recommended size (640×320
   minimum) with a 1 MB cap. A draft can be composed from the project's own pictures:
   `uv run csp examples/demo/murdoku_1_first_case.txt --png murdoku.png` writes a board, and
   a 1280×640 canvas with two boards beside the site name is enough.
4. **Save**. Nothing is committed: the image lives in the repository settings, so a clone
   cannot show it and CI cannot check it.

The same panel is where the description, homepage link and topics from the command above
end up, so check them while you are there.

## Search engines

Crawlers will find the site by themselves eventually. Submitting it is about being indexed
this week instead of next month, and it needs a Google (and optionally a Microsoft)
account, so no pull request can do it.

### 1. Tell Google the site is yours

1. Open <https://search.google.com/search-console> → **Add property** → choose **URL
   prefix** and enter `https://operdeck.github.io/human-reasoning-puzzles/`. Do not pick
   "Domain": that needs DNS records, which a GitHub project page does not let you add.
2. Pick the **HTML tag** method. Google shows a line like
   `<meta name="google-site-verification" content="…" />`; copy it.
3. Paste it into `web/index.html` inside `<head>`, beside the `<title>`, and commit it on a
   branch. That is the only page you touch: the build copies the tag into every prerendered
   page, which you can confirm with `grep -rl google-site-verification web/dist | wc -l`
   (it should print the number of pages plus two).
4. Merge, let Pages deploy, then press **Verify**.
5. Leave the tag in place; removing it can de-verify the property later.

`msvalidate.01` (Bing) and `yandex-verification` work the same way, and all three can sit
in the same `<head>`.

### 2. Hand Google the sitemap

In the property, open **Indexing → Sitemaps**, enter `sitemap.xml` and press **Submit**. It
reads `https://operdeck.github.io/human-reasoning-puzzles/sitemap.xml`, which the build
writes with every prerendered URL and a `<lastmod>` on each. The date is the build date —
`SOURCE_DATE_EPOCH` overrides it if you ever want a fixed one — or a puzzle's own date, if
the export ever grows one. Status turns to "Success" within a day or so; pages then appear
in search over the following days to weeks.

### 3. Bing (optional)

<https://www.bing.com/webmasters> → **Import from Google Search Console** copies the site
and its sitemap in one step. Otherwise add the same URL prefix and verify with
`msvalidate.01`.

## Getting links

Ranking depends mostly on who links to you, and there is no shortcut:

- the Murdoku and logic-puzzle subreddits
- Hacker News, as "Show HN: an explainable logic-puzzle solver"
- Lobsters
- the Simon Tatham puzzle-collection and puzzle-programming communities
- "awesome" lists such as awesome-constraint-programming

Link `/murdoku/` for players and the repository for developers.
