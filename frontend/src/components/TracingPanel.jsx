import React from 'react';

/**
 * TracingPanel: Displays three horizontal bars (Proportional, FIFO, LIBR)
 * of tainted amount against the balance as the full-width reference,
 * with tainted_min as the "sure part" (teal) and tainted_min..tainted_max as the "maybe band" (amber, lighter).
 */
export default function TracingPanel({
  balance = 0,
  taintedProp = 0,
  taintedFifo = 0,
  taintedLibr = 0,
  taintedMin = 0,
  taintedMax = 0,
}) {
  const refBalance = balance > 0 ? balance : Math.max(taintedMax, 1);

  const methods = [
    { name: 'Proportional', amount: taintedProp, key: 'prop' },
    { name: 'FIFO', amount: taintedFifo, key: 'fifo' },
    { name: 'LIBR', amount: taintedLibr, key: 'libr' },
  ];

  return (
    <div className="card-panel tracing-panel">
      <div className="panel-header">
        <h5 className="panel-title">Tracing Breakdown</h5>
        <span className="panel-badge-range">
          Range: ₹{Math.round(taintedMin).toLocaleString('en-IN')} – ₹{Math.round(taintedMax).toLocaleString('en-IN')}
        </span>
      </div>

      <div className="tracing-bars">
        {methods.map((m) => {
          const totalTainted = Math.max(0, m.amount);
          const surePart = Math.min(totalTainted, Math.max(0, taintedMin));
          const maybePart = Math.max(0, totalTainted - surePart);

          const surePct = Math.min(100, (surePart / refBalance) * 100);
          const maybePct = Math.min(100 - surePct, (maybePart / refBalance) * 100);

          return (
            <div key={m.key} className="tracing-bar-group">
              <div className="tracing-bar-label">
                <span className="method-name">{m.name}</span>
                <span className="method-amount">
                  ₹{Math.round(m.amount).toLocaleString('en-IN')}{' '}
                  <span className="method-pct">
                    ({((m.amount / (balance || 1)) * 100).toFixed(0)}%)
                  </span>
                </span>
              </div>
              <div className="bar-track" title={`${m.name}: ₹${m.amount.toFixed(0)} of ₹${balance.toFixed(0)}`}>
                <div
                  className="bar-fill bar-sure"
                  style={{ width: `${surePct}%` }}
                  title={`Sure part: ₹${surePart.toFixed(0)}`}
                />
                <div
                  className="bar-fill bar-maybe"
                  style={{ width: `${maybePct}%` }}
                  title={`Maybe band: ₹${maybePart.toFixed(0)}`}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="tracing-legend">
        <div className="legend-item">
          <span className="legend-dot dot-sure" />
          <span className="legend-text">
            Sure part (min): <strong>₹{Math.round(taintedMin).toLocaleString('en-IN')}</strong>
          </span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-maybe" />
          <span className="legend-text">
            Maybe band: <strong>₹{Math.round(taintedMin).toLocaleString('en-IN')} – ₹{Math.round(taintedMax).toLocaleString('en-IN')}</strong>
          </span>
        </div>
      </div>

      <p className="panel-caption">
        Three accepted tracing rules give a range; we lock the sure part first.
      </p>
    </div>
  );
}
