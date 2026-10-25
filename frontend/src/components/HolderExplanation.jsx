import React, { useState, useEffect } from 'react';
import { FileCheck, ArrowRight, Check, History } from 'lucide-react';
import { formatMoney, formatMoneyExact } from '../utils/format';

const EVIDENCE_OPTIONS = [
  'Invoice or receipt for the payment',
  'Known regular customer or payer',
  'Regular business or salary inflows',
  'Verified identity and long account history',
];

const ACTION_SEVERITY = {
  timed_hold: 3,
  lien_cap: 2,
  lien: 1,
  none: 0,
};

/**
 * HolderExplanation: Interactive evidence checklist calling POST /api/whatif,
 * showing before/after impact side by side, and providing human approval for release.
 */
export default function HolderExplanation({
  accountId,
  scamId,
  delay,
  lam,
  auditLog = [],
  onApproveRelease,
}) {
  const [checked, setChecked] = useState([false, false, false, false]);
  const [whatIfData, setWhatIfData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [justApproved, setJustApproved] = useState(false);

  // Reset checkboxes when account or scam changes
  useEffect(() => {
    setChecked([false, false, false, false]);
    setJustApproved(false);
  }, [accountId, scamId]);

  // Call /api/whatif whenever checked items, account, scam, delay, or lam change
  useEffect(() => {
    if (!accountId || !scamId) return;

    const count = checked.filter(Boolean).length;
    setLoading(true);
    setError(null);

    fetch('/api/whatif', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: accountId,
        scam_id: scamId,
        delay: Number(delay),
        lam: Number(lam),
        evidence_count: count,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setWhatIfData(data);
      })
      .catch((err) => {
        setError(`What-if simulation failed: ${err.message}`);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [accountId, scamId, delay, lam, checked]);

  const handleToggle = (index) => {
    setJustApproved(false);
    setChecked((prev) => {
      const next = [...prev];
      next[index] = !next[index];
      return next;
    });
  };

  const evidenceCount = checked.filter(Boolean).length;
  const before = whatIfData?.before;
  const after = whatIfData?.after;

  // Determine if after action is less restrictive than before
  const isLessRestrictive =
    before &&
    after &&
    (ACTION_SEVERITY[after.action] < ACTION_SEVERITY[before.action] ||
      after.held < before.held);

  const handleApprove = () => {
    if (!before || !after || !onApproveRelease) return;

    const entry = {
      account: accountId,
      scam: scamId,
      delay: delay,
      evidence: evidenceCount,
      'old action': before.action,
      'new action': after.action,
      time: new Date().toLocaleTimeString(),
    };

    onApproveRelease(entry);
    setJustApproved(true);
  };

  return (
    <div className="card-panel holder-explanation-panel">
      <div className="panel-header">
        <div className="panel-title-group">
          <FileCheck size={16} className="panel-icon text-teal" />
          <h5 className="panel-title">Holder Explanation & Evidence</h5>
        </div>
        <span className="panel-subbadge tabular-nums">
          {evidenceCount} of 4 items verified
        </span>
      </div>

      {/* Checkbox Options */}
      <div className="evidence-checklist">
        {EVIDENCE_OPTIONS.map((opt, idx) => (
          <label key={opt} className={`checklist-item ${checked[idx] ? 'checked' : ''}`}>
            <input
              type="checkbox"
              checked={checked[idx]}
              onChange={() => handleToggle(idx)}
              className="checklist-checkbox"
            />
            <span className="checklist-text">{opt}</span>
          </label>
        ))}
      </div>

      {/* Before / After Comparison */}
      {error && <div className="panel-error">{error}</div>}

      {whatIfData && (
        <div className={`whatif-comparison ${loading ? 'loading-fade' : ''}`}>
          {/* Before */}
          <div className="whatif-box before-box">
            <span className="whatif-title">Before Evidence</span>
            <div className="whatif-row">
              <span className="whatif-label">Priority (S):</span>
              <span className="whatif-val tabular-nums">
                {before ? Number(before.S).toFixed(3) : '—'}
              </span>
            </div>
            <div className="whatif-row">
              <span className="whatif-label">Action:</span>
              <span className={`badge badge-${before?.action || 'none'}`}>
                {before?.action || 'none'}
              </span>
            </div>
            <div className="whatif-row">
              <span className="whatif-label">Held:</span>
              <span className="whatif-val tabular-nums" title={before ? formatMoneyExact(before.held) : '₹0'}>
                {before ? formatMoney(before.held) : '₹0'}
              </span>
            </div>
          </div>

          <div className="whatif-arrow">
            <ArrowRight size={18} className="text-muted" />
          </div>

          {/* After */}
          <div className="whatif-box after-box">
            <span className="whatif-title">After Evidence</span>
            <div className="whatif-row">
              <span className="whatif-label">Priority (S):</span>
              <span className="whatif-val whatif-val-improved tabular-nums">
                {after ? Number(after.S).toFixed(3) : '—'}
              </span>
            </div>
            <div className="whatif-row">
              <span className="whatif-label">Action:</span>
              <span className={`badge badge-${after?.action || 'none'}`}>
                {after?.action || 'none'}
              </span>
            </div>
            <div className="whatif-row">
              <span className="whatif-label">Held:</span>
              <span className="whatif-val whatif-val-improved tabular-nums" title={after ? formatMoneyExact(after.held) : '₹0'}>
                {after ? formatMoney(after.held) : '₹0'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Release Button */}
      {isLessRestrictive && (
        <div className="release-action-area">
          <button
            type="button"
            className="approve-release-btn"
            onClick={handleApprove}
            disabled={justApproved}
          >
            {justApproved ? (
              <>
                <Check size={14} /> Release Approved
              </>
            ) : (
              'Approve release'
            )}
          </button>
          {justApproved && (
            <span className="release-approved-msg">
              Recorded in session audit log.
            </span>
          )}
        </div>
      )}

      <p className="panel-caption">
        Demo of the workflow. Evidence moves the score by an assumed fixed amount; a human approves every release.
      </p>

      {/* Audit Log Table */}
      <div className="audit-log-section">
        <div className="audit-log-header-row">
          <History size={13} className="text-muted" />
          <h6 className="audit-log-title">Audit log (this session)</h6>
        </div>
        {auditLog.length === 0 ? (
          <div className="audit-log-empty">No approvals recorded yet in this session.</div>
        ) : (
          <div className="audit-log-table-wrapper">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Account</th>
                  <th>Scam</th>
                  <th>Evid.</th>
                  <th>Old Action</th>
                  <th>New Action</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((entry, i) => (
                  <tr key={i} className={entry.account === accountId ? 'current-account-entry' : ''}>
                    <td className="tabular-nums">{entry.time}</td>
                    <td><code>{entry.account}</code></td>
                    <td>{entry.scam}</td>
                    <td>{entry.evidence} items</td>
                    <td>
                      <span className={`badge badge-${entry['old action']}`}>
                        {entry['old action']}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge-${entry['new action']}`}>
                        {entry['new action']}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
