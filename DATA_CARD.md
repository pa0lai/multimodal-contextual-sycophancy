# Data card

## Scope

This release supports a controlled high-conflict image–text diagnostic of multimodal contextual sycophancy. It is not an estimate of real-world RAG failure rates.

## Image sources

- Abnormal split: 499 WHOOPS! cases.
- Normal control source pool: 500 images selected from the ImageNet-1k (`ILSVRC/imagenet-1k`) train split.
- GPT-4o-regenerated metadata subset: 200 cases, comprising 100 abnormal and 100 normal cases; the camera-ready headline uses the 100 abnormal cases.

The ImageNet selection rule streams `train`, shuffles with seed 42 and buffer size 10,000, retains source images whose width and height are both at least 256 pixels, and takes the first 500 eligible examples. After selection, evaluation-input normalization applies EXIF orientation, converts to RGB while preserving ICC, encodes PNG with fixed parameters, and uses the recovered encoded-size trigger before any conditional resize. `scripts/prepare_imagenet_normal.py` records source, intermediate, reconstructed, archived, and environment evidence separately.

## Canonical decoded-pixel hash

Every provenance comparison converts the image to RGB and computes:

```text
SHA-256(big-endian uint32 width || big-endian uint32 height || row-major RGB bytes)
```

This procedure is implemented in `src/utils/image_hashing.py`.

## Current provenance status

- WHOOPS revision `cca58d854ee35b6bfbedc14a9155483e89500ae9` plus official historical image ZIP revision `213b8c1dbf058e1132839c1084b3ec4166315485`: 466/499 current private files match exactly and 33/499 have uniquely verified deterministic transforms from exact official-source matches. All 499 source identities are resolved; no cases are unmatched or ambiguous.
- ImageNet revision `49e2ee26f3810fb5a7536bbf732a7b07389a47b5`: `datasets==4.4.2` and Pillow 12.3.0 recover 500/500 source identities, 500/500 unique historical assignments, and 500/500 exact decoded-pixel matches after documented preprocessing. Selection 304 alone crosses the `3,145,728`-byte intermediate-PNG trigger and is resized; selection 331 is EXIF-normalized. Status: `RECOVERED`.
- The private normal directory contains numeric `1.png` through `499.png` plus `image_0228.png`; the latter is uniquely verified as selection 229. No selected or private hash is duplicated.

Raw images remain private and are ignored by Git. Do not infer mappings from filenames, order, or perceptual similarity.

## Licensing

Author-owned derived metadata, annotations, and numeric measurements are covered by `LICENSE-DATA` (CC BY 4.0). WHOOPS! and ImageNet material remain under their original terms; see `THIRD_PARTY_LICENSES.md`.
