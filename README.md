# Do Multimodal LLMs See Before They Read? Diagnosing Contextual Sycophancy

Yi-Cheng Lai and Hen-Hsen Huang  
Findings of the Association for Computational Linguistics: EMNLP 2026

This repository contains the evaluation code, prompts, portable metadata, and camera-ready aggregate results for a controlled diagnostic of **multimodal contextual sycophancy**. S2VA (System-2 Visual Arbitration) is the diagnostic context-blind witness–arbiter configuration; it is not a proposed architecture.

Paper: [arXiv:2609.00067](https://arxiv.org/abs/2609.00067)

## Camera-ready headline results

| Population | Configuration | GPT-5.1 correctness |
|---|---|---:|
| Full abnormal split, Gemini-generated false text (`n=499`) | Joint | 7.9% |
| Same | Witness-Only | 49.7% |
| Same | Leaky Witness | 63.7% |
| Same | S2VA | 84.2% |
| GPT-4o-regenerated abnormal subset (`n=100`) | Joint | 68.0% |
| Same | Witness-Only | 61.0% |
| Same | S2VA | 85.0% |

`baseline_rag`, `witness_only`, `s2va_leaky`, and `s2va` are the implementation names for Joint, Witness-Only, Leaky Witness, and S2VA, respectively.

The Witness-Only scores were corrected on August 25, 2026 by scoring the witness report itself rather than a downstream arbiter-formatted answer. The canonical corrected aggregates and paired statistics are in `results/summaries/witness_only_corrected_results.json`. Superseded case-level result files are intentionally excluded from this release; users can regenerate result rows with the released code and prompts.

## Repository contents

- `src/`: inference, arbitration, evaluation, and attack code.
- `scripts/`: experiment, aggregation, provenance, and verification entry points.
- `data/metadata/`: portable case metadata without image bytes.
- `data/manifests/`: WHOOPS and ImageNet source mappings and hashes.
- `results/summaries/`: canonical camera-ready aggregates, including corrected Witness-Only results.
- `annotations/`: sanitized human-audit tables.
- `docs/ALL_PROMPTS.md`: inference prompt templates.

Rendered paper figures, raw images, full model responses, witness/arbiter text, and judge reasoning are intentionally not included.

## Install and verify

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are recommended.

```bash
uv sync
uv run pytest
uv run python scripts/verify_reported_numbers.py
```

The verifier checks the released camera-ready values, corrected Witness-Only aggregates, and paired-count invariants. No hosted model call is required.

Example aggregation after regenerating private or authorized result rows:

```bash
uv run python scripts/summarize_results.py \
  /path/to/regenerated_results.jsonl \
  --generator-source-split gemini_generated \
  --image-type abnormal \
  --model-id openai/gpt-5.1 \
  --experimental-phase baseline_rag \
  --text-condition false_text \
  --attack-condition none
```

## Data and images

Raw images are not distributed.

- Abnormal cases originate from [WHOOPS!](https://huggingface.co/datasets/nlphuji/whoops).
- The normal control pool originates from the [ImageNet-1k training split](https://huggingface.co/datasets/ILSVRC/imagenet-1k).

Users must accept the applicable dataset terms and obtain the images themselves. Exact source mappings and preprocessing evidence are provided in `data/manifests/`. See [DATA_CARD.md](DATA_CARD.md), [REPRODUCIBILITY.md](REPRODUCIBILITY.md), and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

To reconstruct the authorized ImageNet pool:

```bash
uv sync --extra collectors
uv run --extra collectors --with 'datasets==4.4.2' python scripts/prepare_imagenet_normal.py \
  --revision 49e2ee26f3810fb5a7536bbf732a7b07389a47b5
```

The script writes no image bytes unless `--write-images` is explicitly supplied.

## Optional hosted-model reruns

Hosted inference and judging require an OpenRouter key and may incur cost:

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY locally.

uv run python scripts/run_inference.py --help
uv run python scripts/run_judge.py --help
```

These stages are not needed for offline verification. Full generated outputs remain private; see [MODEL_OUTPUTS.md](MODEL_OUTPUTS.md).

## Citation

```bibtex
@misc{lai2026multimodalllmsreaddiagnosing,
  title         = {Do Multimodal LLMs See Before They Read? Diagnosing Contextual Sycophancy},
  author        = {Yi-Cheng Lai and Hen-Hsen Huang},
  year          = {2026},
  eprint        = {2609.00067},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2609.00067}
}
```

Machine-readable citation metadata is provided in [CITATION.cff](CITATION.cff). We will update it with the ACL Anthology URL and DOI when the proceedings version becomes available.

## License

- Code: MIT ([LICENSE](LICENSE)).
- Author-owned derived metadata, annotations, and numeric measurements: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)).
- WHOOPS! and ImageNet images remain under their original terms and are not included.
