import React from 'react';

/**
 * PriorityPanel: Diverging bars for B, T, H (positive right, negative left),
 * investigation priority score S, and lists of reasons for/against.
 * NOTE: Never display is_mule or role.
 */
export default function PriorityPanel({
  S = 0,
  B = 0,
  T = 0,
  H = 0,
  reasonsFor = [],
  reasonsAgainst = [],
}) {
  const factors = [
    { label: 'B', name: 'Behavior', val: Number(B) || 0 },
    { label: 'T', name: 'Trail', val: Number(T) || 0 },
    { label: 'H', name: 'History / Legitimacy', val: Number(H) || 0 },
  ];

  const maxVal = Math.max(4.0, ...factors.map((f) => Math.abs(f.val)));

  return (
    <div className="card-panel priority-panel">
      <div className="panel-header">
        <h5 className="panel-title">Investigation Priority (S)</h5>
        <span className="priority-score-badge">
          S = {Number(S).toFixed(3)}
        </span>
      </div>

      {/* S Meter */}
      <div className="priority-meter-container">
        <div className="priority-meter-track">
          <div
            className="priority-meter-fill"
            style={{ width: `${Math.min(100, Math.max(0, S * 100))}%` }}
          />
        </div>
        <div className="priority-labels">
          <span>0.0 (Low)</span>
          <span>Investigation priority: {(S * 100).toFixed(1)}%</span>
          <span>1.0 (High)</span>
        </div>
      </div>
      <p className="panel-caption priority-caption">
        A prioritisation signal on simulated data, not proof.
      </p>

      {/* Diverging Bars for B, T, H */}
      <div className="diverging-factors">
        <div className="diverging-header">
          <span>← Reduces priority (Innocent signs)</span>
          <span>Increases priority (Risk signs) →</span>
        </div>
        {factors.map((factor) => {
          const val = factor.val;
          const pct = Math.min(50, (Math.abs(val) / maxVal) * 50);
          const isPos = val >= 0;

          return (
            <div key={factor.label} className="factor-row">
              <div className="factor-meta">
                <span className="factor-code">{factor.label}</span>
                <span className="factor-desc">{factor.name}</span>
                <span className="factor-num">
                  {isPos ? `+${val.toFixed(2)}` : val.toFixed(2)}
                </span>
              </div>
              <div className="diverging-bar-wrapper">
                <div className="diverging-center-line" />
                {isPos ? (
                  <div
                    className="diverging-bar pos-bar"
                    style={{ left: '50%', width: `${pct}%` }}
                  />
                ) : (
                  <div
                    className="diverging-bar neg-bar"
                    style={{ left: `${50 - pct}%`, width: `${pct}%` }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Explanatory Reasons */}
      <div className="reasons-container">
        <div className="reasons-block">
          <h6 className="reasons-title reasons-for-title">Why mule-like</h6>
          {reasonsFor && reasonsFor.length > 0 ? (
            <ul className="reasons-list reasons-for-list">
              {reasonsFor.map((r, idx) => (
                <li key={idx}>{r}</li>
              ))}
            </ul>
          ) : (
            <div className="reasons-empty">none found</div>
          )}
        </div>

        <div className="reasons-block">
          <h6 className="reasons-title reasons-against-title">Why this might be innocent</h6>
          {reasonsAgainst && reasonsAgainst.length > 0 ? (
            <ul className="reasons-list reasons-against-list">
              {reasonsAgainst.map((r, idx) => (
                <li key={idx}>{r}</li>
              ))}
            </ul>
          ) : (
            <div className="reasons-empty">none found</div>
          )}
        </div>
      </div>
    </div>
  );
}
