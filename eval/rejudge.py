"""Append named reevaluations to existing metrics while preserving original scores."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from infer_api_utils import check_sample_completed
from utils.llm_judger import _extract_answer_from_text, _get_client, compute_score


SUCCESS_STATUSES = {"scored", "answer_extraction_failed"}
ERROR_PREFIXES = (
    "Evaluation API error:",
    "Evaluation failed:",
    "Error processing evaluation response:",
    "Evaluation error:",
    "Invalid reward value:",
)
EXTRA_INFO = {
    "acc_reward_weight": 1.0,
    "gpt_extract_answer": True,
    "extract_answer_tags": "strict",
}


def write_json(path, data):
    # Replace one record atomically so interrupted writes are safe to retry.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def update_reevaluation(path, name, values):
    """Merge one named evaluation without replacing original or other scores."""
    document = json.loads(path.read_text())
    entry = document.setdefault("reevaluations", {}).setdefault(name, {})
    entry.update(values)
    write_json(path, document)


def load_tasks(source):
    """Require complete original results and load the exact saved judge inputs."""
    summary = json.loads((source / "metrics_at_k.json").read_text())
    args = SimpleNamespace(skip_completed=True, rollouts_per_sample=summary["num_rollouts"])
    sample_dirs = sorted(p.parent for p in source.glob("*/metrics_sample.json"))
    if not sample_dirs or len(sample_dirs) != summary["num_samples"]:
        raise ValueError("Source sample count does not match its dataset summary")
    tasks = []
    for directory in sample_dirs:
        completed = check_sample_completed(str(directory), args)
        if completed is None:
            raise ValueError("Incomplete source question: " + directory.name)
        for result in completed["sample_rollout_results"]:
            if result["question_id"] != directory.name:
                raise ValueError("Source question ID mismatch: " + directory.name)
            tasks.append((directory.name, result["_rollout_idx"], result))
    return tasks, args.rollouts_per_sample


def score_rollout(task):
    """Keep extraction failures as zero, but exclude judge/service errors."""
    question_id, rollout_idx, result = task
    predictions = [m["content"] for m in result["conversation_history"] if m["role"] == "assistant"]
    record = {
        "question_id": question_id,
        "rollout_idx": rollout_idx,
        "accuracy_score": None,
        "status": "evaluation_error",
        "trajectory_analysis": "",
        "extracted_answer": None,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if not result["ground_truth"]:
            raise ValueError("Missing ground truth; original inference did not judge this answer")
        _, answer = _extract_answer_from_text(" ".join(predictions), predictions, "strict")
        record["extracted_answer"] = answer
        score, analysis = compute_score(
            prompt=result["prompt"],
            predict_str_list=predictions,
            ground_truth=result["ground_truth"],
            extra_info=EXTRA_INFO,
        )
        record["trajectory_analysis"] = analysis
        if analysis.startswith(ERROR_PREFIXES):
            return record
        record["status"] = "answer_extraction_failed" if analysis == "Answer extraction failed" else "scored"
        record["accuracy_score"] = score
    except Exception as exc:
        # A failed API call or malformed saved answer must never become a zero.
        record["trajectory_analysis"] = f"{type(exc).__name__}: {exc}"
    return record


def summarize(tasks, records, source, rollouts, name):
    sample_ids = list(dict.fromkeys(task[0] for task in tasks))
    complete_samples = []
    for question_id in sample_ids:
        rows = [records.get((question_id, i)) for i in range(rollouts)]
        scores = [row["accuracy_score"] if row else None for row in rows]
        completed = all(row and row["status"] in SUCCESS_STATUSES for row in rows)
        sample = {"question_id": question_id, "num_rollouts": rollouts, "accuracies": scores, "completed": completed}
        if completed:
            for k in range(1, rollouts + 1):
                sample[f"pass@{k}"] = float(any(score > 0 for score in scores[:k]))
                sample[f"average@{k}"] = sum(scores[:k]) / k
            complete_samples.append(sample)
        update_reevaluation(source / question_id / "metrics_sample.json", name, sample)
    summary = {
        "num_samples": len(sample_ids),
        "num_rollouts": rollouts,
        "num_completed_samples": len(complete_samples),
        "num_scored_rollouts": sum(row["status"] in SUCCESS_STATUSES for row in records.values()),
        "num_extraction_failures": sum(row["status"] == "answer_extraction_failed" for row in records.values()),
        "num_evaluation_errors": sum(row["status"] == "evaluation_error" for row in records.values()),
        "num_pending_rollouts": len(tasks) - len(records),
        "completed": len(complete_samples) == len(sample_ids),
        "k_metrics": None,
    }
    # Publish dataset metrics only when no API errors or missing scores remain.
    if summary["completed"]:
        summary["k_metrics"] = {
            str(k): {
                "pass_at_k": round(sum(s[f"pass@{k}"] for s in complete_samples) / len(sample_ids), 4),
                "average_at_k": round(sum(s[f"average@{k}"] for s in complete_samples) / len(sample_ids), 4),
            }
            for k in range(1, rollouts + 1)
        }
    update_reevaluation(source / "metrics_at_k.json", name, summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="Completed inference directory; append named scores to its metrics files.")
    parser.add_argument("--evaluation-name", required=True, help="Name under reevaluations; reuse to resume, change for an independent evaluation.")
    parser.add_argument("--num-workers", type=int, default=4)
    args = parser.parse_args()
    source = args.input_dir.resolve()
    name = args.evaluation_name
    if not name.strip():
        parser.error("--evaluation-name must not be empty")
    if args.num_workers < 1:
        parser.error("--num-workers must be positive")

    # Keep original scores and prevent mixed judges within one evaluation name.
    tasks, rollouts = load_tasks(source)
    client = _get_client()
    settings = {
        "verifier_model": client.model_name,
        "verifier_endpoint": str(client.client.base_url),
        "num_rollouts": rollouts,
        "question_ids": list(dict.fromkeys(task[0] for task in tasks)),
        "extraction_mode": "strict",
        "temperature_attempts": [0.0, 0.2, 0.4, 0.6, 0.8],
        "max_tokens": 8192,
        "timeout_seconds": 120,
    }
    summary_path = source / "metrics_at_k.json"
    previous = json.loads(summary_path.read_text()).get("reevaluations", {}).get(name)
    if previous is not None and previous.get("settings") != settings:
        parser.error("Evaluation name has different judge settings or samples; choose another name")
    update_reevaluation(summary_path, name, {"settings": settings})

    # Skip only successful scores; failed judge calls are retried on resume.
    records = {}
    pending = []
    for task in tasks:
        key = task[:2]
        path = source / key[0] / f"rollout_{key[1]}" / "metrics.json"
        record = json.loads(path.read_text()).get("reevaluations", {}).get(name)
        if record is not None:
            if (record["question_id"], record["rollout_idx"]) != key:
                raise ValueError("Stored score identity mismatch: " + str(path))
            records[key] = record
            if record["status"] in SUCCESS_STATUSES:
                continue
        pending.append(task)
    summarize(tasks, records, source, rollouts, name)
    print(f"Loaded {len(tasks)} rollouts; reusing {len(tasks) - len(pending)}, grading {len(pending)}.", flush=True)
    with ThreadPoolExecutor(max_workers=args.num_workers) as pool:
        futures = {pool.submit(score_rollout, task): task[:2] for task in pending}
        for future in as_completed(futures):
            key = futures[future]
            record = future.result()
            update_reevaluation(source / key[0] / f"rollout_{key[1]}" / "metrics.json", name, record)
            records[key] = record
            print(f"{key[0]}/rollout_{key[1]}: {record['status']} score={record['accuracy_score']}", flush=True)
    summary = summarize(tasks, records, source, rollouts, name)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    raise SystemExit(0 if summary["completed"] else 1)
