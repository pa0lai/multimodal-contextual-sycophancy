# Do Multimodal LLMs See Before They Read? Diagnosing Contextual Sycophancy

Yi-Cheng Lai and Hen-Hsen Huang  
Findings of the Association for Computational Linguistics: EMNLP 2026

Repository: https://github.com/pa0lai/multimodal-contextual-sycophancy

This is the paper's code and compact-result release. It studies **multimodal contextual sycophancy** in a controlled high-conflict image–text evaluation; it is not an estimate of real-world RAG failure rates.

The information boundary separates a **context-blind witness** from an **optional arbiter**. **S2VA (System-2 Visual Arbitration) is shorthand for the diagnostic witness–arbiter configuration, not a proposed architecture.** The implementation identifier `baseline_rag` is the paper's **Joint condition**; **Witness-Only** uses the witness result without the optional arbiter.

Benchmark-specific outcome patterns are reported as:

- contaminant pattern: GPT-5.1, Gemini 2.5, Qwen3-Thinking
- scaffold pattern: Claude Sonnet 4.5, Qwen3-Instruct, Kimi-K2.5

## Headline results

| Population | Configuration | GPT-5.1 correctness |
|---|---|---:|
| Full abnormal split, Gemini-generated false text (`n=499`) | Joint (`baseline_rag`) | 7.9% |
| Same | Witness-Only | 84.2% |
| GPT-4o-regenerated abnormal subset (`n=100`) | Joint (`baseline_rag`) | 68.0% |
| Same | full witness–arbiter configuration (`s2va`) | 85.0% |

The GPT-4o-regenerated manifest has 200 cases: 100 abnormal and 100 normal. Its camera-ready headline uses the 100 abnormal cases.

## Image sources and current provenance status

- Abnormal: WHOOPS!, 499 cases. Source identity is resolved for all 499: 466 current private files are exact decoded-pixel matches and 33 are reproducibly verified max-side-1536 LANCZOS transforms of exact official-source matches. No WHOOPS image archive is included or claimed.
- Normal control source pool: 500 images from the ImageNet-1k train split. ImageNet images are never redistributed. Users must accept the dataset terms and reconstruct them locally.

All 500 ImageNet source identities and stream positions were recovered. The preparation pipeline reproduces all 500 archived evaluation inputs exactly after post-selection EXIF orientation normalization and the recovered PNG-size-triggered max-side-1536 LANCZOS normalization. EXIF normalization affected selection 331 and resizing affected selection 304; selections 477 and 494 are not resized. Downloaded raw sources are not claimed to be 500/500 pixel-identical before preprocessing. `image_0228.png` is explicitly mapped to selection 229; quantitative evidence is in `data/manifests/imagenet_forensic_report.json`.

## Install and offline verification

```bash
uv sync
uv run python -c "import src"
uv run python scripts/verify_reported_numbers.py
uv run python scripts/verify_release_manifest.py
uv run pytest
```

Offline aggregation example:

```bash
uv run python scripts/summarize_results.py \
  results/compact/gemini_generated.jsonl \
  --generator-source-split gemini_generated \
  --image-type abnormal \
  --model-id openai/gpt-5.1 \
  --experimental-phase baseline_rag \
  --text-condition false_text \
  --attack-condition none
```

## Reconstruct the ImageNet normal pool

First accept the `ILSVRC/imagenet-1k` terms on Hugging Face. The script uses an authorized environment token or the local Hugging Face credential cache without printing or persisting it. Then run:

```bash
uv sync --extra collectors
uv run --extra collectors --with 'datasets==4.4.2' python scripts/prepare_imagenet_normal.py \
  --revision 49e2ee26f3810fb5a7536bbf732a7b07389a47b5 \
  --verify-against /path/to/authorized/private/normal
```

By default the script writes no image bytes. It records the reproducible naming plan and provenance in `data/manifests/imagenet_normal_manifest.csv`; `--write-images` is an explicit private-only option. The strict release gate requires 500/500 exact positional and set matches.

The post-selection order is EXIF normalization, RGB conversion with ICC preservation, explicit PNG encoding (`compress_level=6`, `optimize=false`), a `>3 MiB` encoded-size trigger, and—only when triggered—max-side-1536 LANCZOS resizing with positive-dimension floor rounding. The trigger reproduces the Git-history partition exactly; the absent one-off historical script prevents distinguishing a decimal 3 MB threshold from 3 MiB using blobs alone, so this release pins 3 MiB (`3,145,728` bytes).

## Paid inference and judging

Only these stages call hosted models and incur cost:

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY locally.

uv run python scripts/run_inference.py \
  --data_dir data/metadata/schema_v2_cases.jsonl \
  --output_dir results/raw \
  --models openai/gpt-5.1 \
  --phases baseline_rag s2va witness_only \
  --conditions false_text \
  --image_type abnormal \
  --attacks none

uv run python scripts/run_judge.py \
  --data_dir data/metadata/schema_v2_cases.jsonl \
  --results_dir results/raw \
  --models openai/gpt-5.1 \
  --phases baseline_rag s2va witness_only \
  --judge_model openai/gpt-4o
```

These paid stages are optional and are not needed for the offline headline checks. `run_eval.py` is a deprecated alias for paid judging, not offline aggregation.

## Deliberately excluded outputs

Full model-generated answers, witness text, arbiter/judge reasoning, raw provider responses, and provider payloads are private. Released result files contain only identifiers and derived numeric measurements. Annotation tables are sanitized compact copies.

## Citation

```bibtex
@inproceedings{lai-huang-2026-multimodal-contextual-sycophancy,
  title     = {Do Multimodal LLMs See Before They Read? Diagnosing Contextual Sycophancy},
  author    = {Lai, Yi-Cheng and Huang, Hen-Hsen},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2026},
  year      = {2026}
}
```

No DOI or ACL Anthology URL is claimed before an official record exists.

## License scope

- Code: MIT (`LICENSE`).
- Author-owned derived metadata, annotations, and numeric measurements: CC BY 4.0 (`LICENSE-DATA`).
- WHOOPS! and ImageNet images: original dataset licenses and terms; not covered by the licenses above and not included in this code repository.
