"""Export AgentVista images and create an XSkill accumulation/test split."""

import argparse
import io
import json
import random
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

if __name__ == "__main__":
    # Parse explicit input and output directories.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing the original Parquet shards.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New directory for images, split JSON files, and split metadata.",
    )
    args = parser.parse_args()
    source = args.input_dir
    output = args.output_dir

    # Keep source files unchanged and create a separate output directory.
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    samples = []
    source_files = sorted(source.glob("*.parquet"))
    image_count = 0

    # Preserve embedded image bytes and assign IDs in source row order.
    for source_file in source_files:
        parquet = pq.ParquetFile(source_file)
        for batch in parquet.iter_batches(batch_size=8):
            for row in batch.to_pylist():
                sample_id = f"agentvista_{len(samples):04d}"
                image_paths = []
                for image_index, embedded in enumerate(row["images"]):
                    payload = embedded["bytes"]
                    with Image.open(io.BytesIO(payload)) as image:
                        suffix = image.format.lower()
                        image.verify()
                    relative = f"images/{sample_id}_{image_index}.{suffix}"
                    with (output / relative).open("xb") as handle:
                        handle.write(payload)
                    image_paths.append(relative)
                    image_count += 1
                samples.append(
                    {
                        "doc_id": sample_id,
                        "problem": row["problem"],
                        "solution": row["answer"],
                        "images": image_paths,
                        "domain": row["domain"],
                        "subdomain": row["subdomain"],
                    }
                )
        print(f"Exported {source_file.name}: {len(samples)} samples", flush=True)

    # Sample accumulation IDs while retaining source order within both splits.
    assert len(samples) == 209, f"Unexpected source size: {len(samples)}"
    train_indices = set(random.Random(42).sample(range(len(samples)), 100))
    train = [sample for index, sample in enumerate(samples) if index in train_indices]
    test = [sample for index, sample in enumerate(samples) if index not in train_indices]
    for name, records in (("train", train), ("test", test)):
        with (output / f"{name}.json").open("x", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    info = {
        "source_dataset": "Warrieryes/AgentVista",
        "source_files": [str(path) for path in source_files],
        "source_order": "Sorted parquet filenames, then original row order",
        "seed": 42,
        "algorithm": "random.Random(42).sample(range(209), 100)",
        "within_split_order": "Original source row order",
        "author_split_match": "Not verified; author sample IDs are unavailable",
        "image_encoding": "Original embedded bytes, without re-encoding",
        "num_samples": len(samples),
        "num_images": image_count,
        "train_ids": [sample["doc_id"] for sample in train],
        "test_ids": [sample["doc_id"] for sample in test],
    }
    with (output / "split_info.json").open("x", encoding="utf-8") as handle:
        json.dump(info, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    # Verify saved splits and every exported image before reporting completion.
    saved_train = json.loads((output / "train.json").read_text())
    saved_test = json.loads((output / "test.json").read_text())
    train_ids = {sample["doc_id"] for sample in saved_train}
    test_ids = {sample["doc_id"] for sample in saved_test}
    assert len(saved_train) == len(train_ids) == 100
    assert len(saved_test) == len(test_ids) == 109
    assert train_ids.isdisjoint(test_ids)
    assert len(train_ids | test_ids) == 209
    for sample in saved_train + saved_test:
        assert sample["problem"] and sample["solution"]
        for relative in sample["images"]:
            with Image.open(output / relative) as image:
                image.verify()
    print(
        f"Verified: train=100, test=109, images={image_count}, "
        f"disjoint IDs, all images readable. Output: {output}",
        flush=True,
    )
