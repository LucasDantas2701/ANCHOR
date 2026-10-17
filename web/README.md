# The ANCHOR interface (Angular)

The interface of ANCHOR's local program. It is built into `anchor/ui/static/`, where the Python
server (`python -m anchor.ui`) serves it; the server is the only thing that talks to ANCHOR.

Colours, type and logos come from the ANCHOR design system (`src/styles.css` holds its tokens).

```
npm install          # once (the versions are pinned in package.json and package-lock.json)
npm run build        # builds into ../anchor/ui/static
```

Then, from the repository's root: `python -m anchor.ui`.
