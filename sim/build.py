import os
from pathlib import Path
import pandas as pd
from sim.normal import generate_normal
from sim.scams import add_scams
from sim.innocents import add_innocents


def build_all(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Runs full simulation pipeline:
    1. generate_normal
    2. add_scams
    3. add_innocents
    Writes output files to data/ directory.
    """
    # 1. Normal traffic
    accounts, txns = generate_normal(seed=seed)

    # 2. Add scams
    accounts, txns, scam_truth = add_scams(accounts, txns, n_scams=10, seed=seed)

    # 3. Add innocents and look-alikes
    accounts, txns, scam_truth, account_truth = add_innocents(accounts, txns, scam_truth, seed=seed)

    # Save to data/
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    accounts.to_csv(data_dir / "accounts.csv", index=False)
    txns.to_csv(data_dir / "transactions.csv", index=False)
    scam_truth.to_csv(data_dir / "scam_truth.csv", index=False)
    account_truth.to_csv(data_dir / "account_truth.csv", index=False)

    return accounts, txns, scam_truth, account_truth


def main():
    accounts, txns, scam_truth, account_truth = build_all(seed=42)

    print("=" * 50)
    print("Simulation Build Summary")
    print("=" * 50)
    print(f"Total Accounts:      {len(accounts)}")
    print(f"Total Transactions:  {len(txns)}")
    print(f"Total Scams:         {len(scam_truth)}")
    print("\nAccounts by Role:")
    role_counts = account_truth["role"].value_counts()
    for role, count in role_counts.items():
        print(f"  {role:<20}: {count}")
    print("=" * 50)


if __name__ == "__main__":
    main()
