"""
Tracing engine for Smart Freeze implementing three taint-tracking methods:
1. Proportional: Outflow carries taint in proportion to current balance taint.
2. FIFO: Lots ordered by arrival time (opening balance is oldest clean lot).
3. LIBR (Lowest Intermediate Balance Rule): Taint claim capped by running balance.
"""

from collections import deque
import pandas as pd


def trace(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    scam_id: str,
    as_of: float | None = None,
) -> pd.DataFrame:
    """
    Traces stolen money from a scam across accounts under Proportional, FIFO, and LIBR.
    If as_of is provided, uses only transactions with time <= as_of.
    Returns DataFrame with columns:
    [account_id, balance, tainted_prop, tainted_fifo, tainted_libr, tainted_min, tainted_max]
    """
    if as_of is not None:
        txns = txns[txns["time"] <= as_of]

    account_ids = accounts["account_id"].tolist()
    victim_set = set(accounts.loc[accounts["type"] == "victim", "account_id"])
    opening_balances = dict(zip(accounts["account_id"], accounts["opening_balance"].astype(float)))

    # Global ledger and method-specific state
    balances = opening_balances.copy()
    prop_tainted = {aid: 0.0 for aid in account_ids}
    libr_claim = {aid: 0.0 for aid in account_ids}
    fifo_lots = {
        aid: deque([[bal, 0.0]]) if bal > 0 else deque()
        for aid, bal in opening_balances.items()
    }

    # Sort transactions by (time, txn_id)
    sorted_txns = txns.sort_values(by=["time", "txn_id"])

    for _, txn in sorted_txns.iterrows():
        txn_id = txn["txn_id"]
        src = txn["src"]
        dst = txn["dst"]
        amount = float(txn["amount"])
        curr_scam_id = str(txn.get("scam_id", ""))

        src_bal = balances[src]
        if src_bal < amount - 1e-6:
            raise ValueError(f"Transaction {txn_id}: Insufficient balance in {src} ({src_bal} < {amount})")

        # 1. Compute tainted outflow for each method
        # Proportional
        if src_bal > 0:
            prop_out = amount * (prop_tainted[src] / src_bal)
        else:
            prop_out = 0.0

        # FIFO
        fifo_out = 0.0
        rem_to_take = amount
        lots = fifo_lots[src]
        while rem_to_take > 1e-9 and lots:
            lot = lots[0]
            lot_amt, lot_t = lot[0], lot[1]
            if lot_amt <= rem_to_take + 1e-9:
                fifo_out += lot_t
                rem_to_take -= lot_amt
                lots.popleft()
            else:
                fraction = rem_to_take / lot_amt
                t_taken = lot_t * fraction
                fifo_out += t_taken
                lot[0] -= rem_to_take
                lot[1] -= t_taken
                rem_to_take = 0.0

        # LIBR
        old_claim = libr_claim[src]
        new_src_bal = max(0.0, src_bal - amount)
        new_claim = min(old_claim, new_src_bal)
        libr_out = old_claim - new_claim

        # 2. Update src state
        balances[src] = new_src_bal
        prop_tainted[src] = max(0.0, prop_tainted[src] - prop_out)
        libr_claim[src] = new_claim

        # 3. Determine tainted inflow to dst
        # Seed: if scam_id matches and src is a victim, dst receives full amount as taint
        if curr_scam_id == scam_id and src in victim_set:
            prop_in = amount
            fifo_in = amount
            libr_in = amount
        else:
            prop_in = prop_out
            fifo_in = fifo_out
            libr_in = libr_out

        # 4. Update dst state
        balances[dst] += amount
        prop_tainted[dst] += prop_in
        libr_claim[dst] += libr_in
        fifo_lots[dst].append([amount, fifo_in])

    # Assemble result rows
    results = []
    for aid in account_ids:
        bal = balances[aid]
        # Victims never hold taint
        if aid in victim_set:
            p = f = l = 0.0
        else:
            p = min(bal, max(0.0, prop_tainted[aid]))
            f = min(bal, max(0.0, sum(lot[1] for lot in fifo_lots[aid])))
            l = min(bal, max(0.0, libr_claim[aid]))

        t_min = min(p, f, l)
        t_max = max(p, f, l)

        results.append({
            "account_id": aid,
            "balance": round(bal, 2),
            "tainted_prop": round(p, 2),
            "tainted_fifo": round(f, 2),
            "tainted_libr": round(l, 2),
            "tainted_min": round(t_min, 2),
            "tainted_max": round(t_max, 2),
        })

    return pd.DataFrame(results)
