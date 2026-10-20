"""Prepare the five-category XSkill TIR-Bench split without changing source data.

Read TIR-Bench.json and data.zip from --input-dir; write a new --output-dir.
Use --source-revision to record the downloaded Hugging Face dataset revision.
The category quotas match XSkill Table 7; sample IDs are not author-verified.
"""

import argparse
import json
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image

# Preserve this category order because it determines the random draw sequence.
SPLIT_COUNTS = {
    "refcoco": (27, 60),
    "maze": (27, 51),
    "instrument": (22, 39),
    "ocr": (15, 28),
    "contrast": (9, 22),
}


if __name__ == "__main__":
    # Parse the source snapshot and destination boundaries.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    source = args.input_dir.resolve()
    output = args.output_dir.resolve()
    rows = json.loads((source / "TIR-Bench.json").read_text(encoding="utf-8"))
    filtered = [row for row in rows if row["task"] in SPLIT_COUNTS]
    assert len(rows) == 1215, f"Unexpected source size: {len(rows)}"
    assert len(filtered) == 430, f"Unexpected filtered size: {len(filtered)}"
    assert len({row["id"] for row in rows}) == len(rows), "Duplicate source IDs"

    # Draw disjoint per-category samples, then retain source order within splits.
    rng = random.Random(42)
    train_ids = set()
    test_ids = set()
    for category, (train_count, test_count) in SPLIT_COUNTS.items():
        candidates = [row["id"] for row in filtered if row["task"] == category]
        selected = rng.sample(candidates, train_count + test_count)
        train_ids.update(selected[:train_count])
        test_ids.update(selected[train_count:])
    selected_rows = [row for row in filtered if row["id"] in train_ids | test_ids]

    # Export only selected images, preserving archive bytes and subdirectories.
    output.mkdir(parents=True, exist_ok=False)
    samples = []
    exported = set()
    with zipfile.ZipFile(source / "data.zip") as archive:
        for row in selected_rows:
            images = []
            for field in ("image_1", "image_2"):
                if not row.get(field):
                    continue
                original_path = Path(row[field])
                relative = Path("images") / original_path.relative_to("data")
                if relative not in exported:
                    (output / relative).parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(row[field]) as src:
                        with (output / relative).open("xb") as dst:
                            shutil.copyfileobj(src, dst)
                    exported.add(relative)
                images.append(relative.as_posix())
            samples.append(
                {
                    "doc_id": f"tirbench_{row['id']:04d}",
                    "id": row["id"],
                    "problem": row["prompt"],
                    "solution": row["answer"],
                    "images": images,
                    "task": row["task"],
                    "meta_data": row["meta_data"],
                    "image_1": row["image_1"],
                    "image_2": row["image_2"],
                }
            )

    # Save model-ready splits and enough provenance to reproduce the selection.
    splits = {
        "train": [sample for sample in samples if sample["id"] in train_ids],
        "test": [sample for sample in samples if sample["id"] in test_ids],
    }
    for name, records in splits.items():
        with (output / f"{name}.json").open("x", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    info = {
        "source_dataset": "Agents-X/TIR-Bench",
        "source_revision": args.source_revision,
        "source_files": [str(source / name) for name in ("TIR-Bench.json", "data.zip")],
        "paper": "https://arxiv.org/html/2603.12056v1#A2.SS1",
        "seed": 42,
        "algorithm": (
            "One random.Random(42), categories in category_order; for each category, "
            "random.sample(source-order IDs, train_count + test_count); first "
            "train_count IDs form train, remaining IDs form test."
        ),
        "category_order": list(SPLIT_COUNTS),
        "category_counts": {
            category: {"train": counts[0], "test": counts[1]}
            for category, counts in SPLIT_COUNTS.items()
        },
        "source_category_counts": dict(Counter(row["task"] for row in rows)),
        "within_split_order": "Original JSON row order",
        "author_split_match": (
            "Not verified. Author split files and sampling code were not found "
            "in the public XSkill main tree. Seed and category quotas match the "
            "paper, but sample IDs may differ."
        ),
        "num_source_samples": len(rows),
        "num_filtered_samples": len(filtered),
        "num_images": len(exported),
        "image_encoding": "Original ZIP entry bytes, without re-encoding",
        "train_ids": [sample["id"] for sample in splits["train"]],
        "test_ids": [sample["id"] for sample in splits["test"]],
        "unused_filtered_ids": [
            row["id"] for row in filtered if row["id"] not in train_ids | test_ids
        ],
    }
    with (output / "split_info.json").open("x", encoding="utf-8") as handle:
        json.dump(info, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    # Check the written conversion against original annotations and image files.
    original = {row["id"]: row for row in rows}
    for index, name in enumerate(("train", "test")):
        saved = json.loads((output / f"{name}.json").read_text(encoding="utf-8"))
        assert Counter(sample["task"] for sample in saved) == {
            category: counts[index] for category, counts in SPLIT_COUNTS.items()
        }
        for sample in saved:
            row = original[sample["id"]]
            assert sample["problem"] == row["prompt"]
            assert sample["solution"] == row["answer"]
    for relative in exported:
        with Image.open(output / relative) as image:
            image.verify()
    print(
        f"Prepared train={len(splits['train'])}, test={len(splits['test'])}, "
        f"unused={len(info['unused_filtered_ids'])}, images={len(exported)}. "
        f"Output: {output}",
        flush=True,
    )
