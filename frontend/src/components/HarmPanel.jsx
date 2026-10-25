import React from 'react';

/**
 * HarmPanel: Displays small metrics for financial harm assessment:
 * harm_score, cover_days, float_need, salary_dependence, thin_cover.
 */
export default function HarmPanel({
  harmScore = 0,
  coverDays = 0,
  floatNeed = 0,
  salaryDependence = 0,
  thinCover = 0,
}) {
  const metrics = [
    {
      label: 'Harm Score',
      value: Number(harmScore).toFixed(2),
      subtext: '0.0 (low) to 1.0 (severe)',
      highlight: harmScore > 0.6,
    },
    {
      label: 'Cover Days',
      value: `${Number(coverDays).toFixed(1)} d`,
      subtext: 'Liquidity runway',
      highlight: coverDays < 10,
    },
    {
      label: 'Float Need',
      value: Number(floatNeed).toFixed(2),
      subtext: 'Operating liquidity',
      highlight: floatNeed > 0.5,
    },
    {
      label: 'Salary Dep.',
      value: `${(Number(salaryDependence) * 100).toFixed(0)}%`,
      subtext: 'Payroll reliance',
      highlight: salaryDependence > 0.5,
    },
    {
      label: 'Thin Cover',
      value: Number(thinCover).toFixed(2),
      subtext: 'Buffer vulnerability',
      highlight: thinCover > 0.5,
    },
  ];

  return (
    <div className="card-panel harm-panel">
      <div className="panel-header">
        <h5 className="panel-title">Harm Model Assessment</h5>
        <span className="panel-subbadge">Vulnerability metrics</span>
      </div>

      <div className="harm-metrics-grid">
        {metrics.map((m) => (
          <div key={m.label} className={`harm-metric-card ${m.highlight ? 'metric-alert' : ''}`}>
            <span className="metric-label">{m.label}</span>
            <span className="metric-value">{m.value}</span>
            <span className="metric-subtext">{m.subtext}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
