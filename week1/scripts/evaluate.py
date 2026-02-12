#!/usr/bin/env python3
"""Evaluation script – measures system performance against a test set.

Usage (server must be running):
    python scripts/evaluate.py                       # default 20 samples
    python scripts/evaluate.py --samples 50          # 50 samples
    python scripts/evaluate.py --file test_claims.json

If --file is not provided, a built-in set of curated test claims is used.

Metrics reported:
  - Verification accuracy (vs expected label)
  - Citation presence rate
  - Hallucination rate (citations with no URL)
  - Latency (p50, p95, mean)
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8000/api/verify"

# ---------------------------------------------------------------------------
# Built-in test claims (curated)
# ---------------------------------------------------------------------------

BUILTIN_CLAIMS: list[dict] = [
    {"text": "The Earth is flat.", "expected": "FALSE"},
    {"text": "Water boils at 100 degrees Celsius at sea level.", "expected": "TRUE"},
    {"text": "Humans only use 10% of their brains.", "expected": "FALSE"},
    {"text": "The Great Wall of China is visible from space with the naked eye.", "expected": "FALSE"},
    {"text": "Lightning never strikes the same place twice.", "expected": "FALSE"},
    {"text": "Vitamin C cures the common cold.", "expected": "MISLEADING"},
    {"text": "The speed of light is approximately 300,000 km per second.", "expected": "TRUE"},
    {"text": "Albert Einstein failed mathematics in school.", "expected": "FALSE"},
    {"text": "Goldfish have a memory span of only 3 seconds.", "expected": "FALSE"},
    {"text": "The Amazon rainforest produces 20% of the world's oxygen.", "expected": "MISLEADING"},
    {"text": "Mount Everest is the tallest mountain on Earth.", "expected": "TRUE"},
    {"text": "Bananas are berries, but strawberries are not.", "expected": "TRUE"},
    {"text": "Napoleon Bonaparte was exceptionally short.", "expected": "MISLEADING"},
    {"text": "The Sahara is the largest desert in the world.", "expected": "MISLEADING"},
    {"text": "Bats are blind.", "expected": "FALSE"},
    {"text": "Eating carrots significantly improves night vision.", "expected": "MISLEADING"},
    {"text": "Diamond is the hardest natural substance.", "expected": "TRUE"},
    {"text": "Cracking your knuckles causes arthritis.", "expected": "FALSE"},
    {"text": "The tongue has specific taste zones.", "expected": "FALSE"},
    {"text": "Sharks can detect a single drop of blood in an Olympic swimming pool.", "expected": "MISLEADING"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VERDICT_NORMALISE = {
    "TRUE": "TRUE",
    "FALSE": "FALSE",
    "MISLEADING": "MISLEADING",
    "NOT_ENOUGH_EVIDENCE": "NOT_ENOUGH_EVIDENCE",
    "NEE": "NOT_ENOUGH_EVIDENCE",
}


def normalise_verdict(v: str) -> str:
    return VERDICT_NORMALISE.get(v.upper().strip(), v.upper().strip())


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------

def evaluate(claims: list[dict], api_url: str = API_URL) -> dict:
    """Run each claim through the API and compute metrics."""

    correct = 0
    total = 0
    latencies: list[float] = []
    citation_counts: list[int] = []
    hallucination_flags: list[bool] = []
    nee_count = 0
    errors = 0

    for i, item in enumerate(claims):
        text = item["text"]
        expected = normalise_verdict(item.get("expected", ""))
        logger.info("[%d/%d] Verifying: %s", i + 1, len(claims), text[:80])

        start = time.time()
        try:
            resp = httpx.post(
                api_url,
                json={"text": text},
                timeout=60.0,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            logger.error("  ERROR: %s", exc)
            errors += 1
            continue
        elapsed = time.time() - start
        latencies.append(elapsed)

        predicted = normalise_verdict(result.get("verdict", ""))
        citations = result.get("citations", [])
        citation_counts.append(len(citations))

        # Check for hallucinated citations (empty URL)
        has_hallucinated = any(not c.get("url") for c in citations)
        hallucination_flags.append(has_hallucinated)

        if predicted == "NOT_ENOUGH_EVIDENCE":
            nee_count += 1

        match = predicted == expected
        if match:
            correct += 1
        total += 1

        logger.info(
            "  Predicted=%s  Expected=%s  Match=%s  Citations=%d  Time=%.1fs",
            predicted, expected, match, len(citations), elapsed,
        )

    # Compute metrics
    accuracy = correct / total if total else 0.0
    citation_rate = sum(1 for c in citation_counts if c > 0) / total if total else 0.0
    hallucination_rate = sum(hallucination_flags) / total if total else 0.0
    nee_rate = nee_count / total if total else 0.0

    latency_stats = {}
    if latencies:
        latencies_sorted = sorted(latencies)
        latency_stats = {
            "mean_s": statistics.mean(latencies),
            "p50_s": statistics.median(latencies),
            "p95_s": latencies_sorted[int(len(latencies_sorted) * 0.95)],
            "min_s": min(latencies),
            "max_s": max(latencies),
        }

    metrics = {
        "total_claims": len(claims),
        "evaluated": total,
        "errors": errors,
        "accuracy": round(accuracy, 4),
        "citation_presence_rate": round(citation_rate, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "not_enough_evidence_rate": round(nee_rate, 4),
        "latency": {k: round(v, 2) for k, v in latency_stats.items()},
    }

    return metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate claim verification system")
    parser.add_argument("--samples", type=int, default=20, help="Number of built-in claims to test")
    parser.add_argument("--file", type=str, help="JSON file with test claims ([{text, expected}])")
    parser.add_argument("--url", type=str, default=API_URL, help="API base URL")
    args = parser.parse_args()

    if args.file:
        claims = json.loads(Path(args.file).read_text())
    else:
        claims = BUILTIN_CLAIMS[: args.samples]

    logger.info("Evaluating %d claims against %s", len(claims), args.url)
    metrics = evaluate(claims, api_url=args.url)

    print("\n" + "=" * 60)
    print("  EVALUATION RESULTS")
    print("=" * 60)
    for k, v in metrics.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
    print("=" * 60)

    # Save to file
    out_path = Path(__file__).resolve().parent.parent / "data" / "eval_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2))
    logger.info("Results saved to %s", out_path)


if __name__ == "__main__":
    main()
