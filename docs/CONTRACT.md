Data (built by python -m sim.build into data/, gitignored):
accounts.csv: account_id, type (salaried|merchant|gig|aggregator|mule|victim|exit), age_days, avg_monthly_inflow, opening_balance, is_mule (0/1 truth)
transactions.csv: txn_id, time (int minutes), src, dst, amount, scam_id (blank if normal)
scam_truth.csv: scam_id, shape, start_time, victim_ids, total_stolen, exit_total, remaining_in_mules, duration_min, mule_ids, to_bystanders
account_truth.csv: account_id, role, true_tainted_received, scam_ids

Taint seeding: for a scam_id, txns with that scam_id whose src is a victim inject tainted money. All later txns (any scam_id) propagate taint per method.

trace(accounts, txns, scam_id) -> DataFrame[account_id, balance, tainted_prop, tainted_fifo, tainted_libr, tainted_min, tainted_max]
mule_score(account_id, scores_df) -> dict(S, B, T, H, reasons_for, reasons_against)
harm_all(accounts, txns, as_of=None) -> DataFrame indexed by account_id [harm_score, salary_dependence, float_need, thin_cover, cover_days]
innocent_blocked(balance, tainted_min, tainted_max, held) -> dict(low, high)
decide(row, lam) -> dict(action in {none, lien, lien_cap, timed_hold}, lien_amount, cap_share, hold_hours, needs_human, expected_recovered, expected_clean_blocked, losses, note)
decide_all(trace_df, scores_df, harm_df, txns, as_of=None, lam=1.0) -> DataFrame[account_id, action, lien_amount, cap_share, hold_hours, needs_human, expected_recovered, expected_clean_blocked, losses, note]

Reference test (must pass): account R opening balance 1000 (own). Victim V sends R 4000. R sends out 2000. A clean account sends R 2000. R sends out 1000. Final balance 4000. Expected tainted in R: proportional 1920, FIFO 2000, LIBR 3000.
