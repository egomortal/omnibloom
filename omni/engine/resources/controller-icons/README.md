# Controller prompts

Original PNG assets from **Kenney Input Prompts 1.5A**, downloaded from the official
https://kenney.nl/assets/input-prompts page. License: CC0; the archive's original
license is included as `LICENSE-KENNEY.txt`. Attribution is optional; credit Kenney.

Selected Xbox Series and PlayStation Series **Double** (2×) assets are copied
unchanged. White outline variants provide light borders/symbols and dark interiors
against Omni's dark background. There is no raster recoloring or generated art.
PlayStation Create/Options are the PS5 variants. Right-stick press shows the
actual action for closing tabs; shoulders replace LB/RB and L1/R1 text boxes.

`manifest.json` records each original archive path and SHA-256. `generate.py`
embeds the PNGs into `OmniControllerAssets.h` for a self-contained browser, and
writes `preview.html` using the unchanged originals. To regenerate, run
`python3 engine/resources/controller-icons/generate.py`. To reimport, append the
path to the extracted official archive. No external runtime asset files are needed.

The browser decodes each selected asset at most once, validates dimensions <=256,
caches its SDL surface, and scales it into the existing hint geometry. All icons
together have a bounded small cache; no per-frame PNG decoding occurs.
