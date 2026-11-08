# Discoverability

The published site is a client-side player, so the build does the mechanical half of
being findable: `npm run build` in `web/` prerenders real HTML over it
(`web/scripts/prerender.mjs`, run as the `postbuild` step). What is left is one-time
work on GitHub and with the search engines, listed here. None of it is in the code, so
nothing in a pull request can do it for you.

## What the build already produces

After `vite build`, `scripts/prerender.mjs` reads `dist/puzzles/index.json` (written by
`csp --export`, so Python stays the single source of truth) and writes:

| Output | Contents |
|---|---|
| `dist/index.html` | the built shell with a static puzzle list inside `#app`, which the player replaces on load |
| `dist/murdoku/index.html` | a landing page for online Murdoku, listing every case |
| `dist/p/<id>/index.html` | one page per puzzle: size, grade, board picture, and a button into the player at `#<id>` |
| `dist/sitemap.xml`, `dist/robots.txt` | every prerendered URL |

Every page gets a specific title, a meta description, a canonical URL, Open Graph
tags and JSON-LD taken from the export. `SITE_URL` overrides the public address
(default: the GitHub Pages URL) for previews on another host.

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

Then upload a **social preview image** (Settings → General → Social preview, 1280×640),
for example a Murdoku board next to a solved Queens board with the site name. `gh` has
no command for it; drag the file in.

## Search engines

No verification tag is checked in. When you get one, put it in `web/index.html` and not
in `dist/`: `head()` rebuilds every prerendered page, and copies any
`google-site-verification`, `msvalidate.01` or `yandex-verification` meta tag it finds
in the built shell into all of them, so the one tag covers the home page, `/murdoku/`
and every `/p/<id>/`. Rebuild and check `dist/p/<id>/index.html` before verifying.

1. **Google Search Console**: add the URL-prefix property
   `https://operdeck.github.io/human-reasoning-puzzles/`, verify with the HTML tag (or
   the HTML file, which can live in `web/public/` because vite copies that into `dist/`),
   then Sitemaps → `sitemap.xml`. A project page can take days to be crawled properly.
2. **Bing Webmaster Tools**: import the site from Search Console, or add and verify it
   the same way.

## Getting links

Ranking depends mostly on who links to you, and there is no shortcut:

- the Murdoku and logic-puzzle subreddits
- Hacker News, as "Show HN: an explainable logic-puzzle solver"
- Lobsters
- the Simon Tatham puzzle-collection and puzzle-programming communities
- "awesome" lists such as awesome-constraint-programming

Link `/murdoku/` for players and the repository for developers.
