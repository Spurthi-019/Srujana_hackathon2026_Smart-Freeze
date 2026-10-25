import React from 'react';
import { Columns3, Lock, ShieldCheck } from 'lucide-react';
import { formatMoney, formatMoneyExact } from '../utils/format';

/**
 * ComparisonPanel: Two columns comparing "Blanket freeze" vs "Smart Freeze":
 * rupees held and clean-money range (clean_low to clean_high).
 */
export default function ComparisonPanel({ blanket = {}, smart = {} }) {
  const bHeld = Number(blanket.held || 0);
  const bCleanLow = Number(blanket.clean_low || 0);
  const bCleanHigh = Number(blanket.clean_high || 0);

  const sHeld = Number(smart.held || 0);
  const sCleanLow = Number(smart.clean_low || 0);
  const sCleanHigh = Number(smart.clean_high || 0);

  const cleanSaved = Math.max(0, bCleanLow - sCleanLow);

  return (
    <div className="card-panel comparison-panel">
      <div className="panel-header">
        <div className="panel-title-group">
          <Columns3 size={16} className="panel-icon text-blue" />
          <h5 className="panel-title">Policy Comparison</h5>
        </div>
        {cleanSaved > 0 && (
          <span
            className="clean-saved-badge tabular-nums"
            title={`Saves ${formatMoneyExact(cleanSaved)} of innocent funds from being locked`}
          >
            Saves ~{formatMoney(cleanSaved)} clean
          </span>
        )}
      </div>

      <div className="comparison-columns">
        {/* Blanket Freeze Column */}
        <div className="comparison-col blanket-col">
          <div className="col-header">
            <div className="col-title-wrap">
              <Lock size={12} className="text-red" />
              <span className="col-title">Blanket freeze</span>
            </div>
            <span className="col-tag tag-blanket">Full Balance</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Rupees held:</span>
            <span className="comp-val tabular-nums" title={formatMoneyExact(bHeld)}>
              {formatMoney(bHeld)}
            </span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Clean-money range:</span>
            <span
              className="comp-val comp-range-warn tabular-nums"
              title={`${formatMoneyExact(bCleanLow)} – ${formatMoneyExact(bCleanHigh)}`}
            >
              {formatMoney(bCleanLow)} – {formatMoney(bCleanHigh)}
            </span>
          </div>
          <div className="col-footer-note">Entire balance frozen regardless of taint</div>
        </div>

        {/* Smart Freeze Column */}
        <div className="comparison-col smart-col">
          <div className="col-header">
            <div className="col-title-wrap">
              <ShieldCheck size={12} className="text-teal" />
              <span className="col-title">Smart Freeze</span>
            </div>
            <span className="col-tag tag-smart">Targeted Action</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Rupees held:</span>
            <span className="comp-val comp-smart-val tabular-nums" title={formatMoneyExact(sHeld)}>
              {formatMoney(sHeld)}
            </span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Clean-money range:</span>
            <span
              className="comp-val comp-range-safe tabular-nums"
              title={`${formatMoneyExact(sCleanLow)} – ${formatMoneyExact(sCleanHigh)}`}
            >
              {formatMoney(sCleanLow)} – {formatMoney(sCleanHigh)}
            </span>
          </div>
          <div className="col-footer-note">Lien or timed hold targeted to sure taint</div>
        </div>
      </div>
    </div>
  );
}
