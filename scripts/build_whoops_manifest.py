#!/usr/bin/env python3
"""Recover exact WHOOPS provenance using decoded-pixel hashes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import zipfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from _bootstrap import REPO_ROOT  # noqa: F401
from src.utils.image_hashing import CANONICAL_HASH_ALGORITHM, decode_source, decoded_rgb_sha256, decoded_rgb_sha256_path, sha256_bytes


DATASET = "nlphuji/whoops"
DEFAULT_REVISION = "cca58d854ee35b6bfbedc14a9155483e89500ae9"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True, help="Private abnormal PNG directory")
    parser.add_argument("--archive-repo", type=Path, help="Private Git archive, used only to recover a missing historical case blob")
    parser.add_argument("--fallback-git-revision", default="0379abd", help="Revision containing the evaluated image set")
    parser.add_argument("--original-git-revision", default="0616dca", help="Initial archive revision used to verify deterministic later transforms")
    parser.add_argument("--output", type=Path, default=Path("data/manifests/whoops_abnormal_manifest.csv"))
    parser.add_argument("--status", type=Path, default=Path("data/manifests/whoops_mapping_status.json"))
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--legacy-image-revision", help="Optional official revision containing whoops_images.zip")
    args = parser.parse_args()

    from datasets import Image as DatasetImage, load_dataset
    import datasets
    import PIL

    dataset = load_dataset(DATASET, split="test", revision=args.revision)
    dataset = dataset.cast_column("image", DatasetImage(decode=False))
    by_hash = defaultdict(list)
    for index, example in enumerate(dataset):
        image, raw, source_path = decode_source(example["image"])
        decoded_hash = decoded_rgb_sha256(image)
        by_hash[decoded_hash].append({
            "whoops_source_id": str(example.get("image_id") or index),
            "source_filename_or_path": str(example.get("image_url") or source_path or ""),
            "source_file_sha256": sha256_bytes(raw) if raw is not None else "",
            "width": image.width,
            "height": image.height,
            "dataset_revision": args.revision,
        })

    if args.legacy_image_revision:
        from huggingface_hub import hf_hub_download
        legacy_zip = hf_hub_download(DATASET, "whoops_images.zip", repo_type="dataset", revision=args.legacy_image_revision)
        with zipfile.ZipFile(legacy_zip) as archive:
            for member in archive.namelist():
                if member.endswith("/") or not member.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                raw = archive.read(member)
                try:
                    with Image.open(BytesIO(raw)) as image:
                        decoded_hash = decoded_rgb_sha256(image)
                        if decoded_hash in by_hash:
                            continue
                        by_hash[decoded_hash].append({
                            "whoops_source_id": Path(member).stem,
                            "source_filename_or_path": member,
                            "source_file_sha256": sha256_bytes(raw),
                            "width": image.width,
                            "height": image.height,
                            "dataset_revision": args.legacy_image_revision,
                        })
                except UnidentifiedImageError:
                    continue

    case_images = {}
    for path in args.private_dir.glob("*.png"):
        if path.stem.isdigit():
            case_images[path.stem] = (path.read_bytes(), f"working-tree:{path.name}")
    expected_case_ids = {str(case_id) for case_id in range(500, 999)}
    missing_case_ids = sorted(expected_case_ids - set(case_images), key=int)
    if missing_case_ids and not args.archive_repo:
        raise SystemExit(f"Missing numeric cases {missing_case_ids}; pass --archive-repo for evidence-based Git blob recovery")
    for case_id in missing_case_ids:
        blob_path = f"data/raw_images/abnormal/{case_id}.png"
        raw = subprocess.check_output(["git", "-C", str(args.archive_repo), "show", f"{args.fallback_git_revision}:{blob_path}"])
        case_images[case_id] = (raw, f"git:{args.fallback_git_revision}:{blob_path}")

    rows = []
    unmatched = []
    ambiguous = []
    transformed = []
    for case_id in sorted(case_images, key=int):
        private_raw, evidence_location = case_images[case_id]
        with Image.open(BytesIO(private_raw)) as private_image:
            width, height = private_image.size
            decoded_hash = decoded_rgb_sha256(private_image)
        matches = by_hash.get(decoded_hash, [])
        match_status = "exact_decoded_match"
        deterministic_transform = ""
        transform_evidence = ""
        original_git_blob_sha256 = ""
        original_git_decoded_rgb_sha256 = ""
        if not matches and args.archive_repo:
            blob_path = f"data/raw_images/abnormal/{case_id}.png"
            try:
                original_raw = subprocess.check_output([
                    "git", "-C", str(args.archive_repo), "show",
                    f"{args.original_git_revision}:{blob_path}",
                ])
            except subprocess.CalledProcessError:
                original_raw = b""
            if original_raw:
                original_git_blob_sha256 = sha256_bytes(original_raw)
                with Image.open(BytesIO(original_raw)) as original_image:
                    original_git_decoded_rgb_sha256 = decoded_rgb_sha256(original_image)
                    original_matches = by_hash.get(original_git_decoded_rgb_sha256, [])
                    candidates = []
                    oriented = ImageOps.exif_transpose(original_image).convert("RGB")
                    candidates.append(("exif_transpose_then_rgb", oriented.copy()))
                    oriented.close()
                    if max(original_image.size) > 1536:
                        ratio = 1536 / max(original_image.size)
                        candidates.append((
                            "resize_max_side_1536_lanczos_floor_dimensions",
                            original_image.convert("RGB").resize(
                                (int(original_image.width * ratio), int(original_image.height * ratio)),
                                Image.Resampling.LANCZOS,
                            ),
                        ))
                    verified_transforms = []
                    for name, candidate in candidates:
                        try:
                            if decoded_rgb_sha256(candidate) == decoded_hash:
                                verified_transforms.append(name)
                        finally:
                            candidate.close()
                if len(original_matches) == 1 and len(verified_transforms) == 1:
                    matches = original_matches
                    match_status = "deterministic_transform_verified"
                    deterministic_transform = verified_transforms[0]
                    transform_evidence = (
                        f"official_decoded_rgb_sha256={original_git_decoded_rgb_sha256};"
                        f" transformed_decoded_rgb_sha256={decoded_hash};"
                        f" archive_revision={args.original_git_revision}"
                    )
                    transformed.append(case_id)
        if len(matches) != 1:
            (unmatched if not matches else ambiguous).append(case_id)
            rows.append({
                "case_id": case_id,
                "release_relative_path": f"data/raw_images/abnormal/{case_id}.png",
                "width": width,
                "height": height,
                "decoded_rgb_sha256": decoded_hash,
                "license": "CC BY 4.0 plus WHOOPS! Dataset License Agreement additional conditions",
                "dataset_repository": DATASET,
                "datasets_version": datasets.__version__,
                "pillow_version": PIL.__version__,
                "hash_algorithm": CANONICAL_HASH_ALGORITHM,
                "private_artifact_sha256": hashlib.sha256(private_raw).hexdigest(),
                "private_evidence_location": evidence_location,
                "match_status": "unresolved" if not matches else "ambiguous",
                "original_git_blob_sha256": original_git_blob_sha256,
                "original_git_decoded_rgb_sha256": original_git_decoded_rgb_sha256,
            })
            continue
        match = matches[0]
        rows.append({
            "case_id": case_id,
            "release_relative_path": f"data/raw_images/abnormal/{case_id}.png",
            **match,
            "width": width,
            "height": height,
            "decoded_rgb_sha256": decoded_hash,
            "license": "CC BY 4.0 plus WHOOPS! Dataset License Agreement additional conditions",
            "dataset_repository": DATASET,
            "dataset_revision": match["dataset_revision"],
            "datasets_version": datasets.__version__,
            "pillow_version": PIL.__version__,
            "hash_algorithm": CANONICAL_HASH_ALGORITHM,
            "private_artifact_sha256": hashlib.sha256(private_raw).hexdigest(),
            "private_evidence_location": evidence_location,
            "match_status": match_status,
            "deterministic_transform": deterministic_transform,
            "transform_evidence": transform_evidence,
            "original_git_blob_sha256": original_git_blob_sha256,
            "original_git_decoded_rgb_sha256": original_git_decoded_rgb_sha256,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id", "release_relative_path", "whoops_source_id", "source_filename_or_path",
        "width", "height", "source_file_sha256", "decoded_rgb_sha256", "license",
        "dataset_repository", "dataset_revision", "datasets_version", "pillow_version", "hash_algorithm",
        "private_artifact_sha256", "private_evidence_location",
        "match_status", "deterministic_transform", "transform_evidence",
        "original_git_blob_sha256", "original_git_decoded_rgb_sha256",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"dataset_revision={args.revision}")
    nonnumeric = sum(1 for path in args.private_dir.glob("*.png") if not path.stem.isdigit())
    exact_count = sum(row["match_status"] == "exact_decoded_match" for row in rows)
    print(f"expected_cases={len(case_images)} exact_matches={exact_count} transformed_matches={len(transformed)} unmatched={len(unmatched)} ambiguous={len(ambiguous)} nonnumeric_unassigned={nonnumeric}")
    args.status.write_text(json.dumps({
        "schema_version": 1,
        "status": "RECOVERED" if not unmatched and not ambiguous else "BLOCKED_PENDING_WHOOPS_EXACT_MAPPING",
        "current_dataset_revision": args.revision,
        "legacy_image_revision_attempted": args.legacy_image_revision,
        "expected_cases": len(case_images),
        "exact_decoded_pixel_matches": exact_count,
        "deterministic_transform_verified": len(transformed),
        "resolved_source_identities": exact_count + len(transformed),
        "transformed_case_ids": transformed,
        "unmatched_case_ids": unmatched,
        "ambiguous_case_ids": ambiguous,
        "nonnumeric_unassigned_private_files": nonnumeric,
        "hash_algorithm": CANONICAL_HASH_ALGORITHM,
    }, indent=2) + "\n", encoding="utf-8")
    if unmatched or ambiguous:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
