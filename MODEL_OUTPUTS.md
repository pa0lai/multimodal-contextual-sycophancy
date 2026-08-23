# Model-output documentation

Full hosted-model answers, raw responses, witness reports, arbiter reasoning, judge reasoning, and provider payloads remain private and are not redistributed.

The public compact result rows contain only identifiers and derived numeric measurements: case ID, image type, generator split, requested model ID, phase, condition, attack, correctness, text/visual faithfulness, witness confidence when analyzed, schema version, and private source-artifact provenance. Source sizes, row counts, and SHA-256 values permit audit against the private archive without publishing its text.

The release annotation tables are sanitized compact copies. In particular, `annotations/judge_validation.csv` does not include model answers, contexts, queries, or other generated free text. The private originals were not modified.

Requested hosted model aliases and provider implementations can change, so reruns may differ. Numeric derived measurements are licensed under `LICENSE-DATA`; this does not grant rights over provider-owned or third-party material.

