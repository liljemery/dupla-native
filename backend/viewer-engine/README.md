# Dupla Viewer Engine

Headless Autodesk Viewer utilities used by coordination extraction and screenshot capture.

`extract_fragments.js` loads a 2D APS sheet viewable, walks `getObjectTree()` and
`enumNodeFragments()`, and writes a `.viewer.json` artifact with per-element fragment
world bounds in the APS sheet paper coordinate frame.

`capture.js` loads the same APS viewer, fits the selected viewable, and writes a real
PNG screenshot plus diagnostic JSON. It is the visual companion to the fragment dump.

Runtime dependency:

```bash
npm install playwright
npx playwright install chromium
```

The Python `--dwg-via-aps` path invokes this script automatically when the matching
viewer cache artifact is missing or stale.

Screenshot capture:

```bash
npm run capture -- --urn <URN> --token <TOKEN> --output /tmp/shot.png
```
