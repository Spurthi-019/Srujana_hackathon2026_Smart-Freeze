import React, { useState, useEffect } from 'react';
import TracingPanel from './TracingPanel';
import PriorityPanel from './PriorityPanel';
import HarmPanel from './HarmPanel';
import ComparisonPanel from './ComparisonPanel';
import HolderExplanation from './HolderExplanation';
import HoldClock from './HoldClock';

/**
 * AccountCard: Displays comprehensive account details, tracing, priority,
 * harm assessment, policy comparison, evidence what-if workflow, hold clock,
 * and allows downloading plain-text decision records.
 * NOTE: Never display is_mule or role.
 */
export default function AccountCard({
  accountId,
  scamId,
  delay,
  lam,
  auditLog = [],
  onApproveRelease,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [clockInfo, setClockInfo] = useState({ explanationDay: null, decisionDueDay: 30 });

  // Fetch account data whenever accountId, scamId, delay, or lam change
  useEffect(() => {
    if (!accountId || !scamId) {
      setData(null);
      return;
    }

    setLoading(true);
    setError(null);

    fetch(`/api/account?account_id=${encodeURIComponent(accountId)}&scam_id=${encodeURIComponent(scamId)}&delay=${delay}&lam=${lam}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then((accData) => {
        setData(accData);
        setError(null);
      })
      .catch((err) => {
        setError(`Failed to load account details: ${err.message}`);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [accountId, scamId, delay, lam]);

  // Handle building and downloading plain-text decision record
  const handleDownloadRecord = () => {
    if (!data) return;

    const {
      balance = 0,
      type = 'unknown',
      tainted_prop = 0,
      tainted_fifo = 0,
      tainted_libr = 0,
      tainted_min = 0,
      tainted_max = 0,
      S = 0,
      B = 0,
      T = 0,
      H = 0,
      reasons_for = [],
      reasons_against = [],
      decision = {},
      smart = {},
    } = data;

    const currentAction = decision?.action || 'none';
    const amountHeld = smart?.held ?? 0;
    const note = decision?.note || 'None';

    const accountAuditEntries = auditLog.filter((entry) => entry.account === accountId);
    const auditText =
      accountAuditEntries.length > 0
        ? accountAuditEntries
            .map(
              (e, idx) =>
                `  ${idx + 1}. [${e.time}] Evidence count: ${e.evidence} | Action: ${e['old action']} -> ${e['new action']}`
            )
            .join('\n')
        : '  None recorded for this account in this session.';

    const clockDatesText = [
      `  - Day 0: Hold placed`,
      `  - Day 20: Explanation deadline`,
      `  - Decision due: Day ${clockInfo.decisionDueDay}${
        clockInfo.explanationDay !== null
          ? ` (Explanation received on Day ${clockInfo.explanationDay})`
          : ' (Standard default)'
      }`,
      `  - Day 60: Maximum hold unless police instruct otherwise`,
    ].join('\n');

    const recordLines = [
      '========================================================================',
      'SMART FREEZE - DECISION RECORD (SIMULATED DATA PROTOTYPE)',
      '========================================================================',
      `Date/Time:       ${new Date().toISOString()}`,
      `Scam Incident:   ${scamId}`,
      `Decision Delay:  ${delay} minutes`,
      `Lambda (λ):      ${lam}`,
      '',
      '------------------------------------------------------------------------',
      '1. ACCOUNT IDENTIFICATION',
      '------------------------------------------------------------------------',
      `Account ID:      ${accountId}`,
      `Account Type:    ${type}`,
      `Balance:         Rs. ${Number(balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
      '',
      '------------------------------------------------------------------------',
      '2. TRACING BREAKDOWN',
      '------------------------------------------------------------------------',
      `Proportional:    Rs. ${Number(tainted_prop).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
      `FIFO:            Rs. ${Number(tainted_fifo).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
      `LIBR:            Rs. ${Number(tainted_libr).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
      `Tainted Min:     Rs. ${Number(tainted_min).toLocaleString('en-IN', { minimumFractionDigits: 2 })} (Sure part)`,
      `Tainted Max:     Rs. ${Number(tainted_max).toLocaleString('en-IN', { minimumFractionDigits: 2 })} (Ceiling)`,
      '',
      '------------------------------------------------------------------------',
      '3. INVESTIGATION PRIORITY SCORE (S)',
      '------------------------------------------------------------------------',
      `Priority (S):    ${Number(S).toFixed(4)} (Prioritisation signal on simulated data, not proof)`,
      `Behavior (B):    ${Number(B).toFixed(4)}`,
      `Trail (T):       ${Number(T).toFixed(4)}`,
      `History (H):     ${Number(H).toFixed(4)}`,
      '',
      'Reasons For (Mule-like indicators):',
      reasons_for && reasons_for.length > 0 ? reasons_for.map((r) => `  + ${r}`).join('\n') : '  None found',
      '',
      'Reasons Against (Innocent indicators):',
      reasons_against && reasons_against.length > 0 ? reasons_against.map((r) => `  - ${r}`).join('\n') : '  None found',
      '',
      '------------------------------------------------------------------------',
      '4. RECOMMENDED ACTION & AMOUNT HELD',
      '------------------------------------------------------------------------',
      `Action:          ${currentAction}`,
      `Amount Held:     Rs. ${Number(amountHeld).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
      `Human Approval:  ${decision?.needs_human ? 'REQUIRED' : 'Not required'}`,
      `Decision Note:   ${note}`,
      '',
      '------------------------------------------------------------------------',
      '5. STATUTORY HOLD CLOCK',
      '------------------------------------------------------------------------',
      clockDatesText,
      '',
      '------------------------------------------------------------------------',
      '6. AUDIT ENTRIES FOR THIS ACCOUNT',
      '------------------------------------------------------------------------',
      auditText,
      '',
      '========================================================================',
      'SIMULATED DATA ONLY - A HUMAN APPROVES EVERY ACTION',
      '========================================================================',
    ].join('\n');

    const blob = new Blob([recordLines], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `decision_record_${accountId}_${scamId}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (!accountId) {
    return (
      <div className="card placeholder-card">
        <h4 style={{ fontSize: '1.05rem', color: 'var(--ink)' }}>Account Details</h4>
        <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginTop: '8px' }}>
          Select an account from the graph or review list to inspect details.
        </p>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="card account-card-loading">
        <div className="spinner" />
        <p>Loading account details for <code>{accountId}</code>...</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="card account-card-error">
        <h5>Failed to load account</h5>
        <p>{error}</p>
        <button
          className="retry-btn"
          onClick={() => {
            setLoading(true);
            setError(null);
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const {
    balance = 0,
    type = 'unknown',
    tainted_prop = 0,
    tainted_fifo = 0,
    tainted_libr = 0,
    tainted_min = 0,
    tainted_max = 0,
    S = 0,
    B = 0,
    T = 0,
    H = 0,
    reasons_for = [],
    reasons_against = [],
    harm_score = 0,
    cover_days = 0,
    float_need = 0,
    salary_dependence = 0,
    thin_cover = 0,
    decision = {},
    blanket = {},
    smart = {},
  } = data;

  const action = decision.action || 'none';
  const needsHuman = Boolean(decision.needs_human);
  const note = decision.note || 'No note available.';

  return (
    <div className="card account-card-container">
      {/* 1. Header */}
      <header className="account-card-header">
        <div className="header-top-row">
          <div className="account-title-group">
            <h3 className="account-card-id">{accountId}</h3>
            <span className="account-card-type">{type}</span>
          </div>

          <div className="header-badges">
            <span className={`badge badge-${action}`}>
              {action}
            </span>
            {needsHuman && (
              <span className="badge-human-approval" title="Decision requires human review and confirmation">
                ⚠️ Human approval required
              </span>
            )}
          </div>
        </div>

        <div className="header-balance-row">
          <span className="balance-label">Total Balance:</span>
          <span className="balance-value">
            ₹{Number(balance).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        {note && (
          <div className="decision-note-box">
            <span className="note-icon">📝</span>
            <span className="note-text">{note}</span>
          </div>
        )}
      </header>

      {/* 2. Tracing Breakdown Panel */}
      <TracingPanel
        balance={balance}
        taintedProp={tainted_prop}
        taintedFifo={tainted_fifo}
        taintedLibr={tainted_libr}
        taintedMin={tainted_min}
        taintedMax={tainted_max}
      />

      {/* 3. Priority Panel */}
      <PriorityPanel
        S={S}
        B={B}
        T={T}
        H={H}
        reasonsFor={reasons_for}
        reasonsAgainst={reasons_against}
      />

      {/* 4. Harm Model Panel */}
      <HarmPanel
        harmScore={harm_score}
        coverDays={cover_days}
        floatNeed={float_need}
        salaryDependence={salary_dependence}
        thinCover={thin_cover}
      />

      {/* 5. Policy Comparison Panel */}
      <ComparisonPanel blanket={blanket} smart={smart} />

      {/* 6. Holder Explanation & Evidence */}
      <HolderExplanation
        accountId={accountId}
        scamId={scamId}
        delay={delay}
        lam={lam}
        auditLog={auditLog}
        onApproveRelease={onApproveRelease}
      />

      {/* 7. Hold Clock */}
      <HoldClock onClockUpdate={setClockInfo} />

      {/* 8. Download Decision Record Button */}
      <div className="download-record-area">
        <button
          type="button"
          className="download-record-btn"
          onClick={handleDownloadRecord}
        >
          ⬇ Download decision record (.txt)
        </button>
      </div>
    </div>
  );
}
