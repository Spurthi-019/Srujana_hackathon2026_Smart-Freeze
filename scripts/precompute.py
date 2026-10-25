"""
Precompute engine outputs for Smart Freeze Streamlit app.

Computes and caches:
- trace_df (engine.taint.trace)
- scores_df (engine.score.score_all with S calibration from eval.harness)
- harm_df (engine.harm.harm_all)
for each scam in data/scam_truth.csv and each delay in [60, 180, 300].

Saved to data/cache/<scam_id>_<delay>_{trace,scores,harm}.csv.
"""

import json
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from engine.harm import harm_all
from engine.score import score_all
from engine.taint import trace
from eval.harness import calibrate_scores

DELAYS = [60, 180, 300]


def main() -> None:
    data_dir = PROJECT_ROOT / "data"
    cache_dir = data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    accounts = pd.read_csv(data_dir / "accounts.csv")
    txns = pd.read_csv(data_dir / "transactions.csv")
    scams = pd.read_csv(data_dir / "scam_truth.csv")

    is_mule_series = accounts.set_index("account_id")["is_mule"].astype(int)

    # Score cache per as_of to avoid recomputing score_all multiple times for same as_of
    scores_by_as_of = {}

    start_time = time.time()
    total_tasks = len(scams) * len(DELAYS)
    task_count = 0

    print(f"Starting precomputation for {len(scams)} scams across delays {DELAYS}...")

    for _, scam_row in scams.iterrows():
        sid = scam_row["scam_id"]
        t0 = float(scam_row["start_time"])

        for delay in DELAYS:
            as_of = min(t0 + delay, 43200.0)

            # 1. Scores (cached per as_of)
            if as_of not in scores_by_as_of:
                raw_scores = score_all(accounts, txns, seed=42, as_of=as_of)
                cal_scores = calibrate_scores(raw_scores, is_mule_series.loc[raw_scores["account_id"]])
                scores_by_as_of[as_of] = cal_scores
            cal_scores = scores_by_as_of[as_of]

            # 2. Trace
            trace_df = trace(accounts, txns, sid, as_of=as_of)

            # 3. Harm
            harm_df = harm_all(accounts, txns, as_of=as_of)

            # Save to cache
            trace_path = cache_dir / f"{sid}_{delay}_trace.csv"
            scores_path = cache_dir / f"{sid}_{delay}_scores.csv"
            harm_path = cache_dir / f"{sid}_{delay}_harm.csv"

            # Prepare scores dataframe with reasons_for and reasons_against as JSON strings
            save_scores = cal_scores.copy()
            if "reasons_for" in save_scores.columns:
                save_scores["reasons_for"] = save_scores["reasons_for"].apply(
                    lambda x: json.dumps(x) if isinstance(x, (list, tuple)) else str(x)
                )
            if "reasons_against" in save_scores.columns:
                save_scores["reasons_against"] = save_scores["reasons_against"].apply(
                    lambda x: json.dumps(x) if isinstance(x, (list, tuple)) else str(x)
                )

            trace_df.to_csv(trace_path, index=False)
            save_scores.to_csv(scores_path, index=False)
            harm_df.to_csv(harm_path, index=True)  # harm_df is indexed by account_id


            task_count += 1
            print(f"[{task_count}/{total_tasks}] Precomputed {sid} (delay={delay}m, as_of={as_of}m)")

    elapsed = time.time() - start_time
    print(f"\nDone! Precomputed all {total_tasks} scam/delay combinations in {elapsed:.2f} seconds.")
    print(f"Cache files saved in {cache_dir.resolve()}")


if __name__ == "__main__":
    main()
