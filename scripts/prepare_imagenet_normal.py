#!/usr/bin/env python3
"""Reconstruct the 500 archived ImageNet evaluation inputs without redistributing bytes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from src.utils.image_hashing import CANONICAL_HASH_ALGORITHM, decode_source, decoded_rgb_sha256, decoded_rgb_sha256_path, sha256_bytes


DATASET = "ILSVRC/imagenet-1k"
DEFAULT_REVISION = "49e2ee26f3810fb5a7536bbf732a7b07389a47b5"
PNG_SIZE_TRIGGER_BYTES = 3 * 1024 * 1024
MAX_SIDE = 1536
PNG_COMPRESS_LEVEL = 6
PNG_OPTIMIZE = False
FIELDNAMES = [
    "case_id", "canonical_selection_index", "release_relative_path",
    "private_reference_filename", "historical_private_filename", "match_status", "identity_status",
    "dataset_repository", "dataset_revision", "split", "streaming", "shuffle_seed",
    "shuffle_buffer_size", "minimum_resolution", "selected_stream_index", "source_path_or_key",
    "imagenet_label", "source_width", "source_height", "pre_transform_width", "pre_transform_height",
    "post_exif_width", "post_exif_height", "post_transform_width", "post_transform_height",
    "source_exif_orientation", "applied_exif_transform", "applied_resize", "resize_resampling",
    "resize_dimension_rounding", "max_side", "pre_normalization_png_size_bytes",
    "png_size_trigger_bytes", "png_compress_level", "png_optimize", "icc_profile_preserved",
    "source_file_sha256", "source_decoded_rgb_sha256", "reconstructed_decoded_rgb_sha256",
    "archived_decoded_rgb_sha256", "private_file_sha256", "post_preprocessing_match_status",
    "datasets_version", "pillow_version", "python_version", "hash_algorithm",
]


def private_reference_index(reference_dir: Path) -> tuple[dict[str, list[dict[str, object]]], int]:
    by_hash: dict[str, list[dict[str, object]]] = defaultdict(list)
    files = sorted(path for path in reference_dir.iterdir() if path.is_file())
    for path in files:
        decoded_hash, width, height = decoded_rgb_sha256_path(path)
        by_hash[decoded_hash].append({
            "filename": path.name,
            "file_sha256": sha256_bytes(path.read_bytes()),
            "decoded_rgb_sha256": decoded_hash,
            "width": width,
            "height": height,
        })
    return by_hash, len(files)


def encode_png(image, *, icc_profile: bytes | None) -> bytes:
    """Use the recovered historical PNG settings at the size-trigger decision point."""
    buffer = BytesIO()
    save_args = {"format": "PNG", "compress_level": PNG_COMPRESS_LEVEL, "optimize": PNG_OPTIMIZE}
    if icc_profile is not None:
        save_args["icc_profile"] = icc_profile
    image.save(buffer, **save_args)
    return buffer.getvalue()


def reconstruct_archived_input(image):
    """Apply EXIF normalization, then the historical PNG-size-triggered resize."""
    from PIL import Image, ImageOps

    source_orientation = image.getexif().get(274)
    icc_profile = image.info.get("icc_profile")
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    oriented.info.clear()
    if icc_profile is not None:
        oriented.info["icc_profile"] = icc_profile
    pre_resize_png = encode_png(oriented, icc_profile=icc_profile)
    resize_applied = len(pre_resize_png) > PNG_SIZE_TRIGGER_BYTES
    if resize_applied:
        ratio = MAX_SIDE / max(oriented.size)
        reconstructed = oriented.resize(
            (int(oriented.width * ratio), int(oriented.height * ratio)),
            Image.Resampling.LANCZOS,
        )
        oriented.close()
    else:
        reconstructed = oriented
    reconstructed.info.clear()
    if icc_profile is not None:
        reconstructed.info["icc_profile"] = icc_profile
    final_png = encode_png(reconstructed, icc_profile=icc_profile)
    return reconstructed, final_png, {
        "source_exif_orientation": source_orientation,
        "applied_exif_transform": source_orientation in (2, 3, 4, 5, 6, 7, 8),
        "post_exif_size": (image.height, image.width) if source_orientation in (5, 6, 7, 8) else image.size,
        "applied_resize": resize_applied,
        "pre_normalization_png_size_bytes": len(pre_resize_png),
        "icc_profile_preserved": icc_profile is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw_images/normal"))
    parser.add_argument("--write-images", action="store_true", help="Write reconstructed PNGs; disabled by default")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/imagenet_normal_manifest.csv"))
    parser.add_argument("--status", type=Path, default=Path("data/manifests/imagenet_mapping_status.json"))
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--verify-against", type=Path, required=True, help="Authorized unordered 500-file private reference directory")
    args = parser.parse_args()

    from huggingface_hub import get_token

    token = os.environ.get("HF_TOKEN") or get_token()
    if not token:
        raise SystemExit("No authorized Hugging Face token is available. Tokens are never logged.")
    print("Using an authorized Hugging Face credential without displaying or persisting it.")

    from datasets import Image as DatasetImage, load_dataset
    import datasets
    import PIL

    private_by_hash, private_count = private_reference_index(args.verify_against)
    if private_count != 500:
        raise SystemExit(f"Expected exactly 500 private reference files, found {private_count}")

    dataset = load_dataset(DATASET, streaming=True, revision=args.revision, token=token)
    stream = dataset["train"].cast_column("image", DatasetImage(decode=False))
    stream = stream.shuffle(seed=42, buffer_size=10000)
    if args.write_images:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    reconstructed_hashes = []
    assigned_private_names = []
    selected = 0
    for stream_index, example in enumerate(stream):
        record = example.get("image")
        if record is None:
            continue
        image, raw, source_path = decode_source(record)
        try:
            if image.width < 256 or image.height < 256:
                continue
            selected += 1
            source_width, source_height = image.size
            source_hash = decoded_rgb_sha256(image)
            reconstructed, final_png, prep = reconstruct_archived_input(image)
            try:
                reconstructed_hash = decoded_rgb_sha256(reconstructed)
                reconstructed_hashes.append(reconstructed_hash)
                matches = private_by_hash.get(reconstructed_hash, [])
                unique_match = matches[0] if len(matches) == 1 else None
                if unique_match:
                    assigned_private_names.append(str(unique_match["filename"]))
                if args.write_images:
                    (args.output_dir / f"{selected}.png").write_bytes(final_png)
                post_exif_width, post_exif_height = prep["post_exif_size"]
                source_key = Path(source_path).name if source_path and Path(source_path).is_absolute() else (
                    source_path or example.get("__key__", example.get("filename", example.get("id", "")))
                )
                rows.append({
                    "case_id": selected,
                    "canonical_selection_index": selected,
                    "release_relative_path": f"data/raw_images/normal/{selected}.png",
                    "private_reference_filename": unique_match["filename"] if unique_match else "",
                    "historical_private_filename": unique_match["filename"] if unique_match else "",
                    "match_status": "exact_post_preprocessing_match" if unique_match else ("ambiguous_duplicate_hash" if matches else "unmatched"),
                    "identity_status": "exact_post_preprocessing_match" if unique_match else "unresolved",
                    "dataset_repository": DATASET,
                    "dataset_revision": args.revision,
                    "split": "train",
                    "streaming": "true",
                    "shuffle_seed": 42,
                    "shuffle_buffer_size": 10000,
                    "minimum_resolution": 256,
                    "selected_stream_index": stream_index,
                    "source_path_or_key": source_key,
                    "imagenet_label": example.get("label", ""),
                    "source_width": source_width,
                    "source_height": source_height,
                    "pre_transform_width": source_width,
                    "pre_transform_height": source_height,
                    "post_exif_width": post_exif_width,
                    "post_exif_height": post_exif_height,
                    "post_transform_width": reconstructed.width,
                    "post_transform_height": reconstructed.height,
                    "source_exif_orientation": prep["source_exif_orientation"] if prep["source_exif_orientation"] is not None else "",
                    "applied_exif_transform": str(prep["applied_exif_transform"]).lower(),
                    "applied_resize": str(prep["applied_resize"]).lower(),
                    "resize_resampling": "Pillow Image.Resampling.LANCZOS" if prep["applied_resize"] else "",
                    "resize_dimension_rounding": "int(width*ratio), int(height*ratio) (floor for positive values)" if prep["applied_resize"] else "",
                    "max_side": MAX_SIDE if prep["applied_resize"] else "",
                    "pre_normalization_png_size_bytes": prep["pre_normalization_png_size_bytes"],
                    "png_size_trigger_bytes": PNG_SIZE_TRIGGER_BYTES,
                    "png_compress_level": PNG_COMPRESS_LEVEL,
                    "png_optimize": str(PNG_OPTIMIZE).lower(),
                    "icc_profile_preserved": str(prep["icc_profile_preserved"]).lower(),
                    "source_file_sha256": sha256_bytes(raw) if raw is not None else "",
                    "source_decoded_rgb_sha256": source_hash,
                    "reconstructed_decoded_rgb_sha256": reconstructed_hash,
                    "archived_decoded_rgb_sha256": unique_match["decoded_rgb_sha256"] if unique_match else "",
                    "private_file_sha256": unique_match["file_sha256"] if unique_match else "",
                    "post_preprocessing_match_status": "exact" if unique_match else "unresolved",
                    "datasets_version": datasets.__version__,
                    "pillow_version": PIL.__version__,
                    "python_version": platform.python_version(),
                    "hash_algorithm": CANONICAL_HASH_ALGORITHM,
                })
            finally:
                reconstructed.close()
        finally:
            image.close()
        if selected == 500:
            break
    if selected != 500:
        raise SystemExit(f"Only {selected}/500 eligible images were selected")

    reconstructed_counts = Counter(reconstructed_hashes)
    private_counts = Counter({key: len(value) for key, value in private_by_hash.items()})
    exact_set = sum((reconstructed_counts & private_counts).values())
    unique_assignments = len(set(assigned_private_names))
    exact_rows = sum(row["post_preprocessing_match_status"] == "exact" for row in rows)
    image_0228_rows = [row for row in rows if row["historical_private_filename"] == "image_0228.png"]
    image_0228_index = image_0228_rows[0]["canonical_selection_index"] if len(image_0228_rows) == 1 else None
    resized_indices = [row["canonical_selection_index"] for row in rows if row["applied_resize"] == "true"]
    exif_indices = [row["canonical_selection_index"] for row in rows if row["applied_exif_transform"] == "true"]
    unmatched_indices = [row["canonical_selection_index"] for row in rows if row["post_preprocessing_match_status"] != "exact"]

    with args.manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    passed = exact_set == 500 and exact_rows == 500 and unique_assignments == 500
    status = {
        "schema_version": 3,
        "status": "RECOVERED" if passed else "BLOCKED_PENDING_IMAGENET_POST_PREPROCESSING_RECOVERY",
        "release_verdict": "RELEASE_CANDIDATE_READY_FOR_AUTHOR_REVIEW" if passed else "BLOCKED_PENDING_IMAGENET_POST_PREPROCESSING_RECOVERY",
        "dataset_repository": DATASET,
        "dataset_revision": args.revision,
        "split": "train",
        "streaming": True,
        "shuffle_seed": 42,
        "shuffle_buffer_size": 10000,
        "minimum_resolution": 256,
        "target_image_count": 500,
        "source_identities": exact_rows,
        "unique_assignments": unique_assignments,
        "post_preprocessing_decoded_pixel_matches": exact_rows,
        "post_preprocessing_exact_set_matches": exact_set,
        "unmatched_selection_indices": unmatched_indices,
        "image_0228_verified_index": image_0228_index,
        "resize_applied_selection_indices": resized_indices,
        "exif_normalization_selection_indices": exif_indices,
        "datasets_version": datasets.__version__,
        "pillow_version": PIL.__version__,
        "python_version": platform.python_version(),
        "preprocessing_order": [
            "frozen stream selection on source dimensions",
            "EXIF orientation normalization",
            "RGB conversion with ICC profile preservation",
            "PNG encoding for historical size-trigger decision",
            "conditional max-side-1536 LANCZOS resize",
            "canonical selection-index naming",
        ],
        "png_size_trigger": {
            "operator": ">",
            "threshold_bytes": PNG_SIZE_TRIGGER_BYTES,
            "threshold_label": "3 MiB",
            "decision_point": "after EXIF normalization and RGB conversion, after intermediate PNG encoding, before resize",
            "png_save_parameters": {"format": "PNG", "compress_level": PNG_COMPRESS_LEVEL, "optimize": PNG_OPTIMIZE, "icc_profile": "preserved when present"},
            "git_history_evidence": {
                "commit": "125c888857884dbb19942fdfe4e6c41430591e04",
                "largest_unchanged_png_bytes": 2996612,
                "smallest_changed_png_bytes": 3417733,
                "classification_matches_all_1000_historical_pngs": True,
                "limitation": "The untracked one-off script is absent; Git blobs distinguish the classes but cannot distinguish decimal 3,000,000 from binary 3,145,728. The canonical release pins 3 MiB exactly.",
            },
        },
        "wrote_image_bytes": args.write_images,
        "hash_algorithm": CANONICAL_HASH_ALGORITHM,
    }
    args.status.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"dataset_revision={args.revision} datasets_version={datasets.__version__} pillow_version={PIL.__version__}")
    print(f"source_identities={exact_rows}/500 unique_assignments={unique_assignments}/500 post_preprocessing_matches={exact_rows}/500")
    print(f"resized_indices={resized_indices} exif_indices={exif_indices} image_0228_verified_index={image_0228_index}")
    if not passed:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
