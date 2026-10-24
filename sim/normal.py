import numpy as np
import pandas as pd


def generate_normal(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simulates 30 days (43,200 minutes) of normal financial transactions across ~500 accounts.
    Returns (accounts_df, txns_df).
    
    Hard rule: Simulate in time order and never let an account's balance go below 0
    (skip or shrink a transaction instead).
    """
    rng = np.random.default_rng(seed)

    # Total accounts ~500:
    # 5 employers (type 'merchant', large balances)
    # 3 aggregators (type 'aggregator')
    # Remaining: ~60% salaried, ~20% merchants, ~10% gig
    # For exactly 500 total accounts:
    # 5 employers
    # 300 salaried (60%)
    # 100 regular merchants (20%)
    # 50 gig workers (10%)
    # 3 aggregators
    # Total = 458 accounts (well within 450-550 range)
    # Let's adjust to be close to 500:
    # e.g., 5 employers + 300 salaried + 100 merchants + 50 gig + 3 aggregators + 42 distributed:
    # Let's do:
    # n_employers = 5
    # n_salaried = 310
    # n_merchants = 100
    # n_gig = 50
    # n_aggregators = 3
    # Total = 468
    
    n_employers = 5
    n_salaried = 320
    n_merchants = 110
    n_gig = 60
    n_aggregators = 3

    total_accounts = n_employers + n_salaried + n_merchants + n_gig + n_aggregators  # 498 accounts

    accounts = []
    # Account IDs: ACC_0000 to ACC_xxxx
    curr_id = 0

    # 1. Employers
    employer_ids = []
    for _ in range(n_employers):
        aid = f"ACC_{curr_id:04d}"
        curr_id += 1
        age_days = int(rng.integers(365, 3000))
        # Large balances for employers to pay salaries
        avg_monthly_inflow = float(rng.uniform(10_000_000, 30_000_000))
        opening_balance = float(rng.uniform(20_000_000, 50_000_000))
        employer_ids.append(aid)
        accounts.append({
            "account_id": aid,
            "type": "merchant",
            "age_days": age_days,
            "avg_monthly_inflow": avg_monthly_inflow,
            "opening_balance": opening_balance,
            "is_mule": 0,
            "role": "employer",
        })

    # 2. Salaried
    salaried_ids = []
    salaried_incomes = {}
    salaried_employers = {}
    for _ in range(n_salaried):
        aid = f"ACC_{curr_id:04d}"
        curr_id += 1
        age_days = int(rng.integers(90, 3000))
        # Monthly salary lognormal around 25,000 - 150,000 INR
        # log(50000) ~ 10.82
        salary = float(rng.lognormal(mean=10.8, sigma=0.4))
        avg_monthly_inflow = salary
        # Opening balance linked to income (0.2x to 1.5x monthly salary)
        opening_balance = float(salary * rng.uniform(0.2, 1.5))
        salaried_ids.append(aid)
        salaried_incomes[aid] = salary
        salaried_employers[aid] = rng.choice(employer_ids)
        accounts.append({
            "account_id": aid,
            "type": "salaried",
            "age_days": age_days,
            "avg_monthly_inflow": avg_monthly_inflow,
            "opening_balance": opening_balance,
            "is_mule": 0,
            "role": "salaried",
        })

    # 3. Regular Merchants
    merchant_ids = []
    for _ in range(n_merchants):
        aid = f"ACC_{curr_id:04d}"
        curr_id += 1
        age_days = int(rng.integers(90, 3000))
        # Monthly inflow lognormal around 100,000 - 800,000
        avg_monthly_inflow = float(rng.lognormal(mean=12.5, sigma=0.6))
        opening_balance = float(avg_monthly_inflow * rng.uniform(0.3, 1.2))
        merchant_ids.append(aid)
        accounts.append({
            "account_id": aid,
            "type": "merchant",
            "age_days": age_days,
            "avg_monthly_inflow": avg_monthly_inflow,
            "opening_balance": opening_balance,
            "is_mule": 0,
            "role": "merchant",
        })

    # 4. Gig workers
    gig_ids = []
    for _ in range(n_gig):
        aid = f"ACC_{curr_id:04d}"
        curr_id += 1
        age_days = int(rng.integers(90, 2000))
        # Inflows lognormal around 15,000 - 45,000
        avg_monthly_inflow = float(rng.lognormal(mean=10.2, sigma=0.5))
        opening_balance = float(avg_monthly_inflow * rng.uniform(0.1, 0.8))
        gig_ids.append(aid)
        accounts.append({
            "account_id": aid,
            "type": "gig",
            "age_days": age_days,
            "avg_monthly_inflow": avg_monthly_inflow,
            "opening_balance": opening_balance,
            "is_mule": 0,
            "role": "gig",
        })

    # 5. Aggregators
    aggregator_ids = []
    for _ in range(n_aggregators):
        aid = f"ACC_{curr_id:04d}"
        curr_id += 1
        age_days = int(rng.integers(180, 2500))
        avg_monthly_inflow = float(rng.uniform(2_000_000, 10_000_000))
        opening_balance = float(rng.uniform(500_000, 2_000_000))
        aggregator_ids.append(aid)
        accounts.append({
            "account_id": aid,
            "type": "aggregator",
            "age_days": age_days,
            "avg_monthly_inflow": avg_monthly_inflow,
            "opening_balance": opening_balance,
            "is_mule": 0,
            "role": "aggregator",
        })

    accounts_df = pd.DataFrame(accounts)
    # Store initial balances for simulation
    balances = {acc["account_id"]: float(acc["opening_balance"]) for acc in accounts}

    # Generate Planned Events / Transactions:
    # 1. Salary payouts:
    # Employers pay monthly salary to ~60% of accounts (salaried) around day 1 (minutes: day 1 = 0..1440, e.g., 400..1200)
    planned_txns = []

    for s_id in salaried_ids:
        emp = salaried_employers[s_id]
        salary = salaried_incomes[s_id]
        # Payout time around day 1: minutes between 480 (8 AM) and 1200 (8 PM)
        t = int(rng.integers(480, 1200))
        planned_txns.append({
            "time": t,
            "src": emp,
            "dst": s_id,
            "amount": round(salary, 2),
            "type": "salary"
        })

    # 2. Salaried rent payments:
    # Once a month, between day 2 and day 5 (minutes 1440 * 2 to 1440 * 5)
    # Pay to random merchant (or another account acting as landlord/rental agency)
    for s_id in salaried_ids:
        rent_time = int(rng.integers(1440 * 2, 1440 * 5))
        # Rent is typically 20-40% of salary
        rent_amount = round(salaried_incomes[s_id] * rng.uniform(0.2, 0.4), 2)
        landlord = rng.choice(merchant_ids)
        planned_txns.append({
            "time": rent_time,
            "src": s_id,
            "dst": landlord,
            "amount": rent_amount,
            "type": "rent"
        })

    # 3. Salaried purchases from merchants:
    # "buy from merchants a few times a week" -> ~12-16 purchases across 30 days
    all_merchants = merchant_ids + employer_ids
    for s_id in salaried_ids:
        n_purchases = int(rng.integers(10, 18))
        purchase_times = rng.integers(0, 43200, size=n_purchases)
        for t in purchase_times:
            # Lognormal amount for retail purchases (e.g. groceries, dining, shopping): median ~500, log(500) ~ 6.2
            amt = round(float(rng.lognormal(mean=6.2, sigma=0.8)), 2)
            dst_m = rng.choice(merchant_ids)
            planned_txns.append({
                "time": int(t),
                "src": s_id,
                "dst": dst_m,
                "amount": max(10.0, amt),
                "type": "purchase"
            })

    # 4. Gig workers:
    # Irregular small inflows from various accounts (salaried or merchants) or aggregators
    for g_id in gig_ids:
        n_gigs = int(rng.integers(15, 35))
        gig_times = rng.integers(0, 43200, size=n_gigs)
        for t in gig_times:
            amt = round(float(rng.lognormal(mean=6.5, sigma=0.7)), 2)
            # Gig worker receives payment from merchant, employer, or customer
            sender = rng.choice(merchant_ids + salaried_ids)
            planned_txns.append({
                "time": int(t),
                "src": sender,
                "dst": g_id,
                "amount": max(50.0, amt),
                "type": "gig_payment"
            })
        # Gig workers also spend at merchants
        n_spends = int(rng.integers(8, 15))
        spend_times = rng.integers(0, 43200, size=n_spends)
        for t in spend_times:
            amt = round(float(rng.lognormal(mean=5.5, sigma=0.7)), 2)
            dst_m = rng.choice(merchant_ids)
            planned_txns.append({
                "time": int(t),
                "src": g_id,
                "dst": dst_m,
                "amount": max(10.0, amt),
                "type": "gig_spend"
            })

    # 5. Merchants:
    # In addition to inflows from salaried/gig, periodic payouts to suppliers/employers
    # Payouts 2 to 4 times a month
    for m_id in merchant_ids:
        n_payouts = int(rng.integers(2, 5))
        payout_times = rng.integers(1440, 43200, size=n_payouts)
        for t in payout_times:
            # Supplier payout amount
            amt = round(float(rng.lognormal(mean=10.0, sigma=0.8)), 2)
            dst_supplier = rng.choice(employer_ids + merchant_ids)
            if dst_supplier != m_id:
                planned_txns.append({
                    "time": int(t),
                    "src": m_id,
                    "dst": dst_supplier,
                    "amount": amt,
                    "type": "supplier_payout"
                })

    # 6. Aggregators:
    # 3 aggregators: many senders, settle most inflow onward within an hour (an innocent look-alike)
    # Senders: various salaried, merchants, gig
    all_senders = salaried_ids + merchant_ids + gig_ids
    for agg_id in aggregator_ids:
        n_inflows = int(rng.integers(120, 200))
        inflow_times = rng.integers(0, 42000, size=n_inflows)
        for t_in in inflow_times:
            amt = round(float(rng.lognormal(mean=7.5, sigma=0.8)), 2)
            amt = max(100.0, amt)
            sender = rng.choice(all_senders)
            planned_txns.append({
                "time": int(t_in),
                "src": sender,
                "dst": agg_id,
                "amount": amt,
                "type": "agg_inflow"
            })
            # Settle most inflow onward (e.g. 95% - 99% of it) within an hour (1..59 minutes)
            delay = int(rng.integers(5, 55))
            t_out = min(43200, int(t_in + delay))
            settle_amt = round(amt * float(rng.uniform(0.95, 0.99)), 2)
            settle_dst = rng.choice(merchant_ids + employer_ids)
            planned_txns.append({
                "time": t_out,
                "src": agg_id,
                "dst": settle_dst,
                "amount": settle_amt,
                "type": "agg_settle"
            })

    # Sort planned transactions strictly by time
    planned_txns.sort(key=lambda x: x["time"])

    # Simulate in time order and never let balance go below 0
    executed_txns = []
    txn_counter = 0

    for pt in planned_txns:
        src = pt["src"]
        dst = pt["dst"]
        requested_amt = round(float(pt["amount"]), 2)
        t = pt["time"]

        src_bal = balances[src]
        if src_bal <= 0:
            # Cannot spend anything, skip
            continue

        # If balance is less than requested amount, shrink to available balance
        if src_bal < requested_amt:
            # Floor to 2 decimals or exact balance to prevent floating point overshoot
            actual_amt = round(np.floor(src_bal * 100) / 100.0, 2)
        else:
            actual_amt = requested_amt

        if actual_amt <= 0:
            continue

        # Update balances
        balances[src] -= actual_amt
        balances[dst] += actual_amt

        executed_txns.append({
            "txn_id": f"TXN_{txn_counter:06d}",
            "time": t,
            "src": src,
            "dst": dst,
            "amount": actual_amt,
            "scam_id": ""
        })
        txn_counter += 1

    # Prepare final clean accounts_df matching required columns:
    # account_id, type, age_days, avg_monthly_inflow, opening_balance, is_mule
    final_accounts_df = accounts_df[[
        "account_id",
        "type",
        "age_days",
        "avg_monthly_inflow",
        "opening_balance",
        "is_mule"
    ]].copy()

    # Final txns_df matching required columns:
    # txn_id, time (int minutes, 0..43200 = 30 days), src, dst, amount, scam_id
    final_txns_df = pd.DataFrame(executed_txns, columns=[
        "txn_id",
        "time",
        "src",
        "dst",
        "amount",
        "scam_id"
    ])

    return final_accounts_df, final_txns_df
