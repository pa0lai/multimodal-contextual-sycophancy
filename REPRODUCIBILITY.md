# Reproducibility

## Offline verification

```bash
uv sync
uv run python -c "import src"
uv run pytest
uv run python scripts/verify_reported_numbers.py
```

The verifier validates the camera-ready headline table, the corrected Witness-Only aggregates, and paired-count identities in `results/summaries/witness_only_corrected_results.json`.

Corrected Witness-Only case-level judge labels are not redistributed. The released summary records the exact aggregate statistics used by the camera-ready paper without exposing model-generated witness text.

## Image provenance

Canonical decoded-RGB hashes use dimensions plus row-major RGB bytes as documented in `DATA_CARD.md`.

### WHOOPS

```bash
uv run --extra collectors python scripts/build_whoops_manifest.py \
  --private-dir /path/to/private/abnormal \
  --archive-repo /path/to/private/archive \
  --revision cca58d854ee35b6bfbedc14a9155483e89500ae9 \
  --legacy-image-revision 213b8c1dbf058e1132839c1084b3ec4166315485
```

The recovered mapping contains 466 exact current-file matches and 33 exact deterministic-transform verifications, resolving all 499 source identities without fuzzy promotion.

### ImageNet-1k

Revision `49e2ee26f3810fb5a7536bbf732a7b07389a47b5`, `datasets==4.4.2`, and Pillow 12.3.0 recover 500/500 source identities, 500/500 unique historical assignments, and 500/500 exact decoded-pixel matches after documented preprocessing.

The reconstruction stages are:

1. stream the training split, shuffle with seed 42 and buffer size 10,000, retain images at least 256 pixels in both dimensions, and select the first 500 eligible examples;
2. normalize EXIF orientation, convert to RGB while preserving ICC, and encode an intermediate PNG with compression level 6 and `optimize=false`;
3. if the PNG exceeds the pinned 3 MiB (`3,145,728` bytes) trigger, resize to maximum side 1536 using Pillow LANCZOS and floor-rounded dimensions;
4. map the canonical selection index to the recovered historical filename.

Selection 304 is resized, selection 331 is EXIF-normalized, and selections 477 and 494 remain unresized. `image_0228.png` maps uniquely to selection 229. Full per-item evidence is in `data/manifests/`.

## Artifact map

| Claim or artifact | Entry point | Released input/output |
|---|---|---|
| Camera-ready headline values | `scripts/verify_reported_numbers.py` | `results/summaries/headline_results.json` |
| Corrected Witness-Only results | `scripts/verify_reported_numbers.py` | `results/summaries/witness_only_corrected_results.json` |
| Offline aggregation | `scripts/summarize_results.py` | regenerated result rows |
| WHOOPS mapping | `scripts/build_whoops_manifest.py` | WHOOPS manifest and status |
| ImageNet reconstruction | `scripts/prepare_imagenet_normal.py` | ImageNet manifest and status |
| Hosted inference | `scripts/run_inference.py` | private raw results |
| Hosted judging | `scripts/run_judge.py` | private judged results |

Rendered paper figures are intentionally not tracked. The analysis scripts remain available for users who regenerate the required result layout.
