# Data layout

- `metadata/schema_v2_cases.jsonl`: evaluated metadata for 499 abnormal and 499 normal cases.
- `metadata/gpt4o_regenerated_cases.jsonl`: 200 cases (100 abnormal, 100 normal).
- `manifests/whoops_abnormal_manifest.csv`: 499 WHOOPS source identities: 466 exact current-file matches and 33 verified deterministic transforms.
- `manifests/imagenet_normal_manifest.csv`: 500-row selection, preprocessing, historical-filename, and exact post-preprocessing hash evidence; contains no image bytes.
- `manifests/*_mapping_status.json`: exact recovery status and reproducible preprocessing evidence.
- `manifests/private_image_sha256.json`: hashes of 999 private image files; no image bytes.

The source image pools contain 499 abnormal WHOOPS! cases and 500 ImageNet normal images. The released evaluated metadata has 499 normal cases. The extra private normal file `image_0228.png` is verified as stream selection 229; the manifest records the full reconstructed naming plan without redistributing bytes.
