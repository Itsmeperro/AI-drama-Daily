# AI Drama Daily

The juiciest AI headlines, refreshed every morning.

- `build.py` pulls public news feeds, scores headlines for drama, and writes `index.html`.
- `.github/workflows/update.yml` runs it daily (~6 AM Central) and commits the result; GitHub Pages serves it.
- Manual refresh: **Actions → Update AI Drama Daily → Run workflow**.
- `feed.xml` gets 3 new headlines each morning (no repeats) for social auto-posters like Buffer: https://jcbriney71-hub.github.io/AI-drama-Daily/feed.xml
- `status.json` shows which news feeds succeeded on the last build.
