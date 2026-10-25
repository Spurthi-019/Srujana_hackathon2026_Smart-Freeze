"""
Runner script for rule-robustness evaluation.

Runs evaluate_robustness across simulated scams and delays [60, 180, 300],
saves results to data/results_robust.csv, and prints one table per delay.
"""

from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from eval.robust import evaluate_robustness


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    accounts = pd.read_csv(data_dir / "accounts.csv")
    txns = pd.read_csv(data_dir / "transactions.csv")
    scams = pd.read_csv(data_dir / "scam_truth.csv")

    start_time = time.time()
    results_df = evaluate_robustness(accounts, txns, scams)
    runtime = time.time() - start_time

    # Save to data/results_robust.csv
    out_csv = data_dir / "results_robust.csv"
    results_df.to_csv(out_csv, index=False)

    print("=" * 115)
    print("RULE-ROBUSTNESS EVALUATION RESULTS (saved to data/results_robust.csv)")
    print("=" * 115)

    display_cols = [
        "policy",
        "lam",
        "rec_rate_mean",
        "rec_rate_worst",
        "clean_blocked_mean",
        "clean_blocked_worst",
    ]

    target_delays = [180, 300]
    for d in target_delays:
        sub = results_df[results_df["delay"] == d]
        mask = (
            sub["policy"].isin(["lien_only", "lien_prop", "lien_fifo", "lien_libr"])
            | ((sub["policy"] == "tarazu_0.1") & (sub["lam"] == 0.1))
            | ((sub["policy"] == "tarazu_1.0") & (sub["lam"] == 1.0))
        )
        filtered = sub[mask][display_cols]
        print(f"\n--- DELAY = {d} minutes ---")
        print(filtered.to_string(index=False))

    print("-" * 115)
    print(f"Total evaluation runtime: {runtime:.2f} seconds")
    print("=" * 115)



if __name__ == "__main__":
    main()
