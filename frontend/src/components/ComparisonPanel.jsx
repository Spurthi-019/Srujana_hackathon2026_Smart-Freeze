import React from 'react';

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
        <h5 className="panel-title">Policy Comparison</h5>
        {cleanSaved > 0 && (
          <span className="clean-saved-badge">
            Saves up to ₹{Math.round(cleanSaved).toLocaleString('en-IN')} clean funds
          </span>
        )}
      </div>

      <div className="comparison-columns">
        {/* Blanket Freeze Column */}
        <div className="comparison-col blanket-col">
          <div className="col-header">
            <span className="col-title">Blanket freeze</span>
            <span className="col-tag tag-blanket">Full Balance</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Rupees held:</span>
            <span className="comp-val">₹{Math.round(bHeld).toLocaleString('en-IN')}</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Clean-money range:</span>
            <span className="comp-val comp-range-warn">
              ₹{Math.round(bCleanLow).toLocaleString('en-IN')} – ₹{Math.round(bCleanHigh).toLocaleString('en-IN')}
            </span>
          </div>
          <div className="col-footer-note">Entire balance frozen regardless of taint</div>
        </div>

        {/* Smart Freeze Column */}
        <div className="comparison-col smart-col">
          <div className="col-header">
            <span className="col-title">Smart Freeze</span>
            <span className="col-tag tag-smart">Targeted Action</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Rupees held:</span>
            <span className="comp-val comp-smart-val">₹{Math.round(sHeld).toLocaleString('en-IN')}</span>
          </div>
          <div className="comparison-metric">
            <span className="comp-label">Clean-money range:</span>
            <span className="comp-val comp-range-safe">
              ₹{Math.round(sCleanLow).toLocaleString('en-IN')} – ₹{Math.round(sCleanHigh).toLocaleString('en-IN')}
            </span>
          </div>
          <div className="col-footer-note">Lien or timed hold targeted to sure taint</div>
        </div>
      </div>
    </div>
  );
}
