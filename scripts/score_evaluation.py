"""Summarize artifact-bound human adjudications against the selected seeded defects."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score(run: Path) -> dict:
    run = run.resolve()
    manifest = read_json(run / "manifest.json")
    judgments = read_json(run / "judgments.json")
    truth_bytes = (run / "ground-truth.json").read_bytes()
    if hashlib.sha256(truth_bytes).hexdigest() != manifest["ground_truth_sha256"]:
        raise ValueError("Ground truth differs from the original manifest")
    truth = {case["id"]: case for case in json.loads(truth_bytes)["cases"]}
    if judgments["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Judgments reference a different dataset")
    completed = {
        case["case_id"]: case for case in manifest["cases"] if case["status"] == "COMPLETE"
    }
    stages = ("draft", "revision") if manifest["settings"]["paired"] else ("final",)
    expected = {(case_id, stage) for case_id in completed for stage in stages}
    if not expected:
        raise ValueError("No completed model responses to score")
    result = {
        "completed_cases": len(completed),
        "incomplete_or_unstarted_cases": len(manifest["cases"]) - len(completed),
        "stages": {},
    }
    for review in judgments["reviews"]:
        case_id, stage = review["case_id"], review["stage"]
        if (case_id, stage) not in expected:
            raise ValueError("Duplicate or unexpected case/stage review")
        expected.remove((case_id, stage))
        if review["status"] != "verified" or not (review["reviewer"] or "").strip():
            raise ValueError(f"{case_id}/{stage} needs signed human adjudication")
        path = (run / completed[case_id]["structured_report"]).resolve()
        if not path.is_relative_to(run):
            raise ValueError("Report outside selected run")
        response = read_json(path)[
            {"draft": "draft", "revision": "revision", "final": "analysis"}[stage]
        ]
        case = completed[case_id]
        digest = case["analysis_sha256"] if stage == "final" else case["pair"][stage + "_sha256"]
        if not hashlib.sha256(response.encode()).hexdigest() == review["artifact_sha256"] == digest:
            raise ValueError("Judged artifact differs from recorded response")

        totals = result["stages"].setdefault(
            stage,
            {
                "tp": 0,
                "fp": 0,
                "fn": 0,
                "ambiguous": 0,
                "supported_additional": 0,
            },
        )
        seeds = {defect["id"] for defect in truth[case_id]["defects"]}
        detected = set()
        for finding in review["findings"]:
            kind = finding["classification"]
            if (
                not finding["quote"].strip()
                or finding["quote"] not in response
                or not finding["reason"].strip()
            ):
                raise ValueError(
                    "Each classified finding needs a response excerpt and evidence-based reason"
                )
            if kind == "seeded":
                defect = finding["defect_id"]
                if defect not in seeds or defect in detected:
                    raise ValueError("Each seeded defect can match at most one finding")
                detected.add(defect)
                totals["tp"] += 1
            elif kind in {"unsupported", "ambiguous", "supported_additional"}:
                totals["fp" if kind == "unsupported" else kind] += 1
            else:
                raise ValueError(f"Unknown classification {kind}")
        missed = review["missed_defects"]
        if set(missed) != seeds - detected or len(set(missed)) != len(missed):
            raise ValueError("Classify every remaining seeded defect as missed")
        totals["fn"] += len(missed)
    if expected:
        raise ValueError("Every complete case/stage requires a verified review")
    for totals in result["stages"].values():
        tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
        totals["precision"] = tp / (tp + fp) if tp + fp else None
        totals["recall"] = tp / (tp + fn) if tp + fn else None
        totals["f1"] = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    try:
        result = score(args.run)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(1, f"Unable to score run: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
