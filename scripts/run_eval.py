"""
Runner script for evaluation harness.

Runs the evaluation over simulated scams, saves results to data/results.csv,
and prints the summary table and calibration diagnostics.
"""

from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from eval.harness import evaluate_all



def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    accounts = pd.read_csv(data_dir / "accounts.csv")
    txns = pd.read_csv(data_dir / "transactions.csv")
    scams = pd.read_csv(data_dir / "scam_truth.csv")

    start_time = time.time()
    results_df, first_scam_diag = evaluate_all(accounts, txns, scams)
    runtime = time.time() - start_time

    # Save to data/results.csv
    out_csv = data_dir / "results.csv"
    results_df.to_csv(out_csv, index=False)

    print("=" * 115)
    print("SMART FREEZE EVALUATION RESULTS (saved to data/results.csv)")
    print("=" * 115)

    unique_delays = results_df["delay"].unique()
    for d in unique_delays:
        sub = results_df[results_df["delay"] == d]
        print(f"\n--- DELAY = {d} minutes ---")
        print(sub.to_string(index=False))

    print("-" * 115)
    print(f"Total evaluation runtime: {runtime:.2f} seconds")
    print(
        f"First scam ({first_scam_diag.get('scam_id')}, as_of={first_scam_diag.get('as_of')}): "
        f"Non-mules with S > 0.5: raw = {first_scam_diag.get('non_mules_raw_s_gt_05')}, "
        f"calibrated = {first_scam_diag.get('non_mules_cal_s_gt_05')}"
    )
    print("=" * 115)


if __name__ == "__main__":
    main()

