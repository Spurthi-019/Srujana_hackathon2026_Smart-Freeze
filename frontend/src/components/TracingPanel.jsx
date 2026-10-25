import React from 'react';
import { GitFork } from 'lucide-react';
import { formatMoney, formatMoneyExact } from '../utils/format';

/**
 * TracingPanel: Three horizontal bars (Proportional, FIFO, LIBR)
 * of tainted amount against the balance as the full-width reference.
 * Sure part (teal #2DD4BF) and maybe band (amber #F59E0B).
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
        <div className="panel-title-group">
          <GitFork size={16} className="panel-icon text-teal" />
          <h5 className="panel-title">Tracing Breakdown</h5>
        </div>
        <span
          className="panel-badge-range tabular-nums"
          title={`Min: ${formatMoneyExact(taintedMin)} | Max: ${formatMoneyExact(taintedMax)}`}
        >
          {formatMoney(taintedMin)} – {formatMoney(taintedMax)}
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
                <span
                  className="method-amount tabular-nums"
                  title={`${m.name}: ${formatMoneyExact(m.amount)} of balance ${formatMoneyExact(balance)}`}
                >
                  {formatMoney(m.amount)}{' '}
                  <span className="method-pct">
                    ({((m.amount / (balance || 1)) * 100).toFixed(0)}%)
                  </span>
                </span>
              </div>
              <div
                className="bar-track"
                title={`${m.name}: ${formatMoneyExact(m.amount)} (Sure: ${formatMoneyExact(surePart)}, Maybe: ${formatMoneyExact(maybePart)})`}
              >
                <div
                  className="bar-fill bar-sure"
                  style={{ width: `${surePct}%` }}
                />
                <div
                  className="bar-fill bar-maybe"
                  style={{ width: `${maybePct}%` }}
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
            Sure part (min):{' '}
            <strong className="tabular-nums" title={formatMoneyExact(taintedMin)}>
              {formatMoney(taintedMin)}
            </strong>
          </span>
        </div>
        <div className="legend-item">
          <span className="legend-dot dot-maybe" />
          <span className="legend-text">
            Maybe band:{' '}
            <strong className="tabular-nums" title={`${formatMoneyExact(taintedMin)} to ${formatMoneyExact(taintedMax)}`}>
              {formatMoney(taintedMin)} – {formatMoney(taintedMax)}
            </strong>
          </span>
        </div>
      </div>

      <p className="panel-caption">
        Three accepted tracing rules give a range; we lock the sure part first.
      </p>
    </div>
  );
}
