import React, { useState } from 'react';

/**
 * HoldClock: SVG timeline from Day 0 to Day 60 with RBI draft direction markers:
 * - Day 0: hold placed
 * - Day 20: explanation deadline
 * - Decision due: Day 30 (or explanation day + 10)
 * - Day 60: maximum hold unless police instruct otherwise
 */
export default function HoldClock({ onClockUpdate }) {
  const [explanationDayInput, setExplanationDayInput] = useState('');

  const numInput = parseInt(explanationDayInput, 10);
  const hasExplanationDay = !isNaN(numInput) && numInput >= 0 && numInput <= 20;
  const explanationDay = hasExplanationDay ? numInput : null;
  const decisionDueDay = hasExplanationDay ? explanationDay + 10 : 30;

  // Notify parent if callback provided
  React.useEffect(() => {
    if (onClockUpdate) {
      onClockUpdate({
        explanationDay,
        decisionDueDay,
      });
    }
  }, [explanationDay, decisionDueDay, onClockUpdate]);

  // Coordinate calculations
  // Timeline length = 460px (x from 40 to 500)
  const xOrigin = 40;
  const xTotal = 460;
  const getY = 65;

  const getX = (day) => xOrigin + (Math.max(0, Math.min(60, day)) / 60) * xTotal;

  const x0 = getX(0);
  const x20 = getX(20);
  const xDecision = getX(decisionDueDay);
  const x60 = getX(60);

  return (
    <div className="card-panel hold-clock-panel">
      <div className="panel-header">
        <h5 className="panel-title">Hold Clock (Statutory Timeline)</h5>
        <span className="panel-subbadge">Draft RBI Directions</span>
      </div>

      {/* Input control */}
      <div className="hold-clock-input-row">
        <label htmlFor="explanation-day-input" className="clock-input-label">
          Explanation received on day (0-20):
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            id="explanation-day-input"
            type="number"
            min="0"
            max="20"
            placeholder="e.g. 5"
            value={explanationDayInput}
            onChange={(e) => {
              const val = e.target.value;
              if (val === '') {
                setExplanationDayInput('');
              } else {
                const parsed = parseInt(val, 10);
                if (!isNaN(parsed)) {
                  setExplanationDayInput(Math.max(0, Math.min(20, parsed)).toString());
                }
              }
            }}
            className="clock-number-input"
          />
          {explanationDayInput !== '' && (
            <button
              type="button"
              className="clock-clear-btn"
              onClick={() => setExplanationDayInput('')}
              title="Reset to default Day 30"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Timeline Status Callout */}
      <div className="clock-status-callout">
        {hasExplanationDay ? (
          <span>
            Explanation recorded on <strong>Day {explanationDay}</strong> → Decision due in 10 days on{' '}
            <strong style={{ color: 'var(--teal)' }}>Day {decisionDueDay}</strong>.
          </span>
        ) : (
          <span>
            No explanation filed yet → Default decision due deadline is{' '}
            <strong style={{ color: 'var(--teal)' }}>Day 30</strong>.
          </span>
        )}
      </div>

      {/* SVG Timeline */}
      <div className="svg-timeline-container">
        <svg
          viewBox="0 0 540 145"
          className="hold-clock-svg"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Main timeline track background */}
          <line
            x1={xOrigin}
            y1={getY}
            x2={xOrigin + xTotal}
            y2={getY}
            stroke="#CBD5E1"
            strokeWidth="5"
            strokeLinecap="round"
          />

          {/* Active / Elapsed segment up to decision due */}
          <line
            x1={xOrigin}
            y1={getY}
            x2={xDecision}
            y2={getY}
            stroke="var(--teal)"
            strokeWidth="5"
            strokeLinecap="round"
          />

          {/* Major tick lines along timeline */}
          {[0, 10, 20, 30, 40, 50, 60].map((t) => {
            const tx = getX(t);
            return (
              <line
                key={t}
                x1={tx}
                y1={getY - 4}
                x2={tx}
                y2={getY + 4}
                stroke="#94A3B8"
                strokeWidth="1.5"
              />
            );
          })}

          {/* Marker 1: Day 0 */}
          <circle cx={x0} cy={getY} r="6" fill="#3B82F6" stroke="#FFFFFF" strokeWidth="2" />
          <text x={x0} y={getY - 14} textAnchor="start" className="clock-svg-day">
            Day 0
          </text>
          <text x={x0} y={getY + 22} textAnchor="start" className="clock-svg-text">
            hold placed
          </text>

          {/* Marker 2: Day 20 */}
          <circle cx={x20} cy={getY} r="6" fill="#D97706" stroke="#FFFFFF" strokeWidth="2" />
          <text x={x20} y={getY - 14} textAnchor="middle" className="clock-svg-day">
            Day 20
          </text>
          <text x={x20} y={getY + 22} textAnchor="middle" className="clock-svg-text">
            explanation deadline
          </text>

          {/* Marker 3: Decision due Day (Day 30 or Day explanation + 10) */}
          <g>
            <circle
              cx={xDecision}
              cy={getY}
              r="8"
              fill="#0F766E"
              stroke="#FFFFFF"
              strokeWidth="2.5"
            />
            {/* Pulsing visual halo */}
            <circle
              cx={xDecision}
              cy={getY}
              r="12"
              fill="none"
              stroke="#0F766E"
              strokeWidth="1.5"
              opacity="0.4"
            />
            <text
              x={xDecision}
              y={getY - 16}
              textAnchor="middle"
              className="clock-svg-day clock-svg-decision-day"
            >
              Day {decisionDueDay}
            </text>
            <text
              x={xDecision}
              y={getY + 42}
              textAnchor="middle"
              className="clock-svg-text clock-svg-decision-text"
            >
              decision due
            </text>
          </g>

          {/* Marker 4: Day 60 */}
          <circle cx={x60} cy={getY} r="6" fill="#DC2626" stroke="#FFFFFF" strokeWidth="2" />
          <text x={x60} y={getY - 14} textAnchor="end" className="clock-svg-day">
            Day 60
          </text>
          <text x={x60} y={getY + 22} textAnchor="end" className="clock-svg-text">
            max hold unless police instruct
          </text>
        </svg>
      </div>

      <p className="panel-caption">
        Based on the draft RBI directions (Sept 2026); draft, may change. Smart Freeze's timed hold auto-releases in 24 hours.
      </p>
    </div>
  );
}
