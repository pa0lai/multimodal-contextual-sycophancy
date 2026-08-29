# Model-output documentation

Full hosted-model answers, raw responses, witness reports, arbiter reasoning, judge reasoning, and provider payloads remain private and are not redistributed.

Case-level hosted-model outputs and derived scores are not redistributed. The public release contains camera-ready aggregate numeric measurements only.

## Corrected Witness-Only evaluation

The original release candidate scored the downstream arbiter-formatted answer for rows labeled `witness_only`. The camera-ready analysis instead scores the witness report itself. The affected legacy case-level files are excluded from the public release.

`results/summaries/witness_only_corrected_results.json` is the canonical public record for corrected Witness-Only accuracy, paired S2VA gains, bootstrap intervals, and improve/degrade/same counts. It contains no generated text. The correction covers 3,394 labels with zero failed labels: six models on 499 main-split cases and four models on the 100-case cross-generator subset.

The release annotation tables are sanitized copies. They do not include model answers, contexts, queries, or other generated free text. The judge-validation audit is retained as an audit of the original judged artifacts and is not a source for the corrected Witness-Only camera-ready values.

Requested hosted model aliases and provider implementations can change, so reruns may differ. Numeric derived measurements are licensed under `LICENSE-DATA`; this does not grant rights over provider-owned or third-party material.
