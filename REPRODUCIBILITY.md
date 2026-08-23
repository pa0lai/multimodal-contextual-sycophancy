# Reproducibility

## Offline release gates

```bash
uv sync
uv run python -c "import src"
uv run python scripts/verify_reported_numbers.py
uv run python scripts/verify_release_manifest.py
uv run pytest
```

The headline verifier explicitly filters generator split, image type, model, phase, text condition, and attack. Inference and LLM judging are separate paid stages.

## Image provenance

Canonical decoded-RGB hashes use dimensions plus row-major RGB bytes as documented in `DATA_CARD.md`.

WHOOPS recovery command:

```bash
uv run --extra collectors python scripts/build_whoops_manifest.py \
  --private-dir /path/to/private/abnormal \
  --archive-repo /path/to/private/archive \
  --revision cca58d854ee35b6bfbedc14a9155483e89500ae9 \
  --legacy-image-revision 213b8c1dbf058e1132839c1084b3ec4166315485
```

Result: 466/499 exact current-file matches plus 33/499 deterministic-transform verifications, for 499/499 resolved source identities and 0 unresolved or ambiguous cases. Each transformed row requires an initial Git blob that exactly matches one official source and an exact decoded-RGB match after the recorded LANCZOS transform. No fuzzy candidate is promoted.

ImageNet reconstruction at revision `49e2ee26f3810fb5a7536bbf732a7b07389a47b5` with archive-date-compatible `datasets==4.4.2` and Pillow 12.3.0 achieves 500/500 source identities, 500/500 unique assignments, and 500/500 post-preprocessing decoded-pixel matches. Pillow 10.4.0, 11.3.0, and 12.3.0 produced identical relevant forensic hashes. `image_0228.png` is selection 229.

The four distinct stages are: (1) select the first 500 eligible frozen-stream examples; (2) normalize EXIF, RGB/ICC, then encode an intermediate PNG with compression level 6 and `optimize=false`; (3) if that PNG is larger than the pinned 3 MiB (`3,145,728` bytes) trigger, resize to maximum side 1536 using Pillow LANCZOS and `int()` floor dimensions; and (4) map the canonical selection index to the independently recovered historical private filename. The evaluation input is the resulting post-normalization image, not the downloaded raw file. Selection 304 is resized; selection 331 is EXIF-normalized; 477 and 494 remain unresized. See `data/manifests/imagenet_forensic_report.json`.

## Artifact map

| Paper item | Script | Artifact |
|---|---|---|
| Four headline values | `verify_reported_numbers.py` | `results/compact/*.jsonl`, `results/summaries/headline_results.json` |
| WHOOPS mapping | `build_whoops_manifest.py` | `data/manifests/whoops_abnormal_manifest.csv`, mapping status JSON |
| ImageNet reconstruction | `prepare_imagenet_normal.py` | ImageNet manifest and mapping status JSON |
| Dose response | `analyze_dose_response.py` | compact main rows, `figures/dose_response_*.png` |
| Interaction | `analyze_interaction.py` | compact main rows, `figures/interaction_plot_*.png` |
| Threshold | `analyze_threshold.py` | compact main rows, `figures/threshold_sensitivity_*.png` |
| Cross-model | `analyze_universal.py` | compact main rows, `figures/universal_controls_*.png` |

Legacy plotting scripts still expect the private per-file layout. Only the four camera-ready headline values are release-gated and exactly reproduced here.
